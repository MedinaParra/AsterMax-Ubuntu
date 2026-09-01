"""Frozen Windows entry point for AsterMax PMV.

Default: launch the real STEP desktop workflow.
Compatibility: --verified-demo dispatches to the deterministic joint evidence demo.
"""
from __future__ import annotations

import sys


def main() -> int:
    if "--verified-demo" in sys.argv:
        from astermax.windows_demo_runner import main as demo_main
        argv=[arg for arg in sys.argv[1:] if arg != "--verified-demo"]
        return demo_main(argv)
    from astermax.windows_app import main as desktop_main
    return desktop_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
