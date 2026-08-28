from __future__ import annotations

from pathlib import Path

import gmsh  # type: ignore
import pytest

from astermax.fea.cad_axial_witness import cad_axial_stress_evidence, derive_cad_axial_stress_witness


def _write_box(path: Path, lx: float = 100.0, ly: float = 20.0, lz: float = 20.0) -> None:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c3_2_box")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, lx, ly, lz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_exact_step_area_drives_axial_reference(tmp_path: Path) -> None:
    step = tmp_path / "bar.step"
    _write_box(step)
    witness, section = derive_cad_axial_stress_witness(step, 40000.0, axis=0, end="MAX")
    assert section.area_mm2 == pytest.approx(400.0, rel=0.0, abs=1.0e-8)
    assert witness.area_mm2 == pytest.approx(400.0, rel=0.0, abs=1.0e-8)
    assert witness.analytical_sigma_mpa == pytest.approx(100.0, rel=0.0, abs=1.0e-9)
    assert witness.source_sha256 == section.source_sha256
    assert witness.section_sha256 == section.section_sha256


def test_changed_cross_section_changes_reference_without_dimension_literal(tmp_path: Path) -> None:
    step = tmp_path / "bar.step"
    _write_box(step, ly=25.0, lz=20.0)
    witness, _ = derive_cad_axial_stress_witness(step, 40000.0)
    assert witness.area_mm2 == pytest.approx(500.0, abs=1.0e-8)
    assert witness.analytical_sigma_mpa == pytest.approx(80.0, abs=1.0e-9)


def test_witness_hash_is_deterministic_and_claim_bounded(tmp_path: Path) -> None:
    step = tmp_path / "bar.step"
    _write_box(step)
    a, _ = derive_cad_axial_stress_witness(step, 40000.0)
    b, _ = derive_cad_axial_stress_witness(step, 40000.0)
    assert a.witness_sha256 == b.witness_sha256
    evidence = cad_axial_stress_evidence(a)
    assert evidence.metadata["ansys_equivalence"] is False
    assert evidence.metadata["industrial_validation"] is False
    assert evidence.metadata["area_mm2"] == pytest.approx(400.0)
