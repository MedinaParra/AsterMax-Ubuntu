from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


class KirschError(ValueError):
    pass


@dataclass(frozen=True)
class KirschHoleWitness:
    schema: str
    witness_id: str
    hole_radius_mm: float
    far_field_stress_mpa: float
    boundary_clearance_over_diameter: float
    minimum_clearance_over_diameter: float
    load_direction: str
    theory: str
    reference_note: str
    witness_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("witness_sha256")
        return payload


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise KirschError(f"{name} must be finite")
    return result


def build_kirsch_hole_witness(
    *,
    witness_id: str,
    hole_radius_mm: float,
    far_field_stress_mpa: float,
    boundary_clearance_over_diameter: float,
    minimum_clearance_over_diameter: float = 3.0,
) -> KirschHoleWitness:
    witness_id = str(witness_id).strip()
    if not witness_id:
        raise KirschError("witness_id must be non-empty")
    a = _finite("hole_radius_mm", hole_radius_mm)
    sigma = _finite("far_field_stress_mpa", far_field_stress_mpa)
    clearance = _finite("boundary_clearance_over_diameter", boundary_clearance_over_diameter)
    minimum = _finite("minimum_clearance_over_diameter", minimum_clearance_over_diameter)
    if a <= 0.0 or clearance <= 0.0 or minimum <= 0.0:
        raise KirschError("radius and clearance ratios must be positive")
    if clearance < minimum:
        raise KirschError("KIRSCH_INFINITE_PLATE_APPROXIMATION_OUT_OF_DOMAIN")

    payload = {
        "schema": "AsterMaxKirschHoleWitnessV1",
        "witness_id": witness_id,
        "hole_radius_mm": a,
        "far_field_stress_mpa": sigma,
        "boundary_clearance_over_diameter": clearance,
        "minimum_clearance_over_diameter": minimum,
        "load_direction": "UNIAXIAL_FAR_FIELD_X",
        "theory": "KIRSCH_INFINITE_PLATE_LINEAR_ELASTICITY_PLANE_STRESS",
        "reference_note": (
            "Closed-form circular-hole field; finite-boundary use requires declared clearance. "
            "This is an analytical verification witness, not physical validation."
        ),
    }
    return KirschHoleWitness(**payload, witness_sha256=canonical_sha256(payload))


def kirsch_polar_stress_mpa(
    witness: KirschHoleWitness,
    *,
    radius_mm: float,
    theta_rad: float,
) -> tuple[float, float, float]:
    r = _finite("radius_mm", radius_mm)
    theta = _finite("theta_rad", theta_rad)
    a = witness.hole_radius_mm
    if r < a * (1.0 - 1.0e-12):
        raise KirschError("KIRSCH_QUERY_INSIDE_HOLE")
    r = max(r, a)
    ratio2 = (a / r) ** 2
    ratio4 = ratio2 * ratio2
    c2 = math.cos(2.0 * theta)
    s2 = math.sin(2.0 * theta)
    sigma = witness.far_field_stress_mpa

    sigma_rr = 0.5 * sigma * (1.0 - ratio2) + 0.5 * sigma * (
        1.0 - 4.0 * ratio2 + 3.0 * ratio4
    ) * c2
    sigma_tt = 0.5 * sigma * (1.0 + ratio2) - 0.5 * sigma * (
        1.0 + 3.0 * ratio4
    ) * c2
    tau_rt = -0.5 * sigma * (1.0 + 2.0 * ratio2 - 3.0 * ratio4) * s2
    return sigma_rr, sigma_tt, tau_rt


def kirsch_plane_stress_von_mises_mpa(
    witness: KirschHoleWitness,
    *,
    radius_mm: float,
    theta_rad: float,
) -> float:
    sigma_rr, sigma_tt, tau_rt = kirsch_polar_stress_mpa(
        witness, radius_mm=radius_mm, theta_rad=theta_rad
    )
    return math.sqrt(
        sigma_rr * sigma_rr
        - sigma_rr * sigma_tt
        + sigma_tt * sigma_tt
        + 3.0 * tau_rt * tau_rt
    )


def kirsch_boundary_kt(witness: KirschHoleWitness) -> float:
    _, hoop, _ = kirsch_polar_stress_mpa(
        witness,
        radius_mm=witness.hole_radius_mm,
        theta_rad=0.5 * math.pi,
    )
    denominator = abs(witness.far_field_stress_mpa)
    if denominator <= 0.0:
        raise KirschError("KIRSCH_KT_UNDEFINED_FOR_ZERO_FAR_FIELD_STRESS")
    return abs(hoop) / denominator


def kirsch_witness_evidence(witness: KirschHoleWitness) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"KIRSCH:{witness.witness_id}",
        kind="KIRSCH_HOLE_WITNESS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description="Closed-form Kirsch circular-hole stress field within its declared infinite-plate approximation domain.",
        payload_sha256=witness.witness_sha256,
        metadata={**witness.canonical_without_hash(), "boundary_kt": kirsch_boundary_kt(witness)},
    )
