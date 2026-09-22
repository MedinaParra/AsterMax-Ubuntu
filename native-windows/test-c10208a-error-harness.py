#!/usr/bin/env python3
"""Static guard for the C10.20.8a patch-error harness. No solver values are generated."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
h=(ROOT/"harness-c10208a-patch-chain.ps1").read_text(encoding="utf-8-sig")
p=(ROOT/"patch-c10203-cancel-solve.ps1").read_text(encoding="utf-8-sig")
v=(ROOT/"validate-patch-chain.py").read_text(encoding="utf-8-sig")
w=(ROOT.parent/".github"/"workflows"/"astermax-workflow-conformance.yml").read_text(encoding="utf-8-sig")

for token in [
    "astermax-patch-harness/v1",
    "critical_hashes_before",
    "critical_hashes_after",
    "ANCHOR_DRIFT",
    "failure-snapshot",
    "final-snapshot",
    "AsterMaxIntegratedResults.cs",
    "PATCH_FAILURE.json",
    "Do not continue dependent patches",
]:
    assert token in h, token

assert "structural anchor missing: RunCaptured(ProcessStartInfo psi,string stem)" in p
assert "$capturedSignature=" in p
assert "$capturedStart=$s.IndexOf" in p
assert "$depth=0" in p
assert "$capturedEnd=$i+1" in p
assert "$capturedPattern=" not in p
assert "$capturedOld=@'" not in p
assert 'return RunTrackedProcess(psi,stem+"_STDOUT.log",stem+"_STDERR.log");' in p
assert "(?<![A-Za-z0-9_.-])" in v
assert "harness-c10208a-patch-chain.ps1" in w
assert "foreach($p in $patches)" not in w
print("C10.20.8a PATCH_ERROR_HARNESS_REGRESSION_OK")

smoke=(ROOT/"patch-c10208-functional-command-smoke.ps1").read_text(encoding="utf-8-sig")
for token in [
    "direct_diagnostic_attempted",
    "direct_diagnostic_produced_mesh",
    "direct_diagnostic_error",
    "netgen_exe_present",
    "_controller.CreateMesh(candidateNames[0])",
]:
    assert token in smoke, token

runner=(ROOT/"workflow-conformance"/"run-e2e.ps1").read_text(encoding="utf-8-sig")
for token in [
    "mesh-command-preflight.json",
    "mesh-workdir-manifest.json",
    "source_work_directory",
    "Get-FileHash",
]:
    assert token in runner, token

workflow_patch=(ROOT/"patch-c1020-workflow-conformance.ps1").read_text(encoding="utf-8-sig")
for token in [
    "C1020RequestAuditExit(directory, 0)",
    "C1020RequestAuditExit(directory, 1)",
    "deferred_until_callback_unwinds",
    "Environment.ExitCode = exitCode",
    "BeginInvoke(new Action(() =>",
    "audit-exit-request.json",
]:
    assert token in workflow_patch, token
assert "                    Environment.Exit(0);" not in workflow_patch
assert "                    Environment.Exit(1);" not in workflow_patch
