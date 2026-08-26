import pytest

from astermax.domain.fea_authorization import (
    BoltIdentityEvidenceV1,
    BoltPreloadEvidenceV1,
    ContactFrictionEvidenceV1,
    EvidenceBasisV1,
    EvidenceStrength,
    FeaAuthorizationStatus,
    FeaInputBundleV1,
    GeometryVariantEvidenceV1,
    LoadEnvelopeEvidenceV1,
    MaterialEvidenceV1,
    evaluate_fea_authorization,
)


def basis(strength: EvidenceStrength = EvidenceStrength.AUTHORITATIVE):
    return EvidenceBasisV1(source_ids=["source-1"], strength=strength)


def material(name: str, strength: EvidenceStrength = EvidenceStrength.AUTHORITATIVE):
    return MaterialEvidenceV1(
        designation=name,
        elastic_modulus_mpa=205000.0,
        poisson_ratio=0.30,
        density_kg_m3=7850.0,
        yield_strength_mpa=350.0,
        ultimate_strength_mpa=500.0,
        basis=basis(strength),
    )


def complete_bundle() -> FeaInputBundleV1:
    return FeaInputBundleV1(
        geometry=GeometryVariantEvidenceV1(
            source_step_sha256="a" * 64,
            variant_step_sha256="b" * 64,
            gap_mm=0.40,
            gap_evidence_class="MEASURED_ENDPOINT",
            solid_count=6,
            basis=basis(),
        ),
        hub_material=material("CERTIFIED-HUB-MATERIAL"),
        segment_material=material("CERTIFIED-SEGMENT-MATERIAL"),
        segment_bolts=BoltIdentityEvidenceV1(
            count_per_sprocket=30,
            nominal_diameter_mm=22.0,
            hole_diameter_mm=24.5,
            thread_designation="M22",
            property_class_or_material="10.9",
            basis=basis(),
        ),
        bolt_preload=BoltPreloadEvidenceV1(
            preload_n=150000.0,
            tightening_sequence="documented star/cross sequence",
            lubrication_condition="documented installation condition",
            basis=basis(),
        ),
        contact_friction=ContactFrictionEvidenceV1(
            coefficient=0.15,
            surface_pair="documented hub/segment interface",
            surface_condition="documented surface condition",
            basis=basis(),
        ),
        load_envelope=LoadEnvelopeEvidenceV1(
            case_id="documented-jam-case",
            jam_torque_knm=100.0,
            loaded_start_torque_knm=80.0,
            sprocket_speed_rpm=5.0,
            loaded_teeth_count=3,
            wrap_angle_deg=140.0,
            right_sprocket_load_share_percent=50.0,
            axial_thrust_kn=0.0,
            basis=basis(),
        ),
    )


def test_empty_bundle_fails_closed_with_named_blockers() -> None:
    decision = evaluate_fea_authorization(FeaInputBundleV1())
    assert decision.status == FeaAuthorizationStatus.BLOCKED
    assert decision.authentic_solver_job_authorized is False
    assert decision.blockers == sorted([
        "bolts:preload_missing",
        "bolts:segment_identity_missing",
        "contact:friction_missing",
        "geometry:variant_evidence_missing",
        "load:envelope_missing",
        "material:hub_missing",
        "material:segment_missing",
    ])


def test_procurement_m12_hardware_cannot_authorize_segment_bolts() -> None:
    bundle = complete_bundle()
    bundle.segment_bolts = BoltIdentityEvidenceV1(
        count_per_sprocket=14,
        nominal_diameter_mm=12.0,
        hole_diameter_mm=13.0,
        thread_designation="M12x1.75",
        property_class_or_material="8.8",
        basis=basis(EvidenceStrength.OBSERVATION_ONLY),
    )
    decision = evaluate_fea_authorization(bundle)
    assert decision.status == FeaAuthorizationStatus.BLOCKED
    assert "bolts:identity:non_authoritative_evidence" in decision.blockers
    assert "bolts:count_mismatch" in decision.blockers
    assert "bolts:hole_pattern_mismatch" in decision.blockers


def test_procured_lubricant_name_is_not_a_friction_coefficient() -> None:
    bundle = complete_bundle()
    bundle.contact_friction = ContactFrictionEvidenceV1(
        coefficient=0.15,
        surface_pair="hub/segment",
        surface_condition="DRI LUBE procured; application not verified",
        basis=basis(EvidenceStrength.OBSERVATION_ONLY),
    )
    decision = evaluate_fea_authorization(bundle)
    assert decision.status == FeaAuthorizationStatus.BLOCKED
    assert "contact:friction:non_authoritative_evidence" in decision.blockers


def test_generic_material_assumption_cannot_authorize_authentic_solve() -> None:
    bundle = complete_bundle()
    bundle.hub_material = material("generic steel", EvidenceStrength.ASSUMPTION)
    bundle.segment_material = material("generic steel", EvidenceStrength.ASSUMPTION)
    decision = evaluate_fea_authorization(bundle)
    assert decision.status == FeaAuthorizationStatus.BLOCKED
    assert "material:hub:non_authoritative_evidence" in decision.blockers
    assert "material:segment:non_authoritative_evidence" in decision.blockers


def test_assumed_jam_torque_cannot_authorize_authentic_solve() -> None:
    bundle = complete_bundle()
    bundle.load_envelope.basis = basis(EvidenceStrength.ASSUMPTION)
    decision = evaluate_fea_authorization(bundle)
    assert decision.status == FeaAuthorizationStatus.BLOCKED
    assert decision.blockers == ["load:envelope:non_authoritative_evidence"]


def test_torque_only_preload_requires_explicit_conversion_basis() -> None:
    with pytest.raises(ValueError, match="torque-to-preload basis"):
        BoltPreloadEvidenceV1(
            tightening_torque_nm=500.0,
            tightening_sequence="documented",
            lubrication_condition="documented",
            basis=basis(),
        )


def test_complete_authoritative_bundle_is_ready() -> None:
    decision = evaluate_fea_authorization(complete_bundle())
    assert decision.status == FeaAuthorizationStatus.READY
    assert decision.blockers == []
    assert decision.authentic_solver_job_authorized is True
