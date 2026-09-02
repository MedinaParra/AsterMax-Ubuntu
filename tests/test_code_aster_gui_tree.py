from astermax.code_aster_capabilities import CapabilityStatus
from astermax.code_aster_gui_tree import ROOT_ID, build_code_aster_gui_tree, gui_tree_summary


def test_gui_tree_contains_all_registered_capabilities_and_variables():
    tree = build_code_aster_gui_tree()
    ids = {node.id for node in tree}
    assert ROOT_ID in ids
    assert "structural.linear_static_3d" in ids
    assert "structural.modal" in ids
    assert "structural.contact" in ids
    assert "thermal.steady" in ids
    assert "fracture.xfem" in ids
    assert "fatigue.structural" in ids
    assert "structural.linear_static_3d::material.E" in ids
    assert "structural.linear_static_3d::load.traction.fx" in ids


def test_schema_only_capability_is_visible_but_disabled():
    tree = {node.id: node for node in build_code_aster_gui_tree()}
    modal = tree["structural.modal"]
    assert modal.status is CapabilityStatus.SCHEMA_ONLY
    assert modal.enabled is False
    assert modal.roadmap_phase == "C13"
    child = tree["structural.modal::modal.n_modes"]
    assert child.enabled is False
    assert child.operator == "CALC_MODES"


def test_current_linear_static_contract_is_selectable_but_not_marked_verified():
    tree = {node.id: node for node in build_code_aster_gui_tree()}
    static = tree["structural.linear_static_3d"]
    assert static.enabled is True
    assert static.status is CapabilityStatus.IMPLEMENTED_UNVERIFIED
    traction = tree["structural.linear_static_3d::load.traction.fx"]
    assert traction.enabled is True
    assert traction.unit == "N/mm^2"
    assert traction.keyword == "FORCE_FACE/FX"


def test_tree_summary_exposes_implementation_gap_without_hiding_options():
    summary = gui_tree_summary()
    assert summary["capabilities"] >= 10
    assert summary["variables"] >= 20
    assert summary["enabled_capabilities"] >= 1
    assert summary["disabled_capabilities"] >= 1
    assert summary["enabled_capabilities"] + summary["disabled_capabilities"] == summary["capabilities"]
