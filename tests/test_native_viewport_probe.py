from __future__ import annotations

import numpy as np
import pytest

from astermax.native_viewport import extract_tet10_boundary
from astermax.native_viewport_probe import nearest_projected_face, probe_surface_face
from astermax.native_vtu_preview import NativeVtuPreviewData


def _data() -> NativeVtuPreviewData:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 0.5, 0.0],
            [0.0, 0.0, 0.5],
            [0.0, 0.5, 0.5],
            [0.5, 0.0, 0.5],
        ],
        dtype=float,
    )
    u = np.zeros_like(points)
    u[5] = [0.3, 0.4, 0.0]
    return NativeVtuPreviewData(
        schema="AsterMaxNativeVtuPreviewV1",
        points_mm=points,
        displacement_mm=u,
        tet10_connectivity=np.arange(10, dtype=np.int64)[None, :],
        von_mises_ip_max_mpa=np.asarray([123.456]),
        source_sha256="0" * 64,
        converged_claim=False,
        industrial_validation_claim=False,
        stress_is_nodal=False,
    )


def test_probe_preserves_owner_ip_max_and_exact_nodal_displacement() -> None:
    data = _data()
    surface = extract_tet10_boundary(data)
    face_index = next(i for i, f in enumerate(surface.tri6_connectivity) if 5 in f)
    probe = probe_surface_face(data, surface, face_index)
    assert probe.owner_cell_index == 0
    assert probe.owner_von_mises_ip_max_mpa == pytest.approx(123.456)
    assert probe.maximum_face_displacement_node == 5
    assert probe.maximum_face_displacement_mm == pytest.approx(0.5)
    assert probe.maximum_face_displacement_vector_mm == pytest.approx((0.3, 0.4, 0.0))
    assert "NOT_NODAL_STRESS" in probe.evidence_boundary
    assert "EXACT_VTU_NODAL_DATA" in probe.evidence_boundary


def test_probe_rejects_invalid_face_index() -> None:
    data = _data()
    surface = extract_tet10_boundary(data)
    with pytest.raises(IndexError):
        probe_surface_face(data, surface, 999)


def test_nearest_projected_face_is_deterministic_and_tolerance_bounded() -> None:
    data = _data()
    surface = extract_tet10_boundary(data)
    xy = data.points_mm[:, :2] * 100.0
    centroids = xy[surface.tri6_connectivity[:, :3]].mean(axis=1)
    expected = 0
    x, y = centroids[expected]
    assert nearest_projected_face(xy, surface, x, y, maximum_distance_pixels=1.0) == expected
    assert nearest_projected_face(xy, surface, 10000.0, 10000.0, maximum_distance_pixels=10.0) is None


def test_probe_does_not_create_nodal_stress_field() -> None:
    data = _data()
    surface = extract_tet10_boundary(data)
    probe = probe_surface_face(data, surface, 0)
    assert not hasattr(probe, "nodal_von_mises_mpa")
