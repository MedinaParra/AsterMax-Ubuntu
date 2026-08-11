"""AsterMax native FreeCAD viewer sidecar.

Runs inside the official FreeCAD GUI process. AsterMax keeps its own workflow,
Details, Gmsh and solver state, while FreeCAD owns STEP visualization through
its native Qt/Coin3D/OpenCASCADE stack.
"""
from __future__ import annotations

import json
import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Import
from PySide import QtCore, QtWidgets

STEP_PATH = os.environ["ASTERMAX_VIEWER_STEP"]
READY_PATH = os.environ["ASTERMAX_VIEWER_READY"]
SCREENSHOT_PATH = os.environ.get("ASTERMAX_VIEWER_SCREENSHOT", "")
COMMAND_PATH = os.environ.get("ASTERMAX_VIEWER_COMMAND", "")


def _write_ready(payload: dict) -> None:
    os.makedirs(os.path.dirname(READY_PATH), exist_ok=True)
    temporary = READY_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
    os.replace(temporary, READY_PATH)


def _hide_freecad_chrome(main_window) -> None:
    try:
        main_window.menuBar().hide()
    except Exception:
        pass
    try:
        main_window.statusBar().hide()
    except Exception:
        pass
    for toolbar in main_window.findChildren(QtWidgets.QToolBar):
        toolbar.hide()
    for dock in main_window.findChildren(QtWidgets.QDockWidget):
        dock.hide()


def _active_view():
    document = Gui.activeDocument()
    return document.activeView() if document else None


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
        if command == "close":
            Gui.getMainWindow().close()
            return
        _apply_command(command)
    except Exception as exc:
        App.Console.PrintWarning(f"AsterMax viewer command failed: {exc}\n")


def _publish_ready(main_window, document) -> None:
    try:
        view = _active_view()
        if view is None:
            raise RuntimeError("FreeCAD did not create an active 3D view.")
        view.viewAxonometric()
        view.fitAll()
        QtWidgets.QApplication.processEvents()

        if SCREENSHOT_PATH:
            os.makedirs(os.path.dirname(SCREENSHOT_PATH), exist_ok=True)
            view.saveImage(SCREENSHOT_PATH, 1280, 720, "Current")

        visible_objects = 0
        shape_objects = 0
        for obj in document.Objects:
            view_object = getattr(obj, "ViewObject", None)
            if view_object is not None and bool(getattr(view_object, "Visibility", False)):
                visible_objects += 1
            shape = getattr(obj, "Shape", None)
            if shape is not None and not bool(getattr(shape, "isNull", lambda: True)()):
                shape_objects += 1

        _write_ready(
            {
                "ok": True,
                "hwnd": int(main_window.winId()),
                "document": document.Name,
                "objects": len(document.Objects),
                "visible_objects": visible_objects,
                "shape_objects": shape_objects,
                "step": os.path.abspath(STEP_PATH),
                "screenshot": os.path.abspath(SCREENSHOT_PATH) if SCREENSHOT_PATH else "",
                "freecad_version": ".".join(App.Version()[0:3]),
            }
        )
    except Exception as exc:
        _write_ready(
            {
                "ok": False,
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
        )


try:
    if not os.path.isfile(STEP_PATH):
        raise FileNotFoundError(STEP_PATH)

    document = App.newDocument("AsterMaxNativeViewer")
    Import.insert(STEP_PATH, document.Name)
    document.recompute()
    if not document.Objects:
        raise RuntimeError("FreeCAD imported zero objects from the STEP file.")

    main = Gui.getMainWindow()
    main.setWindowTitle("AsterMax — FreeCAD Native Viewer")
    _hide_freecad_chrome(main)

    mdi = main.findChild(QtWidgets.QMdiArea)
    if mdi is not None:
        subwindow = mdi.activeSubWindow()
        if subwindow is not None:
            subwindow.showMaximized()

    # Realize the native Qt/Coin3D widget before AsterMax reparents the HWND.
    main.show()
    main.raise_()
    QtWidgets.QApplication.processEvents()

    view = _active_view()
    if view is None:
        raise RuntimeError("FreeCAD GUI has no active 3D view after STEP import.")
    view.viewAxonometric()
    view.fitAll()

    _command_timer = QtCore.QTimer(main)
    _command_timer.setInterval(120)
    _command_timer.timeout.connect(_poll_command)
    _command_timer.start()

    QtCore.QTimer.singleShot(450, lambda: _publish_ready(main, document))
except Exception as exc:
    _write_ready(
        {
            "ok": False,
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
    )
    App.Console.PrintError(traceback.format_exc() + "\n")
