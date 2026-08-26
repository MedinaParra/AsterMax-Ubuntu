from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScreeningEvidenceClass(StrEnum):
    EXPLORATORY = "EXPLORATORY"


class SlipScreenStatus(StrEnum):
    LIKELY_GROSS_SLIP = "LIKELY_GROSS_SLIP"
    NO_GROSS_SLIP_SCREEN = "NO_GROSS_SLIP_SCREEN"


class ContactPatchV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pressure_mpa: float = Field(ge=0)
    area_mm2: float = Field(gt=0)
    radius_mm: float = Field(gt=0)


class FrictionScreenInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="FrictionScreenInputV1", pattern=r"^FrictionScreenInputV1$"
    )
    evidence_class: ScreeningEvidenceClass
    patches: list[ContactPatchV1] = Field(min_length=1)
    friction_coefficient: float = Field(gt=0, le=2.0)
    applied_torque_knm: float = Field(ge=0)
    repeated_segments: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def require_active_normal_load(self) -> "FrictionScreenInputV1":
        if not any(p.pressure_mpa > 0 for p in self.patches):
            raise ValueError("friction screening requires positive active normal pressure")
        return self


class FrictionScreenResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="FrictionScreenResultV1", pattern=r"^FrictionScreenResultV1$"
    )
    evidence_class: ScreeningEvidenceClass
    status: SlipScreenStatus
    normal_force_kn: float = Field(gt=0)
    active_area_mm2: float = Field(gt=0)
    pressure_weighted_radius_mm: float = Field(gt=0)
    friction_torque_capacity_knm: float = Field(gt=0)
    applied_torque_knm: float = Field(ge=0)
    utilization: float = Field(ge=0)
    required_friction_coefficient: float = Field(ge=0)
    solver_truth_claim_allowed: bool = False
    acceptance_claim_allowed: bool = False
    interpretation: str


def evaluate_friction_screen(input_data: FrictionScreenInputV1) -> FrictionScreenResultV1:
    # MPa == N/mm^2. This module is deliberately a scalar Coulomb capacity screen.
    weighted_normal_n = sum(
        patch.pressure_mpa * patch.area_mm2 for patch in input_data.patches
    )
    if weighted_normal_n <= 0:
        raise ValueError("normal force must be positive")

    active_area_mm2 = sum(
        patch.area_mm2 for patch in input_data.patches if patch.pressure_mpa > 0
    )
    if active_area_mm2 <= 0:
        raise ValueError("active contact area must be positive")

    weighted_radius_mm = sum(
        patch.pressure_mpa * patch.area_mm2 * patch.radius_mm
        for patch in input_data.patches
    ) / weighted_normal_n

    capacity_nmm_single = input_data.friction_coefficient * sum(
        patch.pressure_mpa * patch.area_mm2 * patch.radius_mm
        for patch in input_data.patches
    )
    capacity_knm = capacity_nmm_single * input_data.repeated_segments / 1_000_000.0
    if capacity_knm <= 0:
        raise ValueError("friction torque capacity must be positive")

    utilization = input_data.applied_torque_knm / capacity_knm
    capacity_per_mu_knm = capacity_knm / input_data.friction_coefficient
    required_mu = (
        input_data.applied_torque_knm / capacity_per_mu_knm
        if input_data.applied_torque_knm > 0
        else 0.0
    )

    if utilization > 1.0:
        status = SlipScreenStatus.LIKELY_GROSS_SLIP
        interpretation = (
            "Applied torque exceeds the integrated scalar Coulomb capacity. "
            "Prioritize nonlinear 3D contact/slip analysis."
        )
    else:
        status = SlipScreenStatus.NO_GROSS_SLIP_SCREEN
        interpretation = (
            "The scalar global screen does not predict gross slip. This is not a safety, "
            "local-stick, stress, fatigue, or acceptance result; nonlinear 3D analysis remains required."
        )

    return FrictionScreenResultV1(
        evidence_class=input_data.evidence_class,
        status=status,
        normal_force_kn=weighted_normal_n * input_data.repeated_segments / 1000.0,
        active_area_mm2=active_area_mm2 * input_data.repeated_segments,
        pressure_weighted_radius_mm=weighted_radius_mm,
        friction_torque_capacity_knm=capacity_knm,
        applied_torque_knm=input_data.applied_torque_knm,
        utilization=utilization,
        required_friction_coefficient=required_mu,
        solver_truth_claim_allowed=False,
        acceptance_claim_allowed=False,
        interpretation=interpretation,
    )
