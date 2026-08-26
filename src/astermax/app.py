from __future__ import annotations

import sys
from pathlib import Path


def _load_gui():
    try:
        from PySide6 import QtWidgets
        from astermax.ui.main_window import MainWindow
    except ImportError as exc:
        raise SystemExit(
            'Windows GUI dependencies are missing. Install with: '
            'python -m pip install -e ".[windows]"'
        ) from exc
    return QtWidgets, MainWindow


def main() -> int:
    QtWidgets, MainWindow = _load_gui()

    from astermax.audit.store import AuditStore

    app = QtWidgets.QApplication(sys.argv)
    data_dir = Path.home() / ".astermax"
    window = MainWindow(AuditStore(data_dir / "audit.db"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
