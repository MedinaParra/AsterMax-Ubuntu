#!/usr/bin/env python3
"""Wire Code_Aster and solver-harness settings into PrePoMax Settings UI."""

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


def patch_settings_container(text):
    text = replace_once(
        text,
        "        private CodeAsterSettings _codeAster;",
        "        private CodeAsterSettings _codeAster;\n        private HarnessSettings _harness;",
        "Harness settings field",
    )
    text = replace_once(
        text,
        "        public CodeAsterSettings CodeAster { get { return _codeAster; } set { _codeAster = value; } }",
        "        public CodeAsterSettings CodeAster { get { return _codeAster; } set { _codeAster = value; } }\n"
        "        public HarnessSettings Harness { get { return _harness; } set { _harness = value; } }",
        "Harness settings property",
    )
    text = replace_once(
        text,
        "            _codeAster = new CodeAsterSettings();",
        "            _codeAster = new CodeAsterSettings();\n            _harness = new HarnessSettings();",
        "Harness settings initialize",
    )
    text = replace_once(
        text,
        "            _codeAster.Reset();",
        "            _codeAster.Reset();\n            _harness.Reset();",
        "Harness settings reset",
    )
    text = replace_once(
        text,
        "            _codeAster = clone._codeAster;",
        "            _codeAster = clone._codeAster;\n            _harness = clone._harness;",
        "Harness settings clone",
    )
    text = replace_once(
        text,
        '            items.Add("Code_Aster", _codeAster);',
        '            items.Add("Code_Aster", _codeAster);\n            items.Add("Solver Harness", _harness);',
        "Harness settings dictionary",
    )
    old = '''                ISettings codeAsterSettings;
                if (items.TryGetValue("Code_Aster", out codeAsterSettings))
                    _codeAster = (CodeAsterSettings)codeAsterSettings;
                else _codeAster = new CodeAsterSettings();'''
    new = '''                ISettings codeAsterSettings;
                if (items.TryGetValue("Code_Aster", out codeAsterSettings))
                    _codeAster = (CodeAsterSettings)codeAsterSettings;
                else _codeAster = new CodeAsterSettings();
                ISettings harnessSettings;
                if (items.TryGetValue("Solver Harness", out harnessSettings))
                    _harness = (HarnessSettings)harnessSettings;
                else _harness = new HarnessSettings();'''
    text = replace_once(text, old, new, "Harness settings load")
    return text


def patch_settings_form(text):
    old = '''                    else if (entry.Value is CalculixSettings cas)
                        _viewSettings.Add(entry.Key, new ViewCalculixSettings(cas.DeepClone()));'''
    new = '''                    else if (entry.Value is CalculixSettings cas)
                        _viewSettings.Add(entry.Key, new ViewCalculixSettings(cas.DeepClone()));
                    else if (entry.Value is PrePoMax.CodeAsterSettings codeAster)
                        _viewSettings.Add(entry.Key, new ViewCodeAsterSettings(codeAster.DeepClone()));
                    else if (entry.Value is PrePoMax.HarnessSettings harness)
                        _viewSettings.Add(entry.Key, new ViewHarnessSettings(harness.DeepClone()));'''
    return replace_once(text, old, new, "Settings form solver views")


def patch_controller(text):
    return text.replace(
        "job, _settings.CodeAster.PythonExecutable, harnessScript);",
        "job, _settings.Harness.PythonExecutable, harnessScript);",
    )


def patch_project(text):
    text = replace_once(
        text,
        '    <Compile Include="Settings\\CodeAsterSettings.cs" />',
        '    <Compile Include="Settings\\CodeAsterSettings.cs" />\n'
        '    <Compile Include="Settings\\HarnessSettings.cs" />',
        "Harness settings compile item",
    )
    text = replace_once(
        text,
        '    <Compile Include="Forms\\51_Settings\\ViewCalculixSettings.cs" />',
        '    <Compile Include="Forms\\51_Settings\\ViewCalculixSettings.cs" />\n'
        '    <Compile Include="Forms\\51_Settings\\ViewCodeAsterSettings.cs" />\n'
        '    <Compile Include="Forms\\51_Settings\\ViewHarnessSettings.cs" />',
        "Solver settings views compile items",
    )
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "Settings" / "SettingsContainer.cs", patch_settings_container)
    patch_file(repo / "PrePoMax" / "Forms" / "51_Settings" / "FrmSettings.cs", patch_settings_form)
    patch_file(repo / "PrePoMax" / "Controller.cs", patch_controller)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    print("Code_Aster and solver-harness settings UI applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
