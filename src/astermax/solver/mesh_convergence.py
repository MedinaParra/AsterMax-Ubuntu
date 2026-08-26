from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConvergenceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class MeshLevelV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["MeshLevelV1"] = "MeshLevelV1"
    level_id: str = Field(min_length=1)
    global_size_mm: float = Field(gt=0)
    local_size_mm: float = Field(gt=0)
    element_family: Literal["TET4", "TET10"]
    node_count: int = Field(gt=0)
    element_count: int = Field(gt=0)


class MeshMetricsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["MeshMetricsV1"] = "MeshMetricsV1"
    max_displacement_mm: float = Field(ge=0)
    reaction_resultant_n: float
    contact_resultant_n: float = Field(ge=0)
    active_contact_area_mm2: float = Field(ge=0)
    von_mises_p95_mpa: float = Field(ge=0)
    von_mises_p99_mpa: float = Field(ge=0)
    contact_pressure_p95_mpa: float = Field(ge=0)
    contact_pressure_p99_mpa: float = Field(ge=0)
    reported_peak_von_mises_mpa: float = Field(ge=0)
    reported_peak_contact_pressure_mpa: float = Field(ge=0)


class MeshRunV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["MeshRunV1"] = "MeshRunV1"
    mesh: MeshLevelV1
    metrics: MeshMetricsV1


class ConvergenceThresholdsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ConvergenceThresholdsV1"] = "ConvergenceThresholdsV1"
    displacement_relative: float = Field(default=0.02, gt=0)
    reaction_relative: float = Field(default=0.02, gt=0)
    contact_resultant_relative: float = Field(default=0.02, gt=0)
    active_contact_area_relative: float = Field(default=0.05, gt=0)
    stress_percentile_relative: float = Field(default=0.05, gt=0)
    contact_pressure_percentile_relative: float = Field(default=0.05, gt=0)


class MetricComparisonV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    coarse_value: float
    fine_value: float
    relative_change: float
    threshold: float
    status: ConvergenceStatus


class MeshConvergenceReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["MeshConvergenceReportV1"] = "MeshConvergenceReportV1"
    coarse_level: str
    fine_level: str
    same_element_family: bool
    comparisons: list[MetricComparisonV1]
    maxima_excluded_from_gate: list[str]
    status: ConvergenceStatus

    @model_validator(mode="after")
    def ensure_gate_has_comparisons(self) -> "MeshConvergenceReportV1":
        if not self.comparisons:
            raise ValueError("convergence report requires gated comparisons")
        return self


def _relative_change(coarse: float, fine: float) -> float:
    scale = max(abs(fine), abs(coarse), 1e-12)
    return abs(fine - coarse) / scale


def _compare(name: str, coarse: float, fine: float, threshold: float) -> MetricComparisonV1:
    relative = _relative_change(coarse, fine)
    return MetricComparisonV1(
        metric=name,
        coarse_value=coarse,
        fine_value=fine,
        relative_change=relative,
        threshold=threshold,
        status=ConvergenceStatus.PASS if relative <= threshold else ConvergenceStatus.FAIL,
    )


def evaluate_mesh_convergence(
    coarse: MeshRunV1,
    fine: MeshRunV1,
    thresholds: ConvergenceThresholdsV1 | None = None,
) -> MeshConvergenceReportV1:
    """Compare adjacent meshes while refusing to hide element-order changes.

    Peak stresses are reported elsewhere but are intentionally excluded from the
    convergence gate because singular/contact-edge maxima can increase with mesh refinement.
    """

    thresholds = thresholds or ConvergenceThresholdsV1()
    if fine.mesh.element_count <= coarse.mesh.element_count:
        raise ValueError("fine mesh must contain more elements than coarse mesh")
    if fine.mesh.local_size_mm > coarse.mesh.local_size_mm:
        raise ValueError("fine mesh cannot have a larger local element size")

    same_family = coarse.mesh.element_family == fine.mesh.element_family
    comparisons = [
        _compare(
            "max_displacement_mm",
            coarse.metrics.max_displacement_mm,
            fine.metrics.max_displacement_mm,
            thresholds.displacement_relative,
        ),
        _compare(
            "reaction_resultant_n",
            coarse.metrics.reaction_resultant_n,
            fine.metrics.reaction_resultant_n,
            thresholds.reaction_relative,
        ),
        _compare(
            "contact_resultant_n",
            coarse.metrics.contact_resultant_n,
            fine.metrics.contact_resultant_n,
            thresholds.contact_resultant_relative,
        ),
        _compare(
            "active_contact_area_mm2",
            coarse.metrics.active_contact_area_mm2,
            fine.metrics.active_contact_area_mm2,
            thresholds.active_contact_area_relative,
        ),
        _compare(
            "von_mises_p95_mpa",
            coarse.metrics.von_mises_p95_mpa,
            fine.metrics.von_mises_p95_mpa,
            thresholds.stress_percentile_relative,
        ),
        _compare(
            "von_mises_p99_mpa",
            coarse.metrics.von_mises_p99_mpa,
            fine.metrics.von_mises_p99_mpa,
            thresholds.stress_percentile_relative,
        ),
        _compare(
            "contact_pressure_p95_mpa",
            coarse.metrics.contact_pressure_p95_mpa,
            fine.metrics.contact_pressure_p95_mpa,
            thresholds.contact_pressure_percentile_relative,
        ),
        _compare(
            "contact_pressure_p99_mpa",
            coarse.metrics.contact_pressure_p99_mpa,
            fine.metrics.contact_pressure_p99_mpa,
            thresholds.contact_pressure_percentile_relative,
        ),
    ]
    passed = same_family and all(item.status == ConvergenceStatus.PASS for item in comparisons)
    return MeshConvergenceReportV1(
        coarse_level=coarse.mesh.level_id,
        fine_level=fine.mesh.level_id,
        same_element_family=same_family,
        comparisons=comparisons,
        maxima_excluded_from_gate=[
            "reported_peak_von_mises_mpa",
            "reported_peak_contact_pressure_mpa",
        ],
        status=ConvergenceStatus.PASS if passed else ConvergenceStatus.FAIL,
    )
