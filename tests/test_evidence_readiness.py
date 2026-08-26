import pytest
from pydantic import ValidationError

from astermax.domain.evidence_readiness import (
    EvidenceClosureStatus,
    EvidenceLedgerItemV1,
    EvidenceReadinessLedgerV1,
    EvidenceSourceClass,
    EvidenceSourceRefV1,
    TighteningProcedureV1,
    derive_thread_kinematics,
    evaluate_evidence_readiness,
)


def source(source_id: str, source_class: EvidenceSourceClass) -> EvidenceSourceRefV1:
    return EvidenceSourceRefV1(source_id=source_id, source_class=source_class)


def item(
    field_id: str,
    status: EvidenceClosureStatus,
    source_class: EvidenceSourceClass,
) -> EvidenceLedgerItemV1:
    return EvidenceLedgerItemV1(
        field_id=field_id,
        status=status,
        sources=[source(f"src:{field_id}", source_class)],
        rationale="test fixture",
    )


def test_assumption_cannot_close_required_evidence() -> None:
    with pytest.raises(ValidationError, match="ASSUMPTION"):
        item(
            "load_envelope",
            EvidenceClosureStatus.CLOSED,
            EvidenceSourceClass.ASSUMPTION,
        )


def test_historical_evidence_alone_cannot_close_current_field() -> None:
    with pytest.raises(ValidationError, match="CURRENT_AUTHORITATIVE or PUBLIC_MANUFACTURER"):
        item(
            "bolt_preload",
            EvidenceClosureStatus.CLOSED,
            EvidenceSourceClass.HISTORICAL_AUTHORITATIVE,
        )


def test_current_authoritative_or_public_manufacturer_can_close_identity() -> None:
    current = item(
        "hub_material_identity",
        EvidenceClosureStatus.CLOSED,
        EvidenceSourceClass.CURRENT_AUTHORITATIVE,
    )
    public = item(
        "bolt_identity",
        EvidenceClosureStatus.CLOSED,
        EvidenceSourceClass.PUBLIC_MANUFACTURER,
    )
    assert current.status == EvidenceClosureStatus.CLOSED
    assert public.status == EvidenceClosureStatus.CLOSED


def test_thread_angle_derivation_is_kinematic_not_preload() -> None:
    procedure = TighteningProcedureV1(
        thread_tpi=14,
        torque_nominal_nm=500,
        torque_tolerance_nm=50,
        additional_turn_angle_deg=120,
        lubrication_condition="documented lubricated installation procedure",
        source=source("procedure:fixture", EvidenceSourceClass.CURRENT_AUTHORITATIVE),
    )
    result = derive_thread_kinematics(procedure)
    assert result.thread_pitch_mm_per_rev == pytest.approx(25.4 / 14)
    assert result.ideal_nut_advance_mm == pytest.approx((25.4 / 14) / 3)
    assert result.preload_n is None
    assert result.derivation_class == "KINEMATIC_DERIVATION"
    assert "not bolt" in result.disclaimer.lower()


def test_documented_tightening_procedure_does_not_close_preload_model() -> None:
    ledger = EvidenceReadinessLedgerV1(
        items=[
            item(
                "tightening_procedure",
                EvidenceClosureStatus.CLOSED,
                EvidenceSourceClass.CURRENT_AUTHORITATIVE,
            ),
            item(
                "preload_model",
                EvidenceClosureStatus.PARTIAL,
                EvidenceSourceClass.HISTORICAL_AUTHORITATIVE,
            ),
        ]
    )
    decision = evaluate_evidence_readiness(
        ledger,
        required_fields=["tightening_procedure", "preload_model"],
    )
    assert decision.ready is False
    assert decision.closed_fields == ["tightening_procedure"]
    assert decision.partial_fields == ["preload_model"]
    assert decision.solver_authorization_recommended is False


def test_missing_and_blocked_fields_are_reported_exactly() -> None:
    ledger = EvidenceReadinessLedgerV1(
        items=[
            item(
                "geometry",
                EvidenceClosureStatus.CLOSED,
                EvidenceSourceClass.CURRENT_AUTHORITATIVE,
            ),
            item(
                "segment_material",
                EvidenceClosureStatus.BLOCKED,
                EvidenceSourceClass.OBSERVATION,
            ),
        ]
    )
    decision = evaluate_evidence_readiness(
        ledger,
        required_fields=["geometry", "segment_material", "load_envelope"],
    )
    assert decision.ready is False
    assert decision.closed_fields == ["geometry"]
    assert decision.blocked_fields == ["segment_material"]
    assert decision.missing_fields == ["load_envelope"]


def test_all_required_fields_closed_is_ready() -> None:
    ledger = EvidenceReadinessLedgerV1(
        items=[
            item("geometry", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.CURRENT_AUTHORITATIVE),
            item("hub_material", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.CURRENT_AUTHORITATIVE),
            item("segment_material", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.CURRENT_AUTHORITATIVE),
            item("bolt_identity", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.PUBLIC_MANUFACTURER),
            item("preload_model", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.CURRENT_AUTHORITATIVE),
            item("friction", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.CURRENT_AUTHORITATIVE),
            item("load_envelope", EvidenceClosureStatus.CLOSED, EvidenceSourceClass.CURRENT_AUTHORITATIVE),
        ]
    )
    decision = evaluate_evidence_readiness(
        ledger,
        required_fields=[
            "geometry",
            "hub_material",
            "segment_material",
            "bolt_identity",
            "preload_model",
            "friction",
            "load_envelope",
        ],
    )
    assert decision.ready is True
    assert decision.partial_fields == []
    assert decision.blocked_fields == []
    assert decision.missing_fields == []
    assert decision.solver_authorization_recommended is True
