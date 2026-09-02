from pathlib import Path

import pytest

from astermax.code_aster_result_contract import (
    CodeAsterResultContractError,
    ResultTableSpec,
    parse_reference_result_tables,
    render_reference_export,
    render_reference_linear_static_comm,
)
from astermax.code_aster_study import LinearStaticStudy


def _study() -> LinearStaticStudy:
    return LinearStaticStudy(
        mesh_filename="astermax.med",
        support_group="FIXED_FACE",
        load_group="LOAD_FACE",
        young_mpa=210000.0,
        poisson=0.0,
        traction_mpa=(50.0, 0.0, 0.0),
    )


def test_comm_requests_solver_fields_and_auditable_scalar_tables():
    comm = render_reference_linear_static_comm(_study())
    assert "FORCE=('REAC_NODA',)" in comm
    assert "CONTRAINTE=('SIGM_ELNO', 'SIGM_NOEU')" in comm
    assert "CRITERES=('SIEQ_ELNO', 'SIEQ_NOEU')" in comm
    assert "GROUP_NO='LOAD_FACE'" in comm
    assert "GROUP_NO='FIXED_FACE'" in comm
    assert "RESULTANTE=('DX','DY','DZ')" in comm
    assert "NOM_CHAM='SIGM_NOEU'" in comm
    assert "NOM_CMP='SIXX'" in comm
    assert "REFERENCE_MEAN_SIXX" in comm
    assert "IMPR_TABLE(TABLE=displ" in comm and "UNITE=91" in comm
    assert "IMPR_TABLE(TABLE=reaction" in comm and "UNITE=92" in comm
    assert "IMPR_TABLE(TABLE=stress" in comm and "UNITE=93" in comm
    assert "DEFI_FICHIER" not in comm
    assert "NOM_CHAM=('DEPL','SIGM_ELNO','SIGM_NOEU','SIEQ_ELNO','SIEQ_NOEU','REAC_NODA')" in comm


def test_export_binds_all_verification_files_to_logical_units():
    export = render_reference_export()
    assert "F comm astermax.comm D 1" in export
    assert "F libr astermax.med D 20" in export
    assert "F rmed astermax_result.med R 80" in export
    assert "F libr reference_displacement.table R 91" in export
    assert "F libr reference_reaction.table R 92" in export
    assert "F libr reference_stress.table R 93" in export


def test_table_contract_rejects_reserved_or_duplicate_units():
    with pytest.raises(CodeAsterResultContractError, match="LOGICAL_UNITS_INVALID"):
        ResultTableSpec(displacement_unit=80).validate()
    with pytest.raises(CodeAsterResultContractError, match="LOGICAL_UNITS_INVALID"):
        ResultTableSpec(displacement_unit=91, reaction_unit=91).validate()


def test_parser_accepts_fortran_d_exponents_and_exactly_one_row(tmp_path: Path):
    disp = tmp_path / "d.table"
    reac = tmp_path / "r.table"
    stress = tmp_path / "s.table"
    disp.write_text("# witness\nINTITULE;MOYENNE\nLOAD_FACE_MEAN_UX;2.500000000000D-02\n", encoding="utf-8")
    reac.write_text("INTITULE;RESULT_X;RESULT_Y;RESULT_Z\nSUPPORT_REACTION;-1.000000000000D+04;0;0\n", encoding="utf-8")
    stress.write_text("INTITULE;MOYENNE\nREFERENCE_MEAN_SIXX;5.000000000000D+01\n", encoding="utf-8")
    metrics = parse_reference_result_tables(disp, reac, stress)
    assert metrics.load_face_mean_ux_mm == pytest.approx(0.025)
    assert metrics.support_reaction_x_n == pytest.approx(-10000.0)
    assert metrics.axial_stress_mpa == pytest.approx(50.0)


def test_parser_fails_closed_on_multiple_rows(tmp_path: Path):
    disp = tmp_path / "d.table"
    reac = tmp_path / "r.table"
    stress = tmp_path / "s.table"
    disp.write_text("INTITULE;MOYENNE\nA;0.025\nB;0.026\n", encoding="utf-8")
    reac.write_text("INTITULE;RESULT_X\nR;-10000\n", encoding="utf-8")
    stress.write_text("INTITULE;MOYENNE\nS;50\n", encoding="utf-8")
    with pytest.raises(CodeAsterResultContractError, match="ROW_NOT_UNIQUE"):
        parse_reference_result_tables(disp, reac, stress)


def test_comm_does_not_claim_runtime_or_results_verification():
    comm = render_reference_linear_static_comm(_study())
    assert "fea_solve_executed" not in comm
    assert "results_verified" not in comm
