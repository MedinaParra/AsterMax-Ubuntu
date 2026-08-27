from __future__ import annotations

import numpy as np
import pytest

from astermax.contact import (
    DeformableTri6TargetFace,
    Tri6SourceFace,
    find_deformable_tri6_surface_pairs,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices


SOURCE_FACE_LOCAL = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
TARGET_FACE_LOCAL = np.asarray([0, 2, 1, 6, 5, 4], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)


def build_switch_fixture(gap_mm: float = 0.0003):
    source_vertices = np.vstack(
        [
            np.asarray([-1.0, -2.0, 0.0]),
            np.asarray([0.0, 2.0, 0.0]),
            np.asarray([1.0, -2.0, 0.0]),
            np.asarray([0.0, 0.0, -5.0]),
        ]
    )
    source_nodes = straight_sided_tet10_from_vertices(source_vertices)

    master_a_a = np.asarray([-8.0, -5.0, gap_mm])
    master_a_b = np.asarray([0.0, 5.0, gap_mm])
    master_a_c = np.asarray([0.0, -5.0, gap_mm])
    master_a_vertices = np.vstack(
        [
            master_a_a,
            master_a_c,
            master_a_b,
            np.asarray([-2.0, 0.0, 5.0 + gap_mm]),
        ]
    )
    master_a_nodes = straight_sided_tet10_from_vertices(master_a_vertices)

    master_b_a = np.asarray([0.0, -5.0, gap_mm])
    master_b_b = np.asarray([0.0, 5.0, gap_mm])
    master_b_c = np.asarray([8.0, -5.0, gap_mm])
    master_b_vertices = np.vstack(
        [
            master_b_a,
            master_b_c,
            master_b_b,
            np.asarray([2.0, 0.0, 5.0 + gap_mm]),
        ]
    )
    master_b_nodes = straight_sided_tet10_from_vertices(master_b_vertices)

    nodes = np.vstack([source_nodes, master_a_nodes, master_b_nodes])
    source = Tri6SourceFace("SOURCE", SOURCE_FACE_LOCAL.copy(), NORMAL.copy())
    master_a = DeformableTri6TargetFace("MASTER_A", TARGET_FACE_LOCAL.copy() + 10)
    master_b = DeformableTri6TargetFace("MASTER_B", TARGET_FACE_LOCAL.copy() + 20)
    return nodes, source, (master_a, master_b)


def source_translation(nodes: np.ndarray, x_mm: float) -> np.ndarray:
    displacement = np.zeros_like(nodes)
    displacement[:10, 0] = float(x_mm)
    return displacement


def target_signature_at(x_mm: float) -> tuple[str, ...]:
    nodes, source, targets = build_switch_fixture()
    records = find_deformable_tri6_surface_pairs(
        nodes_mm=nodes,
        displacement_mm=source_translation(nodes, x_mm),
        source_faces=[source],
        target_faces=targets,
        max_tracking_distance_mm=0.01,
    )
    assert len(records) == 3
    assert max(record.newton_residual_mm for record in records) <= 1.0e-11
    assert np.allclose(
        [record.current_gap_mm for record in records],
        np.full(3, 0.0003),
        rtol=0.0,
        atol=1.0e-12,
    )
    return tuple(record.target_face_id for record in records)


def test_controlled_sliding_path_switches_deformable_master_without_pair_locking() -> None:
    path = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    signatures = [target_signature_at(x_mm) for x_mm in path]
    assert signatures[:3] == [("MASTER_A",) * 3] * 3
    assert signatures[3:] == [("MASTER_B",) * 3] * 3
    assert signatures[0] != signatures[-1]


def test_exact_shared_edge_fails_closed_as_ambiguous() -> None:
    nodes, source, targets = build_switch_fixture()
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
