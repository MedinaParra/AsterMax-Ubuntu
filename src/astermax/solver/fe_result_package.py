from __future__ import annotations

from enum import StrEnum
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ElementFamily(StrEnum):
    TET4 = "TET4"
    TET10 = "TET10"


class FieldAssociation(StrEnum):
    POINT = "POINT"
    CELL = "CELL"


class FieldEvidenceClass(StrEnum):
    SOLVER_RESULT = "SOLVER_RESULT"
    DETERMINISTIC_CALCULATION = "DETERMINISTIC_CALCULATION"


class MeshTopologyV1(BaseModel):
    """Complete FE topology required to reproduce a result without CAD heuristics."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["MeshTopologyV1"] = "MeshTopologyV1"
    element_family: ElementFamily
    nodes_mm: list[tuple[float, float, float]]
    connectivity: list[list[int]]
    body_ids: list[int]
    named_point_sets: dict[str, list[int]] = Field(default_factory=dict)
    named_cell_sets: dict[str, list[int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_topology(self) -> "MeshTopologyV1":
        if len(self.nodes_mm) < 4:
            raise ValueError("mesh must contain at least four nodes")
        if not self.connectivity:
            raise ValueError("mesh must contain at least one element")
        expected = 4 if self.element_family == ElementFamily.TET4 else 10
        node_count = len(self.nodes_mm)
        for element_index, conn in enumerate(self.connectivity):
            if len(conn) != expected:
                raise ValueError(
                    f"{self.element_family} element {element_index} requires {expected} nodes"
                )
            if len(set(conn)) != expected:
                raise ValueError(f"element {element_index} repeats node ids")
            if min(conn) < 0 or max(conn) >= node_count:
                raise ValueError(f"element {element_index} references node outside mesh")
        if len(self.body_ids) != len(self.connectivity):
            raise ValueError("body_ids length must equal element count")
        for name, ids in self.named_point_sets.items():
            if not name or any(index < 0 or index >= node_count for index in ids):
                raise ValueError(f"invalid named point set: {name}")
        cell_count = len(self.connectivity)
        for name, ids in self.named_cell_sets.items():
            if not name or any(index < 0 or index >= cell_count for index in ids):
                raise ValueError(f"invalid named cell set: {name}")
        return self


class FEFieldV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["FEFieldV1"] = "FEFieldV1"
    name: str = Field(min_length=1)
    association: FieldAssociation
    components: int = Field(ge=1, le=9)
    values: list[list[float]]
    unit: str | None = None
    evidence_class: FieldEvidenceClass
    source_field: str | None = None
    averaged: bool = False

    @model_validator(mode="after")
    def validate_values(self) -> "FEFieldV1":
        if any(len(row) != self.components for row in self.values):
            raise ValueError(f"field {self.name} row width does not match components")
        if not np.all(np.isfinite(np.asarray(self.values, dtype=float))):
            raise ValueError(f"field {self.name} contains non-finite values")
        return self


class FEStateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["FEStateV1"] = "FEStateV1"
    load_factor: float = Field(ge=0.0)
    fields: list[FEFieldV1]

    @model_validator(mode="after")
    def unique_fields(self) -> "FEStateV1":
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("state contains duplicate field names")
        return self


class FEResultPackageV1(BaseModel):
    """Hashable logical result content for ANSYS-style deterministic postprocessing."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["FEResultPackageV1"] = "FEResultPackageV1"
    result_class: Literal["SOLVER_RESULT", "EXPLORATORY_NOT_FOR_ACCEPTANCE"]
    mesh: MeshTopologyV1
    states: list[FEStateV1]
    metadata: dict[str, str | float | int | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_package(self) -> "FEResultPackageV1":
        if not self.states:
            raise ValueError("result package must contain at least one state")
        point_count = len(self.mesh.nodes_mm)
        cell_count = len(self.mesh.connectivity)
        previous = -1.0
        for state in self.states:
            if state.load_factor < previous:
                raise ValueError("load factors must be monotonically non-decreasing")
            previous = state.load_factor
            for field in state.fields:
                expected = point_count if field.association == FieldAssociation.POINT else cell_count
                if len(field.values) != expected:
                    raise ValueError(
                        f"field {field.name} has {len(field.values)} rows; expected {expected}"
                    )
        return self

    def state_at_or_before(self, load_factor: float) -> FEStateV1:
        candidates = [state for state in self.states if state.load_factor <= load_factor]
        if not candidates:
            raise ValueError("requested load factor precedes first stored state")
        return max(candidates, key=lambda state: state.load_factor)
