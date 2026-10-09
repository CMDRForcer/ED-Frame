"""Durable profile-local rings, regional reads and lossless observation history.

The original JSON is an unchanged adoption source. Versioned facts retain old
worker snapshots and every displaced payload. SQLite transactions commit current
facts and a history outbox together; failure of the separate history archive
cannot lose an observation. No retention, compression or destructive recovery.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from .catalog_json import (catalog_snapshot_decoder, iter_catalog_candidates,
                           load_catalog_snapshot)
from .mining_batch import mining_observation_key
from .mining_contract import MINING_FRESHNESS_SECONDS
from .mining_finder import (_candidate_identity, merge_mining_candidate_batch,
                            merge_mining_candidates, mining_candidate_freshness)
from ed_companion.worker_budget import WorkerBudget

FORMAT_VERSION = 1
TRANSIENT_FIELDS = frozenset({"ageSeconds", "confirmationStatus", "freshnessLimitSeconds",
                              "recheckRecommended", "stale"})
_VALID = "f.born<=? AND (f.ended IS NULL OR f.ended>?)"


class RingStoreConflict(ValueError):
    pass


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError, OverflowError):
        return None


def _identity(row):
    return _encode(_candidate_identity(row)) if isinstance(row, dict) else ""


def _epoch(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _known(value):
    return str(value or "").strip().casefold() not in {"", "unknown", "unconfirmed", "none"}


def _resource_evidence(row):
    if row.get("hotspots") or row.get("yieldStats"):
        return True
    try:
        return bool(int(row.get("planetaryMiningLocationCount",0) or 0))
    except (ValueError,TypeError,OverflowError):
        # A malformed count is still preserved verbatim in the payload.
        return False


class RingCatalogStore:
    def __init__(self, path, profile):
        self.path = Path(path).resolve()
        self.profile = str(profile)
        self._lock = threading.RLock()

    def _connect(self, *, write=False):
        connection = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                     uri=True, timeout=15)
        try:
            connection.execute("PRAGMA busy_timeout=15000")
            connection.execute("PRAGMA cache_size=-4096")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("PRAGMA mmap_size=0")
            if write:
                connection.execute("PRAGMA synchronous=FULL")
            else:
                connection.execute("PRAGMA query_only=ON")
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _head(connection):
        result = connection.execute("SELECT payload FROM metadata WHERE key='head'").fetchone()
        return json.loads(result[0]) if result else {}

    def _validate(self, head, view=None, *, write=False):
        if (head.get("format") != FORMAT_VERSION or head.get("profile") != self.profile
                or head.get("complete") is not True):
            raise RingStoreConflict("Ring store profile/format mismatch")
        if view is not None and (head.get("database") != view.head["database"]
                or (write and (head["epoch"] != view.head["epoch"] or head["revision"] != view.revision))):
            raise RingStoreConflict("Ring store generation/revision changed")

    @contextmanager
    def reader(self, view=None):
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            self._validate(self._head(connection), view)
            yield connection

    @staticmethod
    def _write_head(connection, head):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('head',?)", (_encode(head),))

    @staticmethod
    def _schema(connection):
        connection.executescript("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE facts (
                id INTEGER PRIMARY KEY, seq INTEGER NOT NULL, born INTEGER NOT NULL,
                ended INTEGER, identity TEXT NOT NULL, system_key TEXT NOT NULL,
                system TEXT NOT NULL, learned_at TEXT NOT NULL,
                observed_at TEXT NOT NULL, observed_epoch REAL,
                evidence TEXT NOT NULL, coords_known INTEGER NOT NULL,
                with_ring INTEGER NOT NULL, with_type INTEGER NOT NULL,
                with_reserve INTEGER NOT NULL, with_resource INTEGER NOT NULL,
                with_hotspots INTEGER NOT NULL, is_record INTEGER NOT NULL,
                x REAL,y REAL,z REAL,exceptional INTEGER NOT NULL,payload TEXT NOT NULL
            );
            CREATE INDEX facts_sequence ON facts(seq,born,ended);
            CREATE INDEX facts_identity ON facts(identity,ended,seq);
            CREATE INDEX facts_system ON facts(system_key,ended,seq);
            CREATE INDEX facts_exceptional ON facts(id) WHERE exceptional=1;
            CREATE VIRTUAL TABLE spatial USING rtree(id,x0,x1,y0,y1,z0,z1);
            CREATE TABLE signals (fact_id INTEGER NOT NULL,commodity TEXT NOT NULL);
            CREATE INDEX signals_fact ON signals(fact_id);
            CREATE TABLE history_pending (
                category TEXT NOT NULL,record_key TEXT NOT NULL,payload TEXT NOT NULL,
                PRIMARY KEY(category,record_key)
            );
            CREATE TABLE legacy_receipts (seq INTEGER PRIMARY KEY,digest TEXT NOT NULL);
            CREATE TABLE legacy_payloads (digest TEXT PRIMARY KEY);
            CREATE TABLE batches (id TEXT PRIMARY KEY,epoch TEXT NOT NULL);
        """)

    @staticmethod
    def _insert(connection, seq, revision, row):
        record = row if isinstance(row, dict) else {}
        system = str(record.get("system") or "").strip()
        position = _position(record.get("coordinates"))
        usable = position is not None and all(math.isfinite(v) and abs(v)<3e38 for v in position)
        xyz = position if usable else [None, None, None]
        coords = record.get("coordinates")
        values = (seq, revision, None, _identity(row), system.casefold(), system,
                  str(record.get("learnedAt") or ""),
                  str(record.get("observedAt") or ""), _epoch(record.get("observedAt")),
                  (str(record.get("sourceEvidence") or "").strip()
                   or str(record.get("evidence") or "").strip() or "STALE"),
                  int(isinstance(coords, (list, tuple)) and len(coords)==3 and all(v is not None for v in coords)),
                  int(bool(str(record.get("ring") or record.get("body") or "").strip())),
                  int(_known(record.get("ringTypeName") or record.get("ringType"))),
                  int(_known(record.get("reserveName") or record.get("reserveLevel"))),
                  int(_resource_evidence(record)),
                  int(bool(record.get("hotspots"))), int(isinstance(row, dict)), *xyz,
                  int(position is not None and not usable), _encode(row))
        fact_id = connection.execute("INSERT INTO facts(seq,born,ended,identity,system_key,system,"
            "learned_at,observed_at,observed_epoch,evidence,coords_known,with_ring,with_type,with_reserve,"
            "with_resource,with_hotspots,is_record,x,y,z,exceptional,payload) VALUES ("
            + ",".join("?" for _ in values) + ")", values).lastrowid
        if usable:
            x,y,z = position
            connection.execute("INSERT INTO spatial VALUES (?,?,?,?,?,?,?)", (fact_id,x,x,y,y,z,z))
        connection.executemany("INSERT INTO signals VALUES (?,?)", (
            (fact_id,str(item.get("commodity") or "")) for item in record.get("hotspots") or []
            if isinstance(item,dict)
        ))

    @staticmethod
    def _pending(connection, category, rows):
        connection.executemany("INSERT OR REPLACE INTO history_pending VALUES (?,?,?)", (
            (category,mining_observation_key(row),_encode(row)) for row in rows if isinstance(row,dict)
        ))

    def adopt(self, source):
        """Create a new durable store without altering the adoption source."""
        source = Path(source)
        if self.path.exists():
            return self.refresh_legacy(source)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staging = self.path.with_name(self.path.name + ".adopting-" + uuid.uuid4().hex)
        before = _digest(source) if source.is_file() else None
        source_stat = self._stat(source)
        root, count = {}, 0
        budget = WorkerBudget()
        try:
            with closing(sqlite3.connect(staging)) as connection, connection:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA cache_size=-4096")
                connection.execute("PRAGMA temp_store=FILE")
                self._schema(connection)
                connection.execute("BEGIN IMMEDIATE")
                for seq,row in enumerate(iter_catalog_candidates(source,root) if before else ()):
                    budget.checkpoint()
                    self._insert(connection,seq,0,row)
                    connection.execute("INSERT INTO legacy_receipts VALUES (?,?)",
                                       (seq,hashlib.sha256(_encode(row).encode()).hexdigest()))
                    connection.execute("INSERT OR IGNORE INTO legacy_payloads VALUES (?)",
                                       (hashlib.sha256(_encode(row).encode()).hexdigest(),))
                    count = seq + 1
                if before and (_digest(source)!=before or self._stat(source)!=source_stat):
                    raise RingStoreConflict("Source changed during ring adoption")
                head={"format":FORMAT_VERSION,"complete":True,"profile":self.profile,
                      "database":uuid.uuid4().hex,"epoch":uuid.uuid4().hex,"revision":0,
                      "count":count,"nextSeq":count,"root":root,"sourceSha256":before,
                      "sourceStat":source_stat}
                self._write_head(connection,head)
                if before and int(root.get("identityVersion",0) or 0)<2:
                    # One-time old-identity compatibility; preserve raw imported
                    # versions as well as the unchanged original file.
                    rows=load_catalog_snapshot(source,{})["candidates"]
                    normalized=merge_mining_candidates(rows)
                    connection.execute("UPDATE facts SET ended=1")
                    for seq,row in enumerate(normalized):
                        budget.checkpoint()
                        self._insert(connection,seq,1,row)
                    head.update(revision=1,count=len(normalized),nextSeq=len(normalized))
                    head["root"]["identityVersion"]=2
                head["root"]["identityVersion"]=2
                self._update_count(connection,head)
                self._write_head(connection,head)
            try:
                if os.name=="nt":
                    os.rename(staging,self.path)
                else:
                    os.link(staging,self.path)
            except FileExistsError:
                # A simultaneous adopter may have published first. Validate
                # that complete store; never replace another generation.
                return self.refresh_legacy(source)
        finally:
            staging.unlink(missing_ok=True)
        with closing(self._connect(write=True)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        return self.view()

    @staticmethod
    def _stat(source):
        if not source.is_file():
            return None
        stat=source.stat()
        return [stat.st_size,stat.st_mtime_ns]

    def view(self):
        with self.reader() as connection:
            return RingCatalogView(self,self._head(connection))

    def refresh_legacy(self,source):
        """Import only changed legacy rows; never discard SQLite-only facts."""
        view=self.view()
        source=Path(source)
        if self._stat(source)==view.head.get("sourceStat") or not source.is_file():
            return view
        digest=_digest(source)
        source_stat=self._stat(source)
        if digest==view.head.get("sourceSha256"):
            with self._lock,closing(self._connect(write=True)) as connection,connection:
                connection.execute("BEGIN IMMEDIATE")
                head=self._head(connection)
                self._validate(head,view,write=True)
                head["sourceStat"]=source_stat
                self._write_head(connection,head)
            return self.view()
        root={}
        with self._lock,closing(self._connect(write=True)) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            head=self._head(connection)
            self._validate(head,view,write=True)
            revision=head["revision"]+1
            pending=[]
            for seq,row in enumerate(iter_catalog_candidates(source,root)):
                row_digest=hashlib.sha256(_encode(row).encode()).hexdigest()
                previous=connection.execute("SELECT 1 FROM legacy_payloads WHERE digest=?",(row_digest,)).fetchone()
                if previous is None:
                    pending.append(row)
                    connection.execute("INSERT INTO legacy_payloads VALUES (?)",(row_digest,))
                connection.execute("INSERT OR REPLACE INTO legacy_receipts VALUES (?,?)",(seq,row_digest))
                if len(pending)>=512:
                    self._merge(connection,head,pending,revision)
                    pending=[]
            self._merge(connection,head,pending,revision)
            if _digest(source)!=digest or self._stat(source)!=source_stat:
                raise RingStoreConflict("Legacy source changed during refresh")
            head.update(revision=revision,sourceSha256=digest,sourceStat=source_stat)
            # Root reset policy stays authoritative in the SQLite generation.
            head["root"].update({k:v for k,v in root.items() if k!="resetAt"})
            head["root"]["identityVersion"]=2
            self._update_count(connection,head)
            self._write_head(connection,head)
        return self.view()

    def _merge(self,connection,head,rows,revision):
        additions=[dict(row) for row in rows if isinstance(row,dict)]
        if not additions:
            return
        keys=list(dict.fromkeys(_identity(row) for row in additions))
        selected={}
        for offset in range(0,len(keys),400):
            chunk=keys[offset:offset+400]
            for fact_id,seq,payload in connection.execute(
                    "SELECT id,seq,payload FROM facts WHERE ended IS NULL AND identity IN ("
                    + ",".join("?" for _ in chunk)+") ORDER BY seq",chunk):
                selected[seq]=(fact_id,json.loads(payload))
        ordered=sorted(selected)
        existing=[selected[seq][1] for seq in ordered]
        merged,displaced=merge_mining_candidate_batch(existing,additions)
        self._pending(connection,"mining_observations",additions)
        self._pending(connection,"mining_catalog",displaced)
        for index,row in enumerate(merged):
            if index<len(existing):
                if row is existing[index]:
                    continue
                seq=ordered[index]
                connection.execute("UPDATE facts SET ended=? WHERE id=?",(revision,selected[seq][0]))
            else:
                seq=head["nextSeq"]
                head["nextSeq"]+=1
                head["count"]+=1
            row={key:value for key,value in row.items() if key not in TRANSIENT_FIELDS}
            self._insert(connection,seq,revision,row)

    @staticmethod
    def _update_count(connection,head):
        reset_at=str(head["root"].get("resetAt") or "")
        head["count"]=connection.execute(
            "SELECT COUNT(*) FROM facts WHERE ended IS NULL AND is_record=1"
            + (" AND learned_at>?" if reset_at else ""),
            (reset_at,) if reset_at else (),
        ).fetchone()[0]

    def ingest(self,view,rows,*,archive=None,batch_id=None):
        if view.overlay:
            raise ValueError("Write the durable base, not a UI overlay")
        with self._lock,closing(self._connect(write=True)) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            head=self._head(connection)
            self._validate(head,view)
            if head["epoch"]!=view.head["epoch"]:
                raise RingStoreConflict("Reset generation changed")
            receipt=connection.execute("SELECT epoch FROM batches WHERE id=?",(batch_id,)).fetchone() if batch_id else None
            if receipt is None:
                self._validate(head,view,write=True)
                revision=head["revision"]+1
                self._merge(connection,head,rows,revision)
                head["root"].update(updatedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),identityVersion=2)
                head["revision"]=revision
                self._update_count(connection,head)
                self._write_head(connection,head)
                if batch_id:
                    connection.execute("INSERT INTO batches VALUES (?,?)",(batch_id,head["epoch"]))
        error=self.flush_history(archive) if archive is not None else ""
        result=self.view()
        result.signals()
        return {"candidates":result,"positions":{},"archiveError":error}

    def flush_history(self,archive):
        if archive is None:
            return ""
        try:
            while True:
                with self.reader() as connection:
                    batch=connection.execute("SELECT category,record_key,payload FROM history_pending LIMIT 512").fetchall()
                if not batch:
                    return ""
                for category in sorted({r[0] for r in batch}):
                    archive.archive(category,[json.loads(p) for c,k,p in batch if c==category],
                                    key_field=mining_observation_key)
                with self._lock,closing(self._connect(write=True)) as connection,connection:
                    # Conditional acknowledgement cannot erase a newer payload.
                    connection.executemany("DELETE FROM history_pending WHERE category=? AND record_key=? AND payload=?",batch)
        except (OSError,sqlite3.Error,ValueError,TypeError) as exc:
            return type(exc).__name__

    def pending_history(self,category):
        with self.reader() as connection:
            for payload, in connection.execute("SELECT payload FROM history_pending WHERE category=?",(category,)):
                yield json.loads(payload)

    def reset(self,view,*,archive=None):
        with self._lock,closing(self._connect(write=True)) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            head=self._head(connection)
            self._validate(head,view,write=True)
            revision=head["revision"]+1
            cursor=connection.execute("SELECT payload FROM facts WHERE ended IS NULL")
            self._pending(connection,"mining_catalog",(json.loads(p) for p, in cursor))
            connection.execute("UPDATE facts SET ended=? WHERE ended IS NULL",(revision,))
            head.update(revision=revision,epoch=uuid.uuid4().hex,count=0)
            now=datetime.now(timezone.utc).isoformat(timespec="seconds")
            head["root"].update(resetAt=now,updatedAt=now,identityVersion=2)
            self._write_head(connection,head)
        self.flush_history(archive)
        return self.view()


class RingCatalogView:
    """Immutable revision bound to retained disk versions and a small UI delta."""
    MAX_REGION_ROWS=130_000
    MAX_REGION_PAYLOAD=128*1024*1024

    def __init__(self,store,head,overlay=()):
        self.store,self.head=store,head
        self.revision=head["revision"]
        self.overlay=tuple(overlay)
        self._region_key,self._region=None,None
        self._region_lock=threading.Lock()
        self._signals=None
        self._overlay_projection=None
        self._count=None

    def __len__(self):
        if not self.overlay:
            return self.head["count"]
        if self._count is None:
            with self.store.reader(self) as connection:
                ids,rows=self._project_overlay(connection)
                self._count=self.head["count"]-len(ids)+len(rows)
        return self._count

    def __bool__(self):
        return bool(self.head["count"] or self.overlay)

    def _project_overlay(self,connection):
        if self._overlay_projection is None:
            keys=list(dict.fromkeys(_identity(row) for row in self.overlay if isinstance(row,dict)))
            selected={}
            valid,args=self._visible()
            for offset in range(0,len(keys),400):
                chunk=keys[offset:offset+400]
                for fact_id,seq,payload in connection.execute(
                        "SELECT f.id,f.seq,f.payload FROM facts f WHERE "+valid
                        +" AND f.identity IN ("+",".join("?" for _ in chunk)+")",(*args,*chunk)):
                    selected[seq]=(fact_id,json.loads(payload))
            ordered=[selected[seq] for seq in sorted(selected)]
            merged,_=merge_mining_candidate_batch((row for fid,row in ordered),self.overlay)
            self._overlay_projection=([fid for fid,row in ordered],merged)
        return self._overlay_projection

    def with_overlay(self,rows):
        if not rows:
            return self
        result=RingCatalogView(self.store,self.head,rows)
        # Keep the preloaded, immutable commodity list off the Qt query path.
        result._signals=self.signals()
        return result

    def _visible(self):
        reset_at=str(self.head["root"].get("resetAt") or "")
        return (_VALID+" AND f.is_record=1"+(" AND f.learned_at>?" if reset_at else ""),
                (self.revision,self.revision,reset_at) if reset_at else (self.revision,self.revision))

    def _query(self,connection,where="",parameters=()):
        valid,args=self._visible()
        return connection.execute("SELECT f.seq,f.payload FROM facts f WHERE "+valid
            + where + " ORDER BY f.seq", (*args,*parameters))

    def raw_records(self,revision=0):
        """Full unmodified adoption payloads, including non-record values."""
        with self.store.reader(self) as connection:
            for payload, in connection.execute("SELECT f.payload FROM facts f WHERE "+_VALID
                    +" ORDER BY f.seq",(revision,revision)):
                yield json.loads(payload)

    def __iter__(self):
        with self.store.reader(self) as connection:
            decoder=catalog_snapshot_decoder()
            rows=(decoder.decode(payload) for seq,payload in self._query(connection))
            if self.overlay:
                # Unbounded explicit export retains coverage; regional search
                # below never materializes this galaxy-wide path.
                merged,_=merge_mining_candidate_batch(rows,self.overlay)
                yield from merged
            else:
                for row in rows:
                    for key in TRANSIENT_FIELDS:
                        row.pop(key,None)
                    yield row

    def coordinates_for(self,system):
        key=str(system or "").strip().casefold()
        if self.overlay:
            for row,size in self._regional_rows(system,None,1):
                position=_position(row.get("coordinates"))
                if position is not None:
                    return position
            return None
        with self.store.reader(self) as connection:
            for seq,payload in self._query(connection," AND f.system_key=?",(key,)):
                position=_position(json.loads(payload).get("coordinates"))
                if position is not None:
                    return position
        return None

    def system_names(self):
        with self.store.reader(self) as connection:
            valid,args=self._visible()
            pairs=connection.execute("SELECT f.system_key,f.system FROM facts f WHERE "+valid
                +" AND f.system_key!='' GROUP BY f.system_key HAVING f.seq=MIN(f.seq) ORDER BY f.system_key",
                args).fetchall()
        return [name for key,name in pairs],[key for key,name in pairs]

    def signals(self):
        if self._signals is None:
            with self.store.reader(self) as connection:
                valid,args=self._visible()
                self._signals=[{"id":c} for c, in connection.execute(
                    "SELECT DISTINCT s.commodity FROM signals s JOIN facts f ON f.id=s.fact_id WHERE "+valid,
                    args)]
        return [*self._signals,*({"id":h.get("commodity")} for row in self.overlay
                for h in row.get("hotspots") or () if isinstance(h,dict))]

    def nearby(self,system,origin,radius):
        position=_position(origin)
        radius=float(radius)
        if not math.isfinite(radius):
            raise ValueError("Finite radius required")
        key=(str(system or "").casefold(),tuple(position) if position is not None else None,radius)
        with self._region_lock:
            if self._region_key==key and self._region is not None:
                return iter(self._region)
            self._region_key,self._region=None,None
        rows=self._regional_rows(system,position,radius)
        selected=[]
        size=0
        for row,size_hint in rows:
            size+=size_hint
            if len(selected)>=self.MAX_REGION_ROWS or size>self.MAX_REGION_PAYLOAD:
                from itertools import chain
                return chain(selected,(row,),(r for r,n in rows))
            selected.append(row)
        with self._region_lock:
            self._region_key,self._region=key,selected
        return iter(selected)

    def _regional_rows(self,system,origin,radius):
        system_key=str(system or "").casefold()
        where,params="",()
        if radius>0 and origin is None:
            where,params=" AND f.system_key=?",(system_key,)
        elif radius>0 and all(math.isfinite(v) for v in origin):
            margin=radius+0.1
            where=" AND f.id IN (SELECT id FROM facts WHERE system_key=? UNION " \
                  "SELECT id FROM facts WHERE exceptional=1 UNION SELECT id FROM spatial WHERE " \
                  "x0<=? AND x1>=? AND y0<=? AND y1>=? AND z0<=? AND z1>=?)"
            params=(system_key,origin[0]+margin,origin[0]-margin,origin[1]+margin,
                    origin[1]-margin,origin[2]+margin,origin[2]-margin)
        budget=WorkerBudget()
        with self.store.reader(self) as connection:
            overlay_ids,overlay_rows=self._project_overlay(connection) if self.overlay else ([],[])
            replacements=dict(zip(overlay_ids,overlay_rows))
            if self.overlay and where:
                if overlay_ids:
                    # Only integer IDs returned by SQLite are interpolated.
                    where=" AND ("+where[5:]+" OR f.id IN ("+",".join(map(str,overlay_ids))+") )"
            decoder=catalog_snapshot_decoder()
            valid,args=self._visible()
            cursor=connection.execute("SELECT f.id,f.payload FROM facts f WHERE "+valid
                +where+" ORDER BY f.seq",(*args,*params))

            def projected():
                # Replace only indexed overlay targets. Unaffected regional
                # rows retain the shared decoder representation; no regional
                # identity index, deep copy or full re-encoding is needed.
                for fact_id,payload in cursor:
                    if fact_id in replacements:
                        payload=_encode(replacements[fact_id])
                    yield decoder.decode(payload),len(payload.encode("utf-8"))
                for row in overlay_rows[len(overlay_ids):]:
                    payload=_encode(row)
                    yield decoder.decode(payload),len(payload.encode("utf-8"))

            decoded=projected()
            for row,size in decoded:
                budget.checkpoint()
                for field in TRANSIENT_FIELDS:
                    row.pop(field,None)
                coords=_position(row.get("coordinates"))
                if str(row.get("system") or "").strip().casefold()==system_key:
                    distance=0.0
                elif origin is not None and coords is not None:
                    distance=round(math.sqrt(sum((a-b)**2 for a,b in zip(origin,coords))),1)
                else:
                    distance=None
                if radius<=0 or (distance is not None and not float(distance)>radius):
                    yield row,size

    def summary(self,now=None):
        now=now or datetime.now(timezone.utc)
        cases=" OR ".join("(f.evidence=? AND f.observed_epoch>?)" for _ in MINING_FRESHNESS_SECONDS)
        parameters=[v for evidence,seconds in MINING_FRESHNESS_SECONDS.items()
                    for v in (evidence,now.timestamp()-seconds-1)]
        with self.store.reader(self) as connection:
            valid,args=self._visible()
            ids,merged=self._project_overlay(connection) if self.overlay else ([],[])
            # IDs originate from SQLite. Exclude only the small replaced delta.
            if ids:
                valid+=" AND f.id NOT IN ("+",".join(str(fid) for fid in ids)+")"
            values=connection.execute("SELECT COUNT(*),COUNT(DISTINCT NULLIF(f.system_key,'')),"
                "SUM(f.evidence='LOCAL_CONFIRMED'),SUM(f.evidence='LIVE_REPORTED'),"
                "SUM(f.evidence='CATALOG_CANDIDATE'),SUM(f.evidence='STALE'),"
                "SUM(f.with_hotspots),SUM(f.system_key!=''),SUM(f.coords_known),SUM(f.with_ring),"
                "SUM(f.with_type),SUM(f.with_reserve),SUM(f.with_resource),SUM("+cases+"),"
                "MAX(f.observed_at) FROM facts f WHERE "+valid,
                (*parameters,*args)).fetchone()
            values=list(values)
            known_systems=set()
            for source in merged:
                row=mining_candidate_freshness(source,now=now)
                evidence=str(row.get("evidence") or "STALE")
                system=str(row.get("system") or "").strip().casefold()
                if system and system not in known_systems:
                    known_systems.add(system)
                    if not connection.execute("SELECT 1 FROM facts f WHERE "+valid
                            +" AND f.system_key=? LIMIT 1",(*args,system)).fetchone():
                        values[1]+=1
                coords=row.get("coordinates")
                delta=(1,0,int(evidence=="LOCAL_CONFIRMED"),int(evidence=="LIVE_REPORTED"),
                    int(evidence=="CATALOG_CANDIDATE"),int(evidence=="STALE"),
                    int(bool(row.get("hotspots"))),int(bool(system)),
                    int(isinstance(coords,(list,tuple)) and len(coords)==3 and all(v is not None for v in coords)),
                    int(bool(str(row.get("ring") or row.get("body") or "").strip())),
                    int(_known(row.get("ringTypeName") or row.get("ringType"))),
                    int(_known(row.get("reserveName") or row.get("reserveLevel"))),
                    int(bool(row.get("hotspots") or row.get("yieldStats") or int(row.get("planetaryMiningLocationCount",0) or 0))),
                    int(not row["stale"]))
                for index,addition in enumerate(delta):
                    values[index]=(values[index] or 0)+addition
                values[14]=max(values[14] or "",str(row.get("observedAt") or ""))
        total,systems,local,live,catalog,stale,hotspots,with_system,coords,ring,kind,reserve,resource,current,latest=values
        percent=lambda value: int(round(100*(value or 0)/total)) if total else 0
        return {"total":total,"systems":systems,"local":local or 0,"live":live or 0,
                "catalog":catalog or 0,"stale":stale or 0,"withHotspots":hotspots or 0,
                "recordCompleteness":int(round(100*sum(v or 0 for v in
                    (with_system,coords,ring,kind,reserve,resource))/(total*6))) if total else 0,
                "coordinatesPercent":percent(coords),"ringPercent":percent(ring),
                "ringTypePercent":percent(kind),"reservePercent":percent(reserve),
                "resourceEvidencePercent":percent(resource),"currentPercent":percent(current),
                "latestAt":latest.replace("T"," ")[:16] if latest else "—"}
