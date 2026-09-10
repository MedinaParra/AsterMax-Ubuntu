#!/usr/bin/env python3
"""Wire headless Code_Aster generation/import probes into patched PrePoMax."""

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
    return replace_once(
        text,
        "            // Set MessageBoxButtons to English defaults\n",
        "            // Headless CI/proof paths run before WinForms or MessageBox hooks are initialized.\n"
        "            if (args != null && args.Length > 0 &&\n"
        "                String.Equals(args[0], \"--codeaster-generate-probe\", StringComparison.OrdinalIgnoreCase))\n"
        "            {\n"
        "                Environment.ExitCode = PrePoMax.CodeAster.CodeAsterStudyProbe.Run(args.Skip(1).ToArray());\n"
        "                return;\n"
        "            }\n"
        "            if (args != null && args.Length > 0 &&\n"
        "                String.Equals(args[0], \"--codeaster-import-probe\", StringComparison.OrdinalIgnoreCase))\n"
        "            {\n"
        "                Environment.ExitCode = PrePoMax.CodeAster.CodeAsterImportProbe.Run(args.Skip(1).ToArray());\n"
        "                return;\n"
        "            }\n"
        "            // Set MessageBoxButtons to English defaults\n",
        "Program headless Code_Aster probes",
    )


def patch_project(text):
    return replace_once(
        text,
        '    <Compile Include="CodeAster\\CodeAsterResultBridge.cs" />',
        '    <Compile Include="CodeAster\\CodeAsterResultBridge.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterImportProbe.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterStudyProbe.cs" />',
        "PrePoMax Code_Aster probe compile items",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "Program.cs", patch_program)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    print("Code_Aster headless generation/import probes applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
