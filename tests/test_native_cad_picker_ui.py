from pathlib import Path

import numpy as np
import pytest

from astermax.fea.arbitrary_bc import prepare_arbitrary_bc_model, solve_arbitrary_bc_model
from astermax.fea.cad_face_picker import build_cad_face_picker_catalog
from astermax.fea.face_ownership import OwnedCadFaceTri6, Tet10FaceOwnershipInventory, mesh_step_tet10_with_face_ownership
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.native_cad_picker_ui import (
    NativeCadPickerUiError,
    build_native_picker_assignment,
    update_selected_face_ids,
)
from astermax.fea.persistent_geometry import list_face_signatures


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


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_3b_sloped_prism")
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


def _face_click(face) -> tuple[float, float]:
    tri = np.asarray(face.projected_triangles_px[0], dtype=float)
    point = tri.mean(axis=0)
    return float(point[0]), float(point[1])


def test_native_click_and_ctrl_click_selection_semantics_are_deterministic() -> None:
    catalog = build_cad_face_picker_catalog(_synthetic_inventory(), viewport_width_px=800, viewport_height_px=500)
    x1, y1 = _face_click(catalog.faces[0])
    x2, y2 = _face_click(catalog.faces[1])
    selected = update_selected_face_ids(catalog, tuple(), x1, y1, additive=False)
    assert selected == ("F001",)
    selected = update_selected_face_ids(catalog, selected, x2, y2, additive=True)
    assert selected == ("F001", "F002")
    selected = update_selected_face_ids(catalog, selected, x1, y1, additive=True)
    assert selected == ("F002",)


def test_native_picker_assignment_rejects_support_load_overlap(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    catalog = build_cad_face_picker_catalog(inventory)
    face_id = catalog.faces[0].face_id
    with pytest.raises(NativeCadPickerUiError, match="NATIVE_PICKER_SUPPORT_LOAD_OVERLAP"):
        build_native_picker_assignment(step, inventory, catalog, support_face_ids=(face_id,), load_face_ids=(face_id,))


def test_native_picker_sloped_load_preserves_exact_provenance_to_solver(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    catalog = build_cad_face_picker_catalog(inventory)
    sloped_sha = _sloped_signature(step)
    load_face = next(face for face in catalog.faces if face.signature_sha256 == sloped_sha)
    support_face = next(face for face in catalog.faces if face.signature_sha256 != sloped_sha)
    assignment = build_native_picker_assignment(
        step,
        inventory,
        catalog,
        support_face_ids=(support_face.face_id,),
        load_face_ids=(load_face.face_id,),
    )
    assert assignment.load_evidence.picked_signature_sha256 == (sloped_sha,)
    assert assignment.load_binding.face_signature_sha256 == (sloped_sha,)
    prepared = prepare_arbitrary_bc_model(
        step,
        mesh_size_mm=12.0,
        support_selection=assignment.support_selection,
        load_selection=assignment.load_selection,
    )
    solved = solve_arbitrary_bc_model(
        prepared,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    evidence = solved["solve_evidence"]
    assert evidence.support_binding_sha256 == assignment.support_binding.binding_sha256
    assert evidence.load_binding_sha256 == assignment.load_binding.binding_sha256
    assert evidence.converged is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False
