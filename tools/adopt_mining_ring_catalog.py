"""Lossless local adoption with full payload and original-file verification.

Uses the production store without starting the Controller, connecting to HTTP,
reading credentials, or writing any legacy JSON/history database.
"""
from __future__ import annotations

import argparse
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ed_companion.navigation.catalog_json import iter_catalog_candidates
from ed_companion.navigation.mining_ring_store import RingCatalogStore


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle,"sha256").hexdigest()


def adopt(directory,report):
    directory=directory.resolve()
    match=re.fullmatch(r"profile-([0-9a-f]{16}|unidentified)",directory.name)
    if not match or not directory.is_dir():
        raise ValueError("An existing exact ED-Frame profile directory is required")
    if report.resolve().is_relative_to(directory):
        raise ValueError("The verification report must be outside the profile")
    source=directory/"mining_finder_catalog.json"
    if not source.is_file():
        raise ValueError("The retained mining JSON must exist")
    names=("mining_finder_catalog.json","mining_market_cache.json",
           "mining_powerplay_catalog.json","mining_powerplay_observations.json",
           "data_history.sqlite3","data_history.sqlite3-wal","data_history.sqlite3-shm")
    originals={name:digest(directory/name) for name in names if (directory/name).is_file()}
    started=time.perf_counter()
    store=RingCatalogStore(directory/"mining_ring_catalog.sqlite3",match[1])
    was_present=store.path.exists()
    view=store.adopt(source)
    elapsed=time.perf_counter()-started
    metadata={};count=0;checksum=hashlib.sha256();sentinel=object()
    for original,stored in zip_longest(iter_catalog_candidates(source,metadata),view.raw_records(),fillvalue=sentinel):
        if original is sentinel or stored is sentinel:
            raise AssertionError("Adoption payload count differs")
        encoded=json.dumps(original,ensure_ascii=False,separators=(",",":"))
        if encoded!=json.dumps(stored,ensure_ascii=False,separators=(",",":")):
            raise AssertionError("Adoption payload/order differs")
        checksum.update(encoded.encode("utf-8"));count+=1
    if {k:v for k,v in view.head["root"].items() if k!="identityVersion"}!={k:v for k,v in metadata.items() if k!="identityVersion"}:
        raise AssertionError("Adoption metadata differs")
    with store.reader(view) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise AssertionError("SQLite integrity check failed")
        if db.execute("SELECT rtreecheck('spatial')").fetchone()[0]!="ok":
            raise AssertionError("Spatial index integrity check failed")
    unchanged=all((directory/name).is_file() and digest(directory/name)==checksum
                  for name,checksum in originals.items())
    if not unchanged:
        raise AssertionError("An original file changed during verification")
    result={"payloads":count,"activeRings":len(view),"payloadOrderSha256":checksum.hexdigest(),
            "rootMetadataEqual":True,"sqliteIntegrity":"ok","spatialIntegrity":"ok",
            "originalsUnchanged":True,"originals":originals,"adoptionSeconds":round(elapsed,3),
            "databaseBytes":store.path.stat().st_size,"existingStoreReused":was_present}
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-directory",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(adopt(args.profile_directory,args.report),indent=2))
