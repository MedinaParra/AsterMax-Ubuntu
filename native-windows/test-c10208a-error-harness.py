#!/usr/bin/env python3
"""Static guard for the C10.20.8a patch-error harness. No solver values are generated."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
h=(ROOT/"harness-c10208a-patch-chain.ps1").read_text(encoding="utf-8-sig")
p=(ROOT/"patch-c10203-cancel-solve.ps1").read_text(encoding="utf-8-sig")

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
assert "$capturedPattern=" in p
assert "$capturedOld=@'" not in p
assert 'return RunTrackedProcess(psi,stem+"_STDOUT.log",stem+"_STDERR.log");' in p
print("C10.20.8a PATCH_ERROR_HARNESS_REGRESSION_OK")
