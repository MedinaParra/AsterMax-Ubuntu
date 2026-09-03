#!/usr/bin/env python3
"""Apply the AsterMax Mechanical ribbon shell to the pinned PrePoMax source tree."""

from __future__ import print_function

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OVERLAY = HERE.parent / "overlay"


def fail(message):
    raise SystemExit(message)


def insert_before_method_close(text, signature, statement):
    start = text.find(signature)
    if start < 0:
        fail("Could not find method: " + signature)
    brace = text.find("{", start)
    if brace < 0:
        fail("Could not find method body: " + signature)
    depth = 0
    i = brace
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[:i] + "                " + statement + "\n" + text[i:]
        i += 1
    fail("Could not find closing brace: " + signature)


def main():
    if len(sys.argv) != 2:
        fail("usage: apply_ribbon_ui.py <PrePoMax source tree>")

    root = Path(sys.argv[1]).resolve()
    source = OVERLAY / "PrePoMax" / "Forms" / "FrmMain.AsterMaxRibbon.cs"
    target = root / "PrePoMax" / "Forms" / "FrmMain.AsterMaxRibbon.cs"
    if not source.exists():
        fail("Ribbon overlay source is missing: " + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(target))

    csproj = root / "PrePoMax" / "PrePoMax.csproj"
    project = csproj.read_text(encoding="utf-8-sig")
    compile_line = '    <Compile Include="Forms\\FrmMain.AsterMaxRibbon.cs" />\n'
    if "Forms\\FrmMain.AsterMaxRibbon.cs" not in project:
        anchor = '    <Compile Include="Forms\\FrmMain.cs">'
        pos = project.find(anchor)
        if pos < 0:
            fail("Could not locate FrmMain.cs compile item in PrePoMax.csproj")
        project = project[:pos] + compile_line + project[pos:]
        csproj.write_text(project, encoding="utf-8")

    frm = root / "PrePoMax" / "Forms" / "FrmMain.cs"
    text = frm.read_text(encoding="utf-8-sig")

    init_marker = "            InitializeComponent();\n"
    init_call = "            InitializeAsterMaxRibbon();\n"
    if init_call not in text:
        if init_marker not in text:
            fail("Could not locate InitializeComponent() in FrmMain constructor")
        text = text.replace(init_marker, init_marker + init_call, 1)

    visibility_call = "ApplyAsterMaxRibbonVisibility();"
    signature = "        private void SetMenuAndToolStripVisibility()"
    method_start = text.find(signature)
    if method_start < 0:
        fail("Could not locate SetMenuAndToolStripVisibility")
    next_region = text.find("\n        #endregion", method_start)
    method_slice = text[method_start:next_region if next_region >= 0 else len(text)]
    if visibility_call not in method_slice:
        text = insert_before_method_close(text, signature, visibility_call)

    frm.write_text(text, encoding="utf-8")
    print("AsterMax ribbon UI applied:", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
