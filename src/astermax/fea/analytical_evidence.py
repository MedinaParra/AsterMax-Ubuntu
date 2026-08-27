from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi, sqrt
from typing import Any

import numpy as np

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .section_evidence import PlanarSectionProperties


class AnalyticalEvidenceError(ValueError):
    pass


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise AnalyticalEvidenceError(f"{name} must be finite")
    return result


def _positive(name: str, value: float) -> float:
    result = _finite(name, value)
    if result <= 0.0:
        raise AnalyticalEvidenceError(f"{name} must be positive")
    return result


@dataclass(frozen=True)
class AnalyticalStressWitness:
    schema: str
    section_sha256: str
    method: str
    normal_stress_mpa: float
    shear_stress_mpa: float
    von_mises_mpa: float
    inputs: dict[str, Any]
    assumptions: tuple[str, ...]
    witness_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("witness_sha256")
        payload["assumptions"] = list(self.assumptions)
        return payload


def axial_normal_stress_mpa(force_n: float, area_mm2: float) -> float:
    return _finite("force_n", force_n) / _positive("area_mm2", area_mm2)


def principal_bending_normal_stress_mpa(
    *,
    moment_u_nmm: float,
    moment_v_nmm: float,
    u_mm: float,
    v_mm: float,
    i_u_mm4: float,
    i_v_mm4: float,
    i_uv_mm4: float = 0.0,
    principal_axis_relative_tolerance: float = 1.0e-10,
) -> float:
    """Normal stress for bending about declared local principal axes.

    Sign convention: +Mu produces compression at +v and +Mv produces tension at +u.
    The function intentionally fails closed when the supplied axes are not principal;
    general unsymmetric bending belongs to a later C2 gate.
    """
    mu = _finite("moment_u_nmm", moment_u_nmm)
    mv = _finite("moment_v_nmm", moment_v_nmm)
    u = _finite("u_mm", u_mm)
    v = _finite("v_mm", v_mm)
    iu = _positive("i_u_mm4", i_u_mm4)
    iv = _positive("i_v_mm4", i_v_mm4)
    iuv = _finite("i_uv_mm4", i_uv_mm4)
    tol = _positive("principal_axis_relative_tolerance", principal_axis_relative_tolerance)
    scale = max(iu, iv)
    if abs(iuv) > tol * scale:
        raise AnalyticalEvidenceError("BENDING_WITNESS_REQUIRES_PRINCIPAL_AXES")
    return -(mu * v / iu) + (mv * u / iv)


def circular_torsion_max_shear_mpa(
    torque_nmm: float,
    section: PlanarSectionProperties,
    *,
    circularity_relative_tolerance: float = 1.0e-6,
) -> tuple[float, float]:
    """Saint-Venant torsion witness for a solid circular section only.

    Radius is independently inferred from CAD area and the CAD polar second moment
    must match pi*r^4/2 within the declared tolerance. Non-circular sections fail
    closed rather than receiving a circular-shaft approximation.
    """
    torque = _finite("torque_nmm", torque_nmm)
    area = _positive("section.area_mm2", section.area_mm2)
    polar = _positive("section.polar_i_n_mm4", section.polar_i_n_mm4)
    tol = _positive("circularity_relative_tolerance", circularity_relative_tolerance)
    radius = sqrt(area / pi)
    expected_polar = 0.5 * pi * radius**4
    residual = abs(polar - expected_polar) / max(abs(polar), abs(expected_polar), 1.0e-30)
    if residual > tol:
        raise AnalyticalEvidenceError(f"CIRCULAR_TORSION_OUT_OF_DOMAIN:{residual:.17g}")
    return torque * radius / polar, residual


def von_mises_from_normal_and_shear_mpa(normal_stress_mpa: float, shear_stress_mpa: float) -> float:
    sigma = _finite("normal_stress_mpa", normal_stress_mpa)
    tau = _finite("shear_stress_mpa", shear_stress_mpa)
    return sqrt(sigma * sigma + 3.0 * tau * tau)


def combined_principal_bending_circular_torsion_witness(
    section: PlanarSectionProperties,
    *,
    axial_force_n: float,
    moment_u_nmm: float,
    moment_v_nmm: float,
    u_mm: float,
    v_mm: float,
    torque_nmm: float,
    principal_axis_relative_tolerance: float = 1.0e-10,
    circularity_relative_tolerance: float = 1.0e-6,
) -> AnalyticalStressWitness:
    axial = axial_normal_stress_mpa(axial_force_n, section.area_mm2)
    bending = principal_bending_normal_stress_mpa(
        moment_u_nmm=moment_u_nmm,
        moment_v_nmm=moment_v_nmm,
        u_mm=u_mm,
        v_mm=v_mm,
        i_u_mm4=section.i_u_mm4,
        i_v_mm4=section.i_v_mm4,
        i_uv_mm4=section.i_uv_mm4,
        principal_axis_relative_tolerance=principal_axis_relative_tolerance,
    )
    tau, circularity_residual = circular_torsion_max_shear_mpa(
        torque_nmm,
        section,
        circularity_relative_tolerance=circularity_relative_tolerance,
    )
    sigma = axial + bending
    vm = von_mises_from_normal_and_shear_mpa(sigma, tau)
    assumptions = (
        "small_deformation_linear_elastic_mechanics",
        "section_axes_are_principal",
        "solid_circular_section_for_torsion",
        "stress_point_uses_declared_local_section_coordinates",
        "no_stress_concentration_or_notch_factor",
    )
    payload = {
        "schema": "AsterMaxAnalyticalStressWitnessV1",
        "section_sha256": section.section_sha256,
        "method": "LINEAR_ELASTIC_AXIAL_PLUS_PRINCIPAL_BENDING_PLUS_SOLID_CIRCULAR_SAINT_VENANT_TORSION",
        "normal_stress_mpa": sigma,
        "shear_stress_mpa": tau,
        "von_mises_mpa": vm,
        "inputs": {
            "axial_force_n": float(axial_force_n),
            "moment_u_nmm": float(moment_u_nmm),
            "moment_v_nmm": float(moment_v_nmm),
            "u_mm": float(u_mm),
            "v_mm": float(v_mm),
            "torque_nmm": float(torque_nmm),
            "circularity_relative_residual": circularity_residual,
        },
        "assumptions": list(assumptions),
    }
    return AnalyticalStressWitness(
        schema=payload["schema"],
        section_sha256=payload["section_sha256"],
        method=payload["method"],
        normal_stress_mpa=payload["normal_stress_mpa"],
        shear_stress_mpa=payload["shear_stress_mpa"],
        von_mises_mpa=payload["von_mises_mpa"],
        inputs=payload["inputs"],
        assumptions=assumptions,
        witness_sha256=canonical_sha256(payload),
    )


def analytical_stress_evidence(witness: AnalyticalStressWitness) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"ANALYTICAL_STRESS:{witness.witness_sha256[:24]}",
        kind="ANALYTICAL_STRESS_WITNESS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description=(
            "Closed-form linear-elastic stress witness derived from CAD section evidence "
            "within an explicitly bounded analytical domain."
        ),
        payload_sha256=witness.witness_sha256,
        metadata={
            "section_sha256": witness.section_sha256,
            "method": witness.method,
            "normal_stress_mpa": witness.normal_stress_mpa,
            "shear_stress_mpa": witness.shear_stress_mpa,
            "von_mises_mpa": witness.von_mises_mpa,
            "assumptions": list(witness.assumptions),
            "ansys_equivalence": False,
            "industrial_validation": False,
        },
    )
