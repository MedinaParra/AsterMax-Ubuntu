from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from astermax.audit.store import AuditStore
from astermax.ui.main_window import MainWindow


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory(prefix="astermax-w2b-") as temporary:
        store = AuditStore(Path(temporary) / "audit.db")
        window = MainWindow(store)
        app.processEvents()

        assert isinstance(window.vtk_widget, QVTKRenderWindowInteractor)
        assert window.vtk_widget.GetRenderWindow() is not None
        assert window.vtk_widget.GetRenderWindow().GetRenderers().GetNumberOfItems() == 1
        assert window.renderer.GetActors().GetNumberOfItems() == 2
        assert window._vtk_initialized is False
        assert window.result_banner.text().startswith("REFERENCE GEOMETRY")
        assert window.result_field_combo.isEnabled() is False
        assert "No validated solver result loaded" in window.result_evidence.toPlainText()

        window.close()
        app.processEvents()

    print("ASTERMAX_W2B_WINDOWS_MAINWINDOW_CONSTRUCTION=PASS")
    print("ASTERMAX_W2B_QVTK_RENDERER_WIRING=PASS")
    print("ASTERMAX_W2B_RENDER_CONTEXT_DEFERRED_UNTIL_SHOW=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
