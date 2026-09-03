#!/usr/bin/env python3
"""Make AsterMax Mechanical work-directory handling safe on fresh installs."""

from __future__ import annotations

import argparse
from pathlib import Path


OLD = '''        public string GetWorkDirectory()\n        {\n            string lastFileName = _general.LastFileName;\n            if (_calculix.UsePmxFolderAsWorkDirectory && lastFileName != null && File.Exists(lastFileName) &&\n                Path.GetExtension(lastFileName) == ".pmx")\n            {\n                return Path.GetDirectoryName(lastFileName);\n            }\n            else return _calculix.WorkDirectory;\n        }'''

NEW = '''        public string GetWorkDirectory()\n        {\n            string workDirectory = null;\n            string lastFileName = _general.LastFileName;\n            if (_calculix.UsePmxFolderAsWorkDirectory && lastFileName != null && File.Exists(lastFileName) &&\n                Path.GetExtension(lastFileName) == ".pmx")\n            {\n                workDirectory = Path.GetDirectoryName(lastFileName);\n            }\n            else workDirectory = _calculix.WorkDirectory;\n\n            if (!string.IsNullOrWhiteSpace(workDirectory) && Directory.Exists(workDirectory))\n                return workDirectory;\n\n            // Fresh/portable AsterMax Mechanical builds can start without a configured\n            // CalculiX work directory. Geometry importers still require a real writable\n            // directory for temporary CAD conversion files, so create one automatically.\n            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);\n            string fallback = Path.Combine(localAppData, "AsterMax Mechanical", "Work");\n            try\n            {\n                Directory.CreateDirectory(fallback);\n            }\n            catch\n            {\n                fallback = Path.Combine(Path.GetTempPath(), "AsterMax Mechanical", "Work");\n                Directory.CreateDirectory(fallback);\n            }\n\n            try { _calculix.WorkDirectory = fallback; }\n            catch { }\n            return fallback;\n        }'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", help="Patched PrePoMax checkout root")
    args = parser.parse_args()

    path = Path(args.destination).resolve() / "PrePoMax" / "Settings" / "SettingsContainer.cs"
    text = path.read_text(encoding="utf-8-sig")
    if NEW in text:
        print("AsterMax work-directory fix already applied.")
        return 0
    if OLD not in text:
        raise RuntimeError("Expected SettingsContainer.GetWorkDirectory() body was not found")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8-sig")
    print("Applied AsterMax Mechanical automatic work-directory fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
