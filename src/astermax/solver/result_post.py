from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ElementFamily(StrEnum):
    TET4 = "TET4"
    TET10 = "TET10"


class ResultAssociation(StrEnum):
    POINT = "POINT"
    CELL = "CELL"


class MeshLevelV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="MeshLevelV1", pattern=r"^MeshLevelV1$")
    level_id: str = Field(min_length=1)
    global_size_mm: float = Field(gt=0)
    contact_size_mm: float = Field(gt=0)
    element_family: ElementFamily
    node_count: int = Field(gt=0)
    element_count: int = Field(gt=0)
    mesh_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_refinement(self) -> "MeshLevelV1":
        if self.contact_size_mm > self.global_size_mm:
            raise ValueError("contact mesh size cannot exceed global mesh size")
        return self


class ResultArrayV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="ResultArrayV1", pattern=r"^ResultArrayV1$")
    name: str = Field(min_length=1)
    association: ResultAssociation
    components: int = Field(gt=0)
    unit: str | None = None
    evidence_class: str = Field(min_length=1)
    raw_solver_values: bool
    smoothed_display_only: bool = False

    @model_validator(mode="after")
    def check_semantics(self) -> "ResultArrayV1":
        if self.raw_solver_values and self.smoothed_display_only:
            raise ValueError("a raw solver array cannot be labelled smoothed display only")
        return self


class FeResultTopologyManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="FeResultTopologyManifestV1",
        pattern=r"^FeResultTopologyManifestV1$",
    )
    mesh: MeshLevelV1
    point_coordinate_unit: str = Field(default="mm", min_length=1)
    body_ids: list[str] = Field(min_length=1)
    named_selections: dict[str, list[int]] = Field(default_factory=dict)
    arrays: list[ResultArrayV1] = Field(min_length=1)
    topology_preserved: bool = True
    node_ids_preserved: bool = True
    connectivity_preserved: bool = True

    @model_validator(mode="after")
    def check_topology_evidence(self) -> "FeResultTopologyManifestV1":
        if not (self.topology_preserved and self.node_ids_preserved and self.connectivity_preserved):
            raise ValueError("W2M result manifest requires complete mesh topology preservation")
        names = [item.name for item in self.arrays]
        if len(names) != len(set(names)):
            raise ValueError("result array names must be unique")
        if len(self.body_ids) != len(set(self.body_ids)):
            raise ValueError("body IDs must be unique")
        return self


class MeshConvergenceSampleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="MeshConvergenceSampleV1",
        pattern=r"^MeshConvergenceSampleV1$",
    )
    mesh: MeshLevelV1
    displacement_probe_mm: float = Field(ge=0)
    reaction_resultant_n: float
    contact_resultant_n: float = Field(ge=0)
    active_contact_area_mm2: float = Field(gt=0)
    von_mises_p95_mpa: float = Field(ge=0)
    von_mises_p99_mpa: float = Field(ge=0)
    contact_pressure_p95_mpa: float = Field(ge=0)
    contact_pressure_p99_mpa: float = Field(ge=0)
    von_mises_max_mpa: float = Field(ge=0)
    contact_pressure_max_mpa: float = Field(ge=0)

    @model_validator(mode="after")
    def check_percentiles(self) -> "MeshConvergenceSampleV1":
        values = self.model_dump(exclude={"mesh", "schema_version"}).values()
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("convergence metrics must be finite")
        if self.von_mises_p95_mpa > self.von_mises_p99_mpa:
            raise ValueError("von Mises p95 cannot exceed p99")
        if self.von_mises_p99_mpa > self.von_mises_max_mpa:
            raise ValueError("von Mises p99 cannot exceed max")
        if self.contact_pressure_p95_mpa > self.contact_pressure_p99_mpa:
            raise ValueError("contact pressure p95 cannot exceed p99")
        if self.contact_pressure_p99_mpa > self.contact_pressure_max_mpa:
            raise ValueError("contact pressure p99 cannot exceed max")
        return self


class ConvergenceThresholdsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="ConvergenceThresholdsV1",
        pattern=r"^ConvergenceThresholdsV1$",
    )
    displacement_fraction: float = Field(default=0.02, gt=0)
    reaction_fraction: float = Field(default=0.02, gt=0)
    contact_resultant_fraction: float = Field(default=0.02, gt=0)
    active_contact_area_fraction: float = Field(default=0.05, gt=0)
    von_mises_percentile_fraction: float = Field(default=0.05, gt=0)
    contact_pressure_percentile_fraction: float = Field(default=0.05, gt=0)


class ConvergenceMetricResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    coarse_value: float
    fine_value: float
    relative_change: float
    threshold: float
    passed: bool
    gate_metric: bool = True


class MeshConvergenceReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="MeshConvergenceReportV1",
        pattern=r"^MeshConvergenceReportV1$",
    )
    coarse_level: str
    fine_level: str
    same_element_family: bool
    metrics: list[ConvergenceMetricResultV1]
    passed: bool
    maxima_are_diagnostic_only: bool = True


def relative_change(coarse: float, fine: float, *, floor: float = 1e-12) -> float:
    denominator = max(abs(fine), floor)
    return abs(fine - coarse) / denominator


def _metric(
    name: str,
    coarse: float,
    fine: float,
    threshold: float,
    *,
    gate_metric: bool = True,
) -> ConvergenceMetricResultV1:
    change = relative_change(coarse, fine)
    return ConvergenceMetricResultV1(
        metric=name,
        coarse_value=coarse,
        fine_value=fine,
        relative_change=change,
        threshold=threshold,
        passed=(change <= threshold + 1e-12) if gate_metric else True,
        gate_metric=gate_metric,
    )


def evaluate_pair(
    coarse: MeshConvergenceSampleV1,
    fine: MeshConvergenceSampleV1,
    thresholds: ConvergenceThresholdsV1 | None = None,
) -> MeshConvergenceReportV1:
    thresholds = thresholds or ConvergenceThresholdsV1()
    if fine.mesh.global_size_mm >= coarse.mesh.global_size_mm:
        raise ValueError("fine mesh global size must be smaller than coarse mesh size")
    if fine.mesh.contact_size_mm >= coarse.mesh.contact_size_mm:
        raise ValueError("fine contact size must be smaller than coarse contact size")
    if fine.mesh.node_count <= coarse.mesh.node_count:
        raise ValueError("fine mesh must contain more nodes than coarse mesh")
    if fine.mesh.element_count <= coarse.mesh.element_count:
        raise ValueError("fine mesh must contain more elements than coarse mesh")
    if fine.mesh.element_family != coarse.mesh.element_family:
        raise ValueError("Tet4 and Tet10 cannot be compared as equivalent convergence evidence")

    metrics = [
        _metric(
            "displacement_probe_mm",
            coarse.displacement_probe_mm,
            fine.displacement_probe_mm,
            thresholds.displacement_fraction,
        ),
        _metric(
            "reaction_resultant_n",
            coarse.reaction_resultant_n,
            fine.reaction_resultant_n,
            thresholds.reaction_fraction,
        ),
        _metric(
            "contact_resultant_n",
            coarse.contact_resultant_n,
            fine.contact_resultant_n,
            thresholds.contact_resultant_fraction,
        ),
        _metric(
            "active_contact_area_mm2",
            coarse.active_contact_area_mm2,
            fine.active_contact_area_mm2,
            thresholds.active_contact_area_fraction,
        ),
        _metric(
            "von_mises_p95_mpa",
            coarse.von_mises_p95_mpa,
            fine.von_mises_p95_mpa,
            thresholds.von_mises_percentile_fraction,
        ),
        _metric(
            "von_mises_p99_mpa",
            coarse.von_mises_p99_mpa,
            fine.von_mises_p99_mpa,
            thresholds.von_mises_percentile_fraction,
        ),
        _metric(
            "contact_pressure_p95_mpa",
            coarse.contact_pressure_p95_mpa,
            fine.contact_pressure_p95_mpa,
            thresholds.contact_pressure_percentile_fraction,
        ),
        _metric(
            "contact_pressure_p99_mpa",
            coarse.contact_pressure_p99_mpa,
            fine.contact_pressure_p99_mpa,
            thresholds.contact_pressure_percentile_fraction,
        ),
        _metric(
            "von_mises_max_mpa",
            coarse.von_mises_max_mpa,
            fine.von_mises_max_mpa,
            1.0,
            gate_metric=False,
        ),
        _metric(
            "contact_pressure_max_mpa",
            coarse.contact_pressure_max_mpa,
            fine.contact_pressure_max_mpa,
            1.0,
            gate_metric=False,
        ),
    ]
    return MeshConvergenceReportV1(
        coarse_level=coarse.mesh.level_id,
        fine_level=fine.mesh.level_id,
        same_element_family=True,
        metrics=metrics,
        passed=all(item.passed for item in metrics if item.gate_metric),
    )


def evaluate_ladder(
    samples: Iterable[MeshConvergenceSampleV1],
    thresholds: ConvergenceThresholdsV1 | None = None,
) -> list[MeshConvergenceReportV1]:
    ordered = list(samples)
    if len(ordered) < 2:
        raise ValueError("at least two mesh levels are required for convergence evaluation")
    return [
        evaluate_pair(ordered[index], ordered[index + 1], thresholds)
        for index in range(len(ordered) - 1)
    ]
