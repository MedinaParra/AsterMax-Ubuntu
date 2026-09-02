from pathlib import Path

import numpy as np

from astermax.code_aster_reference_harness import (
    ReferenceObservedMetrics,
    UniaxialPrismSpec,
    generate_uniaxial_prism_tet10,
    prepare_reference_solver_bundle,
    verify_uniaxial_reference_results,
)


def test_reference_closed_form_is_mm_n_mpa_consistent():
    spec = UniaxialPrismSpec(
        length_mm=100.0,
        width_mm=20.0,
        height_mm=10.0,
        young_mpa=200000.0,
        poisson=0.3,
        total_force_n=10000.0,
    )
    assert spec.area_mm2 == 200.0
    assert spec.traction_x_mpa == 50.0
    assert spec.expected_sigma_x_mpa == 50.0
    assert spec.expected_epsilon_x == 0.00025
    assert spec.expected_ux_mm == 0.025
    assert spec.expected_support_reaction_x_n == -10000.0


def test_real_gmsh_reference_mesh_is_quadratic_and_end_faces_are_geometric():
    spec = UniaxialPrismSpec(mesh_size_mm=20.0)
    mesh = generate_uniaxial_prism_tet10(spec)
    assert mesh.nodes_mm.shape[1] == 3
    assert mesh.tet10.ndim == 2 and mesh.tet10.shape[1] == 10 and mesh.tet10.shape[0] > 0
    assert mesh.support_tri6.ndim == 2 and mesh.support_tri6.shape[1] == 6 and mesh.support_tri6.shape[0] > 0
    assert mesh.load_tri6.ndim == 2 and mesh.load_tri6.shape[1] == 6 and mesh.load_tri6.shape[0] > 0

    support_x = mesh.nodes_mm[mesh.support_tri6[:, :3], 0]
    load_x = mesh.nodes_mm[mesh.load_tri6[:, :3], 0]
    assert np.max(np.abs(support_x)) < 1e-8
    assert np.max(np.abs(load_x - spec.length_mm)) < 1e-8


def test_reference_bundle_proves_mesh_med_and_comm_but_not_a_solve(tmp_path: Path):
    spec = UniaxialPrismSpec(mesh_size_mm=20.0)
    ev = prepare_reference_solver_bundle(spec, tmp_path)
    assert ev["case"] == "3D_UNIAXIAL_PRISM_TET10"
    assert ev["tet10"] > 0
    assert ev["support_tri6"] > 0
    assert ev["load_tri6"] > 0
    assert ev["med_groups_verified"] is True
    assert len(ev["med_sha256"]) == 64
    assert len(ev["comm_sha256"]) == 64
    assert ev["fea_solve_executed"] is False
    assert ev["numerical_verification"] is False
    assert ev["results_verified"] is False
    comm = (tmp_path / "astermax.comm").read_text(encoding="utf-8")
    assert "GROUP_MA='FIXED_FACE'" in comm
    assert "GROUP_MA='LOAD_FACE'" in comm
    assert "FX=50" in comm


def test_matching_numbers_without_real_solve_cannot_claim_verification():
    spec = UniaxialPrismSpec()
    observed = ReferenceObservedMetrics(
        load_face_mean_ux_mm=spec.expected_ux_mm,
        support_reaction_x_n=spec.expected_support_reaction_x_n,
        axial_stress_mpa=spec.expected_sigma_x_mpa,
    )
    ev = verify_uniaxial_reference_results(spec, observed, fea_solve_executed=False)
    assert ev.displacement_verified is True
    assert ev.reaction_verified is True
    assert ev.stress_verified is True
    assert ev.fea_solve_executed is False
    assert ev.numerical_verification is False
    assert ev.results_verified is False


def test_real_solve_flag_still_requires_all_mechanical_checks():
    spec = UniaxialPrismSpec()
    bad = ReferenceObservedMetrics(
        load_face_mean_ux_mm=spec.expected_ux_mm,
        support_reaction_x_n=0.5 * spec.expected_support_reaction_x_n,
        axial_stress_mpa=spec.expected_sigma_x_mpa,
    )
    ev = verify_uniaxial_reference_results(spec, bad, fea_solve_executed=True)
    assert ev.displacement_verified is True
    assert ev.reaction_verified is False
    assert ev.stress_verified is True
    assert ev.numerical_verification is False
    assert ev.results_verified is False
