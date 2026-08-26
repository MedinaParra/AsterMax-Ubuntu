from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceClosureStatus(StrEnum):
    CLOSED = "CLOSED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class EvidenceSourceClass(StrEnum):
    CURRENT_AUTHORITATIVE = "CURRENT_AUTHORITATIVE"
    HISTORICAL_AUTHORITATIVE = "HISTORICAL_AUTHORITATIVE"
    PUBLIC_MANUFACTURER = "PUBLIC_MANUFACTURER"
    OBSERVATION = "OBSERVATION"
    ASSUMPTION = "ASSUMPTION"


class EvidenceSourceRefV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_class: EvidenceSourceClass
    notes: str | None = None


class EvidenceLedgerItemV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1)
    status: EvidenceClosureStatus
    sources: list[EvidenceSourceRefV1] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_closure_strength(self) -> "EvidenceLedgerItemV1":
        if self.status != EvidenceClosureStatus.CLOSED:
            return self
        if not self.sources:
            raise ValueError("CLOSED evidence requires at least one source")
        source_classes = {source.source_class for source in self.sources}
        if EvidenceSourceClass.ASSUMPTION in source_classes:
            raise ValueError("ASSUMPTION cannot participate in a CLOSED evidence item")
        accepted = {
            EvidenceSourceClass.CURRENT_AUTHORITATIVE,
            EvidenceSourceClass.PUBLIC_MANUFACTURER,
        }
        if source_classes.isdisjoint(accepted):
            raise ValueError(
                "CLOSED evidence requires CURRENT_AUTHORITATIVE or PUBLIC_MANUFACTURER support"
            )
        return self


class TighteningProcedureV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_tpi: float = Field(gt=0)
    torque_nominal_nm: float = Field(gt=0)
    torque_tolerance_nm: float = Field(ge=0)
    additional_turn_angle_deg: float = Field(ge=0, le=360)
    lubrication_condition: str = Field(min_length=1)
    source: EvidenceSourceRefV1


class ThreadKinematicDerivationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="ThreadKinematicDerivationV1",
        pattern=r"^ThreadKinematicDerivationV1$",
    )
    thread_pitch_mm_per_rev: float = Field(gt=0)
    additional_turn_angle_deg: float = Field(ge=0, le=360)
    ideal_nut_advance_mm: float = Field(ge=0)
    derivation_class: str = Field(
        default="KINEMATIC_DERIVATION",
        pattern=r"^KINEMATIC_DERIVATION$",
    )
    preload_n: None = None
    disclaimer: str = Field(min_length=1)


def derive_thread_kinematics(
    procedure: TighteningProcedureV1,
) -> ThreadKinematicDerivationV1:
    pitch_mm = 25.4 / procedure.thread_tpi
    ideal_advance_mm = pitch_mm * procedure.additional_turn_angle_deg / 360.0
    return ThreadKinematicDerivationV1(
        thread_pitch_mm_per_rev=pitch_mm,
        additional_turn_angle_deg=procedure.additional_turn_angle_deg,
        ideal_nut_advance_mm=ideal_advance_mm,
        preload_n=None,
        disclaimer=(
            "Ideal thread advance is a screw-kinematic derivation only. It is not bolt "
            "elongation, joint compression, clamp force, preload, or a torque-to-preload "
            "conversion. A validated joint/preload model is required before solver use."
        ),
    )


class EvidenceReadinessLedgerV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="EvidenceReadinessLedgerV1",
        pattern=r"^EvidenceReadinessLedgerV1$",
    )
    items: list[EvidenceLedgerItemV1] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_fields(self) -> "EvidenceReadinessLedgerV1":
        field_ids = [item.field_id for item in self.items]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("evidence ledger field_id values must be unique")
        return self


class EvidenceReadinessDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="EvidenceReadinessDecisionV1",
        pattern=r"^EvidenceReadinessDecisionV1$",
    )
    ready: bool
    closed_fields: list[str]
    partial_fields: list[str]
    blocked_fields: list[str]
    missing_fields: list[str]
    solver_authorization_recommended: bool


def evaluate_evidence_readiness(
    ledger: EvidenceReadinessLedgerV1,
    *,
    required_fields: list[str],
) -> EvidenceReadinessDecisionV1:
    if not required_fields:
        raise ValueError("required_fields must not be empty")
    if len(required_fields) != len(set(required_fields)):
        raise ValueError("required_fields must be unique")

    by_field = {item.field_id: item for item in ledger.items}
    closed: list[str] = []
    partial: list[str] = []
    blocked: list[str] = []
    missing: list[str] = []

    for field_id in required_fields:
        item = by_field.get(field_id)
        if item is None:
            missing.append(field_id)
        elif item.status == EvidenceClosureStatus.CLOSED:
            closed.append(field_id)
        elif item.status == EvidenceClosureStatus.PARTIAL:
            partial.append(field_id)
        else:
            blocked.append(field_id)

    ready = not partial and not blocked and not missing
    return EvidenceReadinessDecisionV1(
        ready=ready,
        closed_fields=sorted(closed),
        partial_fields=sorted(partial),
        blocked_fields=sorted(blocked),
        missing_fields=sorted(missing),
        solver_authorization_recommended=ready,
    )
