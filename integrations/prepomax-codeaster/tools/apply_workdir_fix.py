#!/usr/bin/env python3
"""Make AsterMax Mechanical work-directory handling safe on fresh installs."""

from __future__ import annotations

import argparse
from pathlib import Path


SETTINGS_CONTAINER_OLD = '''        public string GetWorkDirectory()\n        {\n            string lastFileName = _general.LastFileName;\n            if (_calculix.UsePmxFolderAsWorkDirectory && lastFileName != null && File.Exists(lastFileName) &&\n                Path.GetExtension(lastFileName) == ".pmx")\n            {\n                return Path.GetDirectoryName(lastFileName);\n            }\n            else return _calculix.WorkDirectory;\n        }'''

SETTINGS_CONTAINER_NEW = '''        public string GetWorkDirectory()\n        {\n            string lastFileName = _general.LastFileName;\n            if (_calculix.UsePmxFolderAsWorkDirectory && lastFileName != null && File.Exists(lastFileName) &&\n                Path.GetExtension(lastFileName) == ".pmx")\n            {\n                return Path.GetDirectoryName(lastFileName);\n            }\n            else return _calculix.WorkDirectory;\n        }'''

CALCULIX_OLD = '''        public string WorkDirectory \n        { \n            get { return Tools.GetGlobalPath(_workDirectory); }\n            set \n            {\n                string path = Tools.GetGlobalPath(value);\n                if (!Directory.Exists(path))\n                    throw new Exception("The selected work directory does not exist.");\n                _workDirectory = Tools.GetLocalPath(path);\n            } \n        }'''

CALCULIX_NEW = '''        public string WorkDirectory \n        { \n            get\n            {\n                string path = Tools.GetGlobalPath(_workDirectory);\n                if (!string.IsNullOrWhiteSpace(path) && Directory.Exists(path)) return path;\n\n                // AsterMax Mechanical can run as a portable/fresh build. CAD conversion,\n                // Netgen and solver jobs all require a real writable work directory.\n                // Create a user-local directory automatically instead of failing imports.\n                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);\n                string fallback = Path.Combine(localAppData, "AsterMax Mechanical", "Work");\n                try\n                {\n                    Directory.CreateDirectory(fallback);\n                }\n                catch\n                {\n                    fallback = Path.Combine(Path.GetTempPath(), "AsterMax Mechanical", "Work");\n                    Directory.CreateDirectory(fallback);\n                }\n                _workDirectory = Tools.GetLocalPath(fallback);\n                return fallback;\n            }\n            set \n            {\n                string path = Tools.GetGlobalPath(value);\n                if (!Directory.Exists(path))\n                    throw new Exception("The selected work directory does not exist.");\n                _workDirectory = Tools.GetLocalPath(path);\n            } \n        }'''


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if new in text:
        print(label + " already applied.")
        return
    if old not in text:
        raise RuntimeError("Expected marker not found for " + label + " in " + str(path))
    path.write_text(text.replace(old, new, 1), encoding="utf-8-sig")
    print("Applied " + label + ".")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", help="Patched PrePoMax checkout root")
    args = parser.parse_args()

    root = Path(args.destination).resolve()
    calculix = root / "PrePoMax" / "Settings" / "CalculixSettings.cs"
    settings_container = root / "PrePoMax" / "Settings" / "SettingsContainer.cs"

    replace_once(calculix, CALCULIX_OLD, CALCULIX_NEW, "self-healing CalculiX work directory")

    # Keep SettingsContainer simple: all callers, including direct CAD paths, now receive
    # the same guaranteed directory from CalculixSettings.WorkDirectory.
    text = settings_container.read_text(encoding="utf-8-sig")
    legacy_autofix_marker = 'string fallback = Path.Combine(localAppData, "AsterMax Mechanical", "Work");'
    if legacy_autofix_marker in text:
        start = text.find('        public string GetWorkDirectory()')
        end = text.find('\n        }', start) + len('\n        }')
        if start < 0 or end <= start:
            raise RuntimeError("Could not normalize SettingsContainer.GetWorkDirectory()")
        text = text[:start] + SETTINGS_CONTAINER_NEW + text[end:]
        settings_container.write_text(text, encoding="utf-8-sig")
        print("Normalized SettingsContainer.GetWorkDirectory().")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
