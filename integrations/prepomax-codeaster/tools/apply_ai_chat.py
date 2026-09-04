#!/usr/bin/env python3
"""Wire the AsterMax AI engineering copilot into pinned PrePoMax."""
from __future__ import print_function

import argparse
import shutil
from pathlib import Path


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError("Patch anchor not found: " + label)
    return text.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    src = Path(__file__).resolve().parent.parent / "src" / "PrePoMax" / "AsterMaxAI" / "AsterMaxAiChatForm.cs"
    dst_dir = repo / "PrePoMax" / "AsterMaxAI"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst_dir / "AsterMaxAiChatForm.cs"))

    project = repo / "PrePoMax" / "PrePoMax.csproj"
    text = project.read_text(encoding="utf-8-sig")
    if 'AsterMaxAI\\AsterMaxAiChatForm.cs' not in text:
        anchor = '    <Compile Include="CodeAster\\CodeAsterStudyProbe.cs" />'
        text = replace_once(text, anchor,
                            anchor + '\n    <Compile Include="AsterMaxAI\\AsterMaxAiChatForm.cs" />',
                            "AsterMax AI compile item")
        project.write_text(text, encoding="utf-8")

    main_cs = repo / "PrePoMax" / "Forms" / "FrmMain.cs"
    text = main_cs.read_text(encoding="utf-8-sig")
    field_anchor = '        private KeyboardHook _keyboardHook;'
    field_new = field_anchor + '\n        private PrePoMax.AsterMaxAI.AsterMaxAiChatForm _asterMaxAiChatForm;'
    text = replace_once(text, field_anchor, field_new, "AsterMax AI form field")

    ctor_anchor = '''            InitializeComponent();'''
    ctor_new = '''            InitializeComponent();
            ToolStripMenuItem asterMaxAiMenu = new ToolStripMenuItem("AsterMax AI");
            asterMaxAiMenu.Name = "tsmiAsterMaxAI";
            asterMaxAiMenu.ShortcutKeys = Keys.Control | Keys.Shift | Keys.A;
            asterMaxAiMenu.ToolTipText = "Engineering copilot. Solver results remain authoritative.";
            asterMaxAiMenu.Click += (sender, eventArgs) =>
            {
                if (_asterMaxAiChatForm == null || _asterMaxAiChatForm.IsDisposed)
                    _asterMaxAiChatForm = new PrePoMax.AsterMaxAI.AsterMaxAiChatForm(_controller);
                if (!_asterMaxAiChatForm.Visible) _asterMaxAiChatForm.Show(this);
                _asterMaxAiChatForm.BringToFront();
            };
            menuStripMain.Items.Add(asterMaxAiMenu);'''
    text = replace_once(text, ctor_anchor, ctor_new, "AsterMax AI menu wiring")
    main_cs.write_text(text, encoding="utf-8")

    print("AsterMax AI engineering chat wiring applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
