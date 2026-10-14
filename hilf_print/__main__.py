from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import QApplication
from .ui import MainWindow


def main() -> int:
    smoke = "--smoke-test" in sys.argv
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    app.setApplicationName("Hilf Print")
    app.setOrganizationName("Hilf Streetwear")
    # Log event codes only. No PDF contents, names, addresses or file paths.
    directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "hilf-print.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log = logging.getLogger("hilf_print")
        log.addHandler(handler)
        log.setLevel(logging.WARNING)
    except OSError:
        pass  # Logging availability never prevents local operation.
    window = MainWindow()
    window.show()
    if smoke:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
