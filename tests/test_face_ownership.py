from pathlib import Path

import numpy as np
import pytest

from astermax.fea.face_ownership import (
    FaceOwnershipError,
    bind_named_selection_to_owned_faces,
    mesh_step_tet10_with_face_ownership,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.persistent_geometry import list_face_signatures


def _write_sloped_prism(path: Path) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c5_2_sloped_prism")
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


def _sloped_face_tag(step: Path) -> int:
    candidates = []
    for tag, signature in list_face_signatures(step):
        bbox = signature.bbox_mm
        spans = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
        # OCC expands planar face bounding boxes by a small geometric tolerance.
        # Use a fixture-scale threshold so only the genuinely sloped rectangular
        # face spans all three macroscopic directions (40 x 12 x 20 mm).
        if np.count_nonzero(spans > 1.0) == 3:
            candidates.append(tag)
    assert len(candidates) == 1
    return candidates[0]


def test_arbitrary_sloped_cad_face_owns_real_tri6(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    sloped_tag = _sloped_face_tag(step)
    selection = capture_named_selection(step, (sloped_tag,), "Sloped Load", "LOAD")
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    binding, triangles = bind_named_selection_to_owned_faces(step, selection, inventory, expected_role="LOAD")
    assert binding.face_signature_sha256 == (selection.faces[0].signature_sha256,)
    assert binding.tri6_count == triangles.shape[0] > 0
    assert triangles.shape[1] == 6
    assert binding.ownership_sha256 == inventory.ownership_sha256


def test_all_meshed_cad_faces_have_unique_persistent_ownership(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    signatures = [face.signature_sha256 for face in inventory.faces]
    assert len(inventory.faces) == 5
    assert len(signatures) == len(set(signatures))
    assert all(face.tri6_count > 0 and face.triangles.shape[1] == 6 for face in inventory.faces)


def test_multiface_binding_is_deterministic_without_axis_keys(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    tags = tuple(face.face_tag for face in inventory.faces[:2])
    selection = capture_named_selection(step, tags, "Two Faces", "SUPPORT")
    first, tri_first = bind_named_selection_to_owned_faces(step, selection, inventory, expected_role="SUPPORT")
    second, tri_second = bind_named_selection_to_owned_faces(step, selection, inventory, expected_role="SUPPORT")
    assert first.binding_sha256 == second.binding_sha256
    assert first.face_signature_sha256 == tuple(face.signature_sha256 for face in selection.faces)
    assert np.array_equal(tri_first, tri_second)


def test_wrong_role_and_changed_step_fail_closed(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    inventory = mesh_step_tet10_with_face_ownership(step, 12.0)
    selection = capture_named_selection(step, (inventory.faces[0].face_tag,), "Support", "SUPPORT")
    with pytest.raises(FaceOwnershipError, match="role"):
        bind_named_selection_to_owned_faces(step, selection, inventory, expected_role="LOAD")
    step.write_bytes(step.read_bytes() + b"\n")
    with pytest.raises(FaceOwnershipError, match="SOURCE_IDENTITY_MISMATCH"):
        bind_named_selection_to_owned_faces(step, selection, inventory, expected_role="SUPPORT")


def test_inventory_hash_is_deterministic_across_remesh_of_same_step(tmp_path: Path) -> None:
    step = tmp_path / "sloped.step"; _write_sloped_prism(step)
    first = mesh_step_tet10_with_face_ownership(step, 12.0)
    second = mesh_step_tet10_with_face_ownership(step, 12.0)
    assert first.ownership_sha256 == second.ownership_sha256
    assert tuple(face.signature_sha256 for face in first.faces) == tuple(face.signature_sha256 for face in second.faces)
