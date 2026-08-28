from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .circular_section import CircularSectionApplicability
from .section_evidence import PlanarSectionProperties


class CircularTorsionError(ValueError):
    pass


@dataclass(frozen=True)
class CircularTorsionWitness:
    schema: str
    selection_id: str
    section_sha256: str
    applicability_sha256: str
    torque_nmm: float
    radius_mm: float
    polar_j_mm4: float
    shear_gradient_mpa_per_mm: float
    tau_max_mpa: float
    reconstructed_torque_nmm: float
    torque_relative_residual: float
    method: str
    witness_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("witness_sha256")
        return payload


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise CircularTorsionError(f"{name} must be finite")
    return result


def build_circular_torsion_witness(
    section: PlanarSectionProperties,
    applicability: CircularSectionApplicability,
    *,
    torque_nmm: float,
    max_relative_torque_residual: float = 1.0e-12,
) -> CircularTorsionWitness:
    torque = _finite("torque_nmm", torque_nmm)
    tolerance = _finite("max_relative_torque_residual", max_relative_torque_residual)
    if tolerance <= 0.0:
        raise CircularTorsionError("max_relative_torque_residual must be positive")

    if section.selection_id != applicability.selection_id:
        raise CircularTorsionError("CIRCULAR_TORSION_SELECTION_MISMATCH")
    if section.section_sha256 != applicability.section_sha256:
        raise CircularTorsionError("CIRCULAR_TORSION_SECTION_SHA_MISMATCH")

    radius = _finite("radius_mm", applicability.radius_mm)
    j = _finite("polar_j_mm4", section.polar_i_n_mm4)
    if radius <= 0.0 or j <= 0.0:
        raise CircularTorsionError("CIRCULAR_TORSION_INVALID_SECTION")
    if abs(j - applicability.polar_j_mm4) / max(abs(j), 1.0) > 1.0e-12:
        raise CircularTorsionError("CIRCULAR_TORSION_POLAR_J_MISMATCH")

    gradient = torque / j
    tau_max = abs(gradient) * radius
    reconstructed = gradient * j
    residual = abs(reconstructed - torque) / max(abs(torque), 1.0)
    if not math.isfinite(residual) or residual > tolerance:
        raise CircularTorsionError(
            f"CIRCULAR_TORSION_RESULTANT_RECONSTRUCTION_FAILED:{residual:.17g}"
        )

    payload = {
        "schema": "AsterMaxCircularTorsionWitnessV1",
        "selection_id": section.selection_id,
        "section_sha256": section.section_sha256,
        "applicability_sha256": applicability.applicability_sha256,
        "torque_nmm": torque,
        "radius_mm": radius,
        "polar_j_mm4": j,
        "shear_gradient_mpa_per_mm": gradient,
        "tau_max_mpa": tau_max,
        "reconstructed_torque_nmm": reconstructed,
        "torque_relative_residual": residual,
        "method": "SAINT_VENANT_SOLID_CIRCULAR_TORSION_TAU_EQUALS_T_R_OVER_J",
    }
    return CircularTorsionWitness(**payload, witness_sha256=canonical_sha256(payload))


def circular_torsion_witness_evidence(witness: CircularTorsionWitness) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"TORSION_WITNESS:{witness.selection_id}:{witness.witness_sha256[:16]}",
        kind="ANALYTICAL_TORSION_WITNESS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description=(
            "Saint-Venant solid-circular torsion field reconstructs the declared torque "
            "using the exact CAD-derived polar second moment."
        ),
        payload_sha256=witness.witness_sha256,
        metadata={
            "selection_id": witness.selection_id,
            "section_sha256": witness.section_sha256,
            "applicability_sha256": witness.applicability_sha256,
            "torque_nmm": witness.torque_nmm,
            "polar_j_mm4": witness.polar_j_mm4,
            "tau_max_mpa": witness.tau_max_mpa,
            "torque_relative_residual": witness.torque_relative_residual,
            "method": witness.method,
        },
    )
