"""Render real finance QML with simulated history in a disposable profile."""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def run():
    import phase14_main as main
    from PySide6.QtCore import QMetaObject
    from PySide6.QtGui import QFont, QFontDatabase
    from ed_companion.phase14.dashboard_views import build_finance_summary

    original_init = main.SmokeTestRunner.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        for file in ("segoeui.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + file)
        self.window.setProperty("font", QFont("Segoe UI", 12))

        def prepare():
            onboarding = self._find("qa-dialog-onboarding")
            if onboarding:
                QMetaObject.invokeMethod(onboarding, "close")
            self.window.setProperty("currentPage", 10)
            page = self._find("qa-page-cmdr")
            if page is None:
                return False
            now = datetime.now(timezone.utc)
            rows = [{"timestamp": (now - timedelta(minutes=60-i*10)).isoformat(),
                     "credits": 450000000 + i*1200000 - (2000000 if i == 3 else 0),
                     "assets": 900000000+i*1100000, "source": "Journal"}
                    for i in range(7)]
            key = (self.controller._state_revision, self.controller._commander_finance_period)
            self.controller._derived_cache["commander_finance_history"] = (key, rows)
            self.controller._derived_cache["commander_finance_summary"] = (key, build_finance_summary(rows))
            page.setProperty("activeSection", 1)
            self.controller.stateChanged.emit()
            return True

        def capture():
            name = os.environ.get("QA_FINANCE_IMAGE", "ui-final-finance.png")
            if not self.window.grabWindow().save(str(ROOT / "reports" / name)):
                raise RuntimeError("Finance screenshot failed")
            return True

        def scroll():
            viewport = self._find("qa-finance-viewport")
            item = viewport.property("contentItem")
            maximum = max(0, float(item.property("contentHeight")) - float(item.property("height")))
            item.setProperty("contentY", maximum)
            print("FINANCE_SCROLL_RANGE=" + str(maximum), flush=True)
            return True

        def capture_bottom():
            name = os.environ.get("QA_FINANCE_IMAGE", "ui-final-finance.png")
            target = ROOT / "reports" / name.replace(".png", "-bottom.png")
            if not self.window.grabWindow().save(str(target)):
                raise RuntimeError("Finance bottom screenshot failed")
            return True

        self.steps = [("finance-simulated-history", prepare), ("finance-render", capture),
                      ("finance-scroll-bottom", scroll), ("finance-bottom-render", capture_bottom)]

    main.SmokeTestRunner.__init__ = init
    return main.run()

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="edframe-ui-finish-") as scratch:
        os.environ.update(QT_QPA_PLATFORM="offscreen", LOCALAPPDATA=scratch,
                          ED_FRAME_SINGLE_INSTANCE_NAME="ED-Frame-ui-finish-"+str(os.getpid()),
                          PHASE14_SMOKE_TEST="1", PHASE14_PREVIEW_LANGUAGE="de")
        sys.exit(run())
