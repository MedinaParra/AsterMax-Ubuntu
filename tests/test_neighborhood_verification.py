from __future__ import annotations

import numpy as np
import pytest

from astermax.credibility import EvidenceSource, EvidenceStatus
from astermax.fea.neighborhood_verification import (
    NeighborhoodVerificationError,
    NeighborhoodVerificationPolicy,
    neighborhood_verification_evidence,
    tet10_integration_point_positions,
    verify_scalar_stress_neighborhood,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices, tet10_integration_point_results
from astermax.fea.tet4 import IsotropicMaterial


def _unit_tet10() -> np.ndarray:
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 100.0],
        ],
        dtype=float,
    )
    return straight_sided_tet10_from_vertices(vertices)


def _uniaxial_affine_solution(target_sigma_mpa: float = 100.0):
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    coords = _unit_tet10()
    strain_x = target_sigma_mpa / material.young_modulus_mpa
    displacement = np.column_stack(
        [
            strain_x * coords[:, 0],
            -material.poisson_ratio * strain_x * coords[:, 1],
            -material.poisson_ratio * strain_x * coords[:, 2],
        ]
    )
    points = tet10_integration_point_results(coords, displacement, material)
    stresses = np.asarray([point.stress_mpa for point in points], dtype=float)[None, :, :]
    nodes = coords.copy()
    elements = np.arange(10, dtype=np.int64)[None, :]
    return nodes, elements, stresses


def test_affine_uniaxial_patch_matches_analytical_sigma_xx_at_all_ips() -> None:
    nodes, elements, stresses = _uniaxial_affine_solution(100.0)
    positions = tet10_integration_point_positions(nodes, elements)
    report = verify_scalar_stress_neighborhood(
        positions,
        stresses[:, :, 0],
        100.0,
        policy=NeighborhoodVerificationPolicy(lower_fraction=0.0, upper_fraction=1.0, relative_error_limit=1.0e-10),
    )
    assert report.status == "PASS"
    assert report.sample_count_total == 4
    assert report.sample_count_in_neighborhood == 4
    assert report.mean_fea_mpa == pytest.approx(100.0, abs=1.0e-9)
    assert report.rms_error_mpa < 1.0e-9
    assert report.maximum_relative_error < 1.0e-10
    assert report.stress_representation == "TET10_INTEGRATION_POINT_STRESS_NO_NODAL_SMOOTHING"
    assert "NOT_SINGULAR_PEAK" in report.evidence_boundary


def test_neighborhood_gate_fails_when_one_interior_ip_is_materially_wrong() -> None:
    nodes, elements, stresses = _uniaxial_affine_solution(100.0)
    positions = tet10_integration_point_positions(nodes, elements)
    corrupted = stresses[:, :, 0].copy()
    corrupted[0, 1] = 125.0
    report = verify_scalar_stress_neighborhood(
        positions,
        corrupted,
        100.0,
        policy=NeighborhoodVerificationPolicy(lower_fraction=0.0, upper_fraction=1.0, relative_error_limit=0.05),
    )
    assert report.status == "FAIL"
    assert report.maximum_absolute_error_mpa == pytest.approx(25.0)
    assert report.maximum_relative_error == pytest.approx(0.25)
    evidence = neighborhood_verification_evidence(report)
    assert evidence.status is EvidenceStatus.CONTRADICTED
    assert evidence.source is EvidenceSource.DETERMINISTIC_CHECK
    assert evidence.metadata["singular_peak_used"] is False
    assert evidence.metadata["ansys_equivalence"] is False
    assert evidence.metadata["industrial_validation"] is False


def test_window_excludes_end_regions_by_declared_axis_fraction() -> None:
    positions = np.asarray(
        [
            [
                [0.0, 0.0, 0.0],
                [25.0, 0.0, 0.0],
                [75.0, 0.0, 0.0],
                [100.0, 0.0, 0.0],
            ]
        ],
        dtype=float,
    )
    values = np.asarray([[500.0, 100.0, 100.0, 500.0]], dtype=float)
    report = verify_scalar_stress_neighborhood(
        positions,
        values,
        100.0,
        policy=NeighborhoodVerificationPolicy(axis=0, lower_fraction=0.2, upper_fraction=0.8, relative_error_limit=0.01),
    )
    assert report.status == "PASS"
    assert report.sample_count_total == 4
    assert report.sample_count_in_neighborhood == 2
    assert report.mean_fea_mpa == pytest.approx(100.0)


def test_report_hash_is_deterministic_and_evidence_is_claim_bounded() -> None:
    nodes, elements, stresses = _uniaxial_affine_solution(80.0)
    positions = tet10_integration_point_positions(nodes, elements)
    policy = NeighborhoodVerificationPolicy(lower_fraction=0.0, upper_fraction=1.0, relative_error_limit=1.0e-9)
    a = verify_scalar_stress_neighborhood(positions, stresses[:, :, 0], 80.0, policy=policy)
    b = verify_scalar_stress_neighborhood(positions, stresses[:, :, 0], 80.0, policy=policy)
    assert a.report_sha256 == b.report_sha256
    evidence = neighborhood_verification_evidence(a)
    assert evidence.status is EvidenceStatus.VERIFIED
    assert evidence.source is EvidenceSource.DETERMINISTIC_CHECK
    assert evidence.metadata["stress_representation"] == "TET10_INTEGRATION_POINT_STRESS_NO_NODAL_SMOOTHING"
    assert evidence.metadata["ansys_equivalence"] is False
    assert evidence.metadata["industrial_validation"] is False


def test_invalid_policy_and_empty_sample_set_fail_closed() -> None:
    with pytest.raises(NeighborhoodVerificationError):
        NeighborhoodVerificationPolicy(lower_fraction=0.9, upper_fraction=0.1).validate()
    with pytest.raises(NeighborhoodVerificationError, match="at least one integration-point sample"):
        verify_scalar_stress_neighborhood(
            np.empty((0, 4, 3), dtype=float),
            np.empty((0, 4), dtype=float),
            100.0,
        )
