import numpy as np
import pytest

from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_surface_stress import (
    Tet10SurfaceStressError,
    evaluate_tet10_stress_at_natural_point,
    evaluate_tri6_surface_stress_sample,
    resolve_tri6_parent_tet10,
    tri6_point_to_tet10_natural,
)
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)


def _one_tet():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 0.0, 4.0],
        ],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=np.int64).reshape(1, 10)
    return nodes, elements


def _uniaxial_displacement(nodes, *, axial_strain=2.5e-4):
    eps = float(axial_strain)
    nu = MATERIAL.poisson_ratio
    u = np.zeros_like(nodes, dtype=float)
    u[:, 0] = eps * nodes[:, 0]
    u[:, 1] = -nu * eps * nodes[:, 1]
    u[:, 2] = -nu * eps * nodes[:, 2]
    return u


def test_direct_tet10_surface_point_recovers_exact_uniaxial_stress():
    nodes, _ = _one_tet()
    disp = _uniaxial_displacement(nodes)
    strain, stress, det_j = evaluate_tet10_stress_at_natural_point(
        nodes,
        disp,
        MATERIAL,
        (0.2, 0.3, 0.0),
    )
    assert det_j > 0.0
    assert strain[0] == pytest.approx(2.5e-4, rel=0.0, abs=1e-15)
    assert stress[0] == pytest.approx(50.0, rel=0.0, abs=1e-9)
    assert stress[1] == pytest.approx(0.0, rel=0.0, abs=1e-9)
    assert stress[2] == pytest.approx(0.0, rel=0.0, abs=1e-9)
    assert np.max(np.abs(stress[3:])) < 1e-9


def test_tri6_face_maps_to_unique_parent_and_exact_surface_stress():
    nodes, elements = _one_tet()
    disp = _uniaxial_displacement(nodes)
    tri6 = (0, 1, 2, 4, 5, 6)
    parent = resolve_tri6_parent_tet10(elements, tri6)
    assert parent.element_index == 0
    assert parent.opposite_tet_vertex == 3
    natural = tri6_point_to_tet10_natural(parent, (0.25, 0.25))
    assert natural == pytest.approx((0.25, 0.25, 0.0), abs=1e-15)
    sample = evaluate_tri6_surface_stress_sample(
        nodes, elements, disp, MATERIAL, tri6, (0.25, 0.25)
    )
    assert sample.axial_normal_stress_mpa == pytest.approx(50.0, abs=1e-9)
    assert sample.tet10_natural_coordinates[2] == pytest.approx(0.0, abs=1e-15)


def test_rotated_tri6_orientation_maps_same_physical_point_and_stress():
    nodes, elements = _one_tet()
    disp = _uniaxial_displacement(nodes)
    # Cyclic permutation of corners and corresponding midsides.
    tri_a = (0, 1, 2, 4, 5, 6)
    tri_b = (1, 2, 0, 5, 6, 4)
    a = evaluate_tri6_surface_stress_sample(nodes, elements, disp, MATERIAL, tri_a, (0.2, 0.3))
    # Barycentric weights (0.5,0.2,0.3) in tri_a become (0.2,0.3,0.5) in tri_b.
    b = evaluate_tri6_surface_stress_sample(nodes, elements, disp, MATERIAL, tri_b, (0.3, 0.5))
    assert a.physical_point_mm == pytest.approx(b.physical_point_mm, abs=1e-12)
    assert a.axial_normal_stress_mpa == pytest.approx(b.axial_normal_stress_mpa, abs=1e-10)


def test_wrong_midside_order_fails_closed():
    nodes, elements = _one_tet()
    bad_tri6 = (0, 1, 2, 5, 4, 6)
    with pytest.raises(Tet10SurfaceStressError, match="MIDSIDE_ORDER"):
        resolve_tri6_parent_tet10(elements, bad_tri6)


def test_interior_shared_face_is_ambiguous_not_treated_as_boundary():
    _, elements = _one_tet()
    duplicated = np.vstack((elements, elements))
    tri6 = (0, 1, 2, 4, 5, 6)
    with pytest.raises(Tet10SurfaceStressError, match="AMBIGUOUS"):
        resolve_tri6_parent_tet10(duplicated, tri6)


def test_outside_reference_face_and_tetra_fail_closed():
    nodes, elements = _one_tet()
    parent = resolve_tri6_parent_tet10(elements, (0, 1, 2, 4, 5, 6))
    with pytest.raises(Tet10SurfaceStressError, match="OUTSIDE_REFERENCE_FACE"):
        tri6_point_to_tet10_natural(parent, (0.8, 0.4))
    with pytest.raises(Tet10SurfaceStressError, match="OUTSIDE_REFERENCE_ELEMENT"):
        evaluate_tet10_stress_at_natural_point(nodes, _uniaxial_displacement(nodes), MATERIAL, (0.6, 0.6, 0.0))
