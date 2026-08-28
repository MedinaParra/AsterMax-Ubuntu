from pathlib import Path

import numpy as np
import pytest

from astermax.fea.arbitrary_bc import prepare_arbitrary_bc_model, solve_arbitrary_bc_model
from astermax.fea.cad_face_picker import (
    CadFacePickerError,
    build_cad_face_picker_catalog,
    capture_picker_named_selection,
    pick_cad_face,
)
from astermax.fea.face_ownership import OwnedCadFaceTri6, Tet10FaceOwnershipInventory, mesh_step_tet10_with_face_ownership
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import list_face_signatures


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_3_sloped_prism")
        p1 = gmsh.model.occ.addPoint(0.0, 0.0, 0.0)
        p2 = gmsh.model.occ.addPoint(40.0, 0.0, 0.0)
        p3 = gmsh.model.occ.addPoint(0.0, 0.0, 20.0)
        l1 = gmsh.model.occ.addLine(p1, p2)
        l2 = gmsh.model.occ.addLine(p2, p3)
        l3 = gmsh.model.occ.addLine(p3, p1)
        loop = gmsh.model.occ.addCurveLoop([l1, l2, l3])
        face = gmsh.model.occ.addPlaneSurface([loop])
        gmsh.model.occ.extrude([(2, face)], 0.0, 12.0, 0.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _sloped_signature(step: Path) -> str:
    candidates = []
    for _tag, signature in list_face_signatures(step):
        bbox = signature.bbox_mm
        spans = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
        if np.count_nonzero(spans > 1.0) == 3:
            candidates.append(signature.sha256)
    assert len(candidates) == 1
    return candidates[0]


def _synthetic_inventory() -> Tet10FaceOwnershipInventory:
    nodes = np.asarray([
        [0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0],
        [30.0, 0.0, 0.0], [40.0, 0.0, 0.0], [30.0, 10.0, 0.0],
    ])
    tri_a = np.asarray([[0, 1, 2, 0, 1, 2]], dtype=np.int64)
    tri_b = np.asarray([[3, 4, 5, 3, 4, 5]], dtype=np.int64)
    faces = (
        OwnedCadFaceTri6(1, "a" * 64, "Plane", 50.0, (3.3, 3.3, 0.0), (0, 0, 0, 10, 10, 0), 1, tri_a),
        OwnedCadFaceTri6(2, "b" * 64, "Plane", 50.0, (33.3, 3.3, 0.0), (30, 0, 0, 40, 10, 0), 1, tri_b),
    )
    return Tet10FaceOwnershipInventory(
        schema="AsterMaxTet10FaceOwnershipInventoryV1",
        source_step_sha256="c" * 64,
        source_size_bytes=1,
        nodes_mm=nodes,
        elements=np.zeros((0, 10), dtype=np.int64),
        faces=faces,
        bbox_mm=(0, 0, 0, 40, 10, 1),
        dimensions_mm=(40, 10, 1),
        gmsh_version="test",
        ownership_sha256="d" * 64,
    )


def test_picker_catalog_and_hit_test_are_deterministic() -> None:
    inventory = _synthetic_inventory()
    first = build_cad_face_picker_catalog(inventory, viewport_width_px=800, viewport_height_px=500)
    second = build_cad_face_picker_catalog(inventory, viewport_width_px=800, viewport_height_px=500)
    assert first.catalog_sha256 == second.catalog_sha256
    assert tuple(face.face_id for face in first.faces) == ("F001", "F002")
    face = first.faces[0]
    tri = np.asarray(face.projected_triangles_px[0], dtype=float)
    click = tri.mean(axis=0)
    picked = pick_cad_face(first, float(click[0]), float(click[1]))
    assert picked.face_id == face.face_id
    assert picked.signature_sha256 == face.signature_sha256
    with pytest.raises(CadFacePickerError, match="CAD_FACE_PICK_MISS"):
        pick_cad_face(first, -1000.0, -1000.0)


def test_real_sloped_face_picker_binding_preserves_signature_and_tri6(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    catalog = build_cad_face_picker_catalog(inventory)
    sloped_sha = _sloped_signature(step)
    sloped = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    selection, binding, triangles, evidence = capture_picker_named_selection(
        step, inventory, catalog, (sloped.face_id,), name="Picked Sloped Load", role="LOAD"
    )
    assert selection.faces[0].signature_sha256 == sloped_sha
    assert binding.face_signature_sha256 == (sloped_sha,)
    assert evidence.picked_signature_sha256 == (sloped_sha,)
    assert evidence.binding_sha256 == binding.binding_sha256
    assert evidence.tri6_count == triangles.shape[0] > 0


def test_picker_support_and_sloped_load_drive_exact_production_solver_bindings(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    catalog = build_cad_face_picker_catalog(inventory)
    sloped_sha = _sloped_signature(step)
    load_face = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    support_face = next(face for face in catalog.faces if face.signature_sha256 != sloped_sha)
    support, support_binding, _support_tri, support_pick = capture_picker_named_selection(
        step, inventory, catalog, (support_face.face_id,), name="Picked Support", role="SUPPORT"
    )
    load, load_binding, _load_tri, load_pick = capture_picker_named_selection(
        step, inventory, catalog, (load_face.face_id,), name="Picked Sloped Load", role="LOAD"
    )
    prepared = prepare_arbitrary_bc_model(
        step, mesh_size_mm=12.0, support_selection=support, load_selection=load
    )
    assert prepared["support_binding"].face_signature_sha256 == support_pick.picked_signature_sha256
    assert prepared["load_binding"].face_signature_sha256 == load_pick.picked_signature_sha256
    assert prepared["support_binding"].binding_sha256 == support_binding.binding_sha256
    assert prepared["load_binding"].binding_sha256 == load_binding.binding_sha256
    solved = solve_arbitrary_bc_model(
        prepared,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    solve_evidence = solved["solve_evidence"]
    assert solve_evidence.support_binding_sha256 == support_binding.binding_sha256
    assert solve_evidence.load_binding_sha256 == load_binding.binding_sha256
    assert solve_evidence.converged is False
    assert solve_evidence.industrial_validation is False
    assert solve_evidence.ansys_equivalence is False


def test_picker_fails_closed_for_stale_catalog_and_unknown_face(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    catalog = build_cad_face_picker_catalog(inventory)
    with pytest.raises(CadFacePickerError, match="PICKER_FACE_ID_UNKNOWN"):
        capture_picker_named_selection(step, inventory, catalog, ("F999",), name="Bad", role="LOAD")
    step.write_bytes(step.read_bytes() + b"\n")
    with pytest.raises(CadFacePickerError, match="PICKER_SOURCE_IDENTITY_MISMATCH"):
        capture_picker_named_selection(step, inventory, catalog, (catalog.faces[0].face_id,), name="Stale", role="LOAD")
