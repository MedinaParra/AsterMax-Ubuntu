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
    "PATCH_FAILURE.json",
    "Do not continue dependent patches",
]:
    assert token in h, token

assert "structural anchor missing: RunCaptured(ProcessStartInfo psi,string stem)" in p
assert "$capturedSignature=" in p\nassert "$capturedStart=$s.IndexOf" in p\nassert "$depth=0" in p\nassert "$capturedEnd=$i+1" in p\nassert "$capturedPattern=" not in p
assert "$capturedOld=@'" not in p
assert 'return RunTrackedProcess(psi,stem+"_STDOUT.log",stem+"_STDERR.log");' in p
assert "(?<![A-Za-z0-9_.-])" in v
assert "harness-c10208a-patch-chain.ps1" in w
assert "foreach($p in $patches)" not in w
print("C10.20.8a PATCH_ERROR_HARNESS_REGRESSION_OK")
