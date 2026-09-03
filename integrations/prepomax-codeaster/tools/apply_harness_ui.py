#!/usr/bin/env python3
"""Expose read-only solver-harness diagnostics in the PrePoMax Analysis property grid."""

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


def patch_view_job(text):
    old = '''        //
        [CategoryAttribute("Advanced settings")]
        [OrderedDisplayName(0, 10, "Compatibility mode")]'''
    new = '''        //
        [CategoryAttribute("Harness")]
        [OrderedDisplayName(0, 10, "Execution boundary")]
        [DescriptionAttribute("True when this analysis is executed through the AsterMax solver harness.")]
        [Id(1, 5)]
        public bool HarnessEnabled { get { return _job.UseSolverHarness; } }
        //
        [CategoryAttribute("Harness")]
        [OrderedDisplayName(1, 10, "Last exit code")]
        [DescriptionAttribute("Exit code returned by the harness process. Empty until a run completes.")]
        [Id(2, 5)]
        public string HarnessExitCode
        {
            get { return _job.LastExitCode.HasValue ? _job.LastExitCode.Value.ToString() : String.Empty; }
        }
        //
        [CategoryAttribute("Harness")]
        [OrderedDisplayName(2, 10, "Manifest")]
        [DescriptionAttribute("Manifest used for the latest solver run.")]
        [Id(3, 5)]
        public string HarnessManifest { get { return _job.HarnessManifestPath; } }
        //
        [CategoryAttribute("Harness")]
        [OrderedDisplayName(3, 10, "Report")]
        [DescriptionAttribute("Fail-closed JSON report produced by the latest solver run.")]
        [Id(4, 5)]
        public string HarnessReport { get { return _job.HarnessReportPath; } }
        //
        [CategoryAttribute("Advanced settings")]
        [OrderedDisplayName(0, 10, "Compatibility mode")]'''
    return replace_once(text, old, new, "ViewJob harness diagnostics")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "PrePoMax.sln").exists():
        raise SystemExit("Not a PrePoMax source tree: " + str(repo))
    patch_file(repo / "PrePoMax" / "Forms" / "61_Analysis" / "ViewJob.cs", patch_view_job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
