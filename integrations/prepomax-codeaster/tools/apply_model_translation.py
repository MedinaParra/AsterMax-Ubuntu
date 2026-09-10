#!/usr/bin/env python3
"""Wire the FeModel -> Code_Aster study translator into an already overlaid PrePoMax tree.

This is kept as a second, focused patch stage so the original solver-adapter overlay
remains reviewable. It is idempotent and runs immediately after apply_overlay.py.
"""

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


def patch_prepomax_project(text):
    return replace_once(
        text,
        '    <Compile Include="CodeAster\\CodeAsterCaseWriter.cs" />',
        '    <Compile Include="CodeAster\\CodeAsterCaseWriter.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterMeshWriter.cs" />\n'
        '    <Compile Include="CodeAster\\CodeAsterModelTranslator.cs" />',
        "Code_Aster model translator compile items",
    )


def patch_analysis_job(text):
    return replace_once(
        text,
        '            sb.AppendLine("F mmed " + Name + ".med D 20");',
        '            sb.AppendLine("F libr " + Name + ".mail D 20");',
        "AnalysisJob native ASTER mesh export",
    )


def patch_controller(text):
    old = '''        private bool RunJob(string inputFileName, AnalysisJob job)
        {
            ExportToCalculix(inputFileName);
            job.JobStatusChanged = JobStatusChanged;
            job.Submit(1, 1);
            //
            return true;
        }'''

    new = '''        private bool RunJob(string inputFileName, AnalysisJob job)
        {
            if (job.AnalysisSolver == AnalysisSolverTypeEnum.CodeAster)
            {
                // Do not let a failed run appear successful because of stale Code_Aster output.
                foreach (string extension in new string[] { ".comm", ".mail", ".export", ".mess", ".rmed" })
                {
                    string staleFile = Path.Combine(job.WorkDirectory, job.Name + extension);
                    if (File.Exists(staleFile)) File.Delete(staleFile);
                }

                PrePoMax.CodeAster.CodeAsterCaseOptions options = new PrePoMax.CodeAster.CodeAsterCaseOptions();
                options.JobName = job.Name;
                options.WorkingDirectory = job.WorkDirectory;
                options.Version = job.CodeAsterVersion;
                options.NumCpus = job.NumCPUs;
                options.MemoryMB = job.CodeAsterMemoryMB;
                options.TimeLimitSeconds = job.CodeAsterTimeLimitSeconds;

                PrePoMax.CodeAster.CodeAsterTranslationResult translation =
                    PrePoMax.CodeAster.CodeAsterModelTranslator.WriteStudy(_model, options);
                foreach (string warning in translation.Warnings)
                    _form.WriteDataToOutput("Code_Aster: " + warning + Environment.NewLine);
                _form.WriteDataToOutput("Code_Aster study exported: " + translation.CommandFileName + Environment.NewLine);
            }
            else ExportToCalculix(inputFileName);

            job.JobStatusChanged = JobStatusChanged;
            job.Submit(1, 1);
            //
            return true;
        }'''
    return replace_once(text, old, new, "Controller RunJob solver dispatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="Path to the already overlaid PrePoMax source tree")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))

    patch_file(repo / "PrePoMax" / "PrePoMax.csproj", patch_prepomax_project)
    patch_file(repo / "CaeJob" / "AnalysisJob.cs", patch_analysis_job)
    patch_file(repo / "PrePoMax" / "Controller.cs", patch_controller)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
