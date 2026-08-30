from dataclasses import replace

import pytest

from astermax.fea.gmsh_local_refinement import execute_configured_tet10_mesh
from astermax.fea.local_refinement_plan import approve_refinement_plan, build_controlled_local_refinement_plan
from astermax.fea.msh_ownership_importer import MshOwnershipImportError, import_tet10_ownership_from_msh
from astermax.fea.qoi_convergence import LocalRefinementReviewV1
from astermax.credibility import canonical_sha256
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.face_ownership import bind_named_selection_to_owned_faces


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "witness_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55h_step")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _review():
    core = {
        "schema": "AsterMaxLocalRefinementReviewV1",
        "inspector_snapshot_sha256": "d" * 64,
        "candidate_element_indices": (0,),
        "candidate_centroids_mm": ((10.0, 10.0, 10.0),),
        "rationale": ("SYNTHETIC_WITNESS_LOCAL_REGION",),
        "requires_human_approval": True,
        "auto_execution_allowed": False,
        "changes_physics": False,
    }
    return LocalRefinementReviewV1(**core, review_sha256=canonical_sha256(core))


def _make_artifact(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    step = _write_box_step(tmp_path)
    from astermax.fea.evidence import sha256_file
    plan = build_controlled_local_refinement_plan(
        source_step_sha256=sha256_file(step),
        route_sha256="b" * 64,
        baseline_mesh_sha256="c" * 64,
        review=_review(),
        baseline_size_mm=8.0,
        refined_size_factor=0.5,
        influence_radius_factor=1.5,
    )
    approval = approve_refinement_plan(plan, approver="Harness Reviewer", approved=True)
    msh = tmp_path / "approved_local_tet10.msh"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55h_loaded_step")
        gmsh.model.occ.importShapes(str(step))
        gmsh.model.occ.synchronize()
        evidence = execute_configured_tet10_mesh(gmsh, plan=plan, approval=approval, output_path=msh)
    finally:
        gmsh.finalize()
    return step, msh, evidence


def test_exact_approved_msh_is_imported_with_robust_association_and_rebindable_ownership(tmp_path):
    step, msh, remesh_evidence = _make_artifact(tmp_path)
    inventory, import_evidence = import_tet10_ownership_from_msh(
        step, msh, expected_mesh_sha256=remesh_evidence.output_mesh_sha256
    )
    assert inventory.elements.ndim == 2 and inventory.elements.shape[1] == 10
    assert inventory.elements.shape[0] == remesh_evidence.tetra_element_count
    assert inventory.nodes_mm.shape[0] == remesh_evidence.node_count
    assert len(inventory.faces) == 6
    assert all(face.triangles.shape[1] == 6 and face.tri6_count > 0 for face in inventory.faces)
    assert import_evidence.exact_mesh_artifact_consumed is True
    assert import_evidence.transient_tags_are_identity is False
    assert import_evidence.ready_for_rebinding is True
    assert import_evidence.source_mesh_sha256 == remesh_evidence.output_mesh_sha256
    assert import_evidence.association_mode == "ROBUST_MULTI_INVARIANT_TRI6_TO_PERSISTENT_CAD_SIGNATURE_V1"

    ordered = sorted(inventory.faces, key=lambda f: f.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    support_binding, support_tri6 = bind_named_selection_to_owned_faces(step, support, inventory, expected_role="SUPPORT")
    load_binding, load_tri6 = bind_named_selection_to_owned_faces(step, load, inventory, expected_role="LOAD")
    assert support_binding.tri6_count == support_tri6.shape[0] > 0
    assert load_binding.tri6_count == load_tri6.shape[0] > 0


def test_importer_rejects_modified_or_wrongly_admitted_mesh_artifact(tmp_path):
    step, msh, evidence = _make_artifact(tmp_path)
    with pytest.raises(MshOwnershipImportError, match="ARTIFACT_SHA_MISMATCH"):
        import_tet10_ownership_from_msh(step, msh, expected_mesh_sha256="f" * 64)
    msh.write_bytes(msh.read_bytes() + b"\n# tampered\n")
    with pytest.raises(MshOwnershipImportError, match="ARTIFACT_SHA_MISMATCH"):
        import_tet10_ownership_from_msh(step, msh, expected_mesh_sha256=evidence.output_mesh_sha256)


def test_importer_fails_closed_on_ambiguous_persistent_identity(tmp_path, monkeypatch):
    step, msh, evidence = _make_artifact(tmp_path)
    import astermax.fea.msh_ownership_importer as module
    original = module.list_face_signatures

    def duplicated(path):
        faces = list(original(path))
        tag, sig = faces[0]
        faces.append((tag + 1000, sig))
        return tuple(faces)

    monkeypatch.setattr(module, "list_face_signatures", duplicated)
    with pytest.raises(MshOwnershipImportError, match="CAD_SIGNATURE_NOT_UNIQUE"):
        import_tet10_ownership_from_msh(step, msh, expected_mesh_sha256=evidence.output_mesh_sha256)
