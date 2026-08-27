from __future__ import annotations

import numpy as np
import pytest

from astermax.contact import (
    DeformableTri6TargetFace,
    Tri6SourceFace,
    find_deformable_tri6_surface_pairs,
    solve_tet10_deformable_surface_contact,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


SOURCE_FACE_LOCAL = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
TARGET_FACE_LOCAL = np.asarray([0, 2, 1, 6, 5, 4], dtype=int)
SUPPORT_LOCAL = np.asarray([3, 7, 8, 9], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)
REFERENCE_GAP_MM = 0.0003
SLOPE_MM_PER_MM = 0.00005
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)


def build_switch_fixture():
    source_vertices = np.vstack(
        [
            np.asarray([-1.0, -2.0, 0.0]),
            np.asarray([0.0, 2.0, 0.0]),
            np.asarray([1.0, -2.0, 0.0]),
            np.asarray([0.0, 0.0, -5.0]),
        ]
    )
    source_nodes = straight_sided_tet10_from_vertices(source_vertices)

    # Both masters cover the complete prescribed path. Their shallow, opposed
    # slopes cross at x=0, so tangential source motion changes the nearest
    # admissible master without relying on an out-of-domain candidate.
    xy = (
        np.asarray([-8.0, -5.0]),
        np.asarray([0.0, 8.0]),
        np.asarray([8.0, -5.0]),
    )

    def contact_point(point_xy: np.ndarray, slope: float) -> np.ndarray:
        x, y = point_xy
        return np.asarray([x, y, REFERENCE_GAP_MM + slope * x], dtype=float)

    a0, b0, c0 = xy
    master_a_a = contact_point(a0, +SLOPE_MM_PER_MM)
    master_a_b = contact_point(b0, +SLOPE_MM_PER_MM)
    master_a_c = contact_point(c0, +SLOPE_MM_PER_MM)
    master_a_vertices = np.vstack(
        [
            master_a_a,
            master_a_c,
            master_a_b,
            np.asarray([0.0, 0.0, 5.0 + REFERENCE_GAP_MM]),
        ]
    )
    master_a_nodes = straight_sided_tet10_from_vertices(master_a_vertices)

    master_b_a = contact_point(a0, -SLOPE_MM_PER_MM)
    master_b_b = contact_point(b0, -SLOPE_MM_PER_MM)
    master_b_c = contact_point(c0, -SLOPE_MM_PER_MM)
    master_b_vertices = np.vstack(
        [
            master_b_a,
            master_b_c,
            master_b_b,
            np.asarray([0.0, 0.0, 5.0 + REFERENCE_GAP_MM]),
        ]
    )
    master_b_nodes = straight_sided_tet10_from_vertices(master_b_vertices)

    nodes = np.vstack([source_nodes, master_a_nodes, master_b_nodes])
    elements = np.vstack(
        [
            np.arange(0, 10, dtype=int),
            np.arange(10, 20, dtype=int),
            np.arange(20, 30, dtype=int),
        ]
    )
    source = Tri6SourceFace("SOURCE", SOURCE_FACE_LOCAL.copy(), NORMAL.copy())
    master_a = DeformableTri6TargetFace("MASTER_A", TARGET_FACE_LOCAL.copy() + 10)
    master_b = DeformableTri6TargetFace("MASTER_B", TARGET_FACE_LOCAL.copy() + 20)
    support_nodes = np.concatenate(
        [SUPPORT_LOCAL, SUPPORT_LOCAL + 10, SUPPORT_LOCAL + 20]
    )
    fixed = np.asarray(
        [3 * int(node) + component for node in support_nodes for component in range(3)],
        dtype=int,
    )
    return nodes, elements, source, (master_a, master_b), fixed


def source_translation(nodes: np.ndarray, x_mm: float) -> np.ndarray:
    displacement = np.zeros_like(nodes)
    displacement[:10, 0] = float(x_mm)
    return displacement


def target_signature_at(x_mm: float) -> tuple[str, ...]:
    nodes, _, source, targets, _ = build_switch_fixture()
    records = find_deformable_tri6_surface_pairs(
        nodes_mm=nodes,
        displacement_mm=source_translation(nodes, x_mm),
        source_faces=[source],
        target_faces=targets,
        max_tracking_distance_mm=0.01,
    )
    assert len(records) == 3
    assert max(record.newton_residual_mm for record in records) <= 1.0e-11
    for record in records:
        expected_gap = REFERENCE_GAP_MM - SLOPE_MM_PER_MM * abs(record.source_point_mm[0])
        assert record.current_gap_mm == pytest.approx(expected_gap, abs=1.0e-12)
        assert record.current_gap_mm > 0.0
    return tuple(record.target_face_id for record in records)


def endpoint_contact_result(x_mm: float, expected_master: str):
    nodes, elements, source, targets, fixed = build_switch_fixture()
    endpoint_nodes = nodes + source_translation(nodes, x_mm)
    loads = tri6_surface_pressure_generalized_force(
        nodes_mm=endpoint_nodes,
        face_nodes=source.node_indices,
        contact_normal=NORMAL,
        pressure_mpa=np.full(3, 20.0),
    )
    result = solve_tet10_deformable_surface_contact(
        nodes_mm=endpoint_nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=fixed,
        source_faces=[source],
        target_faces=targets,
        max_tracking_distance_mm=0.01,
    )
    assert result.converged is True
    assert tuple(record.target_face_id for record in result.pairing_records) == (
        expected_master,
    ) * 3
    assert np.all(result.contact_pressure_mpa >= 0.0)
    assert np.any(result.contact_pressure_mpa > 0.0)
    assert np.all(result.signed_gaps_mm >= -1.0e-10)
    assert np.allclose(result.complementarity_mpa_mm, 0.0, atol=1.0e-10)
    assert np.linalg.norm(result.net_contact_resultant_n) <= 1.0e-8
    assert result.free_equilibrium_residual_norm_n <= 1.0e-6
    assert result.pressure_is_primary_contact_unknown is True
    assert result.contact_pressure_recovered_from_nodal_reactions is False
    assert result.equal_and_opposite_contact_traction is True
    assert result.penalty_method_used is False
    assert result.friction_solved is False
    assert result.large_sliding_claimed is False
    assert result.finite_strain_claimed is False
    assert result.industrial_validation_claimed is False
    assert result.ot1613_result_claimed is False
    assert result.ansys_equivalence_claimed is False
    assert result.integration_point_von_mises_mpa.shape == (3, 4)
    assert float(np.max(result.integration_point_von_mises_mpa[0])) > 0.0
    selected_index = 1 if expected_master == "MASTER_A" else 2
    assert float(np.max(result.integration_point_von_mises_mpa[selected_index])) > 0.0
    return result


def test_controlled_sliding_path_switches_deformable_master_without_pair_locking() -> None:
    path = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    signatures = [target_signature_at(x_mm) for x_mm in path]
    assert signatures[:3] == [("MASTER_A",) * 3] * 3
    assert signatures[3:] == [("MASTER_B",) * 3] * 3
    assert signatures[0] != signatures[-1]


def test_exact_crossing_fails_closed_as_ambiguous() -> None:
    nodes, _, source, targets, _ = build_switch_fixture()
    with pytest.raises(ValueError, match="ambiguous deformable target pairing"):
        find_deformable_tri6_surface_pairs(
            nodes_mm=nodes,
            displacement_mm=source_translation(nodes, 0.0),
            source_faces=[source],
            target_faces=targets,
            max_tracking_distance_mm=0.01,
        )


def test_switch_is_recomputed_from_current_geometry_not_previous_signature() -> None:
    assert target_signature_at(-2.0) == ("MASTER_A",) * 3
    assert target_signature_at(2.0) == ("MASTER_B",) * 3
    assert target_signature_at(-2.0) == ("MASTER_A",) * 3


def test_primary_pressure_contact_is_valid_on_both_switch_endpoints() -> None:
    left = endpoint_contact_result(-2.0, "MASTER_A")
    right = endpoint_contact_result(2.0, "MASTER_B")
    assert left.active_contact_indices
    assert right.active_contact_indices
    assert left.pairing_target_history[-1] == ("MASTER_A",) * 3
    assert right.pairing_target_history[-1] == ("MASTER_B",) * 3
