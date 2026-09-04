#!/usr/bin/env python3
"""Wire the deterministic verified-results GUI demo into pinned PrePoMax."""
from __future__ import print_function

import argparse
from pathlib import Path


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError("Patch anchor not found: " + label)
    return text.replace(old, new, 1)


def patch_file(path, transform):
    text = path.read_text(encoding="utf-8-sig")
    updated = transform(text)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        print("patched", path)
    else:
        print("unchanged", path)


def patch_program(text):
    old = "            Application.Run(new FrmMain(args));"
    new = '''            FrmMain mainForm = new FrmMain(args);
            if (args != null && args.Length > 0 &&
                String.Equals(args[0], "--astermax-results-demo", StringComparison.OrdinalIgnoreCase))
            {
                string[] demoArgs = args.Skip(1).ToArray();
                mainForm.Shown += (sender, eventArgs) =>
                {
                    mainForm.BeginInvoke((Action)(() =>
                    {
                        int rc = PrePoMax.CodeAster.CodeAsterResultsDemo.Run(mainForm.Controller, demoArgs);
                        Environment.ExitCode = rc;
                        if (rc != 0) mainForm.Close();
                    }));
                };
            }
            Application.Run(mainForm);'''
    return replace_once(text, old, new, "Program deterministic results demo")


def patch_project(text):
    old = '    <Compile Include="CodeAster\\CodeAsterStudyProbe.cs" />'
    new = old + '\n    <Compile Include="CodeAster\\CodeAsterResultsDemo.cs" />'
    return replace_once(text, old, new, "CodeAsterResultsDemo compile item")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "Program.cs", patch_program)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    print("Deterministic verified Results demo wiring applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
