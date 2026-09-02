from __future__ import annotations

import pytest

from astermax.code_aster_capabilities import CapabilityStatus
from astermax.windows_capability_outline import (
    build_windows_outline_rows,
    capability_outline_evidence,
    populate_capability_outline,
    selection_contract,
)


class FakeTree:
    def __init__(self):
        self.rows = []
        self.tags = {}

    def insert(self, parent, index, *, iid, text, open=False, tags=()):
        self.rows.append({
            "parent": parent,
            "index": index,
            "iid": iid,
            "text": text,
            "open": open,
            "tags": tuple(tags),
        })

    def tag_configure(self, tagname, **kwargs):
        self.tags[tagname] = kwargs


def test_outline_exposes_registry_capabilities_without_enabling_schema_only():
    rows = build_windows_outline_rows()
    capabilities = [row for row in rows if row.node_type == "capability"]
    assert capabilities

    linear = next(row for row in capabilities if row.id == "structural.linear_static_3d")
    assert linear.enabled is True
    assert linear.status is CapabilityStatus.IMPLEMENTED_UNVERIFIED
    assert linear.label.startswith("● ")

    modal = next(row for row in capabilities if row.id == "structural.modal")
    assert modal.enabled is False
    assert modal.status is CapabilityStatus.SCHEMA_ONLY
    assert modal.label.startswith("○ ")
    assert "disabled" in modal.tags


def test_selection_contract_blocks_unverified_future_capability():
    modal = selection_contract("structural.modal")
    assert modal.enabled is False
    assert modal.action == "BLOCKED"
    assert "No solver support is implied" in modal.message
    assert modal.status_text == "Schema only"


def test_selection_contract_separates_gui_availability_from_numerical_verification():
    linear = selection_contract("structural.linear_static_3d")
    assert linear.enabled is True
    assert linear.action == "OPEN_ANALYSIS"
    assert linear.status_text == "Implemented · numerical verification pending"
    assert "Numerical verification remains separate" in linear.message


def test_variable_contract_preserves_operator_keyword_and_units():
    variable = selection_contract("structural.linear_static_3d::material.E")
    assert variable.action == "OPEN_PROPERTY"
    assert variable.operator_binding == "DEFI_MATERIAU/ELAS/E"
    assert variable.unit == "MPa"


def test_unknown_tree_node_fails_closed():
    with pytest.raises(KeyError):
        selection_contract("does.not.exist")


def test_fake_tree_population_has_semantic_disabled_tags_and_root():
    tree = FakeTree()
    rows = populate_capability_outline(tree)
    assert tree.rows[0]["iid"] == "code_aster"
    assert tree.rows[0]["text"] == "Code_Aster Capabilities"
    assert "disabled" in tree.tags
    modal = next(item for item in tree.rows if item["iid"] == "structural.modal")
    assert "disabled" in modal["tags"]
    assert rows


def test_evidence_never_claims_solver_or_ansys_equivalence():
    evidence = capability_outline_evidence()
    assert evidence["contract"] == "ASTERMAX_WINDOWS_CAPABILITY_OUTLINE_V1"
    assert evidence["capability_count"] > 1
    assert evidence["enabled_capabilities"] == ["structural.linear_static_3d"]
    assert evidence["verified_capabilities"] == []
    assert evidence["implemented_unverified_capabilities"] == ["structural.linear_static_3d"]
    assert evidence["fea_solve_executed"] is False
    assert evidence["numerical_verification"] is False
    assert evidence["results_verified"] is False
    assert evidence["industrial_validation"] is False
    assert evidence["ansys_equivalence"] is False
