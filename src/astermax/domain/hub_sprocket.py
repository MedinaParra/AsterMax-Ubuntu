from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceStatus(StrEnum):
    KNOWN_FACT = "KNOWN_FACT"
    MEASURED = "MEASURED"
    PROPOSED_MODELING_ASSUMPTION = "PROPOSED_MODELING_ASSUMPTION"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    DERIVED = "DERIVED"
    PENDING_METROLOGY = "PENDING_METROLOGY"


class SourceReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    document_code: str | None = None
    revision: str | None = None
    document_date: str | None = None
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    external_ref: str | None = None
    notes: str | None = None


class EvidenceValueV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any | None = None
    status: EvidenceStatus
    unit: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    derivation: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_evidence_state(self) -> "EvidenceValueV1":
        populated = {
            EvidenceStatus.KNOWN_FACT,
            EvidenceStatus.MEASURED,
            EvidenceStatus.PROPOSED_MODELING_ASSUMPTION,
            EvidenceStatus.DERIVED,
        }
        unpopulated = {
            EvidenceStatus.MISSING_REQUIRED,
            EvidenceStatus.PENDING_METROLOGY,
        }
        if self.status in populated:
            if self.value is None:
                raise ValueError(f"{self.status.value} evidence requires a value")
            if not self.source_ids:
                raise ValueError(f"{self.status.value} evidence requires source_ids")
        if self.status in unpopulated and self.value is not None:
            raise ValueError(f"{self.status.value} evidence must not contain a value")
        if self.status == EvidenceStatus.DERIVED and not self.derivation:
            raise ValueError("DERIVED evidence requires an explicit derivation")
        return self


class DiameterReferenceRole(StrEnum):
    HISTORICAL_REFERENCE = "HISTORICAL_REFERENCE"
    CURRENT_DRAWING_REFERENCE = "CURRENT_DRAWING_REFERENCE"
    TEST_FLANGE = "TEST_FLANGE"
    OEM_POSTERIOR_SEAT = "OEM_POSTERIOR_SEAT"


class DiameterReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diameter_mm: float = Field(gt=0)
    role: DiameterReferenceRole
    status: EvidenceStatus
    source_ids: list[str] = Field(min_length=1)
    notes: str | None = None

    @model_validator(mode="after")
    def require_supported_status(self) -> "DiameterReferenceV1":
        if self.status not in {EvidenceStatus.KNOWN_FACT, EvidenceStatus.MEASURED}:
            raise ValueError("diameter references must be KNOWN_FACT or MEASURED")
        return self


class GapRangeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_mm: float = Field(ge=0)
    maximum_mm: float = Field(ge=0)
    status: EvidenceStatus = EvidenceStatus.MEASURED
    source_ids: list[str] = Field(min_length=1)
    test_flange_diameter_mm: float = Field(gt=0)
    representation: str = Field(default="RANGE", pattern=r"^RANGE$")
    notes: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "GapRangeV1":
        if self.status != EvidenceStatus.MEASURED:
            raise ValueError("the report GAP range must remain MEASURED evidence")
        if self.maximum_mm < self.minimum_mm:
            raise ValueError("maximum GAP must not be below minimum GAP")
        return self


class IdentifierObservationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)
    context: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class IdentificationDiscrepancyV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: list[IdentifierObservationV1] = Field(min_length=2)
    confirmed_value: str | None = None
    confirmation_source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_confirmation(self) -> "IdentificationDiscrepancyV1":
        observed = {item.value for item in self.observations}
        if len(observed) < 2:
            raise ValueError("identification discrepancy requires at least two distinct observed identifiers")
        if self.confirmed_value is not None:
            if not self.confirmation_source_ids:
                raise ValueError("confirmed identifier requires confirmation_source_ids")
        elif self.confirmation_source_ids:
            raise ValueError("confirmation sources require a confirmed identifier")
        return self


class SegmentBaselineV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: EvidenceValueV1
    teeth_per_segment: EvidenceValueV1
    bolts_per_segment: EvidenceValueV1
    segments_per_sprocket: EvidenceValueV1
    mass_kg: EvidenceValueV1
    pitch_mm: EvidenceValueV1
    width_mm: EvidenceValueV1
    diameter_a_mm: EvidenceValueV1
    diameter_c_mm: EvidenceValueV1
    diameter_d_mm: EvidenceValueV1
    bolt_circle_mm: EvidenceValueV1
    hole_diameter_mm: EvidenceValueV1


class HubGeometryBaselineV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_drawing_reference_diameter_mm: EvidenceValueV1
    bolt_circle_mm: EvidenceValueV1
    hole_count: EvidenceValueV1
    hole_diameter_mm: EvidenceValueV1
    oem_posterior_seat_spec_available: EvidenceValueV1


class BoundingBoxV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_length: float = Field(gt=0)
    y_length: float = Field(gt=0)
    z_length: float = Field(gt=0)


class CadUnitNormalizationStatus(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    CONFIRMED_MM_FROM_DRAWING = "CONFIRMED_MM_FROM_DRAWING"


class CadGeometryArtifactV1(BaseModel):
    """Identity and deterministic inspection facts for the uploaded STEP geometry.

    The STEP file currently declares METRE while its numeric hub diameter is 795,
    matching the verified drawing dimension in millimetres. That conflict is
    intentionally represented instead of silently rescaling the model.
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    media_type: str = Field(default="model/step", min_length=1)
    step_schema: str = Field(min_length=1)
    exporter: str | None = None
    declared_length_unit: str = Field(min_length=1)
    intended_analysis_length_unit: str = Field(default="mm", pattern=r"^mm$")
    unit_normalization_status: CadUnitNormalizationStatus
    normalization_basis_source_ids: list[str] = Field(min_length=1)
    human_confirmation_source_ids: list[str] = Field(default_factory=list)
    solid_count: int = Field(gt=0)
    hub_solid_index_1based: int = Field(gt=0)
    segment_solid_indices_1based: list[int] = Field(min_length=1)
    hub_bbox_numeric: BoundingBoxV1
    segment_axial_extent_numeric: float = Field(gt=0)
    segment_volume_numeric: float = Field(gt=0)
    segment_count_with_identical_volume: int = Field(gt=0)
    nominal_segment_hub_min_distance_numeric: list[float] = Field(default_factory=list)
    inspection_tool: str = Field(min_length=1)
    inspection_source_ids: list[str] = Field(min_length=1)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_geometry_identity(self) -> "CadGeometryArtifactV1":
        indices = [self.hub_solid_index_1based, *self.segment_solid_indices_1based]
        if any(index > self.solid_count for index in indices):
            raise ValueError("solid index exceeds declared solid_count")
        if self.hub_solid_index_1based in self.segment_solid_indices_1based:
            raise ValueError("hub solid cannot also be a segment solid")
        if len(set(self.segment_solid_indices_1based)) != len(self.segment_solid_indices_1based):
            raise ValueError("segment solid indices must be unique")
        if self.segment_count_with_identical_volume > len(self.segment_solid_indices_1based):
            raise ValueError("identical-volume count cannot exceed segment count")
        if self.unit_normalization_status == CadUnitNormalizationStatus.CONFIRMED_MM_FROM_DRAWING:
            if not self.human_confirmation_source_ids:
                raise ValueError("confirmed CAD unit normalization requires human_confirmation_source_ids")
        elif self.human_confirmation_source_ids:
            raise ValueError("human confirmation sources require confirmed CAD unit normalization")
        return self


class ModelIntentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_count: EvidenceValueV1
    bolt_connector_count: EvidenceValueV1
    contact_mode: EvidenceValueV1
    allow_opening: EvidenceValueV1
    allow_sliding: EvidenceValueV1
    friction_coefficient: EvidenceValueV1
    nominal_bolt_preload_n: EvidenceValueV1
    minimum_probable_bolt_preload_n: EvidenceValueV1
    optimized_seating_diameter_mm: EvidenceValueV1
    primary_load_mode: EvidenceValueV1
    required_outputs: EvidenceValueV1


REQUIRED_CLIENT_INPUT_IDS = (
    "jam_torque_knm",
    "loaded_start_torque_knm",
    "sprocket_speed_rpm",
    "chain_branch_tensions_kn",
    "wrap_angle_and_loaded_teeth",
    "right_left_load_split_percent",
    "axial_thrust_or_misalignment",
    "bolt_tightening_torque_sequence",
    "bolt_lubricant",
    "hub_material_and_properties",
    "service_history",
)


class HubSprocketBaselineV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="HubSprocketBaselineV1", pattern=r"^HubSprocketBaselineV1$")
    baseline_id: str = Field(min_length=1)
    client: str = Field(min_length=1)
    component: str = Field(min_length=1)
    sources: dict[str, SourceReferenceV1] = Field(min_length=1)
    identifiers: IdentificationDiscrepancyV1
    segment: SegmentBaselineV1
    hub: HubGeometryBaselineV1
    geometry: CadGeometryArtifactV1
    diameter_references: list[DiameterReferenceV1] = Field(min_length=1)
    measured_gap: GapRangeV1
    model_intent: ModelIntentV1
    required_inputs: dict[str, EvidenceValueV1]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_baseline_integrity(self) -> "HubSprocketBaselineV1":
        expected = set(REQUIRED_CLIENT_INPUT_IDS)
        actual = set(self.required_inputs)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"required_inputs mismatch; missing={missing}, extra={extra}")

        if self.hub.oem_posterior_seat_spec_available.value is not False:
            raise ValueError("V1 baseline requires explicit evidence that OEM posterior-seat specification is unavailable")
        if any(item.role == DiameterReferenceRole.OEM_POSTERIOR_SEAT for item in self.diameter_references):
            raise ValueError("cannot label a diameter as OEM posterior seat when the source states that specification is unavailable")

        if abs(self.measured_gap.minimum_mm - self.measured_gap.maximum_mm) < 1e-12:
            raise ValueError("measured GAP evidence must preserve the reported range; a single midpoint/value is not equivalent")

        source_keys = set(self.sources)
        if any(source.source_id != key for key, source in self.sources.items()):
            raise ValueError("source dictionary keys must equal SourceReferenceV1.source_id")

        referenced: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, BaseModel):
                for field_name in value.__class__.model_fields:
                    field_value = getattr(value, field_name)
                    if field_name == "source_ids" or field_name.endswith("_source_ids"):
                        if isinstance(field_value, list):
                            referenced.update(field_value)
                    collect(field_value)
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)

        collect(self.identifiers)
        collect(self.segment)
        collect(self.hub)
        collect(self.geometry)
        collect(self.diameter_references)
        collect(self.measured_gap)
        collect(self.model_intent)
        collect(self.required_inputs)
        unknown = sorted(referenced - source_keys)
        if unknown:
            raise ValueError(f"evidence references unknown source_ids: {unknown}")
        return self
