from dataclasses import replace

import pytest

from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.remesh_face_rebinding import (
    RemeshFaceRebindingError,
    build_remesh_boundary_route_evidence,
    rebind_named_selection_after_remesh,
    verify_remesh_boundary_route_evidence,
)


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "witness_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55c_witness")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _face_tags_for_x_extremes(inventory):
    ordered = sorted(inventory.faces, key=lambda f: f.center_mm[0])
    return ordered[0].face_tag, ordered[-1].face_tag


def test_named_selections_rebind_to_same_cad_faces_after_distinct_tet10_remesh(tmp_path):
    step = _write_box_step(tmp_path)
    baseline = mesh_step_tet10_with_face_ownership(step, 7.0)
    remesh = mesh_step_tet10_with_face_ownership(step, 4.0)
    assert baseline.ownership_sha256 != remesh.ownership_sha256
    support_tag, load_tag = _face_tags_for_x_extremes(baseline)
    support = capture_named_selection(step, [support_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [load_tag], "Load X+", "LOAD")

    support_ev, _, support_tri6 = rebind_named_selection_after_remesh(step, support, baseline, remesh)
    load_ev, _, load_tri6 = rebind_named_selection_after_remesh(step, load, baseline, remesh)
    assert support_ev.same_geometric_identity and support_ev.same_physics_role
    assert load_ev.same_geometric_identity and load_ev.same_physics_role
    assert support_ev.face_signature_sha256 == tuple(f.signature_sha256 for f in support.faces)
    assert load_ev.face_signature_sha256 == tuple(f.signature_sha256 for f in load.faces)
    assert support_tri6.shape[1] == 6 and load_tri6.shape[1] == 6

    route = build_remesh_boundary_route_evidence(step, baseline, remesh, support, load)
    verify_remesh_boundary_route_evidence(route)
    assert route.ready_for_second_solve is True
    assert route.qoi_convergence_claimed is False
    assert route.global_analysis_converged is False
    assert route.industrial_validation is False
    assert route.ansys_equivalence is False


def test_rebinding_rejects_same_mesh_and_wrong_roles(tmp_path):
    step = _write_box_step(tmp_path)
    baseline = mesh_step_tet10_with_face_ownership(step, 7.0)
    support_tag, load_tag = _face_tags_for_x_extremes(baseline)
    support = capture_named_selection(step, [support_tag], "Fixed", "SUPPORT")
    load = capture_named_selection(step, [load_tag], "Load", "LOAD")
    with pytest.raises(RemeshFaceRebindingError, match="DISTINCT_MESH"):
        build_remesh_boundary_route_evidence(step, baseline, baseline, support, load)

    remesh = mesh_step_tet10_with_face_ownership(step, 4.0)
    wrong = capture_named_selection(step, [load_tag], "Reference", "REFERENCE")
    with pytest.raises(RemeshFaceRebindingError, match="ROLES_REQUIRED"):
        build_remesh_boundary_route_evidence(step, baseline, remesh, support, wrong)


def test_route_evidence_fails_closed_on_overclaim_or_tamper(tmp_path):
    step = _write_box_step(tmp_path)
    baseline = mesh_step_tet10_with_face_ownership(step, 7.0)
    remesh = mesh_step_tet10_with_face_ownership(step, 4.0)
    support_tag, load_tag = _face_tags_for_x_extremes(baseline)
    support = capture_named_selection(step, [support_tag], "Fixed", "SUPPORT")
    load = capture_named_selection(step, [load_tag], "Load", "LOAD")
    route = build_remesh_boundary_route_evidence(step, baseline, remesh, support, load)

    with pytest.raises(RemeshFaceRebindingError, match="CONVERGENCE_OVERCLAIM"):
        verify_remesh_boundary_route_evidence(replace(route, qoi_convergence_claimed=True))
    with pytest.raises(RemeshFaceRebindingError, match="VALIDATION_OVERCLAIM"):
        verify_remesh_boundary_route_evidence(replace(route, ansys_equivalence=True))
    with pytest.raises(RemeshFaceRebindingError, match="TAMPERED"):
        verify_remesh_boundary_route_evidence(replace(route, evidence_sha256="a" * 64))
