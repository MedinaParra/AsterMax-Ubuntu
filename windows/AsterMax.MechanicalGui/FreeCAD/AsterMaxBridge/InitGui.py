"""Hidden AsterMax viewer bootstrap loaded by FreeCAD's normal Mod/InitGui path.

This is intentionally NOT a FreeCAD Workbench. It exists only to let the AsterMax
application use FreeCAD's native Qt/Coin3D/OpenCASCADE viewport as an internal renderer.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone

READY_PATH = os.environ.get("ASTERMAX_VIEWER_READY", "")
BOOTSTRAP_PATH = os.environ.get("ASTERMAX_VIEWER_BOOTSTRAP", "")


def _atomic_json(path: str, payload: dict) -> None:
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = dict(payload)
        payload.setdefault("utc", datetime.now(timezone.utc).isoformat())
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
        os.replace(temporary, path)
    except Exception:
        pass


_atomic_json(
    BOOTSTRAP_PATH,
    {
        "phase": "initgui-entered",
        "pid": os.getpid(),
        "python": sys.version,
        "module": __file__,
    },
)

try:
    module_dir = os.path.dirname(os.path.abspath(__file__))
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import astermax_bridge

    _atomic_json(BOOTSTRAP_PATH, {"phase": "bridge-imported", "pid": os.getpid()})
    astermax_bridge.install()
    _atomic_json(BOOTSTRAP_PATH, {"phase": "bridge-scheduled", "pid": os.getpid()})
except Exception as exc:
    payload = {
        "phase": "initgui-error",
        "pid": os.getpid(),
        "error": repr(exc),
        "traceback": traceback.format_exc(),
    }
    _atomic_json(BOOTSTRAP_PATH, payload)
    _atomic_json(READY_PATH, {"ok": False, **payload})
