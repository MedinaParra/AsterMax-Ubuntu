#!/usr/bin/env python3
"""Apply the AsterMax Mechanical unified ANSYS-style outline to PrePoMax ModelTree."""

from __future__ import print_function

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OVERLAY = HERE.parent / "overlay"


def fail(message):
    raise SystemExit(message)


def method_bounds(text, signature):
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
                return start, brace, i
        i += 1
    fail("Could not find closing brace: " + signature)


def insert_before_method_close(text, signature, statement):
    start, brace, end = method_bounds(text, signature)
    body = text[brace:end]
    if statement in body:
        return text
    indent = "            "
    return text[:end] + indent + statement + "\n" + text[end:]


def main():
    if len(sys.argv) != 2:
        fail("usage: apply_outline_tree.py <PrePoMax source tree>")

    root = Path(sys.argv[1]).resolve()
    source = OVERLAY / "UserControls" / "ModelTree.AsterMaxOutline.cs"
    target = root / "UserControls" / "ModelTree.AsterMaxOutline.cs"
    if not source.exists():
        fail("Outline overlay source is missing: " + str(source))

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(target))

    csproj = root / "UserControls" / "UserControls.csproj"
    project = csproj.read_text(encoding="utf-8-sig")
    compile_line = '    <Compile Include="ModelTree.AsterMaxOutline.cs" />\n'
    if "ModelTree.AsterMaxOutline.cs" not in project:
        anchor = '    <Compile Include="ModelTree.cs">'
        pos = project.find(anchor)
        if pos < 0:
            fail("Could not locate ModelTree.cs compile item in UserControls.csproj")
        project = project[:pos] + compile_line + project[pos:]
        csproj.write_text(project, encoding="utf-8")

    model_tree = root / "UserControls" / "ModelTree.cs"
    text = model_tree.read_text(encoding="utf-8-sig")

    text = insert_before_method_close(text, "        public ModelTree()", "InitializeAsterMaxOutline();")

    refresh_methods = [
        "        public void Clear()",
        "        public void ClearResults()",
        "        public void RegenerateTree(",
        "        public void AddTreeNode(",
        "        public void UpdateTreeNode(",
        "        public void SwapTreeNodes(",
        "        public void RemoveTreeNode<T>(",
    ]
    for signature in refresh_methods:
        text = insert_before_method_close(text, signature, "RefreshAsterMaxOutline();")

    sync_methods = [
        "        public void SetGeometryTab()",
        "        public void SetModelTab()",
        "        public void SetResultsTab()",
    ]
    for signature in sync_methods:
        text = insert_before_method_close(text, signature, "SyncAsterMaxOutlineSelectionFromSource();")

    model_tree.write_text(text, encoding="utf-8")
    print("AsterMax unified outline applied:", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
