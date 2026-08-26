from __future__ import annotations

import numpy as np

from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tet10 import (
    tet10_B_matrix,
    tet10_gauss_rule,
    tet10_shape,
    tet10_shape_grad_local,
    tet10_stiffness,
    tet10_stress_at_centroid,
)


def _straight_tet10() -> np.ndarray:
    # Unit reference tetrahedron with midside nodes in Gmsh type-11 order.
    v = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    edges = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
    mids = np.array([(v[a] + v[b]) * 0.5 for a, b in edges])
    return np.vstack((v, mids))


def test_tet10_partition_of_unity_and_gradient_sum_zero():
    for p in ((0.25, 0.25, 0.25), (0.1, 0.2, 0.3), (0.0, 0.0, 0.0)):
        assert np.isclose(tet10_shape(p).sum(), 1.0, atol=1e-14)
        assert np.allclose(tet10_shape_grad_local(p).sum(axis=0), 0.0, atol=1e-14)


def test_tet10_kronecker_property_in_gmsh_order():
    local_nodes = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 0.5, 0.0],
            [0.0, 0.0, 0.5],
            [0.5, 0.0, 0.5],
            [0.0, 0.5, 0.5],
        ]
    )
    for i, p in enumerate(local_nodes):
        expected = np.zeros(10)
        expected[i] = 1.0
        assert np.allclose(tet10_shape(p), expected, atol=1e-14)


def test_tet10_gauss_rule_integrates_reference_volume():
    _, w = tet10_gauss_rule()
    assert np.isclose(w.sum(), 1.0 / 6.0, atol=1e-15)


def test_tet10_rigid_translation_has_zero_strain_energy():
    coords = _straight_tet10()
    mat = IsotropicMaterial(youngs_modulus_mpa=210000.0, poisson_ratio=0.3)
    k = tet10_stiffness(coords, mat)
    u = np.tile([0.8, -1.2, 2.1], (10, 1)).reshape(-1)
    energy = float(u @ k @ u)
    scale = float(np.linalg.norm(k, ord=np.inf) * np.dot(u, u))
    assert abs(energy) <= max(1e-8, scale * 1e-12)


def test_tet10_linear_patch_reproduces_constant_strain():
    coords = _straight_tet10()
    # affine displacement u=A*x + c gives exactly constant small strain
    a = np.array([[0.010, 0.004, -0.002], [0.003, -0.006, 0.005], [0.001, -0.004, 0.008]])
    c = np.array([0.7, -1.1, 0.2])
    u = coords @ a.T + c
    expected = np.array(
        [
            a[0, 0],
            a[1, 1],
            a[2, 2],
            a[0, 1] + a[1, 0],
            a[1, 2] + a[2, 1],
            a[0, 2] + a[2, 0],
        ]
    )
    for p in ((0.25, 0.25, 0.25), (0.1, 0.2, 0.3)):
        b, det_j = tet10_B_matrix(coords, p)
        assert det_j > 0.0
        assert np.allclose(b @ u.reshape(-1), expected, atol=1e-12)


def test_tet10_stiffness_is_symmetric_and_psd_up_to_rigid_modes():
    coords = _straight_tet10()
    mat = IsotropicMaterial(youngs_modulus_mpa=210000.0, poisson_ratio=0.3)
    k = tet10_stiffness(coords, mat)
    assert np.allclose(k, k.T, atol=1e-9)
    eig = np.linalg.eigvalsh(k)
    tol = np.max(np.abs(eig)) * 1e-10
    assert eig.min() >= -tol
    assert np.count_nonzero(np.abs(eig) <= tol) >= 6


def test_tet10_centroid_stress_matches_affine_constitutive_response():
    coords = _straight_tet10()
    mat = IsotropicMaterial(youngs_modulus_mpa=210000.0, poisson_ratio=0.3)
    a = np.array([[0.001, 0.0, 0.0], [0.0, -0.0002, 0.0], [0.0, 0.0, 0.0004]])
    u = coords @ a.T
    stress, vm = tet10_stress_at_centroid(coords, u, mat)
    strain = np.array([0.001, -0.0002, 0.0004, 0.0, 0.0, 0.0])
    expected = mat.constitutive_matrix() @ strain
    assert np.allclose(stress, expected, rtol=1e-12, atol=1e-10)
    assert vm >= 0.0


def test_tet10_rejects_inverted_mapping():
    coords = _straight_tet10().copy()
    coords[:, 0] *= -1.0
    try:
        tet10_B_matrix(coords, (0.25, 0.25, 0.25))
    except ValueError as exc:
        assert "Jacobian" in str(exc)
    else:
        raise AssertionError("inverted TET10 must be rejected")
