#!/usr/bin/env python3
"""Static guard for C10.20.7 model-session identity. No FEA is generated."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10207-model-session-identity.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))

required=[
    "_asterMaxModelSessionRevision",
    "Interlocked.Increment(ref _asterMaxModelSessionRevision)",
    "_asterMaxSolveFrozenModelInstance",
    "_asterMaxSolveFrozenSessionRevision",
    "_asterMaxSolveModelSessionPreserved",
    "Object.ReferenceEquals(_controller.Model,solveModel)",
    "_asterMaxModelSessionRevision!=_asterMaxSolveFrozenSessionRevision",
    "results were not published",
    'add("model_session_identity"',
    '"model-session-identity.json"',
]
for token in required:
    assert token in patch, token

assert "model_session_identity" in contract["cross_cutting_checks"]
assert contract["release"]=="C10.20.7"
print("C10.20.7 MODEL_SESSION_IDENTITY_REGRESSION_OK")
