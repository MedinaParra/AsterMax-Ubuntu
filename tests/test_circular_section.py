from pathlib import Path

import pytest

from astermax.fea.circular_section import prove_solid_circular_section
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import (
    PersistentGeometryError,
    capture_face_selection,
    list_face_signatures,
)


def _write_cylinder(path: Path, radius=10.0, length=40.0):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cylinder")
        gmsh.model.occ.addCylinder(0, 0, 0, length, 0, 0, radius)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _write_box(path: Path):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("box")
        gmsh.model.occ.addBox(0, 0, 0, 40, 20, 10)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _planar_face_at_x(path: Path, x: float) -> int:
    matches = []
    for tag, sig in list_face_signatures(path):
        if sig.surface_type.strip().lower() == "plane" and sig.center_mm[0] == pytest.approx(x, abs=1e-6):
            matches.append(tag)
    assert len(matches) == 1
    return matches[0]


def test_solid_circular_step_face_is_proven_in_domain(tmp_path):
    path = tmp_path / "cylinder.step"
    _write_cylinder(path)
    selection = capture_face_selection(path, _planar_face_at_x(path, 40.0), "TORSION_SECTION")
    result = prove_solid_circular_section(path, selection)

    assert result.radius_mm == pytest.approx(10.0, rel=1e-8)
    assert result.boundary_curve_count == 1
    assert tuple(x.lower() for x in result.boundary_curve_types) == ("circle",)
    assert result.inertia_isotropy_relative_residual <= 1e-8
    assert result.product_inertia_relative_residual <= 1e-8
    assert result.circular_polar_identity_relative_residual <= 1e-8


def test_rectangular_face_is_rejected_before_torsion_formula(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _planar_face_at_x(path, 40.0), "NOT_A_CIRCLE")
    with pytest.raises(PersistentGeometryError, match="CIRCULAR_SECTION_OUT_OF_DOMAIN_BOUNDARY"):
        prove_solid_circular_section(path, selection)
