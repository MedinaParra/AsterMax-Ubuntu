#!/usr/bin/env python3
"""Static guard for verified AsterMax result persistence across PMX save/reopen."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10220-result-persistence.ps1").read_text(encoding="utf-8-sig")
manifest=json.loads((ROOT/"patch-chain.json").read_text(encoding="utf-8-sig"))

required=[
    "_asterMaxEmbeddedResultsJson",
    "CaptureAsterMaxResultsForPmx",
    "RestoreAsterMaxResultsFromPmx",
    "SerializedJson",
    "LoadEmbedded",
    "RequireCurrentModel",
    "C10230ExerciseResultPmxReopen",
    "pmx-result-reopen.json",
    "AuditAsterMaxContextMenus",
    "context_menu_lifecycle_checks_after_reopen",
]
for token in required:
    assert token in patch, token

entry=[x for x in manifest["patches"] if x["id"]=="patch-c10220-result-persistence"]
assert len(entry)==1
assert entry[0]["depends"]==["patch-c10219-load-history"]
assert "CaptureAsterMaxResultsForPmx" in entry[0]["declares"]
assert "RestoreAsterMaxResultsFromPmx" in entry[0]["declares"]

# Stale results must not be embedded or restored without fingerprint validation.
capture=patch.split("internal string CaptureAsterMaxResultsForPmx()",1)[1].split("internal void RestoreAsterMaxResultsFromPmx",1)[0]
assert "RequireCurrentModel" in capture
restore=patch.split("internal void RestoreAsterMaxResultsFromPmx",1)[1].split("$openMethod",1)[0]
assert "candidate.RequireCurrentModel" in restore
assert "_asterMaxLoadedResults = null" in restore

print("C10.30 RESULT_PERSISTENCE_STATIC_GUARD_OK")
