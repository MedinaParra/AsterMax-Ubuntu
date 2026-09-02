from __future__ import annotations

import json
from pathlib import Path

import pytest

from astermax.code_aster_study import (
    CodeAsterStudyError,
    LinearStaticStudy,
    render_linear_static_comm,
    study_sha256,
    write_study_bundle,
)


def _study(**overrides):
    values = dict(
        mesh_filename="model.med",
        support_group="FIXED_FACE",
        load_group="LOAD_FACE",
        young_mpa=210000.0,
        poisson=0.3,
        traction_mpa=(0.0, -2.5, 0.0),
    )
    values.update(overrides)
    return LinearStaticStudy(**values)


def test_comm_is_deterministic_and_uses_mm_n_mpa_contract():
    first = render_linear_static_comm(_study())
    second = render_linear_static_comm(_study())
    assert first == second
    assert "Unit contract: mm / N / MPa" in first
    assert "LIRE_MAILLAGE(FORMAT='MED', UNITE=20)" in first
    assert "MODELISATION='3D'" in first
    assert "E=210000" in first
    assert "NU=0.29999999999999999" in first
    assert "GROUP_MA='FIXED_FACE'" in first
    assert "GROUP_MA='LOAD_FACE'" in first
    assert "FY=-2.5" in first
    assert "MECA_STATIQUE" in first
    assert "NOM_CHAM=('DEPL', 'SIGM_ELNO', 'SIEQ_ELNO')" in first


def test_surface_load_is_explicitly_traction_not_total_force():
    text = render_linear_static_comm(_study())
    assert "FORCE_FACE" in text
    assert "traction in N/mm^2 (= MPa), not total N" in text
    assert "FORCE_NODALE" not in text


def test_units_fail_closed():
    with pytest.raises(CodeAsterStudyError, match="UNITS_MUST_BE_MM_N_MPA"):
        _study(units_length="m").validate()


def test_invalid_groups_and_mesh_fail_closed():
    with pytest.raises(CodeAsterStudyError, match="MESH_MUST_BE_LOCAL_MED"):
        _study(mesh_filename="../model.med").validate()
    with pytest.raises(CodeAsterStudyError, match="INVALID_SUPPORT_GROUP"):
        _study(support_group="bad group").validate()
    with pytest.raises(CodeAsterStudyError, match="GROUPS_MUST_DIFFER"):
        _study(load_group="FIXED_FACE").validate()


def test_material_and_load_validation_fail_closed():
    with pytest.raises(CodeAsterStudyError, match="YOUNG_MUST_BE_POSITIVE"):
        _study(young_mpa=0.0).validate()
    with pytest.raises(CodeAsterStudyError, match="POISSON_OUT_OF_RANGE"):
        _study(poisson=0.5).validate()
    with pytest.raises(CodeAsterStudyError, match="TRACTION_ZERO"):
        _study(traction_mpa=(0.0, 0.0, 0.0)).validate()


def test_bundle_records_non_solve_evidence(tmp_path: Path):
    study = _study()
    evidence = write_study_bundle(study, tmp_path)
    assert (tmp_path / "astermax.comm").is_file()
    stored = json.loads((tmp_path / "study_evidence.json").read_text(encoding="utf-8"))
    assert stored == evidence
    assert evidence["study_sha256"] == study_sha256(study)
    assert evidence["load_representation"] == "SURFACE_TRACTION_N_PER_MM2"
    assert evidence["fea_solve_executed"] is False
    assert evidence["results_verified"] is False
