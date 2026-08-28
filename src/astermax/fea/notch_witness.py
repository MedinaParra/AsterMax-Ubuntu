from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .bounded_stress_concentration import (
    StressConcentrationEvaluation,
    StressConcentrationGrid,
    StressConcentrationGridError,
    evaluate_stress_concentration,
)
from .shaft_shoulder import ShaftShoulderGeometry


class NotchWitnessError(ValueError):
    pass


@dataclass(frozen=True)
class NotchStressWitness:
    schema: str
    geometry_sha256: str
    bending_dataset_sha256: str
    torsion_dataset_sha256: str
    nominal_normal_stress_mpa: float
    nominal_shear_stress_mpa: float
    kt: float
    kts: float
    local_normal_stress_mpa: float
    local_shear_stress_mpa: float
    local_von_mises_mpa: float
    method: str
    witness_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("witness_sha256")
        return payload


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise NotchWitnessError(f"{name} must be finite")
    return result


def build_notch_stress_witness(
    geometry: ShaftShoulderGeometry,
    *,
    bending_grid: StressConcentrationGrid,
    torsion_grid: StressConcentrationGrid,
    nominal_normal_stress_mpa: float,
    nominal_shear_stress_mpa: float,
) -> NotchStressWitness:
    if bending_grid.factor_name.lower() not in {"kt", "k_t"}:
        raise NotchWitnessError("BENDING_GRID_MUST_PROVIDE_KT")
    if torsion_grid.factor_name.lower() not in {"kts", "k_ts"}:
        raise NotchWitnessError("TORSION_GRID_MUST_PROVIDE_KTS")
    if "BEND" not in bending_grid.load_mode.upper():
        raise NotchWitnessError("BENDING_GRID_LOAD_MODE_MISMATCH")
    if "TORS" not in torsion_grid.load_mode.upper():
        raise NotchWitnessError("TORSION_GRID_LOAD_MODE_MISMATCH")

    try:
        kt_eval: StressConcentrationEvaluation = evaluate_stress_concentration(bending_grid, geometry)
        kts_eval: StressConcentrationEvaluation = evaluate_stress_concentration(torsion_grid, geometry)
    except StressConcentrationGridError as exc:
        raise NotchWitnessError(str(exc)) from exc

    sigma_nom = _finite("nominal_normal_stress_mpa", nominal_normal_stress_mpa)
    tau_nom = _finite("nominal_shear_stress_mpa", nominal_shear_stress_mpa)
    sigma_local = kt_eval.factor * sigma_nom
    tau_local = kts_eval.factor * tau_nom
    vm = math.sqrt(sigma_local * sigma_local + 3.0 * tau_local * tau_local)

    payload = {
        "schema": "AsterMaxNotchStressWitnessV1",
        "geometry_sha256": geometry.geometry_sha256,
        "bending_dataset_sha256": bending_grid.dataset_sha256,
        "torsion_dataset_sha256": torsion_grid.dataset_sha256,
        "nominal_normal_stress_mpa": sigma_nom,
        "nominal_shear_stress_mpa": tau_nom,
        "kt": kt_eval.factor,
        "kts": kts_eval.factor,
        "local_normal_stress_mpa": sigma_local,
        "local_shear_stress_mpa": tau_local,
        "local_von_mises_mpa": vm,
        "method": "BOUNDED_EMPIRICAL_KT_KTS_APPLIED_TO_DECLARED_NOMINAL_STRESS",
    }
    return NotchStressWitness(**payload, witness_sha256=canonical_sha256(payload))


def notch_witness_evidence(witness: NotchStressWitness) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"NOTCH_WITNESS:{witness.witness_sha256[:20]}",
        kind="STRESS_CONCENTRATION_WITNESS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description=(
            "Bounded empirical stress-concentration witness for declared nominal normal and shear stress."
        ),
        payload_sha256=witness.witness_sha256,
        metadata=witness.canonical_without_hash(),
    )
