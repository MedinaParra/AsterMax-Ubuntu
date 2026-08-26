from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from astermax.domain.hub_sprocket import (
    CadUnitNormalizationStatus,
    EvidenceStatus,
    HubSprocketBaselineV1,
)


class SolveReadinessStatus(StrEnum):
    BLOCKED = "BLOCKED"
    READY = "READY"


class SolveReadinessV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SolveReadinessV1", pattern=r"^SolveReadinessV1$")
    baseline_id: str
    case_id: str
    status: SolveReadinessStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HubSprocketSolveBlocked(RuntimeError):
    def __init__(self, report: SolveReadinessV1) -> None:
        self.report = report
        super().__init__(
            f"hub/sprocket solve is {report.status.value}: " + ", ".join(report.blockers)
        )


AUTHENTIC_READY_STATUSES = {
    EvidenceStatus.KNOWN_FACT,
    EvidenceStatus.MEASURED,
    EvidenceStatus.DERIVED,
}


def _is_authentic_ready(value) -> bool:
    return value.value is not None and value.status in AUTHENTIC_READY_STATUSES and bool(value.source_ids)


def evaluate_critical_solve_readiness(
    baseline: HubSprocketBaselineV1,
    *,
    case_id: str = "OT1613_MEASURED_GAP_CRITICAL",
) -> SolveReadinessV1:
    blockers: list[str] = []
    warnings: list[str] = []

    for input_id, value in baseline.required_inputs.items():
        if not _is_authentic_ready(value):
            blockers.append(f"required_input:{input_id}")

    for field_name in (
        "friction_coefficient",
        "nominal_bolt_preload_n",
        "minimum_probable_bolt_preload_n",
    ):
        value = getattr(baseline.model_intent, field_name)
        if not _is_authentic_ready(value):
            blockers.append(f"model_input:{field_name}")

    if baseline.geometry.unit_normalization_status != CadUnitNormalizationStatus.CONFIRMED_MM_FROM_DRAWING:
        blockers.append("geometry:unit_normalization_unconfirmed")

    if baseline.identifiers.confirmed_value is None:
        blockers.append("identity:ot_identifier_unconfirmed")

    if baseline.model_intent.optimized_seating_diameter_mm.status == EvidenceStatus.PENDING_METROLOGY:
        warnings.append("optimized_seating_diameter_pending_metrology; measured-gap critical case may proceed once other blockers close")

    if baseline.geometry.nominal_segment_hub_min_distance_numeric:
        if max(abs(value) for value in baseline.geometry.nominal_segment_hub_min_distance_numeric) < 1e-6:
            warnings.append("cad_geometry_is_nominal_touching; measured GAP must be introduced parametrically, not inferred from CAD")

    status = SolveReadinessStatus.READY if not blockers else SolveReadinessStatus.BLOCKED
    return SolveReadinessV1(
        baseline_id=baseline.baseline_id,
        case_id=case_id,
        status=status,
        blockers=sorted(blockers),
        warnings=warnings,
    )


def require_ready_for_solver(
    baseline: HubSprocketBaselineV1,
    *,
    case_id: str = "OT1613_MEASURED_GAP_CRITICAL",
) -> SolveReadinessV1:
    report = evaluate_critical_solve_readiness(baseline, case_id=case_id)
    if report.status != SolveReadinessStatus.READY:
        raise HubSprocketSolveBlocked(report)
    return report
