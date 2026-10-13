"""Publish small update snapshots from the existing bounded I/O scheduler."""
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import Property, QTimer, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from ed_companion.updates.client import UpdateClient
from ed_companion.updates.install import prepare_install
from ed_companion.updates.package import UpdateError
from .state import app_data_dir

LOG = logging.getLogger(__name__)


class UpdatesMixin:
    updateChanged = Signal()
    updateFinished = Signal(object)
    updateProgress = Signal(float)

    def _init_updates(self):
        self._updates = UpdateClient(app_data_dir())
        self._update_status = 'available' if self._updates.release else 'idle'
        self._update_error = ''
        self._update_progress = 0.0
        self._update_package = None
        self._pending_update_job = None
        self._update_backup = ''
        self._update_cancel = threading.Event()
        self.updateFinished.connect(self._finish_update)
        self.updateProgress.connect(self._set_update_progress)
        job_path = self._updates.state.get('prepared_job')
        if job_path:
            try:
                receipt = Path(job_path).parent/'result.json'
                if receipt.resolve().is_relative_to(self._updates.cache.resolve()):
                    result = json.loads(receipt.read_text(encoding='utf-8'))
                    backup = receipt.parent/'userdata'
                    if backup.is_dir():self._update_backup = str(backup)
                    if result.get('status')=='complete':self._update_status = 'updated'
                    if result.get('status') in ('rolled_back','failed','recovery_required'):
                        self._update_status = 'error'
                        self._update_error = 'rollback' if result['status']=='rolled_back' else result.get('code','install')
            except (OSError, ValueError, TypeError):
                pass
        self.updateTimer = QTimer(self)
        self.updateTimer.setInterval(30 * 60 * 1000)
        self.updateTimer.timeout.connect(self._maybe_check_updates)
        self.updateTimer.start()
        QTimer.singleShot(20_000, self._maybe_check_updates)

    def _update_snapshot(self):
        info = self._updates.release or {}
        return {'status':self._update_status,'error':self._update_error,
                'version':info.get('version',''),'notes':info.get('notes',''),
                'progress':self._update_progress,'enabled':self._updates.enabled,
                'autoDownload':self._updates.auto_download,
                'lastCheck':self._updates.state.get('last_success',''),
                'backupAvailable':bool(self._update_backup),
                'canInstall':bool(getattr(sys,'frozen',False) and os.name=='nt'),
                'dismissed':self._updates.state.get('dismissed')==info.get('version'),
                'busy':self._update_status in ('checking','downloading','preparing')}

    updateInfo = Property('QVariantMap', _update_snapshot, notify=updateChanged)

    def _maybe_check_updates(self):
        if not self._shutdown_complete and self._updates.due():
            self._check_updates(False)

    @Slot()
    def checkForUpdates(self):
        self._check_updates(True)

    def _check_updates(self, manual):
        if self._shutdown_complete or self._update_status in ('checking','downloading','preparing','ready'):
            return
        self._update_status = 'checking'
        self._update_error = ''
        self.updateChanged.emit()
        def worker():
            try:
                if self._shutdown_complete:return
                result = self._updates.check(manual=manual)
                payload = ('check',result,None)
            except Exception as error:
                LOG.info('Update check failed')
                payload = ('check',None,getattr(error,'code','network'))
            if not self._shutdown_complete:self.updateFinished.emit(payload)
        if not self._start_network_worker(worker,'app-update-check'):
            self._finish_update(('check',None,'busy'))

    @Slot(object)
    def _finish_update(self, payload):
        operation,result,error = payload
        if self._shutdown_complete:return
        if error:
            self._update_status = 'cancelled' if error=='cancelled' else 'error'
            self._update_error = error
        elif operation=='check':
            self._update_status = 'available' if result else 'current'
        elif operation=='download':
            self._update_package = Path(result)
            self._update_status = 'ready'
        elif operation=='install':
            self._pending_update_job = Path(result)
            self._update_status = 'restarting'
        self.updateChanged.emit()
        if operation=='check' and not error and result and self._updates.auto_download:
            self.downloadUpdate()
        if operation=='install' and not error:
            self.exitRequested.emit()

    @Slot(float)
    def _set_update_progress(self, value):
        if not self._shutdown_complete:
            self._update_progress = value
            self.updateChanged.emit()

    @Slot(bool)
    def setUpdateChecksEnabled(self, value):
        self._update_setting('enabled',value)

    @Slot(bool)
    def setAutomaticUpdateDownload(self, value):
        self._update_setting('auto_download',value)

    def _update_setting(self, key, value):
        try:
            self._updates.setting(key,value)
        except UpdateError:
            self._update_error = 'save'
            self._update_status = 'error'
        self.updateChanged.emit()

    @Slot()
    def dismissUpdate(self):
        try:self._updates.dismiss()
        except UpdateError:self._update_error = 'save'
        self.updateChanged.emit()

    @Slot()
    def openUpdateRelease(self):
        url = self._updates.release['page'] if self._updates.release else 'https://github.com/CMDRForcer/ED-Frame/releases/latest'
        QDesktopServices.openUrl(QUrl(url))

    @Slot()
    def openUpdateBackups(self):
        if self._update_backup:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._update_backup))

    @Slot()
    def downloadUpdate(self):
        if self._shutdown_complete or self._update_status in ('checking','downloading','preparing','ready','restarting') or not self._updates.release:
            return
        self._update_status = 'downloading'
        self._update_progress = 0.0
        self._update_error = ''
        self._update_cancel.clear()
        self.updateChanged.emit()
        def worker():
            last = [0.0]
            def progress(value):
                now=time.monotonic()
                if now-last[0]>=.25 or value==1.0:
                    last[0]=now
                    if not self._shutdown_complete:self.updateProgress.emit(value)
            try:
                package=self._updates.download(cancel=lambda:self._shutdown_complete or self._update_cancel.is_set(),progress=progress)
                payload=('download',str(package),None)
            except Exception as error:
                LOG.info('Update download failed or cancelled')
                payload=('download',None,getattr(error,'code','network'))
            if not self._shutdown_complete:self.updateFinished.emit(payload)
        if not self._start_network_worker(worker,'app-update-download'):
            self._finish_update(('download',None,'busy'))

    @Slot()
    def cancelUpdateDownload(self):
        self._update_cancel.set()

    @Slot()
    def installUpdate(self):
        if self._update_status!='ready' or not self._update_package or not self.updateInfo['canInstall']:
            return
        # Confirm saved UI changes before preparing any process exit.
        if not self._save_ui_config():
            self._finish_update(('install',None,'save'))
            return
        self._update_status='preparing'
        self.updateChanged.emit()
        def worker():
            try:
                job=prepare_install(self._update_package,Path(sys.executable).parent,
                    self._updates.path.parent,self._updates.release['version'])
                with self._updates.lock:
                    self._updates.state['prepared_job']=str(job)
                    self._updates.save()
                payload=('install',str(job),None)
            except Exception as error:
                LOG.info('Update installation preparation failed')
                payload=('install',None,getattr(error,'code','install'))
            if not self._shutdown_complete:self.updateFinished.emit(payload)
        if not self._start_network_worker(worker,'app-update-prepare'):
            self._finish_update(('install',None,'busy'))
