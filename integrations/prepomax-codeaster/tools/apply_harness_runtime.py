#!/usr/bin/env python3
"""Route PrePoMax analysis execution through the AsterMax solver harness.

This patch stage runs after the Code_Aster model and result adapters. It keeps the
solver executable stored on AnalysisJob, but launches the bundled Python harness as
the process boundary. The harness then invokes the configured solver and returns a
non-zero exit code unless all artifact/result contracts pass.
"""

from __future__ import print_function

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_SCRIPT = ROOT / "harness" / "astermax_harness.py"


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


def patch_analysis_job(text):
    text = replace_once(
        text,
        "        protected int _codeAsterTimeLimitSeconds;",
        "        protected int _codeAsterTimeLimitSeconds;\n"
        "        protected bool _useSolverHarness;\n"
        "        protected string _harnessExecutable;\n"
        "        protected string _harnessScriptPath;\n"
        "        protected string _harnessManifestPath;\n"
        "        protected string _harnessReportPath;\n"
        "        [NonSerialized] protected int? _lastExitCode;",
        "AnalysisJob harness fields",
    )

    text = replace_once(
        text,
        "        public int CodeAsterTimeLimitSeconds { get { return _codeAsterTimeLimitSeconds; } set { _codeAsterTimeLimitSeconds = value; } }",
        "        public int CodeAsterTimeLimitSeconds { get { return _codeAsterTimeLimitSeconds; } set { _codeAsterTimeLimitSeconds = value; } }\n"
        "        public bool UseSolverHarness { get { return _useSolverHarness; } set { _useSolverHarness = value; } }\n"
        "        public string HarnessExecutable { get { return _harnessExecutable; } set { _harnessExecutable = value; } }\n"
        "        public string HarnessScriptPath { get { return _harnessScriptPath; } set { _harnessScriptPath = value; } }\n"
        "        public string HarnessManifestPath { get { return _harnessManifestPath; } set { _harnessManifestPath = value; } }\n"
        "        public string HarnessReportPath { get { return _harnessReportPath; } set { _harnessReportPath = value; } }\n"
        "        public int? LastExitCode { get { return _lastExitCode; } }",
        "AnalysisJob harness properties",
    )

    text = replace_once(
        text,
        "            _codeAsterTimeLimitSeconds = 3600;\n            _numCPUs = 1;",
        "            _codeAsterTimeLimitSeconds = 3600;\n"
        "            _useSolverHarness = false;\n"
        "            _harnessExecutable = null;\n"
        "            _harnessScriptPath = null;\n"
        "            _harnessManifestPath = null;\n"
        "            _harnessReportPath = null;\n"
        "            _lastExitCode = null;\n"
        "            _numCPUs = 1;",
        "AnalysisJob harness defaults",
    )

    text = replace_once(
        text,
        '            AppendDataToOutput("Running command: " + _executable + " " + _argument);',
        '            AppendDataToOutput("Running command: " + GetRunExecutable() + " " + GetRunArguments());',
        "AnalysisJob effective command logging",
    )

    text = replace_once(
        text,
        "        private bool ContainsSolverError()\n        {",
        "        private string GetRunExecutable()\n"
        "        {\n"
        "            if (!_useSolverHarness) return _executable;\n"
        "            if (String.IsNullOrWhiteSpace(_harnessExecutable))\n"
        "                throw new InvalidOperationException(\"Harness executable is not configured.\");\n"
        "            return _harnessExecutable;\n"
        "        }\n"
        "        private string GetRunArguments()\n"
        "        {\n"
        "            if (!_useSolverHarness) return _argument;\n"
        "            if (String.IsNullOrWhiteSpace(_harnessScriptPath) || String.IsNullOrWhiteSpace(_harnessManifestPath))\n"
        "                throw new InvalidOperationException(\"Harness script/manifest is not configured.\");\n"
        "            return QuoteArgument(_harnessScriptPath) + \" --manifest \" + QuoteArgument(_harnessManifestPath);\n"
        "        }\n"
        "        private string QuoteArgument(string value)\n"
        "        {\n"
        "            return \"\\\"\" + (value ?? String.Empty).Replace(\"\\\"\", \"\\\\\\\"\") + \"\\\"\";\n"
        "        }\n"
        "        private bool ContainsSolverError()\n        {",
        "AnalysisJob harness process helpers",
    )

    text = replace_once(
        text,
        "        private void bwStart_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)\n        {\n            string resultFileName",
        "        private void bwStart_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)\n"
        "        {\n"
        "            if (e.Error != null)\n"
        "            {\n"
        "                AppendDataToOutput(\" Process start/execution failed: \" + e.Error.Message);\n"
        "                _jobStatus = JobStatus.Failed;\n"
        "            }\n"
        "            string resultFileName",
        "AnalysisJob background process error",
    )

    text = replace_once(
        text,
        "            psi.FileName = _executable;\n            psi.Arguments = _argument;\n            psi.WorkingDirectory = _workDirectory;",
        "            psi.FileName = GetRunExecutable();\n"
        "            psi.Arguments = GetRunArguments();\n"
        "            psi.WorkingDirectory = _workDirectory;",
        "AnalysisJob old Windows harness command",
    )

    text = replace_once(
        text,
        "                // after Kill() _jobStatus is Killed\n                _jobStatus = JobStatus.OK;",
        "                // after Kill() _jobStatus is Killed\n"
        "                _lastExitCode = _exe.ExitCode;\n"
        "                if (_jobStatus != JobStatus.Killed)\n"
        "                    _jobStatus = _exe.ExitCode == 0 ? JobStatus.OK : JobStatus.Failed;",
        "AnalysisJob old Windows exit code",
    )

    text = replace_once(
        text,
        "            psi.FileName = _executable;\n            psi.Arguments = _argument;\n            psi.WorkingDirectory = _workDirectory;\n            psi.WindowStyle = ProcessWindowStyle.Hidden;",
        "            psi.FileName = GetRunExecutable();\n"
        "            psi.Arguments = GetRunArguments();\n"
        "            psi.WorkingDirectory = _workDirectory;\n"
        "            psi.WindowStyle = ProcessWindowStyle.Hidden;",
        "AnalysisJob Win10 harness command",
    )

    text = replace_once(
        text,
        "                    // after Kill() _jobStatus is Killed\n                    if (_jobStatus != JobStatus.Killed) _jobStatus = CaeJob.JobStatus.OK;",
        "                    // after Kill() _jobStatus is Killed\n"
        "                    _lastExitCode = _exe.ExitCode;\n"
        "                    if (_jobStatus != JobStatus.Killed)\n"
        "                        _jobStatus = _exe.ExitCode == 0 ? CaeJob.JobStatus.OK : CaeJob.JobStatus.Failed;",
        "AnalysisJob Win10 exit code",
    )

    text = replace_once(
        text,
        '            string exportFile = Path.Combine(_workDirectory, Name + ".export");\n            StringBuilder sb = new StringBuilder();',
        '            string exportFile = Path.Combine(_workDirectory, Name + ".export");\n'
        '            // The semantic translator owns the export file. Never overwrite a complete generated study.\n'
        '            if (File.Exists(exportFile) && new FileInfo(exportFile).Length > 0) return;\n'
        '            StringBuilder sb = new StringBuilder();',
        "AnalysisJob preserve generated export",
    )

    text = replace_once(
        text,
        '            sb.AppendLine("F mess " + Name + ".mess R 6");\n            sb.AppendLine("F rmed " + Name + ".rmed R 80");',
        '            sb.AppendLine("F mess " + Name + ".mess R 6");\n'
        '            sb.AppendLine("F resu " + Name + ".resu R 8");\n'
        '            sb.AppendLine("F rmed " + Name + ".rmed R 80");',
        "AnalysisJob fallback resu export",
    )
    return text


def patch_controller(text):
    text = replace_once(
        text,
        "            job.JobStatusChanged = JobStatusChanged;\n            job.Submit(1, 1);",
        "            string harnessScript = Path.Combine(Application.StartupPath, \"Harness\", \"astermax_harness.py\");\n"
        "            string harnessManifest = PrePoMax.Harness.SolverHarnessBridge.Prepare(\n"
        "                job, _settings.CodeAster.PythonExecutable, harnessScript);\n"
        "            _form.WriteDataToOutput(\"AsterMax harness manifest: \" + harnessManifest + Environment.NewLine);\n"
        "            job.JobStatusChanged = JobStatusChanged;\n"
        "            job.Submit(1, 1);",
        "Controller route normal analysis through harness",
    )

    text = replace_once(
        text,
        '            string resuFileName = Path.ChangeExtension(fileName, ".resu");\n            try\n            {',
        '            string resuFileName = Path.ChangeExtension(fileName, ".resu");\n'
        '            string harnessReport = PrePoMax.Harness.SolverHarnessBridge.GetReportPathForResult(fileName);\n'
        '            string harnessReason;\n'
        '            if (!PrePoMax.Harness.SolverHarnessBridge.TryValidatePassingReport(harnessReport, out harnessReason))\n'
        '            {\n'
        '                MessageBoxes.ShowError("Code_Aster results were not admitted because the AsterMax harness did not pass." +\n'
        '                                       Environment.NewLine + harnessReason);\n'
        '                return;\n'
        '            }\n'
        '            try\n            {',
        "Controller gate Code_Aster results by harness report",
    )
    return text


def patch_project(text):
    text = replace_once(
        text,
        '    <Compile Include="CodeAster\\CodeAsterResultBridge.cs" />',
        '    <Compile Include="CodeAster\\CodeAsterResultBridge.cs" />\n'
        '    <Compile Include="Harness\\SolverHarnessBridge.cs" />',
        "PrePoMax harness bridge compile item",
    )

    marker = '  <Import Project="$(MSBuildToolsPath)\\Microsoft.CSharp.targets" />'
    content = (
        '  <ItemGroup>\n'
        '    <Content Include="Harness\\astermax_harness.py">\n'
        '      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>\n'
        '    </Content>\n'
        '  </ItemGroup>\n'
    )
    if 'Content Include="Harness\\astermax_harness.py"' not in text:
        if marker not in text:
            raise RuntimeError("Patch anchor not found: harness content item")
        text = text.replace(marker, content + marker, 1)
    return text


def patch_codeaster_settings(text):
    return replace_once(
        text,
        '            _pythonExecutable = "python3";',
        '            _pythonExecutable = "python";',
        "Windows-friendly harness Python default",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="Path to the fully translated/result-bridged PrePoMax tree")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))
    if not HARNESS_SCRIPT.exists():
        raise SystemExit("Harness source missing: " + str(HARNESS_SCRIPT))

    harness_target = repo / "PrePoMax" / "Harness" / "astermax_harness.py"
    harness_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(HARNESS_SCRIPT), str(harness_target))
    print("copied", harness_target.relative_to(repo))

    patch_file(repo / "CaeJob" / "AnalysisJob.cs", patch_analysis_job)
    patch_file(repo / "PrePoMax" / "Controller.cs", patch_controller)
    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_project)
    patch_file(repo / "PrePoMax" / "Settings" / "CodeAsterSettings.cs", patch_codeaster_settings)
    print("AsterMax solver harness runtime applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
