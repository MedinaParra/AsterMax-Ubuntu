from dataclasses import replace

import pytest

from astermax.credibility import canonical_sha256
from astermax.fea.gmsh_local_refinement import (
    build_local_size_callback,
    configure_gmsh_local_refinement,
    execute_configured_tet10_mesh,
    verify_gmsh_local_remesh_evidence,
)
from astermax.fea.local_refinement_plan import (
    approve_refinement_plan,
    build_controlled_local_refinement_plan,
)
from astermax.fea.qoi_convergence import LocalRefinementReviewV1


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def make_review() -> LocalRefinementReviewV1:
    core = {
        "schema": "AsterMaxLocalRefinementReviewV1",
        "inspector_snapshot_sha256": "d" * 64,
        "candidate_element_indices": (4,),
        "candidate_centroids_mm": ((10.0, 10.0, 10.0),),
        "rationale": ("SYNTHETIC_GMSH_EXECUTION_WITNESS_ONLY",),
        "requires_human_approval": True,
        "auto_execution_allowed": False,
        "changes_physics": False,
    }
    return LocalRefinementReviewV1(**core, review_sha256=canonical_sha256(core))


def make_plan():
    return build_controlled_local_refinement_plan(
        source_step_sha256=SHA_A,
        route_sha256=SHA_B,
        baseline_mesh_sha256=SHA_C,
        review=make_review(),
        baseline_size_mm=8.0,
        refined_size_factor=0.25,
        influence_radius_factor=0.75,
    )


def test_callback_is_deterministic_local_and_requires_approval():
    plan = make_plan()
    approval = approve_refinement_plan(plan, approver="Engineering Reviewer", approved=True)
    callback = build_local_size_callback(plan, approval)
    assert callback(3, 1, 10.0, 10.0, 10.0, 99.0) == 2.0
    assert callback(3, 1, 0.0, 0.0, 0.0, 99.0) == 8.0
    rejected = approve_refinement_plan(plan, approver="Engineering Reviewer", approved=False)
    with pytest.raises(ValueError, match="GMSH_REFINEMENT_APPROVAL_REQUIRED"):
        build_local_size_callback(plan, rejected)


def test_adapter_requires_gmsh_size_callback_api():
    plan = make_plan()
    approval = approve_refinement_plan(plan, approver="Reviewer", approved=True)

    class NoMeshApi:
        model = object()

    with pytest.raises(ValueError, match="GMSH_SIZE_CALLBACK_API_UNAVAILABLE"):
        configure_gmsh_local_refinement(NoMeshApi(), plan, approval)


def test_real_gmsh_generates_nonempty_tet10_witness_mesh(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    plan = make_plan()
    approval = approve_refinement_plan(plan, approver="Harness Reviewer", approved=True)
    output = tmp_path / "local_refinement_witness.msh"

    gmsh.initialize()
    try:
        gmsh.model.add("astermax_c5_5b_witness_mm")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 20.0, 20.0, 20.0)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 2.0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 8.0)
        evidence = execute_configured_tet10_mesh(
            gmsh,
            plan=plan,
            approval=approval,
            output_path=output,
        )
    finally:
        gmsh.finalize()

    assert output.is_file()
    assert output.stat().st_size > 0
    assert evidence.element_order == 2
    assert evidence.tetra_element_type == 11
    assert evidence.tetra_element_count > 0
    assert evidence.node_count > 0
    assert evidence.output_mesh_sha256 != plan.baseline_mesh_sha256
    assert evidence.source_step_sha256 == SHA_A
    assert evidence.route_sha256 == SHA_B
    assert evidence.preserves_source_geometry is True
    assert evidence.preserves_bc_load_route is True
    assert evidence.qoi_convergence_claimed is False
    assert evidence.global_analysis_converged is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False
    verify_gmsh_local_remesh_evidence(evidence)


def test_evidence_boundary_rejects_professional_overclaims(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    plan = make_plan()
    approval = approve_refinement_plan(plan, approver="Harness Reviewer", approved=True)
    output = tmp_path / "boundary_witness.msh"
    gmsh.initialize()
    try:
        gmsh.model.add("astermax_c5_5b_boundary")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 12.0, 12.0, 12.0)
        gmsh.model.occ.synchronize()
        evidence = execute_configured_tet10_mesh(gmsh, plan=plan, approval=approval, output_path=output)
    finally:
        gmsh.finalize()

    for field, error in (
        ("qoi_convergence_claimed", "GMSH_REFINEMENT_QOI_CONVERGENCE_OVERCLAIM"),
        ("global_analysis_converged", "GMSH_REFINEMENT_GLOBAL_CONVERGENCE_OVERCLAIM"),
        ("industrial_validation", "GMSH_REFINEMENT_INDUSTRIAL_VALIDATION_OVERCLAIM"),
        ("ansys_equivalence", "GMSH_REFINEMENT_ANSYS_EQUIVALENCE_OVERCLAIM"),
    ):
        with pytest.raises(ValueError, match=error):
            verify_gmsh_local_remesh_evidence(replace(evidence, **{field: True}))
