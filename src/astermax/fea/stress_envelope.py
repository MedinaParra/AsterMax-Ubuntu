from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import canonical_sha256
from .analytical_witness import LinearNormalStressWitness
from .circular_torsion import CircularTorsionWitness
from .combined_stress import CombinedStressError, evaluate_combined_stress


@dataclass(frozen=True)
class CircularCombinedStressEnvelope:
    schema: str
    selection_id: str
    section_sha256: str
    radius_mm: float
    critical_u_mm: float
    critical_v_mm: float
    max_abs_normal_stress_mpa: float
    boundary_torsional_shear_mpa: float
    max_von_mises_mpa: float
    method: str
    envelope_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("envelope_sha256")
        return payload


def circular_combined_stress_envelope(
    normal_witness: LinearNormalStressWitness,
    torsion_witness: CircularTorsionWitness,
) -> CircularCombinedStressEnvelope:
    if normal_witness.selection_id != torsion_witness.selection_id:
        raise CombinedStressError("STRESS_ENVELOPE_SELECTION_MISMATCH")
    if normal_witness.section_sha256 != torsion_witness.section_sha256:
        raise CombinedStressError("STRESS_ENVELOPE_SECTION_SHA_MISMATCH")

    radius = float(torsion_witness.radius_mm)
    a = float(normal_witness.gradient_u_mpa_per_mm)
    b = float(normal_witness.gradient_v_mpa_per_mm)
    sigma0 = float(normal_witness.sigma0_mpa)
    if not all(math.isfinite(x) for x in (radius, a, b, sigma0)) or radius <= 0.0:
        raise CombinedStressError("STRESS_ENVELOPE_INVALID_INPUT")

    gradient = math.hypot(a, b)
    if gradient > 0.0:
        direction = 1.0 if sigma0 >= 0.0 else -1.0
        critical_u = direction * radius * a / gradient
        critical_v = direction * radius * b / gradient
    else:
        critical_u = radius
        critical_v = 0.0

    max_abs_sigma = abs(sigma0) + radius * gradient
    tau_boundary = abs(float(torsion_witness.shear_gradient_mpa_per_mm)) * radius
    max_vm = math.sqrt(max_abs_sigma * max_abs_sigma + 3.0 * tau_boundary * tau_boundary)

    critical = evaluate_combined_stress(
        normal_witness,
        torsion_witness,
        u_mm=critical_u,
        v_mm=critical_v,
    )
    if abs(critical.von_mises_mpa - max_vm) > 1.0e-11 * max(max_vm, 1.0):
        raise CombinedStressError("STRESS_ENVELOPE_CRITICAL_POINT_IDENTITY_FAILED")

    payload = {
        "schema": "AsterMaxCircularCombinedStressEnvelopeV1",
        "selection_id": normal_witness.selection_id,
        "section_sha256": normal_witness.section_sha256,
        "radius_mm": radius,
        "critical_u_mm": critical_u,
        "critical_v_mm": critical_v,
        "max_abs_normal_stress_mpa": max_abs_sigma,
        "boundary_torsional_shear_mpa": tau_boundary,
        "max_von_mises_mpa": max_vm,
        "method": "EXACT_CONVEX_DISK_BOUNDARY_ENVELOPE_LINEAR_NORMAL_PLUS_CIRCULAR_TORSION",
    }
    return CircularCombinedStressEnvelope(**payload, envelope_sha256=canonical_sha256(payload))
