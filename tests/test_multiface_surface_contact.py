from __future__ import annotations

import numpy as np
import pytest

from astermax.contact import (
    RigidTri6TargetFace,
    Tri6SourceFace,
    find_tri6_surface_pairs,
    solve_tet10_multiface_surface_contact,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
LOCAL_FACE = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
LOCAL_SUPPORT = np.asarray([3, 7, 8, 9], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)


def build_two_body_fixture() -> tuple[np.ndarray, np.ndarray, list[Tri6SourceFace], np.ndarray]:
    vertices = np.asarray(
        [
            [-5.0, -5.0, 10.0],
            [0.0, 5.0, 10.0],
            [5.0, -5.0, 10.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    first = straight_sided_tet10_from_vertices(vertices)
    second = first + np.asarray([20.0, 0.0, 0.0])
    nodes = np.vstack([first, second])
    elements = np.vstack([np.arange(10, dtype=int), np.arange(10, 20, dtype=int)])
    sources = [
        Tri6SourceFace("SOURCE_A", LOCAL_FACE.copy(), NORMAL.copy()),
        Tri6SourceFace("SOURCE_B", LOCAL_FACE.copy() + 10, NORMAL.copy()),
    ]
    support_nodes = np.concatenate([LOCAL_SUPPORT, LOCAL_SUPPORT + 10])
    fixed = np.asarray(
        [3 * int(node) + component for node in support_nodes for component in range(3)],
        dtype=int,
    )
    return nodes, elements, sources, fixed


def target_from_source(
    nodes: np.ndarray,
    source_nodes: np.ndarray,
    *,
    gap_mm: float,
    face_id: str,
    xy_shift: tuple[float, float] = (0.0, 0.0),
    reverse_orientation: bool = False,
) -> RigidTri6TargetFace:
    source_xyz = nodes[source_nodes].copy()
    source_xyz[:, 0] += xy_shift[0]
    source_xyz[:, 1] += xy_shift[1]
    source_xyz[:, 2] += gap_mm
    # The fixture's original corner order has geometric normal -Z, which is
    # correctly opposed to the declared +Z closing direction. Reversing it is
    # used only for the explicit wrong-normal negative control.
    if reverse_orientation:
        order = np.asarray([0, 2, 1, 5, 4, 3], dtype=int)
        source_xyz = source_xyz[order]
    return RigidTri6TargetFace(face_id, source_xyz)


def test_geometric_search_pairs_each_source_to_its_nearest_target() -> None:
    nodes, _, sources, _ = build_two_body_fixture()
    targets = [
        target_from_source(nodes, sources[0].node_indices, gap_mm=0.0002, face_id="TARGET_A"),
        target_from_source(nodes, sources[1].node_indices, gap_mm=0.0008, face_id="TARGET_B"),
        target_from_source(
            nodes,
            sources[0].node_indices,
            gap_mm=0.0001,
            face_id="DECOY_OUTSIDE",
            xy_shift=(50.0, 0.0),
        ),
    ]
    records = find_tri6_surface_pairs(
        nodes_mm=nodes,
        source_faces=sources,
        target_faces=targets,
        max_search_distance_mm=0.01,
    )
    assert len(records) == 6
    assert [record.target_face_id for record in records[:3]] == ["TARGET_A"] * 3
    assert [record.target_face_id for record in records[3:]] == ["TARGET_B"] * 3
    assert np.allclose([record.initial_gap_mm for record in records[:3]], 0.0002, atol=1.0e-12)
    assert np.allclose([record.initial_gap_mm for record in records[3:]], 0.0008, atol=1.0e-12)
    assert all(np.all(record.target_barycentric >= -1.0e-12) for record in records)


def test_duplicate_equal_distance_target_fails_closed_as_ambiguous() -> None:
    nodes, _, sources, _ = build_two_body_fixture()
    target = target_from_source(nodes, sources[0].node_indices, gap_mm=0.0002, face_id="TARGET_A")
    duplicate = RigidTri6TargetFace("TARGET_A_DUPLICATE", target.nodes_mm.copy())
    with pytest.raises(ValueError, match="ambiguous target pairing"):
        find_tri6_surface_pairs(
            nodes_mm=nodes,
            source_faces=[sources[0]],
            target_faces=[target, duplicate],
            max_search_distance_mm=0.01,
        )


def test_same_orientation_target_is_not_admissible() -> None:
    nodes, _, sources, _ = build_two_body_fixture()
    wrong = target_from_source(
        nodes,
        sources[0].node_indices,
        gap_mm=0.0002,
        face_id="WRONG_NORMAL",
        reverse_orientation=True,
    )
    with pytest.raises(ValueError, match="no admissible target"):
        find_tri6_surface_pairs(
            nodes_mm=nodes,
            source_faces=[sources[0]],
            target_faces=[wrong],
            max_search_distance_mm=0.01,
        )


def test_multiface_contact_uses_one_global_primary_pressure_problem() -> None:
    nodes, elements, sources, fixed = build_two_body_fixture()
    targets = [
        target_from_source(nodes, sources[0].node_indices, gap_mm=0.0002, face_id="TARGET_A"),
        target_from_source(nodes, sources[1].node_indices, gap_mm=0.0008, face_id="TARGET_B"),
    ]
    loads = np.zeros(nodes.shape[0] * 3, dtype=float)
    for source in sources:
        loads += tri6_surface_pressure_generalized_force(
            nodes_mm=nodes,
            face_nodes=source.node_indices,
            contact_normal=source.contact_normal,
            pressure_mpa=np.full(3, 10.0),
        )
    result = solve_tet10_multiface_surface_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=fixed,
        source_faces=sources,
        target_faces=targets,
        max_search_distance_mm=0.01,
    )
    assert result.geometric_surface_search_executed is True
    assert result.multiple_source_faces_executed is True
    assert result.pressure_is_primary_contact_unknown is True
    assert result.contact_pressure_recovered_from_nodal_reactions is False
    assert result.target_surfaces_rigid is True
    assert result.pairing_frozen_small_displacement is True
    assert result.penalty_method_used is False
    assert result.active_contact_indices == (0, 2)
    assert [state.value for state in result.states] == ["ACTIVE", "OPEN", "ACTIVE", "OPEN", "OPEN", "OPEN"]
    assert np.all(result.contact_pressure_mpa >= 0.0)
    assert np.all(result.signed_gaps_mm >= -1.0e-10)
    assert np.allclose(result.complementarity_mpa_mm, 0.0, atol=1.0e-10)
    assert result.free_equilibrium_residual_norm_n <= 1.0e-6
