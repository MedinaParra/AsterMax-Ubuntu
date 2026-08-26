import numpy as np
import pytest

from astermax.fea.tet10 import (
    TET10_GAUSS_POINTS,
    TET10_GAUSS_WEIGHTS,
    straight_sided_tet10_from_vertices,
    tet10_B_matrix,
    tet10_integration_point_results,
    tet10_shape_derivatives,
    tet10_shape_functions,
    tet10_stiffness,
)
from astermax.fea.tet4 import IsotropicMaterial


def _reference_vertices():
    return np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 0.0, 4.0],
        ]
    )


def test_tet10_shape_functions_are_kronecker_and_partition_unity():
    # Exact Gmsh Tetrahedron10 order: vertices 0..3, then edges
    # 0-1, 1-2, 2-0, 0-3, 2-3, 1-3.
    node_natural_coordinates = np.asarray(
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
        ]
    )
    interpolation = np.vstack([tet10_shape_functions(p) for p in node_natural_coordinates])
    assert np.allclose(interpolation, np.eye(10), atol=1.0e-13)
    for point in TET10_GAUSS_POINTS:
        assert np.isclose(np.sum(tet10_shape_functions(point)), 1.0, atol=1.0e-13)
        assert np.allclose(np.sum(tet10_shape_derivatives(point), axis=0), 0.0, atol=1.0e-13)


def test_tet10_straight_element_integrates_exact_volume_and_has_symmetric_stiffness():
    coords = straight_sided_tet10_from_vertices(_reference_vertices())
    material = IsotropicMaterial(210000.0, 0.30)
    volume = 0.0
    for point, weight in zip(TET10_GAUSS_POINTS, TET10_GAUSS_WEIGHTS):
        _, det_j = tet10_B_matrix(coords, point)
        volume += det_j * weight
    assert np.isclose(volume, 4.0, rtol=0.0, atol=1.0e-12)

    ke = tet10_stiffness(coords, material)
    assert ke.shape == (30, 30)
    assert np.all(np.isfinite(ke))
    assert np.allclose(ke, ke.T, rtol=1.0e-12, atol=1.0e-8)

    # A rigid translation must have zero strain energy.
    translation = np.tile([0.25, -0.5, 0.75], 10)
    assert abs(float(translation @ ke @ translation)) < 1.0e-6


def test_tet10_affine_patch_recovers_constant_strain_and_stress_at_all_gauss_points():
    coords = straight_sided_tet10_from_vertices(_reference_vertices())
    material = IsotropicMaterial(200000.0, 0.29)

    displacement = np.empty_like(coords)
    x, y, z = coords.T
    displacement[:, 0] = 0.0010 * x + 0.0020 * y
    displacement[:, 1] = -0.0005 * y + 0.0003 * z
    displacement[:, 2] = 0.0002 * x + 0.0004 * z

    expected_strain = np.asarray([0.0010, -0.0005, 0.0004, 0.0020, 0.0003, 0.0002])
    expected_stress = material.constitutive_matrix() @ expected_strain
    results = tet10_integration_point_results(coords, displacement, material)
    assert len(results) == 4
    for result in results:
        assert np.allclose(result.strain, expected_strain, rtol=0.0, atol=1.0e-12)
        assert np.allclose(result.stress_mpa, expected_stress, rtol=1.0e-12, atol=1.0e-9)
        assert result.von_mises_mpa > 0.0


def test_tet10_inverted_or_degenerate_jacobian_fails_closed():
    inverted_vertices = _reference_vertices().copy()
    inverted_vertices[[0, 1]] = inverted_vertices[[1, 0]]
    inverted = straight_sided_tet10_from_vertices(inverted_vertices)
    with pytest.raises(ValueError, match="Degenerate or inverted TET10 Jacobian"):
        tet10_stiffness(inverted, IsotropicMaterial(210000.0, 0.30))

    degenerate_vertices = _reference_vertices().copy()
    degenerate_vertices[3] = degenerate_vertices[0]
    degenerate = straight_sided_tet10_from_vertices(degenerate_vertices)
    with pytest.raises(ValueError, match="Degenerate or inverted TET10 Jacobian"):
        tet10_stiffness(degenerate, IsotropicMaterial(210000.0, 0.30))
