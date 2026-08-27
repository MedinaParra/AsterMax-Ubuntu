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
REFERENCE_GAP_MM = 0.003
SLOPE_MM_PER_MM = 0.0005


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
    for record in records:
        expected_gap = REFERENCE_GAP_MM - SLOPE_MM_PER_MM * abs(record.source_point_mm[0])
        assert record.current_gap_mm == pytest.approx(expected_gap, abs=1.0e-12)
        assert record.current_gap_mm > 0.0
    return tuple(record.target_face_id for record in records)


def test_controlled_sliding_path_switches_deformable_master_without_pair_locking() -> None:
    path = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    signatures = [target_signature_at(x_mm) for x_mm in path]
    assert signatures[:3] == [("MASTER_A",) * 3] * 3
    assert signatures[3:] == [("MASTER_B",) * 3] * 3
    assert signatures[0] != signatures[-1]


def test_exact_crossing_fails_closed_as_ambiguous() -> None:
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
