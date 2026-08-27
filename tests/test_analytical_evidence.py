from __future__ import annotations

from math import pi, sqrt

import pytest

from astermax.credibility import EvidenceSource, EvidenceStatus
from astermax.fea.analytical_evidence import (
    AnalyticalEvidenceError,
    analytical_stress_evidence,
    axial_normal_stress_mpa,
    circular_torsion_max_shear_mpa,
    combined_principal_bending_circular_torsion_witness,
    principal_bending_normal_stress_mpa,
    von_mises_from_normal_and_shear_mpa,
)
from astermax.fea.section_evidence import PlanarSectionProperties


def _section(*, area: float, iu: float, iv: float, iuv: float, polar: float, sha: str = "a" * 64) -> PlanarSectionProperties:
    return PlanarSectionProperties(
        schema="AsterMaxPlanarSectionPropertiesV1",
        selection_id="fixture.section",
        source_sha256="b" * 64,
        face_signature_sha256="c" * 64,
        area_mm2=area,
        centroid_mm=(0.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        axis_u=(0.0, 1.0, 0.0),
        axis_v=(0.0, 0.0, 1.0),
        i_u_mm4=iu,
        i_v_mm4=iv,
        i_uv_mm4=iuv,
        principal_i_min_mm4=min(iu, iv),
        principal_i_max_mm4=max(iu, iv),
        polar_i_n_mm4=polar,
        polar_identity_relative_residual=0.0,
        method="INDEPENDENT_CLOSED_FORM_TEST_FIXTURE",
        section_sha256=sha,
    )


def _circle(radius_mm: float = 10.0) -> PlanarSectionProperties:
    area = pi * radius_mm**2
    inertia = pi * radius_mm**4 / 4.0
    return _section(area=area, iu=inertia, iv=inertia, iuv=0.0, polar=2.0 * inertia)


def test_axial_stress_uses_n_mm_mpa_contract() -> None:
    # 10 kN on 200 mm^2 = 50 N/mm^2 = 50 MPa.
    assert axial_normal_stress_mpa(10_000.0, 200.0) == pytest.approx(50.0)


def test_principal_bending_matches_rectangle_closed_form() -> None:
    # Rectangle b=20 mm, h=10 mm: Iu=b*h^3/12=1666.666... mm^4.
    # At v=+5 mm and Mu=100 N*m=100000 N*mm, |sigma|=M*c/I=300 MPa.
    sigma = principal_bending_normal_stress_mpa(
        moment_u_nmm=100_000.0,
        moment_v_nmm=0.0,
        u_mm=0.0,
        v_mm=5.0,
        i_u_mm4=20.0 * 10.0**3 / 12.0,
        i_v_mm4=10.0 * 20.0**3 / 12.0,
        i_uv_mm4=0.0,
    )
    assert sigma == pytest.approx(-300.0)


def test_bending_fails_closed_when_axes_are_not_principal() -> None:
    with pytest.raises(AnalyticalEvidenceError, match="REQUIRES_PRINCIPAL_AXES"):
        principal_bending_normal_stress_mpa(
            moment_u_nmm=1.0,
            moment_v_nmm=2.0,
            u_mm=3.0,
            v_mm=4.0,
            i_u_mm4=100.0,
            i_v_mm4=200.0,
            i_uv_mm4=1.0,
        )


def test_solid_circle_torsion_matches_closed_form() -> None:
    section = _circle(10.0)
    torque = 100_000.0
    tau, residual = circular_torsion_max_shear_mpa(torque, section)
    expected = 2.0 * torque / (pi * 10.0**3)
    assert residual < 1.0e-14
    assert tau == pytest.approx(expected, rel=1.0e-13)


def test_rectangular_section_is_rejected_by_circular_torsion_witness() -> None:
    b = 20.0
    h = 10.0
    rectangle = _section(
        area=b * h,
        iu=b * h**3 / 12.0,
        iv=h * b**3 / 12.0,
        iuv=0.0,
        polar=b * h**3 / 12.0 + h * b**3 / 12.0,
    )
    with pytest.raises(AnalyticalEvidenceError, match="CIRCULAR_TORSION_OUT_OF_DOMAIN"):
        circular_torsion_max_shear_mpa(100_000.0, rectangle)


def test_von_mises_combination_matches_independent_formula() -> None:
    assert von_mises_from_normal_and_shear_mpa(80.0, 30.0) == pytest.approx(
        sqrt(80.0**2 + 3.0 * 30.0**2)
    )


def test_combined_witness_is_deterministic_and_claim_grade() -> None:
    section = _circle(10.0)
    kwargs = dict(
        axial_force_n=10_000.0,
        moment_u_nmm=50_000.0,
        moment_v_nmm=0.0,
        u_mm=0.0,
        v_mm=10.0,
        torque_nmm=100_000.0,
    )
    first = combined_principal_bending_circular_torsion_witness(section, **kwargs)
    second = combined_principal_bending_circular_torsion_witness(section, **kwargs)

    expected_axial = 10_000.0 / (pi * 10.0**2)
    expected_bending = -(50_000.0 * 10.0) / (pi * 10.0**4 / 4.0)
    expected_tau = 2.0 * 100_000.0 / (pi * 10.0**3)
    expected_vm = sqrt((expected_axial + expected_bending) ** 2 + 3.0 * expected_tau**2)

    assert first.witness_sha256 == second.witness_sha256
    assert first.normal_stress_mpa == pytest.approx(expected_axial + expected_bending)
    assert first.shear_stress_mpa == pytest.approx(expected_tau)
    assert first.von_mises_mpa == pytest.approx(expected_vm)

    evidence = analytical_stress_evidence(first)
    assert evidence.status is EvidenceStatus.VERIFIED
    assert evidence.source is EvidenceSource.ANALYTICAL_WITNESS
    assert evidence.payload_sha256 == first.witness_sha256
    assert evidence.metadata["ansys_equivalence"] is False
    assert evidence.metadata["industrial_validation"] is False
