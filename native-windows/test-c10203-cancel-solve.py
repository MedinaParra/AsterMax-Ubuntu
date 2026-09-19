#!/usr/bin/env python3
"""Static regression guard for C10.20.3 cancellation and pipe safety. No FEA is generated."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10203-cancel-solve.ps1").read_text(encoding="utf-8-sig")
legacy=(ROOT/"patch-c1001-automatic-results-handoff.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))

required=[
    "AsterMaxSolveState.Cancelled",
    "public void RequestCancel()",
    "Task.Run(() => TryTerminateProcessTree(active))",
    "TryTerminateProcessTree",
    'Arguments="/PID "+process.Id.ToString(CultureInfo.InvariantCulture)+" /T /F"',
    "RunTrackedProcess",
    "ReadToEndAsync()",
    "ThrowIfCancellationRequested()",
    "CancelAsterMaxNativeSolve()",
    'CommandTile("Cancel Solve"',
    'String.Equals(caption,"Cancel Solve",StringComparison.Ordinal)',
]
for token in required:
    assert token in patch, token
assert "string stdout=p.StandardOutput.ReadToEnd();" in legacy
assert 'return RunTrackedProcess(psi,stem+"_STDOUT.log",stem+"_STDERR.log");' in patch
assert contract["release"]=="C10.20.3"
print("C10.20.3 CANCEL_SOLVE_REGRESSION_OK")
