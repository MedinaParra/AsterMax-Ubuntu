from pathlib import Path

import pytest

from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import (
    PersistentGeometryError,
    capture_face_selection,
    list_face_signatures,
    resolve_face_selection,
    verify_face_selection_across_remesh,
)


def _write_box(path: Path, *, dx=100.0, dy=20.0, dz=10.0):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, dx, dy, dz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _face_at_x(path: Path, x: float) -> int:
    matches = []
    for tag, signature in list_face_signatures(path):
        if signature.center_mm[0] == pytest.approx(x, abs=1e-6):
            matches.append(tag)
    assert len(matches) == 1
    return matches[0]


def test_persistent_face_resolves_without_using_capture_tag_as_identity(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    tag = _face_at_x(path, 100.0)
    selection = capture_face_selection(path, tag, "LOAD_FACE")
    resolution = resolve_face_selection(path, selection)

    assert resolution.selection_id == "LOAD_FACE"
    assert resolution.signature_sha256 == selection.signature.sha256
    assert resolution.selection_sha256 == selection.selection_sha256
    assert selection.signature.center_mm == pytest.approx((100.0, 10.0, 5.0), abs=1e-6)
    assert selection.signature.area_mm2 == pytest.approx(200.0, rel=1e-9)


def test_face_identity_survives_multiple_remesh_sizes(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _face_at_x(path, 100.0), "LOAD_FACE")
    samples = verify_face_selection_across_remesh(path, selection, (20.0, 10.0, 5.0))

    assert len(samples) == 3
    assert all(sample.surface_node_count > 0 for sample in samples)
    assert all(sample.surface_element_count > 0 for sample in samples)
    assert len({sample.signature_sha256 for sample in samples}) == 1
    assert samples[0].surface_element_count != samples[-1].surface_element_count


def test_changed_step_bytes_cannot_silently_rebind_selection(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path, dx=100.0)
    selection = capture_face_selection(path, _face_at_x(path, 100.0), "LOAD_FACE")

    _write_box(path, dx=120.0)
    with pytest.raises(PersistentGeometryError, match="SOURCE_IDENTITY_MISMATCH"):
        resolve_face_selection(path, selection)


def test_signature_contains_geometric_and_topological_identity(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _face_at_x(path, 100.0), "LOAD_FACE")
    sig = selection.signature

    assert sig.surface_type
    assert sig.area_mm2 > 0.0
    assert len(sig.center_mm) == 3
    assert len(sig.bbox_mm) == 6
    assert len(sig.inertia_mm4) == 9
    assert sig.edge_count == 4
    assert sig.adjacent_volume_count == 1
    assert len(sig.sha256) == 64
    assert len(selection.selection_sha256) == 64


def test_invalid_or_missing_source_is_rejected(tmp_path):
    path = tmp_path / "not.step"
    path.write_text("not a STEP file", encoding="utf-8")
    with pytest.raises(Exception):
        list_face_signatures(path)
