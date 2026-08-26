from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceStrength(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    ASSUMPTION = "ASSUMPTION"


class FeaAuthorizationStatus(StrEnum):
    BLOCKED = "BLOCKED"
    READY = "READY"


class EvidenceBasisV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(min_length=1)
    strength: EvidenceStrength
    notes: str | None = None


class GeometryVariantEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_step_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    variant_step_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gap_mm: float = Field(ge=0)
    gap_evidence_class: str = Field(
        pattern=r"^(MEASURED_ENDPOINT|DERIVED_SENSITIVITY)$"
    )
    solid_count: int = Field(default=6, ge=1)
    basis: EvidenceBasisV1


class MaterialEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: str = Field(min_length=1)
    elastic_modulus_mpa: float = Field(gt=0)
    poisson_ratio: float = Field(gt=0, lt=0.5)
    density_kg_m3: float = Field(gt=0)
    yield_strength_mpa: float = Field(gt=0)
    ultimate_strength_mpa: float | None = Field(default=None, gt=0)
    basis: EvidenceBasisV1

    @model_validator(mode="after")
    def validate_strengths(self) -> "MaterialEvidenceV1":
        if (
            self.ultimate_strength_mpa is not None
            and self.ultimate_strength_mpa < self.yield_strength_mpa
        ):
            raise ValueError("ultimate strength cannot be below yield strength")
        return self


class BoltIdentityEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count_per_sprocket: int = Field(gt=0)
    nominal_diameter_mm: float = Field(gt=0)
    hole_diameter_mm: float = Field(gt=0)
    thread_designation: str = Field(min_length=1)
    property_class_or_material: str = Field(min_length=1)
    basis: EvidenceBasisV1

    @model_validator(mode="after")
    def validate_geometric_identity(self) -> "BoltIdentityEvidenceV1":
        if self.nominal_diameter_mm >= self.hole_diameter_mm:
            raise ValueError("bolt nominal diameter must be below the clearance-hole diameter")
        return self


class BoltPreloadEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preload_n: float | None = Field(default=None, gt=0)
    tightening_torque_nm: float | None = Field(default=None, gt=0)
    tightening_sequence: str = Field(min_length=1)
    lubrication_condition: str = Field(min_length=1)
    torque_to_preload_basis: str | None = None
    basis: EvidenceBasisV1

    @model_validator(mode="after")
    def validate_preload_basis(self) -> "BoltPreloadEvidenceV1":
        if self.preload_n is None and self.tightening_torque_nm is None:
            raise ValueError("preload evidence requires direct preload or tightening torque")
        if self.preload_n is None and not self.torque_to_preload_basis:
            raise ValueError(
                "torque-only preload evidence requires an explicit torque-to-preload basis"
            )
        return self


class ContactFrictionEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coefficient: float = Field(ge=0, le=2.0)
    surface_pair: str = Field(min_length=1)
    surface_condition: str = Field(min_length=1)
    basis: EvidenceBasisV1


class LoadEnvelopeEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    jam_torque_knm: float = Field(gt=0)
    loaded_start_torque_knm: float | None = Field(default=None, gt=0)
    sprocket_speed_rpm: float = Field(ge=0)
    loaded_teeth_count: int = Field(gt=0)
    wrap_angle_deg: float = Field(gt=0, le=360)
    right_sprocket_load_share_percent: float = Field(ge=0, le=100)
    axial_thrust_kn: float
    basis: EvidenceBasisV1


class FeaInputBundleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="FeaInputBundleV1", pattern=r"^FeaInputBundleV1$"
    )
    geometry: GeometryVariantEvidenceV1 | None = None
    hub_material: MaterialEvidenceV1 | None = None
    segment_material: MaterialEvidenceV1 | None = None
    segment_bolts: BoltIdentityEvidenceV1 | None = None
    bolt_preload: BoltPreloadEvidenceV1 | None = None
    contact_friction: ContactFrictionEvidenceV1 | None = None
    load_envelope: LoadEnvelopeEvidenceV1 | None = None


class FeaAuthorizationDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="FeaAuthorizationDecisionV1",
        pattern=r"^FeaAuthorizationDecisionV1$",
    )
    status: FeaAuthorizationStatus
    blockers: list[str] = Field(default_factory=list)
    authentic_solver_job_authorized: bool


_REQUIRED = (
    ("geometry", "geometry:variant_evidence_missing"),
    ("hub_material", "material:hub_missing"),
    ("segment_material", "material:segment_missing"),
    ("segment_bolts", "bolts:segment_identity_missing"),
    ("bolt_preload", "bolts:preload_missing"),
    ("contact_friction", "contact:friction_missing"),
    ("load_envelope", "load:envelope_missing"),
)


def _basis_blocker(prefix: str, basis: EvidenceBasisV1) -> str | None:
    if basis.strength == EvidenceStrength.AUTHORITATIVE:
        return None
    return f"{prefix}:non_authoritative_evidence"


def evaluate_fea_authorization(
    bundle: FeaInputBundleV1,
    *,
    expected_segment_bolt_count: int = 30,
    expected_segment_hole_diameter_mm: float = 24.5,
) -> FeaAuthorizationDecisionV1:
    blockers: list[str] = []

    for field_name, missing_blocker in _REQUIRED:
        if getattr(bundle, field_name) is None:
            blockers.append(missing_blocker)

    if bundle.geometry is not None:
        blocker = _basis_blocker("geometry", bundle.geometry.basis)
        if blocker:
            blockers.append(blocker)
        if bundle.geometry.solid_count != 6:
            blockers.append("geometry:unexpected_solid_count")

    for prefix, material in (
        ("material:hub", bundle.hub_material),
        ("material:segment", bundle.segment_material),
    ):
        if material is not None:
            blocker = _basis_blocker(prefix, material.basis)
            if blocker:
                blockers.append(blocker)

    if bundle.segment_bolts is not None:
        blocker = _basis_blocker("bolts:identity", bundle.segment_bolts.basis)
        if blocker:
            blockers.append(blocker)
        if bundle.segment_bolts.count_per_sprocket != expected_segment_bolt_count:
            blockers.append("bolts:count_mismatch")
        if abs(
            bundle.segment_bolts.hole_diameter_mm
            - expected_segment_hole_diameter_mm
        ) > 1e-9:
            blockers.append("bolts:hole_pattern_mismatch")

    if bundle.bolt_preload is not None:
        blocker = _basis_blocker("bolts:preload", bundle.bolt_preload.basis)
        if blocker:
            blockers.append(blocker)

    if bundle.contact_friction is not None:
        blocker = _basis_blocker("contact:friction", bundle.contact_friction.basis)
        if blocker:
            blockers.append(blocker)

    if bundle.load_envelope is not None:
        blocker = _basis_blocker("load:envelope", bundle.load_envelope.basis)
        if blocker:
            blockers.append(blocker)

    blockers = sorted(set(blockers))
    status = (
        FeaAuthorizationStatus.READY
        if not blockers
        else FeaAuthorizationStatus.BLOCKED
    )
    return FeaAuthorizationDecisionV1(
        status=status,
        blockers=blockers,
        authentic_solver_job_authorized=status == FeaAuthorizationStatus.READY,
    )
