#!/usr/bin/env python3
"""Harden native Windows Code_Aster runtime discovery and execution."""

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


def patch_codeaster_settings(text):
    text = replace_once(
        text,
        "            get { return _asRunExecutable; }",
        "            get { return PrePoMax.CodeAster.CodeAsterRuntimeLocator.Resolve(_asRunExecutable); }",
        "Code_Aster launcher getter",
    )
    text = replace_once(
        text,
        '            if (_environmentVariables == null) _environmentVariables = new string[0];',
        '            if (_environmentVariables == null) _environmentVariables = new string[0];\n'
        '            _asRunExecutable = PrePoMax.CodeAster.CodeAsterRuntimeLocator.Resolve(_asRunExecutable);\n'
        '            if (String.IsNullOrWhiteSpace(_workDirectory))\n'
        '                _workDirectory = PrePoMax.CodeAster.CodeAsterRuntimeLocator.GetDefaultWorkDirectory();\n'
        '            try { Directory.CreateDirectory(_workDirectory); } catch { }',
        "Code_Aster settings runtime repair",
    )
    text = replace_once(
        text,
        '            _asRunExecutable = null;',
        '            _asRunExecutable = PrePoMax.CodeAster.CodeAsterRuntimeLocator.Resolve(null);',
        "Code_Aster clear launcher",
    )
    text = replace_once(
        text,
        '            _workDirectory = null;',
        '            _workDirectory = PrePoMax.CodeAster.CodeAsterRuntimeLocator.GetDefaultWorkDirectory();',
        "Code_Aster clear work directory",
    )
    text = replace_once(
        text,
        '            _asRunExecutable = "as_run";',
        '            _asRunExecutable = PrePoMax.CodeAster.CodeAsterRuntimeLocator.Resolve(null);',
        "Code_Aster default launcher",
    )
    text = replace_once(
        text,
        '            _workDirectory = Path.Combine(Path.GetTempPath(), "PrePoMax-CodeAster");',
        '            _workDirectory = PrePoMax.CodeAster.CodeAsterRuntimeLocator.GetDefaultWorkDirectory();',
        "Code_Aster default work directory",
    )
    return text


def patch_controller(text):
    old_settings = '''                CalculixSettings cs = _settings.Calculix;
                foreach (var entry in _jobs)
                {
                    entry.Value.WorkDirectory = Settings.GetWorkDirectory();
                    entry.Value.Executable = cs.CalculixExe;
                    entry.Value.NumCPUs = cs.NumCPUs;
                    entry.Value.EnvironmentVariables = cs.EnvironmentVariables;
                }'''
    new_settings = '''                CalculixSettings cs = _settings.Calculix;
                CodeAsterSettings ca = _settings.CodeAster;
                foreach (var entry in _jobs)
                {
                    if (entry.Value.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster)
                    {
                        entry.Value.WorkDirectory = ca.WorkDirectory;
                        entry.Value.Executable = ca.AsRunExecutable;
                        entry.Value.NumCPUs = ca.NumCPUs;
                        entry.Value.CodeAsterVersion = ca.Version;
                        entry.Value.CodeAsterMemoryMB = ca.MemoryMB;
                        entry.Value.CodeAsterTimeLimitSeconds = ca.TimeLimitSeconds;
                    }
                    else
                    {
                        entry.Value.WorkDirectory = Settings.GetWorkDirectory();
                        entry.Value.Executable = cs.CalculixExe;
                        entry.Value.NumCPUs = cs.NumCPUs;
                        entry.Value.EnvironmentVariables = cs.EnvironmentVariables;
                    }
                }'''
    text = replace_once(text, old_settings, new_settings, "solver-aware ApplySettings")

    old_run = '''        public bool PrepareAndRunJob(string inputFileName, AnalysisJob job, bool onlyCheckModel)
        {
            if (File.Exists(job.Executable))'''
    new_run = '''        public bool PrepareAndRunJob(string inputFileName, AnalysisJob job, bool onlyCheckModel)
        {
            if (job.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster)
            {
                string launcher = PrePoMax.CodeAster.CodeAsterRuntimeLocator.Resolve(job.Executable);
                job.Executable = launcher;
                if (!File.Exists(launcher))
                {
                    throw new CaeException(
                        "Code_Aster is the selected solver, but its Windows runtime was not found." +
                        Environment.NewLine + Environment.NewLine +
                        "AsterMax searched the configured launcher, PATH, the Code_Aster registry keys and:" +
                        Environment.NewLine + PrePoMax.CodeAster.CodeAsterRuntimeLocator.GetExpectedWindowsLauncher() +
                        Environment.NewLine + Environment.NewLine +
                        "Run INSTALL_CODE_ASTER.cmd from the AsterMax Mechanical folder, then press Solve again.");
                }
            }

            if (File.Exists(job.Executable))'''
    text = replace_once(text, old_run, new_run, "Code_Aster runtime preflight")
    return text


def patch_project(text):
    return replace_once(
        text,
        '    <Compile Include="CodeAster\\CodeAsterCatalogService.cs" />',
        '    <Compile Include="CodeAster\\CodeAsterCatalogService.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterRuntimeLocator.cs" />',
        "Code_Aster runtime locator compile item",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "Settings" / "CodeAsterSettings.cs", patch_codeaster_settings)
    patch_file(repo / "PrePoMax" / "Controller.cs", patch_controller)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    print("Native Windows Code_Aster runtime discovery applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
