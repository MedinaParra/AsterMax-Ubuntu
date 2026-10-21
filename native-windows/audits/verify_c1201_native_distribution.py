#!/usr/bin/env python3
"""C12.01 passive Windows x64 GUI and native Code_Aster distribution audit.

Does not launch the GUI, compile software, execute Code_Aster or benchmark
STEP/VTK/ActiViz. Synthetic PE headers are suitable for unit tests only.
Standard-library Python 3.9+; outputs explicit scoped evidence as JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

GUI = Path("upstream/PrePoMax/bin/x64/Release/AsterMax Mechanical.exe")
CMD = Path("native-windows/runtime/CodeAster/astermax-codeaster-runner.cmd")
PS1 = Path("native-windows/runtime/CodeAster/astermax-codeaster-runner.ps1")
AMD64_MACHINE = 0x8664
WSL_TOKEN = re.compile(r"(?i)(?<![\w.\-])wsl(?:\.exe)?(?![\w.\-])")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pe_machine(path: Path) -> int:
    """Inspect COFF architecture without executing the file."""
    size = path.stat().st_size
    if size < 0x40 + 24:
        raise ValueError("GUI output too small for PE/COFF header")
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("not an MZ executable")
        stream.seek(0x3c)
        offset = struct.unpack("<I", stream.read(4))[0]
        if offset < 0x40 or offset > size - 24:
            raise ValueError("PE offset invalid or truncated")
        stream.seek(offset)
        if stream.read(4) != b"PE\x00\x00":
            raise ValueError("PE signature missing")
        return struct.unpack("<H", stream.read(2))[0]


def verify(root: Path) -> dict:
    """Read-only scoped contracts; neither PASS implies an executable launch."""
    root = root.resolve()
    binary_errors = []
    runner_errors = []
    gui_info = {"status": "FAIL", "path": GUI.as_posix()}
    runner_info = {"status": "FAIL", "paths": [CMD.as_posix(), PS1.as_posix()]}

    binary_path = root / GUI
    if not binary_path.is_file():
        binary_errors.append("Expected branded Release/x64 GUI executable missing")
    else:
        try:
            machine = pe_machine(binary_path)
            if machine != AMD64_MACHINE:
                binary_errors.append(f"GUI COFF machine 0x{machine:04x} is not AMD64")
            else:
                gui_info = {
                    "status": "PASS",
                    "path": GUI.as_posix(),
                    "coff_machine": "0x8664",
                    "size_bytes": binary_path.stat().st_size,
                    "sha256": sha256(binary_path),
                }
        except (OSError, ValueError, struct.error) as error:
            binary_errors.append(f"Invalid Windows GUI PE: {error}")

    runner_texts = {}
    for file, label in ((CMD, "CMD"), (PS1, "PS1")):
        path = root / file
        if not path.is_file():
            runner_errors.append(f"Native Code_Aster {label} runner missing")
            continue
        try:
            if path.stat().st_size <= 0:
                runner_errors.append(f"Native Code_Aster {label} runner empty")
                continue
            body = path.read_text(encoding="utf-8-sig")
            runner_texts[label] = body
            if WSL_TOKEN.search(body):
                runner_errors.append(f"WSL token in native {label} runner")
        except (OSError, UnicodeError) as error:
            runner_errors.append(f"Cannot read {label} runner: {error}")

    cmd = runner_texts.get("CMD", "")
    ps1 = runner_texts.get("PS1", "")
    if cmd:
        if not re.search(r"(?i)\bpowershell(?:\.exe)?\b", cmd):
            runner_errors.append("CMD does not dispatch to PowerShell")
        if "astermax-codeaster-runner.ps1" not in cmd.lower():
            runner_errors.append("CMD does not reference native PS1 runner")
    if ps1:
        if "Find-WindowsBackend" not in ps1 or "Invoke-WindowsBackend" not in ps1:
            runner_errors.append("PS1 native backend dispatch entry points missing")
        if not all(token in ps1.lower() for token in ("run_aster", "as_run")):
            runner_errors.append("PS1 native Code_Aster launchers missing")
    if not runner_errors:
        runner_info = {
            "status": "PASS",
            "paths": [CMD.as_posix(), PS1.as_posix()],
            "cmd_sha256": sha256(root / CMD),
            "ps1_sha256": sha256(root / PS1),
        }
    errors = binary_errors + runner_errors
    return {
        "schema": "astermax-c1201-native-distribution-contract/v1",
        "status": "PASS" if not errors else "FAIL",
        "gui_pe_header_contract": gui_info,
        "native_code_aster_runner_files_contract": runner_info,
        "msbuild_execution": "NOT_RUN",
        "gui_execution": "NOT_RUN",
        "code_aster_solver_execution": "NOT_RUN",
        "step_large_assembly_benchmark": "NOT_RUN",
        "vtk_activiz_dynamic_performance": "NOT_RUN",
        "limitations": "Static file/header inspection only, not code execution or proof of installed solver.",
        "errors": errors,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    options = parser.parse_args(argv)
    result = verify(options.root)
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if options.report is not None:
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
