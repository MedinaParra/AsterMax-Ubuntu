#!/usr/bin/env python3
"""Static guard for C10.20.4 result lifecycle. No solver/result data is synthesized."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10204-result-lifecycle.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))
required=[
    "_asterMaxPreviousResultsRetained",
    "Previous solution - new solve running",
    "Previous successful solution retained",
    "previousResults=_asterMaxLoadedResults",
    "_asterMaxPreviousResultsRetained=previousResults!=null",
    "_asterMaxPreviousResultsRetained=false",
    "RefreshAsterMaxResultAvailability();",
]
for token in required:
    assert token in patch, token
assert 'text += "\\r\\nBundle: "' in patch
assert 'text += "\\r\\nStatus: previous successful result retained' in patch
assert 'text += "\nBundle: "' not in patch
print("C10.20.4 RESULT_LIFECYCLE_REGRESSION_OK")
