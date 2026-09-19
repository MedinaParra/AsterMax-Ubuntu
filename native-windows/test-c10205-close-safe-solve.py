#!/usr/bin/env python3
"""Static guard for C10.20.5 close-safe active Solve lifecycle. No FEA is generated."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10205-close-safe-solve.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))

required=[
    "_asterMaxCloseAfterSolveCancel",
    "FormClosing += AsterMaxFormClosingDuringSolve;",
    "private void AsterMaxFormClosingDuringSolve",
    "if(!_asterMaxSolveInProgress) return;",
    "e.Cancel=true;",
    "_asterMaxSolveTransaction.RequestCancel();",
    "bool closeAfterSolveCancel=_asterMaxCloseAfterSolveCancel;",
    "_asterMaxSolveInProgress=false;",
    "BeginInvoke(new Action(Close));",
]
for token in required:
    assert token in patch, token

# The second Close must occur only after the active worker's finally clears in-progress.
assert patch.index("_asterMaxSolveInProgress=false;") < patch.index("BeginInvoke(new Action(Close));")
assert contract["release"]=="C10.20.5"
print("C10.20.5 CLOSE_SAFE_SOLVE_REGRESSION_OK")
