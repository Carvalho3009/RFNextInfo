from __future__ import annotations

import json
import os
import subprocess
import sys


def run_smoke() -> dict[str, object]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6 import QtCore, QtWidgets, __version__ as pyside_version

    existing = QtWidgets.QApplication.instance()
    if existing is not None and existing.platformName() != "offscreen":
        environment = dict(os.environ)
        environment["QT_QPA_PLATFORM"] = "offscreen"
        completed = subprocess.run(
            [sys.executable, "-m", "app.ui_qt.smoke"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )
        return json.loads(completed.stdout.strip().splitlines()[-1])

    from app.ui_qt.main import MainWindow, create_application

    app = create_application(["rf-qol-qt-smoke"])
    window = MainWindow(load_data=False)
    window.resize(window.minimumSize())
    window.show()
    app.processEvents()

    window.nav_buttons[1].click()
    app.processEvents()

    result = {
        "pyside": pyside_version,
        "qt": QtCore.__version__,
        "platform": app.platformName(),
        "width": window.width(),
        "height": window.height(),
        "title": window.windowTitle(),
        "minimum_width": window.minimumWidth(),
        "minimum_height": window.minimumHeight(),
        "page_count": window.page_stack.count(),
        "active_page": window.page_stack.currentIndex(),
        "navigation": [button.text() for button in window.nav_buttons if button.isVisible()],
        "navigation_enabled": {
            button.text(): button.isEnabled() for button in window.nav_buttons
        },
        "frameless": bool(window.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint),
        "overview_groups": len(window.overview_cards),
        "overview_metrics": len(window.metric_labels),
    }
    window.close()
    app.processEvents()
    return result


if __name__ == "__main__":
    print(json.dumps(run_smoke(), ensure_ascii=False, sort_keys=True))
