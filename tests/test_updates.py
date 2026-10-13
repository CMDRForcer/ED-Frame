"""Offline release, package and profile-preservation contracts."""
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
import zipfile

from ed_companion.updates import client, install, helper
from ed_companion.updates.client import UpdateClient, release_info, version_key
from ed_companion.updates.package import (
    MANIFEST, UpdateError, extract_package, file_hash, verify_directory, write_manifest,
)


def release(version='1.0.11', body=b'zip'):
    name=f'ED-Frame-{version}-Windows.zip'
    return {'tag_name':version,'draft':False,'prerelease':False,'body':'Changes',
        'assets':[{'name':name,'size':len(body),'state':'uploaded',
            'browser_download_url':client.RELEASES+f'download/{version}/{name}',
            'digest':'sha256:'+hashlib.sha256(body).hexdigest()}]}


class Response:
    def __init__(self, body=b'', status=200, headers=None):
        self.body,self.status_code,self.headers=body,status,headers or {}
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def iter_content(self,size):
        for start in range(0,len(self.body),size):yield self.body[start:start+size]
    def close(self):pass


def make_package(directory, version='1.0.11'):
    directory.mkdir(parents=True)
    (directory/'ED-Frame.exe').write_bytes(b'new executable')
    (directory/'_internal').mkdir()
    (directory/'_internal/runtime.dll').write_bytes(b'new runtime')
    (directory/'_internal/Main.qml').write_bytes(b'new UI')
    write_manifest(directory,version)
    output=BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in directory.rglob('*'):
            if path.is_file():archive.write(path,path.relative_to(directory).as_posix())
    return output.getvalue()


def snapshot(directory):
    return {path.relative_to(directory).as_posix():path.read_bytes()
            for path in directory.rglob('*') if path.is_file()}


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root=Path(self.scratch.name)
        self.data=self.root/'local/ED-Frame'
        self.service=UpdateClient(self.data,version='1.0.10')
        self.dev=patch.object(client,'is_development_build',return_value=False)
        self.dev.start();self.addCleanup(self.dev.stop)
        self.env=patch.dict(os.environ,{'EDFRAME_NO_UPDATES':'0','PHASE14_SMOKE_TEST':'0'})
        self.env.start();self.addCleanup(self.env.stop)
        self.get=Mock(return_value=Response(json.dumps(release()).encode()))

    def test_daily_check_and_same_day_restart_use_saved_release(self):
        self.assertTrue(self.service.due())
        self.assertEqual(self.service.check(get=self.get)['version'],'1.0.11')
        self.assertFalse(self.service.due())
        reloaded=UpdateClient(self.data,version='1.0.10')
        self.assertEqual(reloaded.check(get=self.get)['version'],'1.0.11')
        self.get.assert_called_once()
        self.assertEqual(self.get.call_args.kwargs['timeout'],5)
        self.assertEqual(self.get.call_args.kwargs['headers']['User-Agent'],'ED-Frame/1.0.10')
        self.assertFalse(self.get.call_args.kwargs['allow_redirects'])

    def test_dev_env_smoke_and_setting_suppress_automatic_checks(self):
        for variable,value in (('EDFRAME_NO_UPDATES','1'),('PHASE14_SMOKE_TEST','1')):
            with patch.dict(os.environ,{variable:value}):
                self.assertFalse(self.service.due())
        with patch.object(client,'is_development_build',return_value=True):
            self.assertFalse(self.service.due())
        self.service.setting('enabled',False)
        self.assertIsNone(self.service.check(get=self.get))
        self.get.assert_not_called()

    def test_manual_check_is_available_in_dev_and_when_auto_check_is_off(self):
        self.service.setting('enabled',False)
        with patch.object(client,'is_development_build',return_value=True):
            self.assertEqual(self.service.check(manual=True,get=self.get)['version'],'1.0.11')
        with patch.dict(os.environ,{'EDFRAME_NO_UPDATES':'1'}):
            with self.assertRaises(UpdateError):self.service.check(manual=True,get=self.get)
        self.get.assert_called_once()

    def test_failure_does_not_retry_automatically_or_destroy_preferences(self):
        self.service.setting('auto_download',True)
        self.get.return_value=Response(status=503)
        with self.assertRaises(UpdateError):self.service.check(get=self.get)
        reloaded=UpdateClient(self.data,version='1.0.10')
        self.assertTrue(reloaded.auto_download)
        self.assertFalse(reloaded.due())
        self.assertIsNone(reloaded.check(get=self.get))
        self.get.assert_called_once()

    def test_manual_retry_after_failure_and_dismissal_are_persisted(self):
        self.service.check(get=self.get)
        self.service.dismiss()
        reloaded=UpdateClient(self.data,version='1.0.10')
        self.assertEqual(reloaded.state['dismissed'],'1.0.11')
        reloaded.check(manual=True,get=self.get)
        self.assertEqual(self.get.call_count,2)

    def test_numeric_and_legacy_version_comparison(self):
        self.assertGreater(version_key('1.0.10'),version_key('1.0.9'))
        self.assertGreater(version_key('1.0.11'),version_key('1.5.43'))
        self.assertGreater(version_key('1.5.44'),version_key('1.0.11'))
        self.get.return_value=Response(json.dumps(release('1.5.43')).encode())
        self.assertIsNone(self.service.check(get=self.get))
        for version in ('v1.0.11','1.0','1.0.11-dev','../1.0.11',''):
            with self.assertRaises(UpdateError):version_key(version)

    def test_bad_release_metadata_is_rejected(self):
        for field,value in (('draft',True),('prerelease',True),('tag_name','../../')):
            with self.subTest(field=field):
                data=release();data[field]=value
                with self.assertRaises(UpdateError):release_info(data)
        for field,value in (('browser_download_url','https://evil.invalid/payload.zip'),
                ('digest',''),('size',client.MAX_ARCHIVE+1),('state','new')):
            with self.subTest(field=field):
                data=release();data['assets'][0][field]=value
                with self.assertRaises(UpdateError):release_info(data)
        data=release();data['assets']*=2
        with self.assertRaises(UpdateError):release_info(data)

    def test_check_save_failure_prevents_network(self):
        with patch.object(client,'atomic_write',return_value=False):
            with self.assertRaises(UpdateError):self.service.check(get=self.get)
            with self.assertRaises(UpdateError):self.service.setting('enabled',False)
        self.assertTrue(self.service.enabled)
        self.get.assert_not_called()

    def test_download_extracts_only_verified_package_and_reports_progress(self):
        body=make_package(self.root/'fixture')
        self.service.release=release_info(release(body=body))
        progress=[]
        package=self.service.download(get=Mock(return_value=Response(body)),progress=progress.append)
        self.assertEqual((package/'ED-Frame.exe').read_bytes(),b'new executable')
        verify_directory(package,'1.0.11')
        self.assertEqual(progress[-1],1.0)
        self.assertFalse(self.data.exists())

    def test_changed_content_and_cancellation_leave_no_partial_download(self):
        body=make_package(self.root/'fixture')
        self.service.release=release_info(release(body=body))
        for delivered,cancel in ((body[:-1]+b'?',lambda:False),(body,lambda:True),(body[:-1],lambda:False)):
            with self.subTest(size=len(delivered)):
                with self.assertRaises(UpdateError):
                    self.service.download(get=Mock(return_value=Response(delivered)),cancel=cancel)
                self.assertEqual(list(self.service.cache.iterdir()),[])

    def test_redirect_hosts_are_bounded_and_never_accept_other_servers(self):
        body=make_package(self.root/'fixture')
        self.service.release=release_info(release(body=body))
        get=Mock(side_effect=[Response(status=302,headers={'Location':'https://release-assets.githubusercontent.com/signed'}),
            Response(body)])
        self.service.download(get=get)
        self.assertEqual(get.call_count,2)
        get=Mock(return_value=Response(status=302,headers={'Location':'https://evil.invalid/zip'}))
        with self.assertRaises(UpdateError):self.service.download(get=get)
        get.assert_called_once()

    def test_not_enough_space_makes_no_request(self):
        self.service.release=release_info(release())
        with patch.object(client.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(UpdateError):self.service.download(get=self.get)
        self.get.assert_not_called()


class PackageAndProfileTests(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root=Path(self.scratch.name)
        self.data=self.root/'local/ED-Frame'
        self.data.mkdir(parents=True)
        for commander in ('alpha','beta'):
            profile=self.data/('profile-'+commander);profile.mkdir()
            (profile/'ship_blueprints.json').write_text(json.dumps({'plans':[{'slot':'PowerPlant','goal':'G5','id':commander}]}))
            (profile/'phase14_graphics.json').write_text('{"theme":"navy","onboarding_complete":true}')
            (profile/'inara_credentials.dat').write_bytes(b'encrypted fixture')
        (self.data/'usage_ping.json').write_text('{"install_id":"shared fixture"}')
        db=sqlite3.connect(self.data/'markets.sqlite')
        db.execute('CREATE TABLE retained (value TEXT)')
        db.execute("INSERT INTO retained VALUES ('public catalog fixture')")
        db.commit();db.close()
        self.before=snapshot(self.data)
        self.target=self.root/'program/ED-Frame'
        self.target.mkdir(parents=True)
        (self.target/'ED-Frame.exe').write_bytes(b'old executable')
        (self.target/'_internal').mkdir()
        (self.target/'_internal/runtime.dll').write_bytes(b'old runtime')
        self.job_dir=self.data.parent/'ED-Frame-updates'/uuid4().hex
        make_package(self.job_dir/'package')
        self.job_path=install.prepare_install(self.job_dir/'package',self.target,self.data,'1.0.11')

    def test_success_replaces_program_only_and_backs_up_every_profile(self):
        transaction=install.InstallTransaction(self.job_path)
        self.assertTrue(transaction.execute(lambda job:True))
        self.assertEqual(snapshot(self.data),self.before)
        self.assertEqual(snapshot(self.job_dir/'userdata/ED-Frame'),self.before)
        self.assertEqual((self.target/'ED-Frame.exe').read_bytes(),b'new executable')
        self.assertEqual((transaction.old/'ED-Frame.exe').read_bytes(),b'old executable')
        self.assertEqual(json.loads((self.job_dir/'result.json').read_text())['status'],'complete')

    def test_failed_first_start_restores_program_and_original_profiles(self):
        transaction=install.InstallTransaction(self.job_path)
        def fail(job):
            (self.data/'profile-alpha/ship_blueprints.json').write_text('new version migration')
            (self.data/'new-cache.txt').write_text('new version data')
            return False
        self.assertFalse(transaction.execute(fail))
        self.assertEqual(snapshot(self.data),self.before)
        self.assertEqual((self.target/'ED-Frame.exe').read_bytes(),b'old executable')
        failed=self.job_dir/'failed-userdata-ED-Frame'
        self.assertEqual((failed/'new-cache.txt').read_text(),'new version data')
        self.assertTrue(self.target.parent.joinpath('.edframe-failed-'+transaction.job['id']).exists())

    def test_failure_between_program_moves_restores_old_folder(self):
        transaction=install.InstallTransaction(self.job_path)
        rename=Path.rename
        def fail_move(path,target):
            if path==transaction.candidate:raise PermissionError('locked fixture')
            return rename(path,target)
        with patch.object(Path,'rename',fail_move):
            self.assertFalse(transaction.execute(lambda job:True))
        self.assertEqual((self.target/'ED-Frame.exe').read_bytes(),b'old executable')
        self.assertEqual(snapshot(self.data),self.before)

    def test_backup_failure_never_touches_program_or_profile(self):
        transaction=install.InstallTransaction(self.job_path)
        with patch.object(transaction,'backup_data',side_effect=PermissionError('fixture')):
            self.assertFalse(transaction.execute(lambda job:True))
        self.assertEqual(snapshot(self.data),self.before)
        self.assertEqual((self.target/'ED-Frame.exe').read_bytes(),b'old executable')

    def test_reinstallation_in_different_program_folder_reuses_profile_storage(self):
        second=self.root/'reinstalled'
        shutil.copytree(self.target,second)
        self.assertEqual(snapshot(self.data),self.before)
        loaded=UpdateClient(self.data,version='1.0.11')
        self.assertEqual(loaded.path.parent,self.data)
        self.assertEqual(snapshot(self.data),self.before)

    def test_program_inside_or_around_userdata_is_rejected(self):
        for target in (self.data,self.data/'app',self.data.parent,self.job_dir,
                self.data.parent/'EDEngineeringCompanion'):
            with self.subTest(target=target):
                target.mkdir(parents=True,exist_ok=True)
                (target/'ED-Frame.exe').write_bytes(b'fixture')
                with self.assertRaises(UpdateError):install.validate_target(target,self.data,self.job_dir.parent)

    def test_tampered_candidate_is_not_installed(self):
        transaction=install.InstallTransaction(self.job_path)
        (transaction.candidate/'ED-Frame.exe').write_bytes(b'tampered')
        self.assertFalse(transaction.execute(lambda job:True))
        self.assertEqual(snapshot(self.data),self.before)
        self.assertEqual((self.target/'ED-Frame.exe').read_bytes(),b'old executable')

    def test_untrusted_job_paths_are_rejected_before_file_operations(self):
        job=json.loads(self.job_path.read_text())
        job['old']=str(self.data)
        self.job_path.write_text(json.dumps(job))
        with self.assertRaises(UpdateError):install.InstallTransaction(self.job_path)
        self.assertEqual(snapshot(self.data),self.before)

    def test_zip_traversal_duplicates_private_files_and_symlinks_are_rejected(self):
        for name in ('../outside','/absolute','C:/drive','_internal\\bad','profile-alpha/plan.json',
                     'phase14_graphics.json','NUL','bad.'):
            with self.subTest(name=name):
                output=BytesIO()
                with zipfile.ZipFile(output,'w') as archive:archive.writestr(name,b'fixture')
                file=self.root/'bad.zip';file.write_bytes(output.getvalue())
                with self.assertRaises(UpdateError):extract_package(file,self.root/'bad-extract','1.0.11')
                self.assertEqual(snapshot(self.data),self.before)
        output=BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('Main.qml',b'one');archive.writestr('MAIN.QML',b'two')
        file=self.root/'bad.zip';file.write_bytes(output.getvalue())
        with self.assertRaises(UpdateError):extract_package(file,self.root/'bad-extract','1.0.11')

    def test_wrong_package_version_or_unlisted_file_is_rejected(self):
        package=self.job_dir/'package'
        with self.assertRaises(UpdateError):verify_directory(package,'1.0.12')
        (package/'unlisted.txt').write_text('fixture')
        with self.assertRaises(UpdateError):verify_directory(package,'1.0.11')

    def test_ready_acknowledgement_cannot_write_to_arbitrary_environment_path(self):
        arbitrary=self.root/'outside.json'
        with patch.dict(os.environ,{'EDFRAME_UPDATE_READY_FILE':str(arbitrary),'EDFRAME_UPDATE_READY_TOKEN':'token'}):
            with self.assertRaises((UpdateError,OSError)):install.report_startup_ready('1.0.11')
        self.assertFalse(arbitrary.exists())

    def test_ready_acknowledgement_matches_target_token_and_version(self):
        job=json.loads(self.job_path.read_text())
        ready=self.job_dir/'ready.json'
        with patch.dict(os.environ,{'EDFRAME_UPDATE_READY_FILE':str(ready),'EDFRAME_UPDATE_READY_TOKEN':job['token']}),\
                patch.object(install.sys,'executable',str(self.target/'ED-Frame.exe')):
            install.report_startup_ready('1.0.11')
        payload=json.loads(ready.read_text())
        self.assertEqual(payload['pid'],os.getpid())
        self.assertEqual(payload['version'],'1.0.11')

    def test_startup_receipt_errors_stop_failed_child_before_rollback(self):
        job=json.loads(self.job_path.read_text());job['directory']=str(self.job_dir)
        (self.job_dir/'ready.json').write_text('{bad')
        with self.assertRaises(UpdateError):helper.launch_and_check(job)
        (self.job_dir/'ready.json').unlink()
        process=Mock(pid=123);process.poll.return_value=None
        def start(*args,**kwargs):
            (self.job_dir/'ready.json').write_text('{bad')
            return process
        with patch.object(helper.subprocess,'Popen',side_effect=start):
            with self.assertRaises(ValueError):helper.launch_and_check(job)
        process.terminate.assert_called_once()
        process.wait.assert_called_once()
