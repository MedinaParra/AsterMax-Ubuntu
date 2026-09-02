from dataclasses import replace

import pytest

from astermax.code_aster_capabilities import (
    CAPABILITIES,
    CapabilityStatus,
    capability_by_id,
    iter_gui_tree,
    validate_registry,
)


def test_registry_has_unique_capabilities_and_valid_mappings():
    validate_registry()
    assert len(CAPABILITIES) >= 10
    assert len({item.id for item in CAPABILITIES}) == len(CAPABILITIES)
    for capability in CAPABILITIES:
        assert capability.operators
        for variable in capability.variables:
            assert variable.operator
            assert variable.keyword
            assert variable.ui_path


def test_linear_static_is_implemented_but_not_solver_verified():
    capability = capability_by_id("structural.linear_static_3d")
    assert capability.status is CapabilityStatus.IMPLEMENTED_UNVERIFIED
    assert capability.gui_selectable is True
    assert capability.solver_claim_allowed is False
    assert "MECA_STATIQUE" in capability.operators
    ids = {variable.id for variable in capability.variables}
    assert {"material.E", "material.nu", "load.traction.fx"}.issubset(ids)


def test_future_capabilities_are_visible_but_not_selectable():
    tree = {capability_id: (status, selectable) for capability_id, _path, status, selectable, _phase in iter_gui_tree()}
    for capability_id in (
        "structural.modal",
        "structural.buckling",
        "structural.nonlinear_static",
        "structural.contact",
        "dynamic.transient",
        "thermal.steady",
        "fracture.xfem",
        "fatigue.structural",
    ):
        status, selectable = tree[capability_id]
        assert status is CapabilityStatus.SCHEMA_ONLY
        assert selectable is False


def test_verified_status_without_verification_gate_fails_closed():
    base = capability_by_id("structural.modal")
    bad = replace(base, status=CapabilityStatus.VERIFIED, verification_gate="")
    with pytest.raises(ValueError, match="VERIFIED_CAPABILITY_WITHOUT_GATE"):
        validate_registry((bad,))


def test_duplicate_capability_id_fails_closed():
    base = capability_by_id("structural.modal")
    with pytest.raises(ValueError, match="CAPABILITY_ID_NOT_UNIQUE"):
        validate_registry((base, base))


def test_variable_contract_preserves_engineering_metadata():
    static = capability_by_id("structural.linear_static_3d")
    e = next(variable for variable in static.variables if variable.id == "material.E")
    assert e.unit == "MPa"
    assert e.operator == "DEFI_MATERIAU"
    assert e.keyword == "ELAS/E"
    assert "E > 0" in e.constraints
    assert e.verification_case == "uniaxial_prism"

    traction = next(variable for variable in static.variables if variable.id == "load.traction.fx")
    assert traction.unit == "N/mm^2"
    assert traction.operator == "AFFE_CHAR_MECA"
    assert traction.keyword == "FORCE_FACE/FX"
