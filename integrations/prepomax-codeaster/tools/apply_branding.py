#!/usr/bin/env python3
"""Apply AsterMax Mechanical product branding without renaming PrePoMax namespaces.

Important: Globals.ProgramName is also the PMX serialization header and the pinned
PrePoMax reader parses semantic version tokens from it. Keep the upstream
`<single-token-name> vMAJOR.MINOR.BUILD` shape here; use assembly metadata for
the full human-facing product name.
"""

from __future__ import annotations

import argparse
from pathlib import Path

PRODUCT_NAME = "AsterMax Mechanical"
PMX_PROGRAM_NAME = "AsterMax v1.4.0"


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

    # PMX compatibility contract: TryReadCompressedPmx splits ProgramName and
    # reads version tokens [1], [2], [3]. Removing `v1.4.0` makes every newly
    # saved AsterMax PMX unreadable even though the file itself is non-empty.
    replace_required(
        globals_cs,
        'public static string ProgramName = "PrePoMax v1.4.0";',
        f'public static string ProgramName = "{PMX_PROGRAM_NAME}";',
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

    print(f"Applied product branding: {PRODUCT_NAME}; PMX header: {PMX_PROGRAM_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
