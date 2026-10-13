"""Small private capacity snapshots; never deletes or rewrites catalog facts."""
from datetime import datetime,timezone,timedelta
import json,math,os,re,shutil,subprocess
from pathlib import Path

REPORT_DIR=Path("/var/lib/edframe-catalog/storage-monitor")


def prune_reports(folder,now):
    cutoff=now-timedelta(days=31)
    for path in folder.glob("snapshot-*.json"):
        if (not path.is_symlink() and path.is_file()
                and re.fullmatch(r"snapshot-\d{8}T\d{12}Z\.json",path.name)
                and datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)<cutoff):
            path.unlink()


def disk_level(percent):
    return "critical" if percent>=85 else "warning" if percent>=70 else "ok"


def main():
    sql="""BEGIN READ ONLY;
    SET LOCAL statement_timeout='5s';
    SET LOCAL lock_timeout='1s';
    SELECT json_build_object(
      'databaseBytes',pg_database_size(current_database()),
      'tables',(SELECT json_agg(row_to_json(t)) FROM (
        SELECT relname,n_live_tup,n_dead_tup,n_tup_upd,n_tup_ins,last_autovacuum,
               pg_total_relation_size(relid) AS bytes
        FROM pg_stat_user_tables
        WHERE relname IN ('markets','station_module_offers','station_outfitting')
        ORDER BY relname) t),
      'indexes',(SELECT json_agg(row_to_json(i)) FROM (
        SELECT c.relname,c.oid,pg_relation_size(c.oid) AS bytes,ix.indisvalid
        FROM pg_class c JOIN pg_index ix ON ix.indexrelid=c.oid
        WHERE c.relname IN ('markets_search_idx','station_module_offers_search_idx')
        ORDER BY c.relname) i));
    ROLLBACK;"""
    command=["docker","compose","exec","-T","db","psql","-qAt",
             "-U",os.environ["POSTGRES_USER"],"-d",os.environ["POSTGRES_DB"],
             "-v","ON_ERROR_STOP=1"]
    # Fetch successfully before writing: a failed check must not replace the
    # last valid snapshot with zeros or a fresh-looking incomplete report.
    result=subprocess.run(command,input=sql,text=True,capture_output=True,
                          check=True,timeout=12)
    data=json.loads(result.stdout)
    now=datetime.now(timezone.utc);disk=shutil.disk_usage("/")
    available=os.statvfs("/").f_bavail*os.statvfs("/").f_frsize
    percent=math.ceil(100*disk.used/(disk.used+available))
    report=dict(checkedAt=now.isoformat(),level=disk_level(percent),
                disk=dict(totalBytes=disk.total,usedBytes=disk.used,
                          freeBytes=available,usedPercent=percent),catalog=data)
    folder=REPORT_DIR
    if folder.is_symlink():raise RuntimeError("Refuse a redirected report directory")
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    encoded=json.dumps(report,indent=2)+"\n"
    stamp=now.strftime("%Y%m%dT%H%M%S%fZ")
    target=folder/("snapshot-"+stamp+".json")
    target.write_text(encoded);target.chmod(0o600)
    tmp=folder/".latest.tmp";tmp.write_text(encoded);tmp.chmod(0o600)
    tmp.replace(folder/"latest.json")
    prune_reports(folder,now)
    print(json.dumps(report),flush=True)
    return 2 if report["level"]=="critical" else 0


if __name__=="__main__":raise SystemExit(main())
