from __future__ import annotations

import json
import os


def run_smoke() -> dict[str, object]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6 import QtCore, QtWidgets, __version__ as pyside_version

    from app.ui_qt.main import MainWindow, PAGES, create_application

    app = create_application(["rf-next-qol-qt-smoke"])
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
        "navigation": [title for title, _ in PAGES],
        "frameless": bool(window.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint),
        "overview_groups": len([
            frame
            for frame in window.findChildren(QtWidgets.QFrame)
            if frame.objectName() == "metricGroup"
        ]),
        "overview_metrics": len(window.metric_labels),
    }
    window.close()
    app.processEvents()
    return result


if __name__ == "__main__":
    print(json.dumps(run_smoke(), ensure_ascii=False, sort_keys=True))
