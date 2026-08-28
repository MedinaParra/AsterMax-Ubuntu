from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .section_evidence import PlanarSectionProperties


class AnalyticalWitnessError(ValueError):
    pass


@dataclass(frozen=True)
class LinearNormalStressWitness:
    schema: str
    selection_id: str
    section_sha256: str
    axial_force_n: float
    moment_u_nmm: float
    moment_v_nmm: float
    sigma0_mpa: float
    gradient_u_mpa_per_mm: float
    gradient_v_mpa_per_mm: float
    inertia_determinant_mm8: float
    inertia_condition_indicator: float
    reconstructed_axial_force_n: float
    reconstructed_moment_u_nmm: float
    reconstructed_moment_v_nmm: float
    axial_force_relative_residual: float
    moment_u_relative_residual: float
    moment_v_relative_residual: float
    max_relative_resultant_residual: float
    convention: str
    method: str
    witness_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("witness_sha256")
        return payload


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise AnalyticalWitnessError(f"{name} must be finite")
    return result


def _relative_residual(actual: float, target: float) -> float:
    return abs(actual - target) / max(abs(target), 1.0)


def _validate_section(section: PlanarSectionProperties) -> tuple[float, float]:
    area = _finite("area_mm2", section.area_mm2)
    i_u = _finite("i_u_mm4", section.i_u_mm4)
    i_v = _finite("i_v_mm4", section.i_v_mm4)
    i_uv = _finite("i_uv_mm4", section.i_uv_mm4)
    if area <= 0.0 or i_u <= 0.0 or i_v <= 0.0:
        raise AnalyticalWitnessError("ANALYTICAL_SECTION_WITNESS_INVALID_SECTION")

    determinant = i_u * i_v - i_uv * i_uv
    scale = i_u * i_v
    condition_indicator = determinant / scale if scale > 0.0 else float("nan")
    if (
        not math.isfinite(determinant)
        or not math.isfinite(condition_indicator)
        or determinant <= 0.0
        or condition_indicator <= 1.0e-12
    ):
        raise AnalyticalWitnessError("ANALYTICAL_SECTION_WITNESS_SINGULAR_INERTIA")
    return determinant, condition_indicator


def build_linear_normal_stress_witness(
    section: PlanarSectionProperties,
    *,
    axial_force_n: float,
    moment_u_nmm: float,
    moment_v_nmm: float,
    max_relative_resultant_residual: float = 1.0e-12,
) -> LinearNormalStressWitness:
    """Build an axial + general biaxial bending witness on a verified planar section.

    Local convention uses the right-handed section basis (u, v, n) from C1 and
    normal traction sigma*n. The field is
        sigma(u,v) = sigma0 + a*u + b*v
    with section resultants
        N   = integral sigma dA
        M_u = integral v*sigma dA
        M_v = -integral u*sigma dA.

    C1 stores I_u=integral(v^2)dA, I_v=integral(u^2)dA and
    I_uv=integral(u*v)dA. Solving these equations supports non-principal axes
    without silently assuming I_uv=0.
    """
    determinant, condition_indicator = _validate_section(section)
    n_force = _finite("axial_force_n", axial_force_n)
    m_u = _finite("moment_u_nmm", moment_u_nmm)
    m_v = _finite("moment_v_nmm", moment_v_nmm)
    tolerance = _finite("max_relative_resultant_residual", max_relative_resultant_residual)
    if tolerance <= 0.0:
        raise AnalyticalWitnessError("max_relative_resultant_residual must be positive")

    area = float(section.area_mm2)
    i_u = float(section.i_u_mm4)
    i_v = float(section.i_v_mm4)
    i_uv = float(section.i_uv_mm4)

    sigma0 = n_force / area
    gradient_u = (-i_uv * m_u - i_u * m_v) / determinant
    gradient_v = (i_v * m_u + i_uv * m_v) / determinant

    reconstructed_n = sigma0 * area
    reconstructed_m_u = gradient_u * i_uv + gradient_v * i_u
    reconstructed_m_v = -(gradient_u * i_v + gradient_v * i_uv)

    residual_n = _relative_residual(reconstructed_n, n_force)
    residual_m_u = _relative_residual(reconstructed_m_u, m_u)
    residual_m_v = _relative_residual(reconstructed_m_v, m_v)
    residual = max(residual_n, residual_m_u, residual_m_v)
    if not math.isfinite(residual) or residual > tolerance:
        raise AnalyticalWitnessError(
            f"ANALYTICAL_SECTION_RESULTANT_RECONSTRUCTION_FAILED:{residual:.17g}"
        )

    payload = {
        "schema": "AsterMaxLinearNormalStressWitnessV1",
        "selection_id": section.selection_id,
        "section_sha256": section.section_sha256,
        "axial_force_n": n_force,
        "moment_u_nmm": m_u,
        "moment_v_nmm": m_v,
        "sigma0_mpa": sigma0,
        "gradient_u_mpa_per_mm": gradient_u,
        "gradient_v_mpa_per_mm": gradient_v,
        "inertia_determinant_mm8": determinant,
        "inertia_condition_indicator": condition_indicator,
        "reconstructed_axial_force_n": reconstructed_n,
        "reconstructed_moment_u_nmm": reconstructed_m_u,
        "reconstructed_moment_v_nmm": reconstructed_m_v,
        "axial_force_relative_residual": residual_n,
        "moment_u_relative_residual": residual_m_u,
        "moment_v_relative_residual": residual_m_v,
        "max_relative_resultant_residual": residual,
        "convention": "RIGHT_HANDED_U_V_N;M_U=INT(v*sigma)dA;M_V=-INT(u*sigma)dA",
        "method": "EXACT_LINEAR_SECTION_RESULTANT_RECONSTRUCTION_FROM_CAD_AREA_INERTIAS",
    }
    return LinearNormalStressWitness(**payload, witness_sha256=canonical_sha256(payload))


def normal_stress_mpa(witness: LinearNormalStressWitness, *, u_mm: float, v_mm: float) -> float:
    u = _finite("u_mm", u_mm)
    v = _finite("v_mm", v_mm)
    return (
        witness.sigma0_mpa
        + witness.gradient_u_mpa_per_mm * u
        + witness.gradient_v_mpa_per_mm * v
    )


def analytical_section_witness_evidence(witness: LinearNormalStressWitness) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SECTION_WITNESS:{witness.selection_id}:{witness.witness_sha256[:16]}",
        kind="ANALYTICAL_SECTION_WITNESS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description=(
            "Axial plus biaxial linear normal-stress field reconstructs the declared "
            "section force and bending moments from CAD-derived section integrals."
        ),
        payload_sha256=witness.witness_sha256,
        metadata={
            "selection_id": witness.selection_id,
            "section_sha256": witness.section_sha256,
            "axial_force_n": witness.axial_force_n,
            "moment_u_nmm": witness.moment_u_nmm,
            "moment_v_nmm": witness.moment_v_nmm,
            "sigma0_mpa": witness.sigma0_mpa,
            "gradient_u_mpa_per_mm": witness.gradient_u_mpa_per_mm,
            "gradient_v_mpa_per_mm": witness.gradient_v_mpa_per_mm,
            "max_relative_resultant_residual": witness.max_relative_resultant_residual,
            "convention": witness.convention,
            "method": witness.method,
        },
    )


def analytical_section_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_LINEAR_SECTION_STRESS_RECONSTRUCTED",
        context_id=context_id,
        statement=(
            "For the exact persistent CAD section, the declared axial force and biaxial "
            "bending moments are reconstructed by an independently evaluated linear "
            "normal-stress field."
        ),
        requirements=(
            ClaimRequirement(
                "CAD_FACE_IDENTITY",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "CAD_SECTION_PROPERTIES",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "ANALYTICAL_SECTION_WITNESS",
                allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,),
            ),
        ),
    )
