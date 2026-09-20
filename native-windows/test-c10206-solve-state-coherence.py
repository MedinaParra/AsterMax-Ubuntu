#!/usr/bin/env python3
"""Static guard for C10.20.6 transaction-state coherence. No FEA is generated."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10206-solve-state-coherence.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))

required=[
    "_stateTransitionSync",
    "_stateFileSync",
    "_stateRevision",
    "State=AsterMaxSolveState.Cancelling;",
    'Message="CANCELLING: termination requested for the active native Solve.";',
    "private void TransitionOrCancel",
    "TransitionOrCancel(AsterMaxSolveState.Running",
    "TransitionOrCancel(AsterMaxSolveState.Postprocessing",
    "TransitionOrCancel(AsterMaxSolveState.SolutionCurrent",
    '["cancel_requested"]=_cancelRequested',
    '["state_revision"]=revision',
    "File.Replace(tempPath,finalPath,null)",
    "File.Move(tempPath,finalPath)",
    "Interlocked.Increment(ref _stateRevision)",
    "private void Fail(string message)",
    "throw new OperationCanceledException(Message)",
    'Fail("Code_Aster runner is not configured.',
    'Fail("Code_Aster solve failed (runner exit "',

]
for token in required:
    assert token in patch, token

print("C10.20.6 SOLVE_STATE_COHERENCE_REGRESSION_OK")
