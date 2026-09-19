#!/usr/bin/env python3
"""Static guard for C10.20.8 functional command smoke. No FEA values are synthesized."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
patch=(ROOT/"patch-c10208-functional-command-smoke.ps1").read_text(encoding="utf-8-sig")
contract=json.loads((ROOT/"workflow-conformance"/"workflow-contract.json").read_text(encoding="utf-8-sig"))

required=[
    'C10208SmokeEditorCommand("Model", "Materials"',
    'C10208SmokeEditorCommand("Mesh", "Mesh Controls"',
    'C10208ExerciseRealGenerateMesh(model)',
    'C10208SmokeEditorCommand("Materiales", "Asignar seccion"',
    'C10208SmokeEditorCommand("Environment", "Analysis Step"',
    'C10208SmokeEditorCommand("Environment", "Supports"',
    'C10208SmokeEditorCommand("Environment", "Loads"',
    'C10208SmokeResultCommand("Results", command)',
    'C10208SmokeResultCommand("View", command)',
    '["execution"]="REAL_NATIVE_CREATE_MESH_COMMAND"',
    'command-execution-smoke.json',
    'add("command_execution_smoke"',
    'C10.20.2',
    'C10.20.8',
    'if(!_asterMaxUiAuditMode) MessageBoxes.ShowError("Errors occurred during meshing.',
]
for token in required:
    assert token in patch, token

marker="$meshNew=@'\n"
assert marker in patch, "meshNew block missing"
mesh_new=patch.split(marker,1)[1].split("\n'@",1)[0]
assert mesh_new.index("C10208ExerciseRealGenerateMesh(model)") < mesh_new.index("C1020PopulateB01Mesh(model);")
assert "commands.Count>=11" in patch

assert "command_execution_smoke" in contract["cross_cutting_checks"]
assert contract["release"]=="C10.20.8"
print("C10.20.8 FUNCTIONAL_COMMAND_SMOKE_REGRESSION_OK")
