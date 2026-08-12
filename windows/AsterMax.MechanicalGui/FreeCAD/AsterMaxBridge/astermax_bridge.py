"""AsterMax native viewer service loaded by FreeCAD InitGui.

No Workbench is registered. FreeCAD provides only the CAD document and native 3D
viewport; AsterMax remains the visible product shell and owns FEM/workflow state.
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone

# Must be set before Coin3D creates the active 3D view on indirect/RDP sessions.
os.environ.setdefault("COIN_FULL_INDIRECT_RENDERING", "1")
os.environ.setdefault("COIN_DONT_INFORM_INDIRECT_RENDERING", "1")

READY_PATH = os.environ.get("ASTERMAX_VIEWER_READY", "")
BOOTSTRAP_PATH = os.environ.get("ASTERMAX_VIEWER_BOOTSTRAP", "")
STEP_PATH = os.environ.get("ASTERMAX_VIEWER_STEP", "")
SCREENSHOT_PATH = os.environ.get("ASTERMAX_VIEWER_SCREENSHOT", "")
COMMAND_PATH = os.environ.get("ASTERMAX_VIEWER_COMMAND", "")

_installed = False
_command_timer = None
_start_timer = None
App = None
Gui = None
Import = None
QtCore = None
QtWidgets = None


def _atomic_json(path: str, payload: dict) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dict(payload)
    payload.setdefault("utc", datetime.now(timezone.utc).isoformat())
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
    os.replace(temporary, path)


def _phase(name: str, **extra) -> None:
    try:
        _atomic_json(BOOTSTRAP_PATH, {"phase": name, "pid": os.getpid(), **extra})
    except Exception:
        pass


def _fail(exc: BaseException, phase: str) -> None:
    payload = {
        "ok": False,
        "phase": phase,
        "pid": os.getpid(),
        "error": repr(exc),
        "traceback": traceback.format_exc(),
    }
    try:
        _atomic_json(BOOTSTRAP_PATH, payload)
    except Exception:
        pass
    try:
        _atomic_json(READY_PATH, payload)
    except Exception:
        pass
    try:
        if App is not None:
            App.Console.PrintError(payload["traceback"] + "\n")
    except Exception:
        pass


def _active_view():
    gui_document = Gui.activeDocument() if Gui is not None else None
    return gui_document.activeView() if gui_document else None


def _hide_freecad_chrome(main_window) -> None:
    try:
        main_window.menuBar().hide()
    except Exception:
        pass
    try:
        main_window.statusBar().hide()
    except Exception:
        pass
    try:
        for toolbar in main_window.findChildren(QtWidgets.QToolBar):
            toolbar.hide()
        for dock in main_window.findChildren(QtWidgets.QDockWidget):
            dock.hide()
    except Exception:
        pass


def _apply_command(command: str) -> None:
    view = _active_view()
    if view is None:
        return
    command = command.strip().lower()
    commands = {
        "fit": view.fitAll,
        "iso": view.viewAxonometric,
        "front": view.viewFront,
        "rear": view.viewRear,
        "back": view.viewRear,
        "left": view.viewLeft,
        "right": view.viewRight,
        "top": view.viewTop,
        "bottom": view.viewBottom,
    }
    action = commands.get(command)
    if action is not None:
        action()
        if command != "fit":
            view.fitAll()


def _poll_command() -> None:
    if not COMMAND_PATH or not os.path.exists(COMMAND_PATH):
        return
    try:
        with open(COMMAND_PATH, "r", encoding="utf-8") as stream:
            command = stream.read().strip()
        os.remove(COMMAND_PATH)
        if command.lower() == "close":
            Gui.getMainWindow().close()
            return
        _apply_command(command)
    except Exception as exc:
        try:
            App.Console.PrintWarning(f"AsterMax viewer command failed: {exc}\n")
        except Exception:
            pass


def _start_viewer() -> None:
    global _command_timer
    try:
        _phase("viewer-start")
        if not STEP_PATH or not os.path.isfile(STEP_PATH):
            raise FileNotFoundError(STEP_PATH or "ASTERMAX_VIEWER_STEP is empty")

        # Remove only a previous AsterMax viewer document from this isolated FreeCAD process.
        try:
            previous = App.getDocument("AsterMaxNativeViewer")
            if previous is not None:
                App.closeDocument(previous.Name)
        except Exception:
            pass

        document = App.newDocument("AsterMaxNativeViewer")
        _phase("document-created", document=document.Name)
        Import.insert(STEP_PATH, document.Name)
        document.recompute()
        if not document.Objects:
            raise RuntimeError("FreeCAD imported zero objects from the STEP file.")
        _phase("step-imported", objects=len(document.Objects))

        main = Gui.getMainWindow()
        if main is None:
            raise RuntimeError("FreeCAD GUI main window is unavailable.")
        main.setWindowTitle("AsterMax — Native CAD Engine")
        _hide_freecad_chrome(main)

        mdi = main.findChild(QtWidgets.QMdiArea)
        if mdi is not None:
            subwindow = mdi.activeSubWindow()
            if subwindow is not None:
                subwindow.showMaximized()

        main.show()
        QtWidgets.QApplication.processEvents()
        view = _active_view()
        if view is None:
            raise RuntimeError("FreeCAD GUI has no active 3D view after STEP import.")
        view.viewAxonometric()
        view.fitAll()
        QtWidgets.QApplication.processEvents()
        _phase("view-realized")

        if SCREENSHOT_PATH:
            os.makedirs(os.path.dirname(SCREENSHOT_PATH), exist_ok=True)
            view.saveImage(SCREENSHOT_PATH, 1280, 720, "Current")
            _phase("screenshot-saved", screenshot=os.path.abspath(SCREENSHOT_PATH))

        visible_objects = 0
        shape_objects = 0
        for obj in document.Objects:
            view_object = getattr(obj, "ViewObject", None)
            if view_object is not None and bool(getattr(view_object, "Visibility", False)):
                visible_objects += 1
            shape = getattr(obj, "Shape", None)
            if shape is not None:
                try:
                    if not shape.isNull():
                        shape_objects += 1
                except Exception:
                    pass

        _atomic_json(
            READY_PATH,
            {
                "ok": True,
                "phase": "ready",
                "pid": os.getpid(),
                "hwnd": int(main.winId()),
                "document": document.Name,
                "objects": len(document.Objects),
                "visible_objects": visible_objects,
                "shape_objects": shape_objects,
                "step": os.path.abspath(STEP_PATH),
                "screenshot": os.path.abspath(SCREENSHOT_PATH) if SCREENSHOT_PATH else "",
                "freecad_version": ".".join(App.Version()[0:3]),
            },
        )
        _phase("ready-published", hwnd=int(main.winId()), shape_objects=shape_objects)

        _command_timer = QtCore.QTimer(main)
        _command_timer.setInterval(120)
        _command_timer.timeout.connect(_poll_command)
        _command_timer.start()
        # Keep a Python reference on the Qt main window as well.
        main._astermax_command_timer = _command_timer
        App.Console.PrintMessage("ASTERMAX_FREECAD_VIEWER_READY\n")
    except Exception as exc:
        _fail(exc, "viewer-start-error")


def install() -> None:
    global _installed, App, Gui, Import, QtCore, QtWidgets, _start_timer
    if _installed:
        return
    _installed = True
    try:
        _phase("freecad-imports-begin")
        import FreeCAD as _App
        import FreeCADGui as _Gui
        import Import as _Import
        from PySide import QtCore as _QtCore, QtWidgets as _QtWidgets

        App = _App
        Gui = _Gui
        Import = _Import
        QtCore = _QtCore
        QtWidgets = _QtWidgets
        _phase("freecad-imports-pass", version=".".join(App.Version()[0:3]))

        main = Gui.getMainWindow()
        if main is None:
            raise RuntimeError("FreeCAD InitGui loaded but no QMainWindow exists.")

        # InitGui is already inside FreeCAD's normal GUI lifecycle. Do not create a nested
        # QEventLoop. Yield to the native Qt loop and start after the main window settles.
        _start_timer = QtCore.QTimer(main)
        _start_timer.setSingleShot(True)
        _start_timer.setInterval(650)
        _start_timer.timeout.connect(_start_viewer)
        _start_timer.start()
        main._astermax_start_timer = _start_timer
        _phase("viewer-scheduled")
    except Exception as exc:
        _fail(exc, "install-error")
