from datetime import datetime,timedelta,timezone
import importlib.util
import os
from pathlib import Path
import tempfile,unittest

p=Path(__file__).resolve().parents[1]/"ops/catalog-storage-monitor.py"
spec=importlib.util.spec_from_file_location("storage_monitor",p)
monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)


class StorageMonitorTests(unittest.TestCase):
    def test_thresholds_are_explicit(self):
        self.assertEqual(monitor.disk_level(69),"ok")
        self.assertEqual(monitor.disk_level(70),"warning")
        self.assertEqual(monitor.disk_level(84),"warning")
        self.assertEqual(monitor.disk_level(85),"critical")

    def test_retention_only_removes_its_old_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);now=datetime.now(timezone.utc)
            old=folder/"snapshot-20260901T121500000000Z.json"
            latest=folder/"latest.json";other=folder/"catalog.dump"
            arbitrary=folder/"snapshot-user-notes.json"
            new=folder/"snapshot-20261012T121500000000Z.json"
            for p in (old,latest,other,arbitrary,new):p.write_text("{}")
            then=(now-timedelta(days=32)).timestamp()
            for p in (old,latest,other,arbitrary):os.utime(p,(then,then))
            monitor.prune_reports(folder,now)
            self.assertFalse(old.exists())
            for p in (latest,other,arbitrary,new):self.assertTrue(p.exists())


if __name__=="__main__":unittest.main()
