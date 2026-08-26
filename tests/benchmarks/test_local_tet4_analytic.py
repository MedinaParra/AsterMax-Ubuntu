import numpy as np
import pytest

from astermax.solver.local_tet4 import (
    IsotropicMaterialV1,
    NormalPenaltyContact,
    tet4_kinematics,
    tet4_stiffness,
    tet4_stress_mpa,
    von_mises_mpa,
)


def _positive_tet(nodes: np.ndarray, tet: list[int]) -> list[int]:
    oriented = list(tet)
    a, b, c, d = nodes[oriented]
    det = np.linalg.det(np.column_stack((b - a, c - a, d - a)))
    if det < 0:
        oriented[1], oriented[2] = oriented[2], oriented[1]
    return oriented


def _extruded_square(length_mm: float, layers: int):
    yz = np.array(
        [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
        dtype=float,
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=int)
    nodes = []
    for x in np.linspace(0.0, length_mm, layers + 1):
        nodes.extend([[x, y, z] for y, z in yz])
    nodes = np.asarray(nodes, dtype=float)
    tets = []
    width = len(yz)
    for layer in range(layers):
        low = layer * width
        high = (layer + 1) * width
        for a, b, c in triangles:
            candidates = [
                [low + a, low + b, low + c, high + a],
                [low + b, high + b, low + c, high + a],
                [high + b, high + c, low + c, high + a],
            ]
            tets.extend(_positive_tet(nodes, tet) for tet in candidates)
    return nodes, np.asarray(tets, dtype=int)


def _assemble_dense(nodes, tets, material):
    ndof = 3 * len(nodes)
    stiffness = np.zeros((ndof, ndof), dtype=float)
    for tet in tets:
        element = tet4_stiffness(nodes[tet], material)
        dofs = np.array(
            [[3 * node, 3 * node + 1, 3 * node + 2] for node in tet],
            dtype=int,
        ).reshape(12)
        stiffness[np.ix_(dofs, dofs)] += element
    return stiffness


def test_constant_strain_tet4_patch_is_exact():
    material = IsotropicMaterialV1(elastic_modulus_mpa=200_000.0, poisson_ratio=0.25)
    nodes = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float
    )
    # u_x = 1e-3*x, u_y = -2e-4*y, u_z = 3e-4*z: exactly affine.
    displacement = np.column_stack(
        [1e-3 * nodes[:, 0], -2e-4 * nodes[:, 1], 3e-4 * nodes[:, 2]]
    )
    stress = tet4_stress_mpa(nodes, displacement, material)
    constitutive_strain = np.array([1e-3, -2e-4, 3e-4, 0, 0, 0], dtype=float)
    # Compute expected stress independently from isotropic Lamé constants.
    e = material.elastic_modulus_mpa
    nu = material.poisson_ratio
    lam = e * nu / ((1 + nu) * (1 - 2 * nu))
    mu = e / (2 * (1 + nu))
    tr = constitutive_strain[:3].sum()
    expected = np.array(
        [
            2 * mu * constitutive_strain[0] + lam * tr,
            2 * mu * constitutive_strain[1] + lam * tr,
            2 * mu * constitutive_strain[2] + lam * tr,
            0,
            0,
            0,
        ]
    )
    assert stress == pytest.approx(expected, rel=1e-12, abs=1e-12)
    assert von_mises_mpa(stress) > 0


def test_extruded_block_matches_closed_form_axial_compression():
    # nu=0 removes Poisson coupling so the fully fixed back face has the exact 1D solution.
    material = IsotropicMaterialV1(elastic_modulus_mpa=200_000.0, poisson_ratio=0.0)
    nodes, tets = _extruded_square(length_mm=20.0, layers=4)
    stiffness = _assemble_dense(nodes, tets, material)
    force = np.zeros(3 * len(nodes), dtype=float)

    back = np.where(np.isclose(nodes[:, 0], 0.0))[0]
    front = np.where(np.isclose(nodes[:, 0], 20.0))[0]
    total_force_n = 1000.0
    force[3 * front] = total_force_n / len(front)

    fixed = np.array(
        [[3 * node, 3 * node + 1, 3 * node + 2] for node in back], dtype=int
    ).reshape(-1)
    free = np.setdiff1d(np.arange(len(force)), fixed)
    displacement = np.zeros_like(force)
    displacement[free] = np.linalg.solve(
        stiffness[np.ix_(free, free)], force[free]
    )

    expected_u_mm = total_force_n * 20.0 / (100.0 * 200_000.0)
    expected_sigma_mpa = total_force_n / 100.0
    assert displacement[3 * front].mean() == pytest.approx(expected_u_mm, rel=1e-12)

    sigma_x = []
    for tet in tets:
        dofs = np.array(
            [[3 * node, 3 * node + 1, 3 * node + 2] for node in tet], dtype=int
        ).reshape(12)
        sigma_x.append(
            tet4_stress_mpa(nodes[tet], displacement[dofs], material)[0]
        )
    assert np.mean(sigma_x) == pytest.approx(expected_sigma_mpa, rel=1e-12)


def test_penalty_contact_matches_closed_form_gap_closure():
    # Two equal 10 mm blocks, A=100 mm², E=200 GPa, F=1000 N, gap=0.25 mm.
    area_mm2 = 100.0
    e_mpa = 200_000.0
    thickness_each_mm = 10.0
    force_n = 1000.0
    gap_mm = 0.25
    pressure_mpa = force_n / area_mm2

    joint_compliance_mm_per_n = (
        thickness_each_mm / (e_mpa * area_mm2)
        + thickness_each_mm / (e_mpa * area_mm2)
    )
    elastic_compression_mm = force_n * joint_compliance_mm_per_n

    penalty_factor = 20.0
    foundation_stiffness_n_per_mm3 = 1.0 / (
        thickness_each_mm / e_mpa + thickness_each_mm / e_mpa
    )
    contact_stiffness_n_per_mm = (
        penalty_factor * foundation_stiffness_n_per_mm3 * area_mm2
    )
    contact = NormalPenaltyContact(
        stiffness_n_per_mm=contact_stiffness_n_per_mm, gap_mm=gap_mm
    )
    penalty_penetration_mm = force_n / contact_stiffness_n_per_mm
    segment_ux_mm = gap_mm + elastic_compression_mm + penalty_penetration_mm
    hub_ux_mm = elastic_compression_mm / 2.0

    # Relative closure beyond the gap is elastic compression + penalty penetration;
    # isolate penalty force using a relative displacement that gives only the penetration term.
    contact_force = contact.force_n(gap_mm + penalty_penetration_mm, 0.0)
    assert contact_force == pytest.approx(force_n, rel=1e-12)
    assert contact_force / area_mm2 == pytest.approx(pressure_mpa, rel=1e-12)
    assert gap_mm + elastic_compression_mm + penalty_penetration_mm == pytest.approx(
        0.25105, rel=1e-12
    )


def test_inverted_and_degenerate_tets_fail_closed():
    valid = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    inverted = valid[[0, 2, 1, 3]]
    degenerate = valid.copy()
    degenerate[3] = [0.5, 0.5, 0.0]
    tet4_kinematics(valid)
    with pytest.raises(ValueError):
        tet4_kinematics(inverted)
    with pytest.raises(ValueError):
        tet4_kinematics(degenerate)
