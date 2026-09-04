#!/usr/bin/env python3
from pathlib import Path
import argparse, shutil

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src" / "PrePoMax" / "AsterMaxAI"

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
    target = repo / "PrePoMax" / "AsterMaxAI"
    target.mkdir(parents=True, exist_ok=True)
    for name in ["AsterMaxAiChatForm.cs", "AsterMaxAiIntegration.cs", "AsterMaxUiTheme.cs", "AsterMaxWorkflowStrip.cs", "AsterMaxEngineeringTree.cs", "AsterMaxResultsWorkspace.cs"]:
        shutil.copy2(SRC / name, target / name)
        print("copied", target / name)

    csproj = repo / "PrePoMax" / "PrePoMax.csproj"
    text = csproj.read_text(encoding="utf-8-sig")
    anchor = '    <Compile Include="CodeAster\\NativeScalarBarGate.cs" />'
    addition = anchor + '\n    <Compile Include="AsterMaxAI\\AsterMaxAiChatForm.cs" />\n    <Compile Include="AsterMaxAI\\AsterMaxAiIntegration.cs" />\n    <Compile Include="AsterMaxAI\\AsterMaxUiTheme.cs" />\n    <Compile Include="AsterMaxAI\\AsterMaxWorkflowStrip.cs" />\n    <Compile Include="AsterMaxAI\\AsterMaxEngineeringTree.cs" />\n    <Compile Include="AsterMaxAI\\AsterMaxResultsWorkspace.cs" />'
    text = replace_once(text, anchor, addition, "AsterMax AI/UI compile items")
    csproj.write_text(text, encoding="utf-8")
    print("patched", csproj)

    frm = repo / "PrePoMax" / "Forms" / "FrmMain.cs"
    text = frm.read_text(encoding="utf-8-sig")
    anchor = '                _controller = new Controller(this);'
    addition = anchor + '\n                InstallAsterMaxAiChat();'
    text = replace_once(text, anchor, addition, "AsterMax AI launcher")
    frm.write_text(text, encoding="utf-8")
    print("patched", frm)
    print("AsterMax AI + workflow + engineering model tree + results workspace integration applied successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
