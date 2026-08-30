from dataclasses import replace

import numpy as np
import pytest

from astermax.fea.arbitrary_bc import prepare_arbitrary_bc_model, solve_arbitrary_bc_model
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.solution_driven_adaptivity import (
    SolutionDrivenAdaptivityError,
    build_solution_driven_local_refinement_review,
    build_solution_driven_refinement_evidence,
)


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "solution_adaptivity_witness_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55m_solution_adaptivity")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _real_baseline_solve(tmp_path):
    step = _write_box_step(tmp_path)
    from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
    inventory = mesh_step_tet10_with_face_ownership(step, 8.0)
    ordered = sorted(inventory.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    prepared = prepare_arbitrary_bc_model(
        step,
        mesh_size_mm=8.0,
        support_selection=support,
        load_selection=load,
    )
    solved = solve_arbitrary_bc_model(
        prepared,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 250.0, 0.0),
    )
    return step, prepared["inventory"], solved


def test_real_tet10_solve_drives_refinement_candidates(tmp_path):
    step, inventory, solved = _real_baseline_solve(tmp_path)
    from astermax.fea.evidence import sha256_file
    evidence = build_solution_driven_refinement_evidence(
        source_step_sha256=sha256_file(step),
        mesh_identity_sha256=inventory.ownership_sha256,
        solve_evidence_sha256=solved["solve_evidence"].solve_evidence_sha256,
        nodes_mm=inventory.nodes_mm,
        elements=inventory.elements,
        result=solved["result"],
        maximum_candidates=5,
    )
    assert evidence.element_count == inventory.elements.shape[0]
    assert 1 <= evidence.candidate_count <= 5
    assert evidence.maximum_indicator > 0.0
    assert evidence.global_von_mises_scale_mpa > 0.0
    assert evidence.estimator_certified is False
    assert evidence.solution_error_bound_claimed is False
    assert evidence.global_analysis_converged is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False
    assert len(set(evidence.candidate_element_indices)) == evidence.candidate_count
    assert all(row.normalized_indicator >= 0.0 for row in evidence.candidates)

    review = build_solution_driven_local_refinement_review(evidence)
    assert review.requires_human_approval is True
    assert review.auto_execution_allowed is False
    assert review.changes_physics is False
    assert review.candidate_element_indices == evidence.candidate_element_indices
    assert "COMPUTED_TET10_VON_MISES_VARIATION" in review.rationale[0]


def test_solution_indicator_is_bound_to_real_solver_evidence(tmp_path):
    step, inventory, solved = _real_baseline_solve(tmp_path)
    from astermax.fea.evidence import sha256_file
    evidence = build_solution_driven_refinement_evidence(
        source_step_sha256=sha256_file(step),
        mesh_identity_sha256=inventory.ownership_sha256,
        solve_evidence_sha256=solved["solve_evidence"].solve_evidence_sha256,
        nodes_mm=inventory.nodes_mm,
        elements=inventory.elements,
        result=solved["result"],
        maximum_candidates=3,
    )
    assert evidence.solve_evidence_sha256 == solved["solve_evidence"].solve_evidence_sha256
    assert evidence.mesh_identity_sha256 == inventory.ownership_sha256
    with pytest.raises(SolutionDrivenAdaptivityError, match="EVIDENCE_TAMPERED"):
        build_solution_driven_local_refinement_review(replace(evidence, maximum_indicator=evidence.maximum_indicator + 1.0))
    with pytest.raises(SolutionDrivenAdaptivityError, match="ESTIMATOR_OVERCLAIM"):
        tampered = replace(evidence, estimator_certified=True)
        from astermax.credibility import canonical_sha256
        core = tampered.__dict__.copy(); core.pop("evidence_sha256")
        tampered = replace(tampered, evidence_sha256=canonical_sha256(core))
        build_solution_driven_local_refinement_review(tampered)


def test_zero_stress_field_fails_closed():
    from astermax.fea.solver import Tet10LinearStaticResult
    nodes = np.array([
        [0.,0.,0.], [1.,0.,0.], [0.,1.,0.], [0.,0.,1.],
        [.5,0,0], [.5,.5,0], [0,.5,0], [0,0,.5], [0,.5,.5], [.5,0,.5]
    ])
    elems = np.arange(10, dtype=np.int64).reshape(1, 10)
    result = Tet10LinearStaticResult(
        displacement_mm=np.zeros((10,3)),
        reactions_n=np.zeros((10,3)),
        integration_point_stress_mpa=np.zeros((1,4,6)),
        integration_point_von_mises_mpa=np.zeros((1,4)),
    )
    with pytest.raises(SolutionDrivenAdaptivityError, match="ZERO_STRESS_FIELD"):
        build_solution_driven_refinement_evidence(
            source_step_sha256="a"*64,
            mesh_identity_sha256="b"*64,
            solve_evidence_sha256="c"*64,
            nodes_mm=nodes,
            elements=elems,
            result=result,
        )
