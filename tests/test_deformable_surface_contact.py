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


MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
SOURCE_FACE = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
TARGET_FACE_LOCAL = np.asarray([0, 2, 1, 6, 5, 4], dtype=int)
TARGET_WRONG_LOCAL = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
SUPPORT_LOCAL = np.asarray([3, 7, 8, 9], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)


def build_deformable_pair_fixture(gap_mm: float = 0.0003):
    a = np.asarray([-5.0, -5.0, 0.0])
    b = np.asarray([0.0, 5.0, 0.0])
    c = np.asarray([5.0, -5.0, 0.0])
    source_vertices = np.vstack([a, b, c, np.asarray([0.0, 0.0, -10.0])])
    source_nodes = straight_sided_tet10_from_vertices(source_vertices)

    at = a + np.asarray([0.0, 0.0, gap_mm])
    bt = b + np.asarray([0.0, 0.0, gap_mm])
    ct = c + np.asarray([0.0, 0.0, gap_mm])
    # A,C,B gives the target volume a positive TET orientation with its apex
    # above the interface. The contact face is separately ordered A,B,C so its
    # geometric normal is -Z, opposed to the source closing direction +Z.
    target_vertices = np.vstack(
        [at, ct, bt, np.asarray([0.0, 0.0, 10.0 + gap_mm])]
    )
    target_nodes = straight_sided_tet10_from_vertices(target_vertices)

    nodes = np.vstack([source_nodes, target_nodes])
    elements = np.vstack([np.arange(10, dtype=int), np.arange(10, 20, dtype=int)])
    source = Tri6SourceFace("SOURCE", SOURCE_FACE.copy(), NORMAL.copy())
    target = DeformableTri6TargetFace("MASTER", TARGET_FACE_LOCAL.copy() + 10)
    support_nodes = np.concatenate([SUPPORT_LOCAL, SUPPORT_LOCAL + 10])
    fixed = np.asarray(
        [3 * int(node) + component for node in support_nodes for component in range(3)],
        dtype=int,
    )
    return nodes, elements, source, target, fixed


def driving_loads(nodes: np.ndarray, source: Tri6SourceFace, target: DeformableTri6TargetFace):
    loads = np.zeros(nodes.shape[0] * 3, dtype=float)
    loads += tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=source.node_indices,
        contact_normal=NORMAL,
        pressure_mpa=np.full(3, 10.0),
    )
    loads += tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=target.node_indices,
        contact_normal=-NORMAL,
        pressure_mpa=np.full(3, 10.0),
    )
    # A small tangential traction deliberately changes master barycentric
    # coordinates. Friction is not solved; this only exercises pair-map update.
    loads += tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=target.node_indices,
        contact_normal=np.asarray([1.0, 0.0, 0.0]),
        pressure_mpa=np.full(3, 0.5),
    )
    return loads


def test_deformable_search_updates_target_barycentrics_under_master_translation() -> None:
    nodes, _, source, target, _ = build_deformable_pair_fixture()
    zero = np.zeros_like(nodes)
    initial = find_deformable_tri6_surface_pairs(
        nodes_mm=nodes,
        displacement_mm=zero,
        source_faces=[source],
        target_faces=[target],
        max_tracking_distance_mm=1.0,
    )
    shifted = zero.copy()
    shifted[10:, 0] = 0.2
    moved = find_deformable_tri6_surface_pairs(
        nodes_mm=nodes,
        displacement_mm=shifted,
        source_faces=[source],
        target_faces=[target],
        max_tracking_distance_mm=1.0,
    )
    assert len(initial) == len(moved) == 3
    assert all(record.target_face_id == "MASTER" for record in moved)
    delta = np.max(
        np.abs(
            np.asarray([record.target_barycentric for record in moved])
            - np.asarray([record.target_barycentric for record in initial])
        )
    )
    assert delta > 1.0e-4
    assert max(record.newton_residual_mm for record in moved) <= 1.0e-11


def test_duplicate_deformable_target_fails_closed() -> None:
    nodes, _, source, target, _ = build_deformable_pair_fixture()
    duplicate = DeformableTri6TargetFace("MASTER_DUP", target.node_indices.copy())
    with pytest.raises(ValueError, match="ambiguous deformable target pairing"):
        find_deformable_tri6_surface_pairs(
            nodes_mm=nodes,
            displacement_mm=np.zeros_like(nodes),
            source_faces=[source],
            target_faces=[target, duplicate],
            max_tracking_distance_mm=1.0,
        )


def test_same_orientation_deformable_target_is_rejected() -> None:
    nodes, _, source, _, _ = build_deformable_pair_fixture()
    wrong = DeformableTri6TargetFace("WRONG", TARGET_WRONG_LOCAL.copy() + 10)
    with pytest.raises(ValueError, match="no admissible deformable target"):
        find_deformable_tri6_surface_pairs(
            nodes_mm=nodes,
            displacement_mm=np.zeros_like(nodes),
            source_faces=[source],
            target_faces=[wrong],
            max_tracking_distance_mm=1.0,
        )


def test_deformable_master_contact_is_equal_opposite_and_evidence_gated() -> None:
    nodes, elements, source, target, fixed = build_deformable_pair_fixture()
    result = solve_tet10_deformable_surface_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=driving_loads(nodes, source, target),
        fixed_dofs=fixed,
        source_faces=[source],
        target_faces=[target],
        max_tracking_distance_mm=0.02,
    )
    assert result.converged is True
    assert result.geometric_surface_search_executed is True
    assert result.target_surfaces_deformable is True
    assert result.equal_and_opposite_contact_traction is True
    assert result.pairing_updated_iteratively is True
    assert result.outer_iterations >= 2
    assert result.pressure_is_primary_contact_unknown is True
    assert result.contact_pressure_recovered_from_nodal_reactions is False
    assert result.penalty_method_used is False
    assert result.friction_solved is False
    assert result.large_sliding_claimed is False
    assert result.finite_strain_claimed is False
    assert result.industrial_validation_claimed is False
    assert result.ot1613_result_claimed is False
    assert result.ansys_equivalence_claimed is False
    assert np.all(result.contact_pressure_mpa >= 0.0)
    assert np.any(result.contact_pressure_mpa > 0.0)
    assert np.all(result.signed_gaps_mm >= -1.0e-10)
    assert np.allclose(result.complementarity_mpa_mm, 0.0, atol=1.0e-10)
    assert np.linalg.norm(result.net_contact_resultant_n) <= 1.0e-8
    assert result.free_equilibrium_residual_norm_n <= 1.0e-6
    assert result.max_geometric_gap_consistency_error_mm <= 1.0e-9
    assert result.max_pairing_barycentric_delta <= 1.0e-9
    assert result.integration_point_von_mises_mpa.shape == (2, 4)
    assert np.all(np.isfinite(result.integration_point_von_mises_mpa))
    assert float(np.max(result.integration_point_von_mises_mpa[0])) > 0.0
    assert float(np.max(result.integration_point_von_mises_mpa[1])) > 0.0
