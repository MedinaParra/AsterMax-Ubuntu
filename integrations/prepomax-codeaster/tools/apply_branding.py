#!/usr/bin/env python3
"""Apply AsterMax Mechanical product branding without renaming PrePoMax namespaces."""

from __future__ import annotations

import argparse
from pathlib import Path

PRODUCT_NAME = "AsterMax Mechanical"


def replace_required(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"Expected branding marker not found in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8-sig")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", help="Patched PrePoMax checkout root")
    args = parser.parse_args()

    root = Path(args.destination).resolve()
    globals_cs = root / "PrePoMax" / "Globals.cs"
    assembly_info = root / "PrePoMax" / "Properties" / "AssemblyInfo.cs"

    replace_required(
        globals_cs,
        'public static string ProgramName = "PrePoMax v1.4.0";',
        f'public static string ProgramName = "{PRODUCT_NAME}";',
    )
    replace_required(
        assembly_info,
        '[assembly: AssemblyTitle("PrePoMax")]',
        f'[assembly: AssemblyTitle("{PRODUCT_NAME}")]',
    )
    replace_required(
        assembly_info,
        '[assembly: AssemblyProduct("PrePoMax")]',
        f'[assembly: AssemblyProduct("{PRODUCT_NAME}")]',
    )

    print(f"Applied product branding: {PRODUCT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
