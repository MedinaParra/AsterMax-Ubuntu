from dataclasses import replace
from pathlib import Path

import pytest

from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.named_selections import (
    NamedSelectionError,
    capture_named_selection,
    resolve_named_selection,
)
from astermax.fea.persistent_geometry import PersistentGeometryError, list_face_signatures


def _write_box(path: Path, *, dx=100.0, dy=20.0, dz=10.0):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("named_selection_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, dx, dy, dz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _face_at(path: Path, axis: int, value: float) -> int:
    matches = [
        tag for tag, sig in list_face_signatures(path)
        if sig.center_mm[axis] == pytest.approx(value, abs=1e-6)
        and sig.bbox_mm[axis] == pytest.approx(value, abs=1e-6)
        and sig.bbox_mm[axis + 3] == pytest.approx(value, abs=1e-6)
    ]
    assert len(matches) == 1
    return matches[0]


def test_single_face_named_selection_resolves_exact_step(tmp_path):
    step = tmp_path / "box.step"; _write_box(step)
    selection = capture_named_selection(step, [_face_at(step, 0, 100.0)], "End Load", "load")
    resolution = resolve_named_selection(step, selection)

    assert selection.role == "LOAD"
    assert selection.face_count == 1
    assert resolution.named_selection_sha256 == selection.named_selection_sha256
    assert resolution.face_signature_sha256 == (selection.faces[0].signature_sha256,)
    assert len(resolution.resolution_sha256) == 64


def test_multiface_named_selection_is_deterministic_and_ordered(tmp_path):
    step = tmp_path / "box.step"; _write_box(step)
    tags = [_face_at(step, 0, 0.0), _face_at(step, 1, 0.0)]
    a = capture_named_selection(step, tags, "Fixture Faces", "SUPPORT")
    b = capture_named_selection(step, tags, "Fixture Faces", "SUPPORT")

    assert a.named_selection_sha256 == b.named_selection_sha256
    assert [face.signature_sha256 for face in a.faces] == [face.signature_sha256 for face in b.faces]
    assert resolve_named_selection(step, a).resolved_tags == resolve_named_selection(step, b).resolved_tags


def test_changed_step_cannot_rebind_named_selection(tmp_path):
    step = tmp_path / "box.step"; _write_box(step, dx=100.0)
    selection = capture_named_selection(step, [_face_at(step, 0, 100.0)], "Load", "LOAD")
    _write_box(step, dx=120.0)

    with pytest.raises(PersistentGeometryError, match="SOURCE_IDENTITY_MISMATCH"):
        resolve_named_selection(step, selection)


def test_tampered_named_selection_identity_fails_closed(tmp_path):
    step = tmp_path / "box.step"; _write_box(step)
    selection = capture_named_selection(step, [_face_at(step, 0, 100.0)], "Load", "LOAD")
    tampered = replace(selection, named_selection_sha256="0" * 64)

    with pytest.raises(NamedSelectionError, match="identity was tampered"):
        resolve_named_selection(step, tampered)


def test_invalid_role_and_duplicate_faces_are_rejected(tmp_path):
    step = tmp_path / "box.step"; _write_box(step)
    tag = _face_at(step, 0, 100.0)
    with pytest.raises(NamedSelectionError, match="role must"):
        capture_named_selection(step, [tag], "Load", "MAGIC")
    with pytest.raises(NamedSelectionError, match="duplicate"):
        capture_named_selection(step, [tag, tag], "Load", "LOAD")
