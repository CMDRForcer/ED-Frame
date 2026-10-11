"""Compile QML off-thread and create its objects in short GUI-thread slices."""
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtQml import QQmlComponent, QQmlIncubationController, QQmlIncubator


class _BudgetedIncubation(QQmlIncubationController):
    def __init__(self, parent):
        super().__init__()
        self.timer = QTimer(parent)
        self.timer.setInterval(5)
        self.timer.timeout.connect(lambda: self.incubateFor(3))
        self._closed = False

    def incubatingObjectCountChanged(self, count):
        if count and not self._closed:
            self.timer.start()
        else:
            self.timer.stop()

    def stop(self):
        self._closed = True
        self.timer.stop()


class _RootIncubator(QQmlIncubator):
    def __init__(self, owner):
        super().__init__(QQmlIncubator.IncubationMode.Asynchronous)
        self.owner = owner

    def statusChanged(self, status):
        if status in (QQmlIncubator.Status.Ready, QQmlIncubator.Status.Error):
            # Finish outside the Qt object-construction callback.
            QTimer.singleShot(0, self.owner._root_finished)


class QmlStartup(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, engine, urls, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.urls = [QUrl(url) for url in urls]
        self.roots = []
        self._components = []
        self._component = None
        self._incubator = None
        self._closed = False
        self._started = False
        self._complete = False
        self._incubation = _BudgetedIncubation(self)
        self.engine.setIncubationController(self._incubation)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.setInterval(60_000)
        self._deadline.timeout.connect(lambda: self._fail("QML startup timed out"))

    def start(self):
        if self._started or self._closed:
            return
        self._started = True
        self._deadline.start()
        self._load_next()

    def _load_next(self):
        if self._closed or self._complete:
            return
        if len(self.roots) == len(self.urls):
            self._complete = True
            self._deadline.stop()
            self.ready.emit(tuple(self.roots))
            return
        component = QQmlComponent(self.engine, self)
        # Keep the creation contexts alive for the lifetime of their roots.
        self._components.append(component)
        self._component = component
        component.statusChanged.connect(self._component_changed)
        component.loadUrl(
            self.urls[len(self.roots)], QQmlComponent.CompilationMode.Asynchronous,
        )
        self._component_changed(component.status())

    def _component_changed(self, status):
        if self._closed or self._incubator is not None:
            return
        if status == QQmlComponent.Status.Error:
            self._fail("\n".join(error.toString() for error in self._component.errors()))
        elif status == QQmlComponent.Status.Ready:
            self._component.statusChanged.disconnect(self._component_changed)
            self._incubator = _RootIncubator(self)
            self._component.create(self._incubator, self.engine.rootContext())

    def _root_finished(self):
        if self._closed or self._incubator is None:
            return
        if self._incubator.isError():
            self._fail("\n".join(error.toString() for error in self._incubator.errors()))
            return
        if not self._incubator.isReady():
            return
        root = self._incubator.object()
        if root is None:
            self._fail("QML startup did not create a window")
            return
        QObject.setParent(root, self.engine)
        self.roots.append(root)
        self._incubator.clear()
        self._incubator = None
        QTimer.singleShot(0, self._load_next)

    def _fail(self, message):
        if self._closed:
            return
        self.cancel()
        self.failed.emit(message)

    def cancel(self):
        self._closed = True
        self._deadline.stop()
        self._incubation.stop()
        if self._incubator is not None:
            self._incubator.clear()
            self._incubator = None
