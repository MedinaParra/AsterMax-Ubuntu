from pathlib import Path

import pytest

from astermax.fea.circular_section import prove_solid_circular_section
from astermax.fea.circular_torsion import (
    CircularTorsionError,
    build_circular_torsion_witness,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import capture_face_selection, list_face_signatures
from astermax.fea.section_evidence import planar_section_properties


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


def _end_face(path: Path, x=40.0):
    matches = [
        tag for tag, sig in list_face_signatures(path)
        if sig.surface_type.strip().lower() == "plane" and sig.center_mm[0] == pytest.approx(x, abs=1e-6)
    ]
    assert len(matches) == 1
    return matches[0]


def _fixture(tmp_path):
    path = tmp_path / "cylinder.step"
    _write_cylinder(path)
    selection = capture_face_selection(path, _end_face(path), "TORSION_SECTION")
    section = planar_section_properties(path, selection)
    applicability = prove_solid_circular_section(path, selection)
    return section, applicability


def test_torsion_witness_recovers_declared_torque(tmp_path):
    section, applicability = _fixture(tmp_path)
    witness = build_circular_torsion_witness(
        section,
        applicability,
        torque_nmm=125000.0,
    )
    assert witness.reconstructed_torque_nmm == pytest.approx(125000.0, rel=1e-14)
    assert witness.torque_relative_residual <= 1e-14
    assert witness.tau_max_mpa == pytest.approx(
        abs(witness.torque_nmm) * applicability.radius_mm / section.polar_i_n_mm4,
        rel=1e-14,
    )


def test_torsion_witness_is_deterministic(tmp_path):
    section, applicability = _fixture(tmp_path)
    first = build_circular_torsion_witness(section, applicability, torque_nmm=-9876.5)
    second = build_circular_torsion_witness(section, applicability, torque_nmm=-9876.5)
    assert first == second
    assert first.witness_sha256 == second.witness_sha256


def test_nonfinite_torque_is_rejected(tmp_path):
    section, applicability = _fixture(tmp_path)
    with pytest.raises(CircularTorsionError, match="must be finite"):
        build_circular_torsion_witness(section, applicability, torque_nmm=float("nan"))
