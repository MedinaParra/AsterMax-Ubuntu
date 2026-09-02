import pytest

from astermax.code_aster_reference_mechanics import (
    CodeAsterReferenceError,
    ReferenceObservation,
    UniaxialPrismReference,
    verify_uniaxial_reference,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _reference():
    return UniaxialPrismReference(
        length_mm=100.0,
        width_mm=10.0,
        height_mm=10.0,
        young_mpa=200000.0,
        poisson=0.30,
        axial_force_n=1000.0,
    )


def test_closed_form_reference_is_dimensionally_consistent_mm_n_mpa():
    ref = _reference()
    assert ref.area_mm2 == pytest.approx(100.0)
    assert ref.axial_traction_mpa == pytest.approx(10.0)
    assert ref.axial_stress_mpa == pytest.approx(10.0)
    assert ref.axial_strain == pytest.approx(5.0e-5)
    assert ref.end_displacement_mm == pytest.approx(0.005)
    assert ref.transverse_strain == pytest.approx(-1.5e-5)
    ev = ref.evidence()
    assert ev["units_length"] == "mm"
    assert ev["units_force"] == "N"
    assert ev["units_stress"] == "MPa"
    assert ev["fea_solve_executed"] is False
    assert ev["numerical_verification"] is False
    assert ev["industrial_validation"] is False
    assert ev["ansys_equivalence"] is False
    assert len(ev["reference_sha256"]) == 64


def test_observation_without_real_solve_evidence_is_rejected():
    ref = _reference()
    fake = ReferenceObservation(
        end_displacement_mm=ref.end_displacement_mm,
        support_reaction_x_n=-ref.axial_force_n,
        axial_stress_mpa=ref.axial_stress_mpa,
        result_med_sha256=SHA_A,
        solve_evidence_sha256=SHA_B,
        fea_solve_executed=False,
    )
    with pytest.raises(CodeAsterReferenceError, match="REQUIRES_REAL_SOLVE_EVIDENCE"):
        verify_uniaxial_reference(ref, fake)


def test_gate_logic_accepts_in_tolerance_observation_but_is_only_software_test():
    # This is deliberately synthetic data used to test gate logic. It is not a
    # Code_Aster solve and must never be reported as solver-validation evidence.
    ref = _reference()
    obs = ReferenceObservation(
        end_displacement_mm=0.00505,
        support_reaction_x_n=-999.0,
        axial_stress_mpa=10.05,
        result_med_sha256=SHA_A,
        solve_evidence_sha256=SHA_B,
        fea_solve_executed=True,
    )
    out = verify_uniaxial_reference(ref, obs)
    assert out.sign_pass is True
    assert out.displacement_pass is True
    assert out.reaction_pass is True
    assert out.stress_pass is True
    assert out.numerical_verification is True
    assert out.results_verified is True
    assert out.industrial_validation is False
    assert out.ansys_equivalence is False


def test_reaction_imbalance_fails_numerical_verification():
    ref = _reference()
    obs = ReferenceObservation(
        end_displacement_mm=ref.end_displacement_mm,
        support_reaction_x_n=-950.0,
        axial_stress_mpa=ref.axial_stress_mpa,
        result_med_sha256=SHA_A,
        solve_evidence_sha256=SHA_B,
        fea_solve_executed=True,
    )
    out = verify_uniaxial_reference(ref, obs)
    assert out.reaction_pass is False
    assert out.numerical_verification is False
    assert out.results_verified is False


def test_wrong_sign_fails_even_if_absolute_magnitudes_match():
    ref = _reference()
    obs = ReferenceObservation(
        end_displacement_mm=-ref.end_displacement_mm,
        support_reaction_x_n=ref.axial_force_n,
        axial_stress_mpa=-ref.axial_stress_mpa,
        result_med_sha256=SHA_A,
        solve_evidence_sha256=SHA_B,
        fea_solve_executed=True,
    )
    out = verify_uniaxial_reference(ref, obs)
    assert out.sign_pass is False
    assert out.numerical_verification is False
