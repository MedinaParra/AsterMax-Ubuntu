import pytest

from astermax.fea.analytical_fem_verification import (
    axial_far_field_matrix,
    build_analytical_fem_verification_matrix,
    compare_scalar_qoi,
)


def test_axial_far_field_matrix_replays_verified_c13_scale() -> None:
    matrix = axial_far_field_matrix(
        source_step_sha256="step-c13",
        solve_evidence_sha256="solve-c13",
        analytical_chain_sha256="analytical-c13",
        force_n=1000.0,
        area_mm2=314.1592653589793,
        fem_sigma_x_mpa=3.1832397385244615,
        fem_von_mises_mpa=3.1904456854559844,
        fem_sigma_y_mpa=-0.007409519179450497,
        fem_sigma_z_mpa=-0.006979142494367693,
        fem_tau_xy_mpa=-1.1797190821960964e-05,
        fem_tau_yz_mpa=-4.733015481522408e-05,
        fem_tau_xz_mpa=7.028924957335053e-05,
        relative_limit=0.02,
    )
    assert matrix.status == "CORROBORATED"
    assert len(matrix.qois) == 7
    assert all(qoi.status == "PASS" for qoi in matrix.qois)
    assert matrix.qois[0].rel_error < 5.0e-5
    assert matrix.industrial_validation is False
    assert matrix.ansys_equivalence is False


def test_zero_reference_uses_physical_scale_floor() -> None:
    qoi = compare_scalar_qoi(
        qoi_id="SIGMA_Y_MEAN",
        analytical_value=0.0,
        fem_value=0.01,
        unit="MPa",
        abs_limit=0.02,
        rel_limit=0.02,
        scale_floor=1.0,
    )
    assert qoi.rel_error == pytest.approx(0.01)
    assert qoi.status == "PASS"


def test_failed_qoi_blocks_matrix_without_rounding_or_retuning() -> None:
    qoi = compare_scalar_qoi(
        qoi_id="SURFACE_QOI",
        analytical_value=100.0,
        fem_value=103.191148,
        unit="MPa",
        abs_limit=3.0,
        rel_limit=0.03,
        scale_floor=100.0,
    )
    assert qoi.rel_error == pytest.approx(0.03191148)
    assert qoi.status == "FAIL"
    matrix = build_analytical_fem_verification_matrix(
        [qoi],
        source_step_sha256="step",
        solve_evidence_sha256="solve",
        analytical_chain_sha256="analytical",
    )
    assert matrix.status == "BLOCKED"
    assert matrix.blockers == ("QOI_FAILED:SURFACE_QOI",)


def test_matrix_identity_is_deterministic_and_solve_bound() -> None:
    qoi = compare_scalar_qoi(qoi_id="A", analytical_value=1.0, fem_value=1.0, unit="MPa", abs_limit=0.1, rel_limit=0.1)
    a = build_analytical_fem_verification_matrix([qoi], source_step_sha256="step", solve_evidence_sha256="solve-a", analytical_chain_sha256="analytical")
    b = build_analytical_fem_verification_matrix([qoi], source_step_sha256="step", solve_evidence_sha256="solve-a", analytical_chain_sha256="analytical")
    c = build_analytical_fem_verification_matrix([qoi], source_step_sha256="step", solve_evidence_sha256="solve-b", analytical_chain_sha256="analytical")
    assert a.matrix_sha256 == b.matrix_sha256
    assert a.matrix_sha256 != c.matrix_sha256


def test_units_and_provenance_fail_closed() -> None:
    qoi = compare_scalar_qoi(qoi_id="A", analytical_value=1.0, fem_value=1.0, unit="MPa", abs_limit=0.1, rel_limit=0.1)
    with pytest.raises(ValueError, match="ANALYTICAL_FEM_PROVENANCE_REQUIRED"):
        build_analytical_fem_verification_matrix([qoi], source_step_sha256="", solve_evidence_sha256="solve", analytical_chain_sha256="analytical")
    with pytest.raises(ValueError, match="ANALYTICAL_FEM_UNITS_CONTRACT"):
        build_analytical_fem_verification_matrix([qoi], source_step_sha256="step", solve_evidence_sha256="solve", analytical_chain_sha256="analytical", stress_unit="Pa")


def test_duplicate_qoi_rejected() -> None:
    qoi = compare_scalar_qoi(qoi_id="A", analytical_value=1.0, fem_value=1.0, unit="MPa", abs_limit=0.1, rel_limit=0.1)
    with pytest.raises(ValueError, match="ANALYTICAL_FEM_DUPLICATE_QOI"):
        build_analytical_fem_verification_matrix([qoi, qoi], source_step_sha256="step", solve_evidence_sha256="solve", analytical_chain_sha256="analytical")


def test_no_validation_or_ansys_claim_can_be_promoted() -> None:
    matrix = axial_far_field_matrix(
        source_step_sha256="step", solve_evidence_sha256="solve", analytical_chain_sha256="analytical",
        force_n=1000.0, area_mm2=100.0,
        fem_sigma_x_mpa=10.0, fem_von_mises_mpa=10.0,
        fem_sigma_y_mpa=0.0, fem_sigma_z_mpa=0.0,
        fem_tau_xy_mpa=0.0, fem_tau_yz_mpa=0.0, fem_tau_xz_mpa=0.0,
    )
    text = (matrix.schema + " " + matrix.semantics).lower()
    assert matrix.industrial_validation is False
    assert matrix.ansys_equivalence is False
    assert "industrial_validation=true" not in text
    assert "ansys_equivalence=true" not in text
