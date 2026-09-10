#!/usr/bin/env python3
"""Focused correctness fixups for the solver-harness runtime stage."""

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


def patch_analysis_job(text):
    old = '''            if (_exe.WaitForExit(ms))
            {
                // Process completed. Check process.ExitCode here.

                // after Kill() _jobStatus is Killed
                _jobStatus = JobStatus.OK;
            }'''
    new = '''            if (_exe.WaitForExit(ms))
            {
                // A harness failure is communicated by a non-zero exit code.
                _lastExitCode = _exe.ExitCode;
                if (_jobStatus != JobStatus.Killed)
                    _jobStatus = _exe.ExitCode == 0 ? JobStatus.OK : JobStatus.Failed;
            }'''
    text = replace_once(text, old, new, "Run_OldWin exit-code contract")

    old = '''            string output = (_sbOutput == null ? "" : _sbOutput.ToString()) +
                            (_sbAllOutput == null ? "" : _sbAllOutput.ToString());
            if (_analysisSolver == AnalysisSolverTypeEnum.Calculix) return output.Contains("*ERROR");'''
    new = '''            string output = (_sbOutput == null ? "" : _sbOutput.ToString()) +
                            (_sbAllOutput == null ? "" : _sbAllOutput.ToString());
            // When the harness owns execution, its exit code is the single source of
            // truth. Do not apply a second, solver-specific text heuristic afterward.
            if (_useSolverHarness) return _lastExitCode.HasValue && _lastExitCode.Value != 0;
            if (_analysisSolver == AnalysisSolverTypeEnum.Calculix) return output.Contains("*ERROR");'''
    text = replace_once(text, old, new, "Harness is authoritative solver validator")
    return text


def patch_controller(text):
    old = '''            // Clear old results
            _wearResults = null;
            //
            job.JobStatusChanged = JobStatusChanged;'''
    new = '''            // Clear old results
            _wearResults = null;
            // Wear/remeshing runs use the same solver execution boundary. PreWearRun
            // may regenerate the .inp before each increment; the manifest remains valid.
            string harnessScript = Path.Combine(Application.StartupPath, "Harness", "astermax_harness.py");
            string harnessManifest = PrePoMax.Harness.SolverHarnessBridge.Prepare(
                job, _settings.CodeAster.PythonExecutable, harnessScript);
            _form.WriteDataToOutput("AsterMax harness manifest: " + harnessManifest + Environment.NewLine);
            //
            job.JobStatusChanged = JobStatusChanged;'''
    return replace_once(text, old, new, "RunWearJob harness boundary")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))
    patch_file(repo / "CaeJob" / "AnalysisJob.cs", patch_analysis_job)
    patch_file(repo / "PrePoMax" / "Controller.cs", patch_controller)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
