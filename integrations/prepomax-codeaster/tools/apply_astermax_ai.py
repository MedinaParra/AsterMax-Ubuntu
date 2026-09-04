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
    ap = argparse.ArgumentParser(); ap.add_argument("repo"); args = ap.parse_args()
    repo = Path(args.repo).resolve(); target = repo / "PrePoMax" / "AsterMaxAI"; target.mkdir(parents=True, exist_ok=True)
    names=["AsterMaxAiChatForm.cs","AsterMaxAiIntegration.cs","AsterMaxUiTheme.cs","AsterMaxWorkflowStrip.cs","AsterMaxViewportHud.cs","AsterMaxGlyphLayer.cs","AsterMaxGlyphIntegration.cs","AsterMaxModelReadiness.cs","AsterMaxReadinessIntegration.cs","AsterMaxRegionBindingInspector.cs","AsterMaxRegionBindingIntegration.cs","AsterMaxEngineeringTree.cs","AsterMaxResultsWorkspace.cs"]
    for name in names: shutil.copy2(SRC/name,target/name); print("copied",target/name)
    csproj=repo/"PrePoMax"/"PrePoMax.csproj"; text=csproj.read_text(encoding="utf-8-sig")
    anchor='    <Compile Include="CodeAster\\NativeScalarBarGate.cs" />'
    items=''.join('\n    <Compile Include="AsterMaxAI\\'+n+'" />' for n in names)
    text=replace_once(text,anchor,anchor+items,"AsterMax compile items"); csproj.write_text(text,encoding="utf-8")
    frm=repo/"PrePoMax"/"Forms"/"FrmMain.cs"; text=frm.read_text(encoding="utf-8-sig")
    anchor='                _controller = new Controller(this);'
    addition=anchor+'\n                InstallAsterMaxAiChat();\n                InstallAsterMaxGlyphLayer();\n                InstallAsterMaxModelReadiness();\n                InstallAsterMaxRegionBindingInspector();'
    text=replace_once(text,anchor,addition,"AsterMax launchers"); frm.write_text(text,encoding="utf-8")
    print("AsterMax C8.53 region binding inspector integration applied successfully."); return 0

if __name__ == "__main__": raise SystemExit(main())
