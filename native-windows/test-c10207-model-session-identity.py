#!/usr/bin/env python3
"""Static guard for C10.20.7 model-session identity. No FEA is generated."""
from pathlib import Path
import json
import re

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

m=re.search(r"\\$publishNew=@'\\n(.*?)\\n'@",patch,re.S)
assert m, "publishNew block missing"
publish_new=m.group(1)
assert publish_new.index("_asterMaxSolveModelSessionPreserved=true;") < publish_new.index("_asterMaxLoadedResults=completedBundle;")
assert "Object.ReferenceEquals(_controller.Model,solveModel)" in publish_new
assert "_asterMaxModelSessionRevision!=_asterMaxSolveFrozenSessionRevision" in publish_new

assert "model_session_identity" in contract["cross_cutting_checks"]
print("C10.20.7 MODEL_SESSION_IDENTITY_REGRESSION_OK")
