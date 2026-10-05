#!/usr/bin/env python3
"""Regression guard for C10.20.1 nodal-load semantics. No FEA values are generated."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
bridge = (ROOT / "patch-c960-native-bridge.ps1").read_text(encoding="utf-8-sig")
exporter = (ROOT / "patch-c961-native-codeaster-export.ps1").read_text(encoding="utf-8-sig")
hotfix = (ROOT / "patch-c10201-cload-semantics.ps1").read_text(encoding="utf-8-sig")
audit = (ROOT / "AsterMaxWorkflowConformanceAudit.cs").read_text(encoding="utf-8-sig")
contract = json.loads((ROOT / "workflow-conformance" / "workflow-contract.json").read_text(encoding="utf-8-sig"))

assert '["fx_total_n"] = cload.F1' in bridge, "Historical bug anchor changed; review hotfix applicability."
assert '["fx_per_node_n"] = cload.F1' in hotfix
assert '"nodal_force_per_node"' in hotfix
assert 'PER_NODE_CLOAD' in hotfix
assert 'LEGACY_TOTAL_DISTRIBUTED' in hotfix
assert 'perNodeLoad ? GetDouble(load,"fx_per_node_n")' in hotfix
assert 'new CLoad("Axial_Force", "LOAD", RegionTypeEnum.NodeSetName, 2500' in hotfix
b01 = contract["reference"]["b01"]
assert b01["total_force_n"] == [10000.0, 0.0, 0.0]
assert b01["cload_per_node_n"] == [2500.0, 0.0, 0.0]
assert 4 * b01["cload_per_node_n"][0] == b01["total_force_n"][0]
assert "cload_semantics" in contract["cross_cutting_checks"]
workflow_states = (ROOT / "AsterMaxWorkflowStates.cs").read_text(encoding="utf-8-sig")
assert 'ValidAsterMaxLoadGroups(contract)' in workflow_states
assert '"nodal_force_per_node"' in workflow_states
assert '"_per_node_n"' in workflow_states
print("C10.20.1 CLOAD_SEMANTICS_REGRESSION_OK")
