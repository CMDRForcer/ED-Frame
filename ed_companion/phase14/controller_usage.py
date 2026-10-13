"""Profile-independent installation ID and background scheduling."""
import logging

from PySide6.QtCore import Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from ed_companion.integrations.usage_ping import UsagePing
from .state import app_data_dir

_LOG = logging.getLogger(__name__)


class UsageMixin:
    usageChanged = Signal()

    def _init_usage_ping(self):
        self._usage_ping = UsagePing(app_data_dir())
        self.usagePingTimer = QTimer(self)
        self.usagePingTimer.setInterval(30 * 60 * 1000)
        self.usagePingTimer.timeout.connect(self._maybe_usage_ping)
        self.usagePingTimer.start()
        QTimer.singleShot(10_000, self._maybe_usage_ping)

    usageInstallId = Property(
        str, lambda self: self._usage_ping.install_id, notify=usageChanged)

    def _maybe_usage_ping(self):
        if self._shutdown_complete or not self._usage_ping.due(self._edframe_catalog_enabled):
            return
        service = self._usage_ping

        def worker():
            service.ping(catalog_enabled=lambda: (
                not self._shutdown_complete and self._edframe_catalog_enabled))
            if not self._shutdown_complete:
                self.usageChanged.emit()

        self._start_network_worker(worker, "usage-ping")

    @Slot()
    def ensureUsageInstallId(self):
        service = self._usage_ping

        def worker():
            try:
                service.ensure_install_id()
            except OSError:
                _LOG.info("Anonymous installation ID could not be saved")
            if not self._shutdown_complete:
                self.usageChanged.emit()

        self._start_network_worker(worker, "usage-id")

    @Slot()
    def copyUsageInstallId(self):
        identity = self._usage_ping.install_id
        if identity:
            QGuiApplication.clipboard().setText(identity)
