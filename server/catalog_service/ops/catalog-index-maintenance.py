"""Bounded online index maintenance. Catalog facts and backups are never deleted."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

BACKUP=Path('/var/backups/edframe-catalog')
BACKUP_UUID=os.environ.get('EDFRAME_BACKUP_UUID','')
ROOT=Path('/var/lib/edframe-catalog/index-maintenance')
ADMIN=Path('/var/lib/edframe-catalog/admin-maintenance')
DB='edframe-catalog-db-1'
INDEXES=('markets_search_idx','station_module_offers_price_idx','markets_received_idx')
GIB=1024**3
MAX_BACKUP_AGE=30*3600


def now():return datetime.now(timezone.utc).isoformat()


def free_bytes():
    value=os.statvfs('/')
    return value.f_bavail*value.f_frsize


def mounted():
    if not BACKUP_UUID:return False
    value=subprocess.run(['findmnt','-n','--mountpoint',str(BACKUP),'-o','UUID'],capture_output=True,text=True,timeout=5)
    return value.returncode==0 and value.stdout.strip()==BACKUP_UUID


def command():
    # Credentials stay in the existing database container environment.
    return ['docker','exec','-i',DB,'sh','-c',
            'exec psql -XqAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']


def sql(query,timeout=90):
    value=subprocess.run(command(),input=query,capture_output=True,text=True,timeout=timeout)
    if value.returncode:raise RuntimeError('Database maintenance query failed; inspect the service log and index state.')
    return value.stdout.strip()


def read_sql(query,timeout=90):return json.loads(sql(query,timeout))


def recommended(row):
    density=row.get('avg_leaf_density')
    return (row.get('name') in INDEXES and row.get('index_size',0)>=512*1024**2
            and isinstance(density,(int,float)) and 0<=density<40)


def required_headroom(row):
    estimate=int(row['index_size']*max(0,row['avg_leaf_density'])/90)
    return max(5*GIB,3*estimate+2*GIB)


def inspect_indexes():
    rows=read_sql("""BEGIN READ ONLY;SET LOCAL statement_timeout='10s';
    SELECT jsonb_build_object('invalid',(SELECT COUNT(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND(NOT i.indisvalid OR NOT i.indisready)),
    'rows',(SELECT jsonb_agg(r) FROM(SELECT c.relname AS name,pg_relation_size(c.oid) AS index_size,
      pg_get_indexdef(c.oid) AS definition,i.indisvalid,i.indisready,i.indisunique,i.indisprimary,i.indrelid AS table_oid
      FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname IN ('markets_search_idx','station_module_offers_price_idx','markets_received_idx'))r));COMMIT;""")
    if rows['invalid']:raise RuntimeError('Invalid or unfinished public indexes exist; manual review required.')
    values=rows['rows'] or []
    if {r['name'] for r in values}!=set(INDEXES):raise RuntimeError('An expected maintenance index is missing.')
    if any(r['indisunique'] or r['indisprimary'] for r in values):raise RuntimeError('Refuse changed index/constraint semantics.')
    # At ample capacity only cheap catalog metadata is needed. Measure actual
    # leaf density when capacity crosses the early-warning threshold.
    if free_bytes()>=12*GIB:return values
    namespace=read_sql("SELECT to_json(n.nspname) FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgstattuple';") if sql("SELECT COUNT(*) FROM pg_extension WHERE extname='pgstattuple';")=='1' else None
    own=namespace is None
    namespace=namespace or 'edframe_index_probe_'+uuid.uuid4().hex[:16]
    quoted='"'+namespace.replace('"','""')+'"'
    setup=('CREATE SCHEMA '+quoted+';CREATE EXTENSION pgstattuple WITH SCHEMA '+quoted+';') if own else ''
    selects=["SELECT '"+name+"' AS name,s.* FROM "+quoted+".pgstatindex('public."+name+"')s" for name in INDEXES]
    probe="BEGIN;SET LOCAL lock_timeout='2s';SET LOCAL statement_timeout='60s';"+setup
    probe+='SELECT jsonb_agg(r) FROM ('+' UNION ALL '.join(selects)+')r;ROLLBACK;'
    density=read_sql(probe,180)
    measured={r['name']:r for r in density}
    return [{**row,**measured[row['name']]} for row in values]


def select_backup(clock=None):
    if not mounted():raise RuntimeError('The expected backup disk is not mounted.')
    clock=time.time() if clock is None else clock
    files=list(BACKUP.glob('catalog-*.dump'))
    # Incident archives are intentionally retained independently of daily retention.
    files+=list(BACKUP.glob('incident-*/before-index-repair.dump'))
    choices=[p for p in files if not p.is_symlink() and p.is_file() and p.resolve().is_relative_to(BACKUP.resolve())
             and p.stat().st_size>0 and 0<=clock-p.stat().st_mtime<=MAX_BACKUP_AGE]
    if not choices:raise RuntimeError('No completed full backup from the last 30 hours; index changes refused.')
    return max(choices,key=lambda p:p.stat().st_mtime)


def verify_backup(path):
    before=path.stat()
    with path.open('rb') as stream:
        value=subprocess.run(['docker','exec','-i',DB,'pg_restore','--exit-on-error','--file=/dev/null'],
                             stdin=stream,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=900)
    if value.returncode:raise RuntimeError('Full backup read verification failed; indexes remain untouched.')
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Backup changed during verification.')
    return {'path':str(path),'bytes':after.st_size,'sha256':digest,'fullArchiveReadVerified':True}


def rebuild(row):
    name=row['name']
    if name not in INDEXES:raise ValueError('Index not allowlisted.')
    if free_bytes()<required_headroom(row):raise RuntimeError('Insufficient rebuild and WAL headroom; no index changed.')
    application='edframe-index-maint-'+uuid.uuid4().hex[:16]
    query=("SET application_name='"+application+"';SET maintenance_work_mem='64MB';"
           "SET max_parallel_maintenance_workers=0;SET lock_timeout='3s';SET statement_timeout='12min';"
           'REINDEX INDEX CONCURRENTLY public.'+name+';')
    process=subprocess.Popen(command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    output={}
    def communicate():
        try:output['streams']=process.communicate(input=query)
        except Exception:output['error']=True
    thread=threading.Thread(target=communicate,daemon=True);thread.start()
    deadline=time.monotonic()+780
    while process.poll() is None:
        if free_bytes()<2*GIB or time.monotonic()>deadline:
            # Terminate only this uniquely named maintenance session, never clients.
            sql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='"+application+"' AND datname=current_database();",20)
            thread.join(30)
            raise RuntimeError('Own index session stopped at the space/time guard. Inspect index remnants before retrying.')
        time.sleep(2)
    thread.join(15)
    if process.returncode or output.get('error'):raise RuntimeError('Concurrent rebuild failed; inspect index state before retrying.')
    after=read_sql("SELECT jsonb_build_object('definition',pg_get_indexdef(c.oid),'bytes',pg_relation_size(c.oid),"
                   "'valid',i.indisvalid,'ready',i.indisready,'table_oid',i.indrelid) FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid "
                   "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='"+name+"';")
    if not after or not after['valid'] or not after['ready'] or after['definition']!=row['definition'] or after['table_oid']!=row['table_oid']:
        raise RuntimeError('Rebuilt index does not match the verified definition/table.')
    return {'name':name,'before':row['index_size'],'after':after['bytes'],'reclaimed':row['index_size']-after['bytes']}


def manual_job_pending():
    active=ADMIN/'active.json'
    if not active.exists():return False
    identifier=json.loads(active.read_text())['job']
    if not re.fullmatch('[a-f0-9]{32}',identifier):raise RuntimeError('Invalid private maintenance job pointer.')
    status=ADMIN/'jobs'/identifier/'status.json'
    if not status.exists():raise RuntimeError('Missing private maintenance status; review required.')
    value=json.loads(status.read_text())
    return value.get('state') in ('queued','running','interrupted') or value.get('requiresReview',False)


def maintain(perform=False,progress=lambda message:None):
    result={'at':now(),'freeBefore':free_bytes(),'mode':'run' if perform else 'check','rebuilds':[]}
    rows=inspect_indexes();result['indexes']=rows
    candidates=[r for r in rows if recommended(r)]
    result['candidateCount']=len(candidates)
    if not perform or not candidates:return {**result,'state':'completed','noop':True,'freeAfter':free_bytes()}
    if (ROOT/'review-required.json').exists():raise RuntimeError('Previous maintenance requires manual review; automatic retries disabled.')
    if free_bytes()<max(required_headroom(r) for r in candidates):raise RuntimeError('Insufficient system capacity for a safe online rebuild.')
    progress('Verify latest completed full backup')
    result['backup']=verify_backup(select_backup())
    # Inspect again after archive verification: never rebuild from stale measurements.
    for row in sorted(inspect_indexes(),key=lambda r:r['index_size'],reverse=True):
        if recommended(row):
            progress('Rebuild '+row['name']+' concurrently')
            result['rebuilds'].append(rebuild(row))
            # One index per cycle bounds I/O, WAL and the total service lifetime.
            # Other candidates are reconsidered at the next six-hour check.
            break
    return {**result,'state':'completed','freeAfter':free_bytes()}


def write_status(value):
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=ROOT/'latest.json';temporary=ROOT/'latest.tmp'
    temporary.write_text(json.dumps(value,indent=2));temporary.chmod(0o600);temporary.replace(target)


def main():
    import fcntl
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700);ADMIN.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (ADMIN/'run.lock').open('a') as guard:
        try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'state':'busy','message':'Another maintenance operation owns the lock.'}));return 0
        if manual_job_pending():
            print(json.dumps({'state':'busy','message':'A private maintenance job is pending or requires review.'}));return 0
        try:
            def progress(message):write_status({'at':now(),'state':'running','message':message})
            result=maintain(args.run,progress);write_status(result);print(json.dumps(result));return 0
        except Exception as error:
            message=str(error) if isinstance(error,(RuntimeError,ValueError)) else type(error).__name__
            result={'at':now(),'state':'failed','message':message,'freeBytes':free_bytes()}
            try:
                write_status(result)
                # A failed REINDEX can leave an invalid copy: stop future automatic work.
                if 'rebuild' in message.lower() or 'index session stopped' in message.lower():
                    review=ROOT/'review-required.json';review.write_text(json.dumps(result));review.chmod(0o600)
            except OSError:pass
            print(json.dumps(result));return 2


if __name__=='__main__':raise SystemExit(main())
