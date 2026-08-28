from __future__ import annotations

import copy

import pytest

from astermax.fea.credibility_visualization import CredibilityVisualizationError
from astermax.fea.native_credibility import build_native_credibility_snapshot


def _payload() -> dict:
    source = "a" * 64
    section = "b" * 64
    witness = "c" * 64
    return {
        "schema": "AsterMaxC3_2CadDerivedAxialBenchmarkV1",
        "provenance": {
            "same_step_drives_meshing_and_analytical_reference": True,
            "source_sha256": source,
            "section_sha256": section,
        },
        "cad_analytical_witness": {
            "source_sha256": source,
            "section_sha256": section,
            "witness_sha256": witness,
            "area_mm2": 400.0,
            "analytical_sigma_mpa": 100.0,
        },
        "levels": [
            {"level": {"mesh_size_mm": 20.0, "rms_error_mpa": 0.20, "maximum_relative_error": 0.012}},
            {"level": {"mesh_size_mm": 14.0, "rms_error_mpa": 0.15, "maximum_relative_error": 0.010}},
            {"level": {"mesh_size_mm": 10.0, "rms_error_mpa": 0.10, "maximum_relative_error": 0.008}},
        ],
        "claims": {
            "cad_derived_reference": True,
            "stress_convergence_for_this_axial_fixture": True,
            "arbitrary_model_convergence": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        },
    }


def test_native_snapshot_preserves_exact_c4_provenance_and_claim_boundary() -> None:
    snapshot = build_native_credibility_snapshot(_payload())
    assert snapshot.step_sha256 == "a" * 64
    assert snapshot.section_sha256 == "b" * 64
    assert snapshot.witness_sha256 == "c" * 64
    assert snapshot.area_mm2 == pytest.approx(400.0)
    assert snapshot.analytical_sigma_mpa == pytest.approx(100.0)
    assert tuple(row.mesh_size_mm for row in snapshot.refinement_rows) == (20.0, 14.0, 10.0)
    assert tuple(row.rms_relative_error for row in snapshot.refinement_rows) == pytest.approx((0.002, 0.0015, 0.001))
    assert snapshot.fixture_convergence_claim is True
    assert snapshot.arbitrary_model_convergence is False
    assert snapshot.industrial_validation is False
    assert snapshot.ansys_equivalence is False
    assert len(snapshot.snapshot_sha256) == 64


def test_native_snapshot_is_deterministic() -> None:
    a = build_native_credibility_snapshot(_payload())
    b = build_native_credibility_snapshot(copy.deepcopy(_payload()))
    assert a.snapshot_sha256 == b.snapshot_sha256
    assert a.canonical_without_hash() == b.canonical_without_hash()


def test_native_snapshot_refuses_ansys_claim_upgrade() -> None:
    payload = _payload()
    payload["claims"]["ansys_equivalence"] = True
    with pytest.raises(CredibilityVisualizationError, match="ANSYS-equivalence"):
        build_native_credibility_snapshot(payload)


def test_native_snapshot_refuses_step_provenance_mismatch() -> None:
    payload = _payload()
    payload["cad_analytical_witness"]["source_sha256"] = "d" * 64
    with pytest.raises(CredibilityVisualizationError, match="STEP SHA mismatch"):
        build_native_credibility_snapshot(payload)


def test_native_snapshot_refuses_non_monotonic_refinement() -> None:
    payload = _payload()
    payload["levels"][1]["level"]["mesh_size_mm"] = 25.0
    with pytest.raises(CredibilityVisualizationError, match="coarse to fine"):
        build_native_credibility_snapshot(payload)
