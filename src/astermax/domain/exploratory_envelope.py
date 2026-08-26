from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .evidence_readiness import EvidenceSourceClass


class ExploratoryResultClass(StrEnum):
    SENSITIVITY_ONLY = "SENSITIVITY_ONLY"
    ASSUMPTION_DERIVATION = "ASSUMPTION_DERIVATION"


class BoundedFloatV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: float
    nominal: float
    high: float
    units: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> "BoundedFloatV1":
        if not self.low <= self.nominal <= self.high:
            raise ValueError("bounded value must satisfy low <= nominal <= high")
        return self


class ExploratoryMaterialV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation: str = Field(min_length=1)
    elastic_modulus_mpa: float = Field(gt=0)
    poisson_ratio: float = Field(gt=0, lt=0.5)
    density_kg_m3: float = Field(gt=0)
    yield_strength_mpa: BoundedFloatV1 | None = None
    source_class: EvidenceSourceClass = EvidenceSourceClass.ASSUMPTION

    @model_validator(mode="after")
    def assumption_only(self) -> "ExploratoryMaterialV1":
        if self.source_class != EvidenceSourceClass.ASSUMPTION:
            raise ValueError("exploratory material values must remain ASSUMPTION")
        if self.yield_strength_mpa and self.yield_strength_mpa.units != "MPa":
            raise ValueError("yield-strength envelope units must be MPa")
        return self


class ExploratoryJointV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bolt_count: int = Field(gt=0)
    preload_per_bolt_kn: BoundedFloatV1
    contact_friction: BoundedFloatV1
    effective_friction_radius_m: BoundedFloatV1
    source_class: EvidenceSourceClass = EvidenceSourceClass.ASSUMPTION

    @model_validator(mode="after")
    def validate_joint(self) -> "ExploratoryJointV1":
        if self.source_class != EvidenceSourceClass.ASSUMPTION:
            raise ValueError("exploratory joint values must remain ASSUMPTION")
        if self.preload_per_bolt_kn.units != "kN":
            raise ValueError("bolt preload units must be kN")
        if self.contact_friction.units != "dimensionless":
            raise ValueError("contact friction must be dimensionless")
        if self.effective_friction_radius_m.units != "m":
            raise ValueError("effective friction radius units must be m")
        if self.contact_friction.low < 0:
            raise ValueError("contact friction cannot be negative")
        return self


class ExploratoryDriveGeometryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chain_pitch_mm: float = Field(gt=0)
    sprocket_tooth_count: int = Field(gt=2)
    source_class: EvidenceSourceClass

    @model_validator(mode="after")
    def accepted_geometry_provenance(self) -> "ExploratoryDriveGeometryV1":
        accepted = {
            EvidenceSourceClass.CURRENT_AUTHORITATIVE,
            EvidenceSourceClass.PUBLIC_MANUFACTURER,
            EvidenceSourceClass.ASSUMPTION,
        }
        if self.source_class not in accepted:
            raise ValueError(
                "drive geometry requires current authoritative, public manufacturer, or explicit assumption provenance"
            )
        return self


class ExploratoryLoadCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    shaft_torque_knm: float = Field(gt=0)
    selected_sprocket_load_share_percent: float = Field(gt=0, le=100)
    chain_speed_mps: float = Field(ge=0)
    loaded_teeth_count: int = Field(gt=0)
    wrap_angle_deg: float = Field(gt=0, le=360)
    axial_thrust_kn: float = 0.0
    source_class: EvidenceSourceClass = EvidenceSourceClass.ASSUMPTION

    @model_validator(mode="after")
    def assumption_only(self) -> "ExploratoryLoadCaseV1":
        if self.source_class != EvidenceSourceClass.ASSUMPTION:
            raise ValueError("exploratory load cases must remain ASSUMPTION")
        return self


class DerivedLoadCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="DerivedLoadCaseV1", pattern=r"^DerivedLoadCaseV1$"
    )
    case_id: str
    pitch_diameter_m: float = Field(gt=0)
    sprocket_speed_rpm: float = Field(ge=0)
    selected_sprocket_torque_knm: float = Field(gt=0)
    chain_tangential_force_kn: float = Field(gt=0)
    force_per_loaded_tooth_kn: float = Field(gt=0)
    wrap_angle_deg: float
    axial_thrust_kn: float
    geometry_source_class: EvidenceSourceClass
    result_class: ExploratoryResultClass = ExploratoryResultClass.ASSUMPTION_DERIVATION
    authentic_solver_authorized: bool = False
    disclaimer: str = Field(min_length=1)


class FrictionSlipScreenV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_clamp_force_kn: BoundedFloatV1
    friction_torque_capacity_knm: BoundedFloatV1
    result_class: ExploratoryResultClass = ExploratoryResultClass.ASSUMPTION_DERIVATION
    authentic_solver_authorized: bool = False
    disclaimer: str = Field(min_length=1)


def pitch_diameter_m(geometry: ExploratoryDriveGeometryV1) -> float:
    pitch_m = geometry.chain_pitch_mm / 1000.0
    return pitch_m / math.sin(math.pi / geometry.sprocket_tooth_count)


def derive_load_case(
    geometry: ExploratoryDriveGeometryV1,
    case: ExploratoryLoadCaseV1,
) -> DerivedLoadCaseV1:
    diameter_m = pitch_diameter_m(geometry)
    radius_m = diameter_m / 2.0
    chain_travel_per_rev_m = (
        geometry.chain_pitch_mm / 1000.0 * geometry.sprocket_tooth_count
    )
    speed_rpm = case.chain_speed_mps * 60.0 / chain_travel_per_rev_m
    sprocket_torque_knm = (
        case.shaft_torque_knm * case.selected_sprocket_load_share_percent / 100.0
    )
    chain_force_kn = sprocket_torque_knm / radius_m
    return DerivedLoadCaseV1(
        case_id=case.case_id,
        pitch_diameter_m=diameter_m,
        sprocket_speed_rpm=speed_rpm,
        selected_sprocket_torque_knm=sprocket_torque_knm,
        chain_tangential_force_kn=chain_force_kn,
        force_per_loaded_tooth_kn=chain_force_kn / case.loaded_teeth_count,
        wrap_angle_deg=case.wrap_angle_deg,
        axial_thrust_kn=case.axial_thrust_kn,
        geometry_source_class=geometry.source_class,
        authentic_solver_authorized=False,
        disclaimer=(
            "Load and force are derived from an exploratory assumption set. Geometry may retain "
            "stronger provenance, but the derived load remains sensitivity-only and must not be "
            "promoted to USER_INPUT, SOLVER_RESULT, or authentic engineering evidence."
        ),
    )


def screen_friction_slip_capacity(joint: ExploratoryJointV1) -> FrictionSlipScreenV1:
    clamp = BoundedFloatV1(
        low=joint.bolt_count * joint.preload_per_bolt_kn.low,
        nominal=joint.bolt_count * joint.preload_per_bolt_kn.nominal,
        high=joint.bolt_count * joint.preload_per_bolt_kn.high,
        units="kN",
    )
    torque = BoundedFloatV1(
        low=(
            clamp.low
            * joint.contact_friction.low
            * joint.effective_friction_radius_m.low
        ),
        nominal=(
            clamp.nominal
            * joint.contact_friction.nominal
            * joint.effective_friction_radius_m.nominal
        ),
        high=(
            clamp.high
            * joint.contact_friction.high
            * joint.effective_friction_radius_m.high
        ),
        units="kN*m",
    )
    return FrictionSlipScreenV1(
        total_clamp_force_kn=clamp,
        friction_torque_capacity_knm=torque,
        authentic_solver_authorized=False,
        disclaimer=(
            "Screening-only Coulomb estimate T = mu * clamp * effective_radius. It ignores "
            "local pressure redistribution, separation, bolt bending, surface damage, "
            "embedment and nonlinear contact. It cannot authorize an engineering solve."
        ),
    )
