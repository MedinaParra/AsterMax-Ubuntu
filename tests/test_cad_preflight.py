from pathlib import Path

import pytest

from astermax.fea.cad_preflight import preflight_step
from astermax.fea.gmsh_bridge import GmshBridgeError, _gmsh


def _write_box(path: Path, boxes):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.model.add("fixture")
        for x, y, z, dx, dy, dz in boxes:
            gmsh.model.occ.addBox(x, y, z, dx, dy, dz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_preflight_certifies_simple_mm_box(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path, [(0, 0, 0, 100, 20, 10)])
    report = preflight_step(path)
    assert report.length_unit == "mm"
    assert report.occ_target_unit == "MM"
    assert report.solid_count == 1
    assert report.surface_count == 6
    assert report.dimensions_mm == pytest.approx((100, 20, 10), abs=1e-6)
    assert report.certified_single_solid_ready is True
    assert report.warnings == ()
    assert all(count == 1 for count in report.axis_scope_counts.values())
    payload = report.to_dict()
    assert payload["length_unit"] == "mm"
    assert payload["occ_target_unit"] == "MM"


def test_preflight_reports_multi_solid_without_mutating(tmp_path):
    path = tmp_path / "two.step"
    _write_box(path, [(0, 0, 0, 10, 10, 10), (20, 0, 0, 10, 10, 10)])
    report = preflight_step(path)
    assert report.solid_count == 2
    assert report.certified_single_solid_ready is False
    assert "MULTI_SOLID:2" in report.warnings


def test_preflight_rejects_non_step(tmp_path):
    path = tmp_path / "bad.txt"; path.write_text("not step", encoding="utf-8")
    with pytest.raises(GmshBridgeError):
        preflight_step(path)
