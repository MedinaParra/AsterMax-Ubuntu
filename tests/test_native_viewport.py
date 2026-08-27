from __future__ import annotations

import numpy as np
import pytest

from astermax.native_viewport import (
    assert_native_viewport_claim_boundary,
    extract_tet10_boundary,
    orthographic_camera_projection,
    viewport_geometry,
)
from astermax.native_vtu_preview import NativeVtuPreviewData


def _data(*, two_cells: bool = False, stress_is_nodal: bool = False) -> NativeVtuPreviewData:
    points = np.zeros((14 if two_cells else 10, 3), dtype=float)
    points[:10] = np.asarray(
        [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [0.5, 0, 0], [0.5, 0.5, 0], [0, 0.5, 0],
            [0, 0, 0.5], [0, 0.5, 0.5], [0.5, 0, 0.5],
        ], dtype=float,
    )
    cells = [np.arange(10, dtype=np.int64)]
    vm = [12.0]
    if two_cells:
        points[10:] = np.asarray(
            [[0, 0, -1], [0, 0, -0.5], [0, 0.5, -0.5], [0.5, 0, -0.5]], dtype=float
        )
        # Shares full TRI6 face (0,1,2,4,5,6) with cell zero.
        cells.append(np.asarray([0, 1, 2, 10, 4, 5, 6, 11, 12, 13], dtype=np.int64))
        vm.append(30.0)
    disp = np.zeros_like(points)
    disp[:, 2] = 0.01
    return NativeVtuPreviewData(
        schema="AsterMaxNativeVtuPreviewV1",
        points_mm=points,
        displacement_mm=disp,
        tet10_connectivity=np.vstack(cells),
        von_mises_ip_max_mpa=np.asarray(vm, dtype=float),
        source_sha256="0" * 64,
        converged_claim=False,
        industrial_validation_claim=False,
        stress_is_nodal=stress_is_nodal,
    )


def test_single_tet_boundary_has_four_tri6_faces() -> None:
    surface = extract_tet10_boundary(_data())
    assert surface.schema == "AsterMaxNativeViewportSurfaceV1"
    assert surface.tri6_connectivity.shape == (4, 6)
    assert surface.owner_cell_index.tolist() == [0, 0, 0, 0]
    assert np.all(surface.owner_von_mises_ip_max_mpa == pytest.approx(12.0))


def test_shared_tet_face_is_removed_from_render_skin() -> None:
    surface = extract_tet10_boundary(_data(two_cells=True))
    assert surface.tri6_connectivity.shape == (6, 6)
    keys = {tuple(sorted(int(v) for v in face[:3])) for face in surface.tri6_connectivity}
    assert (0, 1, 2) not in keys
    assert sorted(surface.owner_cell_index.tolist()) == [0, 0, 0, 1, 1, 1]
    assert sorted(surface.owner_von_mises_ip_max_mpa.tolist()) == [12.0, 12.0, 12.0, 30.0, 30.0, 30.0]


def test_camera_projection_is_deterministic_and_orbit_changes_view() -> None:
    data = _data()
    a_xy, a_depth = orthographic_camera_projection(data.points_mm, azimuth_deg=35, elevation_deg=25)
    b_xy, b_depth = orthographic_camera_projection(data.points_mm, azimuth_deg=35, elevation_deg=25)
    c_xy, _ = orthographic_camera_projection(data.points_mm, azimuth_deg=75, elevation_deg=25)
    np.testing.assert_allclose(a_xy, b_xy, rtol=0, atol=0)
    np.testing.assert_allclose(a_depth, b_depth, rtol=0, atol=0)
    assert not np.allclose(a_xy, c_xy)


def test_viewport_deformation_uses_actual_displacement() -> None:
    data = _data()
    xy0, depth0, surface0 = viewport_geometry(data, deformation_scale=0.0)
    xy5, depth5, surface5 = viewport_geometry(data, deformation_scale=5.0)
    assert surface0.tri6_connectivity.tolist() == surface5.tri6_connectivity.tolist()
    # Uniform translation is removed by camera centering, so a rigid displacement
    # must not create a fake deformation in the projected shape.
    np.testing.assert_allclose(xy0, xy5, atol=1e-14)
    np.testing.assert_allclose(depth0, depth5, atol=1e-14)


def test_viewport_refuses_nodal_stress_claim() -> None:
    with pytest.raises(ValueError, match="nodal stress"):
        assert_native_viewport_claim_boundary(_data(stress_is_nodal=True))
