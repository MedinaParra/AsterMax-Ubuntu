from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


class SingularityDiagnosticError(ValueError):
    pass


@dataclass(frozen=True)
class RefinementFieldSample:
    mesh_size_mm: float
    local_peak_mpa: float
    neighborhood_value_mpa: float


@dataclass(frozen=True)
class SingularityDiagnostic:
    schema: str
    diagnostic_id: str
    classification: str
    sample_count: int
    peak_last_change: float
    neighborhood_last_change: float
    peak_growth_factor: float
    peak_monotonic_non_decreasing: bool
    peak_stability_tolerance: float
    neighborhood_stability_tolerance: float
    minimum_peak_growth_factor_for_singularity: float
    samples: tuple[RefinementFieldSample, ...]
    method: str
    diagnostic_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("diagnostic_sha256")
        return payload


def _relative_change(a: float, b: float) -> float:
    return abs(b - a) / max(abs(b), abs(a), 1.0e-12)


def diagnose_local_singularity(
    *,
    diagnostic_id: str,
    samples: Iterable[RefinementFieldSample],
    peak_stability_tolerance: float = 0.05,
    neighborhood_stability_tolerance: float = 0.03,
    minimum_peak_growth_factor_for_singularity: float = 1.20,
) -> SingularityDiagnostic:
    diagnostic_id = str(diagnostic_id).strip()
    values = tuple(samples)
    if not diagnostic_id:
        raise SingularityDiagnosticError("diagnostic_id must be non-empty")
    if len(values) < 3:
        raise SingularityDiagnosticError("at least three refinement samples are required")
    p_tol = float(peak_stability_tolerance)
    n_tol = float(neighborhood_stability_tolerance)
    min_growth = float(minimum_peak_growth_factor_for_singularity)
    if any(not math.isfinite(x) or x <= 0.0 for x in (p_tol, n_tol, min_growth)):
        raise SingularityDiagnosticError("diagnostic policy values must be finite and positive")

    for sample in values:
        if (
            not math.isfinite(sample.mesh_size_mm)
            or sample.mesh_size_mm <= 0.0
            or not math.isfinite(sample.local_peak_mpa)
            or sample.local_peak_mpa < 0.0
            or not math.isfinite(sample.neighborhood_value_mpa)
            or sample.neighborhood_value_mpa < 0.0
        ):
            raise SingularityDiagnosticError("refinement samples must be finite and non-negative")
    if any(b.mesh_size_mm >= a.mesh_size_mm for a, b in zip(values, values[1:])):
        raise SingularityDiagnosticError("mesh sizes must be strictly decreasing coarse-to-fine")

    peak_last_change = _relative_change(values[-2].local_peak_mpa, values[-1].local_peak_mpa)
    neighborhood_last_change = _relative_change(
        values[-2].neighborhood_value_mpa, values[-1].neighborhood_value_mpa
    )
    first_peak = max(values[0].local_peak_mpa, 1.0e-12)
    peak_growth_factor = values[-1].local_peak_mpa / first_peak
    monotonic_peak = all(
        b.local_peak_mpa >= a.local_peak_mpa * (1.0 - 1.0e-12)
        for a, b in zip(values, values[1:])
    )
    peak_stable = peak_last_change <= p_tol
    neighborhood_stable = neighborhood_last_change <= n_tol

    if (
        not peak_stable
        and neighborhood_stable
        and monotonic_peak
        and peak_growth_factor >= min_growth
    ):
        classification = "LIKELY_SINGULARITY"
    elif peak_stable and neighborhood_stable:
        classification = "LOCALLY_CONVERGED_FIELD"
    else:
        classification = "INCONCLUSIVE"

    payload = {
        "schema": "AsterMaxLocalSingularityDiagnosticV1",
        "diagnostic_id": diagnostic_id,
        "classification": classification,
        "sample_count": len(values),
        "peak_last_change": peak_last_change,
        "neighborhood_last_change": neighborhood_last_change,
        "peak_growth_factor": peak_growth_factor,
        "peak_monotonic_non_decreasing": monotonic_peak,
        "peak_stability_tolerance": p_tol,
        "neighborhood_stability_tolerance": n_tol,
        "minimum_peak_growth_factor_for_singularity": min_growth,
        "samples": values,
        "method": "PEAK_VS_NEIGHBORHOOD_REFINEMENT_TREND_DIAGNOSTIC",
    }
    canonical = dict(payload)
    canonical["samples"] = [asdict(sample) for sample in values]
    return SingularityDiagnostic(**payload, diagnostic_sha256=canonical_sha256(canonical))


def singularity_diagnostic_evidence(diagnostic: SingularityDiagnostic) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SINGULARITY:{diagnostic.diagnostic_id}:{diagnostic.diagnostic_sha256[:16]}",
        kind="LOCAL_SINGULARITY_DIAGNOSTIC",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Deterministic classification of local peak and neighborhood refinement trends. "
            "LIKELY_SINGULARITY is a numerical diagnostic, not proof of a physical crack or defect."
        ),
        payload_sha256=diagnostic.diagnostic_sha256,
        metadata=diagnostic.canonical_without_hash(),
    )
