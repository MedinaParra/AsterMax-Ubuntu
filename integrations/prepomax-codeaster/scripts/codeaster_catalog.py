#!/usr/bin/env python3
"""Return the installed Code_Aster command catalog as JSON.

Run this with a Python interpreter that can import the Code_Aster Python package.
The script intentionally discovers the local catalog instead of maintaining a
version-specific static list.
"""

from __future__ import print_function

import argparse
import importlib
import json
import pkgutil
import sys


def _package_version(code_aster):
    for attr in ("__version__", "VERSION", "version"):
        value = getattr(code_aster, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    try:
        version_mod = importlib.import_module("code_aster.Utilities.version")
        for attr in ("VERSION", "__version__", "version"):
            value = getattr(version_mod, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    except Exception:
        pass
    return None


def discover_commands():
    code_aster = importlib.import_module("code_aster")
    commands_pkg = importlib.import_module("code_aster.Cata.Commands")

    names = set()
    details = {}

    # Most command definitions are modules below code_aster.Cata.Commands.
    if hasattr(commands_pkg, "__path__"):
        for module in pkgutil.iter_modules(commands_pkg.__path__):
            if module.name.startswith("_"):
                continue
            command_name = module.name.upper()
            names.add(command_name)
            details.setdefault(command_name, {})["module"] = (
                "code_aster.Cata.Commands." + module.name
            )

    # Also inspect symbols exported by the package. This catches commands that
    # are re-exported/registered without a one-file-per-command convention.
    for symbol in dir(commands_pkg):
        if symbol.startswith("_") or symbol != symbol.upper():
            continue
        if not any(ch.isalpha() for ch in symbol):
            continue
        names.add(symbol)
        details.setdefault(symbol, {})["exported"] = True

    commands = []
    for name in sorted(names):
        item = {"name": name}
        item.update(details.get(name, {}))
        commands.append(item)

    return {
        "version": _package_version(code_aster),
        "count": len(commands),
        "commands": commands,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filter", default="", help="case-insensitive substring")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        result = discover_commands()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "hint": (
                        "Run this script with the Python environment shipped with "
                        "or configured for Code_Aster."
                    ),
                    "commands": [],
                    "count": 0,
                }
            )
        )
        return 2

    needle = args.filter.strip().upper()
    if needle:
        result["commands"] = [
            item for item in result["commands"] if needle in item["name"]
        ]
        result["count"] = len(result["commands"])

    json.dump(result, sys.stdout, indent=2 if args.pretty else None, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
