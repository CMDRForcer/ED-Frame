"""Safety policy for the fixed, capacity-aware online index job."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

path=Path(__file__).resolve().parents[1]/'ops/catalog-index-maintenance.py'
spec=importlib.util.spec_from_file_location('index_maintenance',path)
job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job)


def row(name='markets_search_idx',size=2*1024**3,density=20):
    return {'name':name,'index_size':size,'avg_leaf_density':density,'definition':'verified definition','table_oid':123}


class IndexMaintenanceTests(unittest.TestCase):
    def test_missing_uuid_configuration_does_not_accept_any_mounted_disk(self):
        with patch.object(job,'BACKUP_UUID',''),patch.object(job.subprocess,'run') as run:
            self.assertFalse(job.mounted())
            run.assert_not_called()

    def test_small_healthy_unknown_and_unallowlisted_indexes_are_not_candidates(self):
        self.assertTrue(job.recommended(row()))
        for value in (row(size=100*1024**2),row(density=40),row(density=90),row(density=None),
                      row(density=-1),row(name='markets_pkey'),row(density=float('nan'))):
            self.assertFalse(job.recommended(value))

    def test_rebuild_headroom_covers_new_index_and_wal(self):
        self.assertEqual(job.required_headroom(row(size=job.GIB,density=10)),5*job.GIB)
        self.assertGreater(job.required_headroom(row(size=20*job.GIB,density=30)),20*job.GIB)

    def test_multiline_sql_json_is_parsed_as_one_document(self):
        with patch.object(job,'sql',return_value='[\n {"name":"one"},\n {"name":"two"}\n]'):
            self.assertEqual(len(job.read_sql('query')),2)

    def test_missing_mount_refuses_backup_selection(self):
        with patch.object(job,'mounted',return_value=False):
            with self.assertRaises(RuntimeError):job.select_backup()

    def test_backup_selection_ignores_partial_empty_and_expired_files(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'BACKUP',Path(directory)),patch.object(job,'mounted',return_value=True):
            folder=Path(directory);clock=time.time()
            for name,age in (('catalog-old.dump',31*3600),('catalog-good.dump',3600),('catalog-new.dump.partial',1)):
                p=folder/name;p.write_bytes(b'fixture');os.utime(p,(clock-age,clock-age))
            (folder/'catalog-empty.dump').touch()
            self.assertEqual(job.select_backup(clock).name,'catalog-good.dump')

    def test_verified_incident_backup_can_bridge_a_failed_daily_backup(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'BACKUP',Path(directory)),patch.object(job,'mounted',return_value=True):
            folder=Path(directory)/'incident-20261031';folder.mkdir()
            p=folder/'before-index-repair.dump';p.write_bytes(b'fixture')
            self.assertEqual(job.select_backup(),p)

    def test_linked_backups_are_refused(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'BACKUP',Path(directory)),patch.object(job,'mounted',return_value=True):
            (Path(directory)/'catalog-test.dump').write_bytes(b'fixture')
            with patch.object(Path,'is_symlink',return_value=True):
                with self.assertRaises(RuntimeError):job.select_backup()

    def test_preview_and_healthy_indexes_do_not_verify_backup_or_rebuild(self):
        for perform,values in ((False,[row()]),(True,[row(density=90)])):
            with patch.object(job,'inspect_indexes',return_value=values),patch.object(job,'free_bytes',return_value=10*job.GIB),patch.object(job,'verify_backup') as backup,patch.object(job,'rebuild') as rebuild:
                self.assertTrue(job.maintain(perform)['noop'])
                backup.assert_not_called();rebuild.assert_not_called()

    def test_low_capacity_refuses_changes_before_backup_or_rebuild(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ROOT',Path(directory)),patch.object(job,'inspect_indexes',return_value=[row()]),patch.object(job,'free_bytes',return_value=job.GIB),patch.object(job,'verify_backup') as backup,patch.object(job,'rebuild') as rebuild:
            with self.assertRaises(RuntimeError):job.maintain(True)
            backup.assert_not_called();rebuild.assert_not_called()

    def test_backup_failure_stops_before_rebuild(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ROOT',Path(directory)),patch.object(job,'inspect_indexes',return_value=[row()]),patch.object(job,'free_bytes',return_value=10*job.GIB),patch.object(job,'select_backup',return_value=Path('backup.dump')),patch.object(job,'verify_backup',side_effect=RuntimeError('unreadable archive')),patch.object(job,'rebuild') as rebuild:
            with self.assertRaises(RuntimeError):job.maintain(True)
            rebuild.assert_not_called()

    def test_stale_candidates_are_rechecked_after_backup_verification(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ROOT',Path(directory)),patch.object(job,'inspect_indexes',side_effect=[[row()],[row(density=90)]]),patch.object(job,'free_bytes',return_value=10*job.GIB),patch.object(job,'select_backup',return_value=Path('backup.dump')),patch.object(job,'verify_backup',return_value={'verified':True}),patch.object(job,'rebuild') as rebuild:
            self.assertEqual(job.maintain(True)['rebuilds'],[])
            rebuild.assert_not_called()

    def test_at_most_one_index_is_rebuilt_per_cycle(self):
        values=[row(size=job.GIB),row(name='markets_received_idx',size=3*job.GIB)]
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ROOT',Path(directory)),patch.object(job,'inspect_indexes',return_value=values),patch.object(job,'free_bytes',return_value=10*job.GIB),patch.object(job,'select_backup',return_value=Path('backup.dump')),patch.object(job,'verify_backup',return_value={'verified':True}),patch.object(job,'rebuild',return_value={'done':True}) as rebuild:
            self.assertEqual(len(job.maintain(True)['rebuilds']),1)
            self.assertEqual(rebuild.call_args.args[0]['name'],'markets_received_idx')

    def test_previous_failed_rebuild_requires_review(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ROOT',Path(directory)),patch.object(job,'inspect_indexes',return_value=[row()]),patch.object(job,'free_bytes',return_value=10*job.GIB),patch.object(job,'rebuild') as rebuild:
            (Path(directory)/'review-required.json').write_text('{}')
            with self.assertRaises(RuntimeError):job.maintain(True)
            rebuild.assert_not_called()

    def test_pending_manual_job_and_review_flag_block_automatic_job(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ADMIN',Path(directory)):
            folder=Path(directory);identifier='a'*32
            (folder/'active.json').write_text(json.dumps({'job':identifier}))
            status=folder/'jobs'/identifier/'status.json';status.parent.mkdir(parents=True)
            for value,expected in (({'state':'running'},True),({'state':'completed'},False),({'state':'failed','requiresReview':True},True)):
                status.write_text(json.dumps(value));self.assertEqual(job.manual_job_pending(),expected)

    def test_job_pointer_cannot_escape_private_directory(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(job,'ADMIN',Path(directory)):
            (Path(directory)/'active.json').write_text('{"job":"../../etc/passwd"}')
            with self.assertRaises(RuntimeError):job.manual_job_pending()

    def test_unknown_index_is_rejected_before_sql_or_process(self):
        with patch.object(job,'sql') as sql,patch.object(job.subprocess,'Popen') as process:
            with self.assertRaises(ValueError):job.rebuild(row(name='markets_search_idx;DROP TABLE markets'))
            sql.assert_not_called();process.assert_not_called()

    def test_space_guard_targets_only_its_uniquely_named_session(self):
        process=Mock();process.poll.return_value=None;process.communicate.return_value=('','')
        with patch.object(job,'free_bytes',side_effect=[10*job.GIB,job.GIB]),patch.object(job.subprocess,'Popen',return_value=process),patch.object(job,'sql') as sql:
            with self.assertRaisesRegex(RuntimeError,'Own index session stopped'):job.rebuild(row())
            query=sql.call_args.args[0]
            self.assertIn("application_name='edframe-index-maint-",query)
            self.assertIn('datname=current_database()',query)


if __name__=='__main__':unittest.main()
