from __future__ import annotations

import numpy as np
import pytest

from astermax.contact import (
    Tri6PressureRecoveryStatus,
    recover_consistent_tri6_pressure,
    tri6_consistent_pressure_matrix_mm2,
    tri6_pressure_value_mpa,
)


CORNERS_MM = np.asarray(
    [
        [-5.0, -5.0, 10.0],
        [0.0, 5.0, 10.0],
        [5.0, -5.0, 10.0],
    ],
    dtype=float,
)
GAP_E_REACTIONS_N = np.asarray(
    [
        263.51144959260034,
        0.0,
        176.54393932955918,
        86.74729325959316,
        264.5720198907532,
        0.0,
    ],
    dtype=float,
)


def test_exact_tri6_consistent_matrix_matches_known_closed_form() -> None:
    matrix = tri6_consistent_pressure_matrix_mm2(50.0)
    expected = (50.0 / 180.0) * np.asarray(
        [
            [6, -1, -1, 0, -4, 0],
            [-1, 6, -1, 0, 0, -4],
            [-1, -1, 6, -4, 0, 0],
            [0, 0, -4, 32, 16, 16],
            [-4, 0, 0, 16, 32, 16],
            [0, -4, 0, 16, 16, 32],
        ],
        dtype=float,
    )
    assert np.array_equal(matrix, expected)
    assert np.allclose(matrix, matrix.T)
    assert np.all(np.linalg.eigvalsh(matrix) > 0.0)


def test_uniform_compressive_pressure_is_recovered_and_authorized() -> None:
    matrix = tri6_consistent_pressure_matrix_mm2(50.0)
    uniform_pressure_mpa = 10.0
    reactions = matrix @ np.full(6, uniform_pressure_mpa)

    result = recover_consistent_tri6_pressure(
        corner_vertices_mm=CORNERS_MM,
        nodal_reactions_n=reactions,
    )

    assert result.status == Tri6PressureRecoveryStatus.VALID_CONSISTENT_COMPRESSIVE_PRESSURE
    assert result.contact_pressure_claim_authorized is True
    assert np.allclose(result.projected_nodal_pressure_mpa, uniform_pressure_mpa, atol=1.0e-12)
    assert result.minimum_pressure_mpa == pytest.approx(uniform_pressure_mpa, abs=1.0e-12)
    assert result.maximum_pressure_mpa == pytest.approx(uniform_pressure_mpa, abs=1.0e-12)
    assert result.nodal_reaction_resultant_n == pytest.approx(500.0, abs=1.0e-10)
    assert result.projected_pressure_resultant_n == pytest.approx(500.0, abs=1.0e-10)


def test_gap_e_nodal_reactions_reproduce_exactly_but_pressure_claim_is_blocked() -> None:
    result = recover_consistent_tri6_pressure(
        corner_vertices_mm=CORNERS_MM,
        nodal_reactions_n=GAP_E_REACTIONS_N,
    )

    assert result.status == Tri6PressureRecoveryStatus.BLOCKED_NEGATIVE_PRESSURE
    assert result.contact_pressure_claim_authorized is False
    assert result.nodal_contact_reactions_remain_valid is True
    assert result.max_reaction_reproduction_error_n <= 1.0e-10
    assert result.resultant_error_n <= 1.0e-10
    assert result.minimum_pressure_mpa < 0.0
    assert result.projected_nodal_pressure_mpa[5] == pytest.approx(-36.91571531, rel=1.0e-8)
    assert tri6_pressure_value_mpa(
        result.projected_nodal_pressure_mpa,
        np.asarray([0.5, 0.0, 0.5]),
    ) < 0.0
    assert result.industrial_validation_claimed is False
    assert result.ot1613_pressure_claimed is False
    assert result.ansys_equivalence_claimed is False


def test_zero_midside_generalized_reaction_is_a_pressure_provenance_warning() -> None:
    # N6 = 4*L3*L1 is non-negative over the whole triangle. An exactly zero
    # generalized force in this mode while other contact forces are positive is
    # therefore incompatible with an ordinary strictly-positive distributed
    # pressure over the interior region where N6 > 0. The consistent quadratic
    # projection exposes that incompatibility as a negative pressure region.
    result = recover_consistent_tri6_pressure(
        corner_vertices_mm=CORNERS_MM,
        nodal_reactions_n=GAP_E_REACTIONS_N,
    )
    assert GAP_E_REACTIONS_N[5] == 0.0
    assert np.sum(GAP_E_REACTIONS_N) > 0.0
    assert result.minimum_pressure_mpa < -1.0
    assert result.contact_pressure_claim_authorized is False


def test_degenerate_triangle_and_tensile_reaction_fail_closed() -> None:
    with pytest.raises(ValueError, match="positive triangle area"):
        recover_consistent_tri6_pressure(
            corner_vertices_mm=np.asarray([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float),
            nodal_reactions_n=np.ones(6),
        )
    bad = GAP_E_REACTIONS_N.copy()
    bad[0] = -1.0
    with pytest.raises(ValueError, match="non-negative"):
        recover_consistent_tri6_pressure(
            corner_vertices_mm=CORNERS_MM,
            nodal_reactions_n=bad,
        )
