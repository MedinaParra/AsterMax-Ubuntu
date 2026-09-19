#!/usr/bin/env python3
"""Static regression guard for C10.20.2 asynchronous Solve orchestration."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10202-async-solve-ui.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))

required=[
    "private async void RunAsterMaxNativeSolve()",
    "await Task.Run(() =>",
    "_asterMaxSolveInProgress",
    "_asterMaxSolveDuplicateRequestsRejected",
    "_asterMaxSolveUiHeartbeatCount",
    "SetAsterMaxSolveUiBusy(true)",
    "SetAsterMaxSolveUiBusy(false)",
    "bool uiBusySet=false;",
    "if(uiBusySet && !IsDisposed && !Disposing)",
    "C1020WaitForSolveCompletion(600)",
    'add("async_solve_ui"',
    'DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fffffff"',
    'Guid.NewGuid().ToString("N").Substring(0,8)',
]
for token in required:
    assert token in patch, token
assert contract["release"]=="C10.20.2"
assert "async_solve_ui" in contract["cross_cutting_checks"]
print("C10.20.2 ASYNC_SOLVE_REGRESSION_OK")
