from __future__ import annotations

from dataclasses import dataclass
import math

from .analytical_witness import LinearNormalStressWitness, normal_stress_mpa
from .circular_torsion import CircularTorsionError, CircularTorsionWitness
from .torsion_field import TorsionShearPoint, torsion_shear_point


class CombinedStressError(ValueError):
    pass


@dataclass(frozen=True)
class CombinedStressPoint:
    u_mm: float
    v_mm: float
    sigma_normal_mpa: float
    tau_u_mpa: float
    tau_v_mpa: float
    tau_magnitude_mpa: float
    von_mises_mpa: float


def evaluate_combined_stress(
    normal_witness: LinearNormalStressWitness,
    torsion_witness: CircularTorsionWitness,
    *,
    u_mm: float,
    v_mm: float,
) -> CombinedStressPoint:
    if normal_witness.selection_id != torsion_witness.selection_id:
        raise CombinedStressError("COMBINED_STRESS_SELECTION_MISMATCH")
    if normal_witness.section_sha256 != torsion_witness.section_sha256:
        raise CombinedStressError("COMBINED_STRESS_SECTION_SHA_MISMATCH")

    sigma = float(normal_stress_mpa(normal_witness, u_mm=u_mm, v_mm=v_mm))
    try:
        shear: TorsionShearPoint = torsion_shear_point(
            torsion_witness,
            u_mm=u_mm,
            v_mm=v_mm,
        )
    except CircularTorsionError as exc:
        raise CombinedStressError(str(exc)) from exc

    vm_sq = sigma * sigma + 3.0 * shear.tau_magnitude_mpa * shear.tau_magnitude_mpa
    if not math.isfinite(vm_sq) or vm_sq < 0.0:
        raise CombinedStressError("COMBINED_STRESS_VON_MISES_INVALID")

    return CombinedStressPoint(
        u_mm=float(u_mm),
        v_mm=float(v_mm),
        sigma_normal_mpa=sigma,
        tau_u_mpa=shear.tau_u_mpa,
        tau_v_mpa=shear.tau_v_mpa,
        tau_magnitude_mpa=shear.tau_magnitude_mpa,
        von_mises_mpa=math.sqrt(vm_sq),
    )
