from __future__ import annotations

import hashlib
import math
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StepEvidenceError(RuntimeError):
    """Raised when a local CAD artifact does not match its evidence fingerprint."""


class CadBackendUnavailable(RuntimeError):
    """Raised when optional local CAD inspection dependencies are unavailable."""


class GapScenarioKind(StrEnum):
    MEASURED_ENDPOINT = "MEASURED_ENDPOINT"
    DERIVED_SENSITIVITY = "DERIVED_SENSITIVITY"


class InterfaceSelectionStatus(StrEnum):
    AMBIGUOUS = "AMBIGUOUS"
    CONFIRMED = "CONFIRMED"


class GeometryPreparationStatus(StrEnum):
    BLOCKED_INTERFACE_SELECTION = "BLOCKED_INTERFACE_SELECTION"
    READY_FOR_PARAMETERIZATION = "READY_FOR_PARAMETERIZATION"


class SegmentRadialFrameV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solid_index_1based: int = Field(gt=0)
    center_y_mm: float
    center_z_mm: float
    radial_center_mm: float = Field(gt=0)
    radial_unit_y: float
    radial_unit_z: float
    angle_deg: float = Field(ge=0, lt=360)


class CylindricalFaceCandidateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solid_index_1based: int = Field(gt=0)
    face_index_1based: int = Field(gt=0)
    radius_mm: float = Field(gt=0)
    area_mm2: float = Field(gt=0)
    axis_alignment_x_abs: float = Field(ge=0, le=1)
    x_min_mm: float | None = None
    x_max_mm: float | None = None

    @model_validator(mode="after")
    def validate_axial_extent(self) -> "CylindricalFaceCandidateV1":
        if (self.x_min_mm is None) != (self.x_max_mm is None):
            raise ValueError("candidate axial extent requires both x_min_mm and x_max_mm")
        if self.x_min_mm is not None and self.x_max_mm < self.x_min_mm:
            raise ValueError("candidate x_max_mm must not be below x_min_mm")
        return self


class StepInspectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="StepInspectionV1", pattern=r"^StepInspectionV1$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    analysis_unit: str = Field(default="mm", pattern=r"^mm$")
    assembly_axis: str = Field(default="X", pattern=r"^X$")
    solid_count: int = Field(gt=0)
    hub_solid_index_1based: int = Field(gt=0)
    segment_solid_indices_1based: list[int] = Field(min_length=1)
    segment_frames: list[SegmentRadialFrameV1] = Field(min_length=1)
    hub_cylindrical_candidates: list[CylindricalFaceCandidateV1] = Field(default_factory=list)
    segment_cylindrical_candidates: list[CylindricalFaceCandidateV1] = Field(default_factory=list)
    interface_selection_status: InterfaceSelectionStatus = InterfaceSelectionStatus.AMBIGUOUS
    spacing_deviation_max_deg: float = Field(ge=0)


class GapScenarioV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    gap_mm: float = Field(ge=0)
    kind: GapScenarioKind
    source_ids: list[str] = Field(min_length=1)
    derivation: str | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> "GapScenarioV1":
        if self.kind == GapScenarioKind.DERIVED_SENSITIVITY and not self.derivation:
            raise ValueError("derived sensitivity scenario requires derivation")
        if self.kind == GapScenarioKind.MEASURED_ENDPOINT and self.derivation:
            raise ValueError("measured endpoint must not carry a derivation")
        return self


class InterfaceSelectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hub_face_index_1based: int = Field(gt=0)
    segment_face_indices_1based: dict[int, list[int]] = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_segment_face_lists(self) -> "InterfaceSelectionV1":
        for solid_index, face_indices in self.segment_face_indices_1based.items():
            if solid_index <= 0:
                raise ValueError("segment solid indices must be positive")
            if not face_indices:
                raise ValueError("each selected segment must contain at least one face")
            if any(face_index <= 0 for face_index in face_indices):
                raise ValueError("selected face indices must be positive")
            if len(set(face_indices)) != len(face_indices):
                raise ValueError("selected face indices must be unique per segment")
        return self


class GeometryPreparationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="GeometryPreparationV1", pattern=r"^GeometryPreparationV1$")
    status: GeometryPreparationStatus
    blockers: list[str] = Field(default_factory=list)
    scenarios: list[GapScenarioV1] = Field(min_length=1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_local_step(
    path: str | Path,
    *,
    expected_sha256: str,
    expected_byte_size: int,
) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise StepEvidenceError(f"STEP file not found: {candidate}")

    actual_size = candidate.stat().st_size
    if actual_size != expected_byte_size:
        raise StepEvidenceError(
            f"STEP byte size mismatch: expected={expected_byte_size} actual={actual_size}"
        )

    actual_sha = sha256_file(candidate)
    if actual_sha != expected_sha256:
        raise StepEvidenceError(
            f"STEP SHA-256 mismatch: expected={expected_sha256} actual={actual_sha}"
        )
    return candidate


def build_segment_radial_frames(
    items: Iterable[tuple[int, float, float]],
) -> tuple[list[SegmentRadialFrameV1], float]:
    frames: list[SegmentRadialFrameV1] = []
    for solid_index, center_y, center_z in items:
        radius = math.hypot(center_y, center_z)
        if radius <= 0:
            raise ValueError("segment centroid lies on assembly axis")
        angle = math.degrees(math.atan2(center_z, center_y)) % 360.0
        frames.append(
            SegmentRadialFrameV1(
                solid_index_1based=solid_index,
                center_y_mm=center_y,
                center_z_mm=center_z,
                radial_center_mm=radius,
                radial_unit_y=center_y / radius,
                radial_unit_z=center_z / radius,
                angle_deg=angle,
            )
        )

    frames.sort(key=lambda item: item.angle_deg)
    if len(frames) < 2:
        return frames, 0.0

    expected_spacing = 360.0 / len(frames)
    angles = [item.angle_deg for item in frames]
    spacings = [
        (angles[(index + 1) % len(angles)] - angles[index]) % 360.0
        for index in range(len(angles))
    ]
    deviation = max(abs(value - expected_spacing) for value in spacings)
    return frames, deviation


def build_gap_sensitivity(
    minimum_mm: float,
    maximum_mm: float,
    *,
    source_id: str,
) -> list[GapScenarioV1]:
    if maximum_mm <= minimum_mm:
        raise ValueError("GAP sensitivity requires a non-zero measured range")

    midpoint = (minimum_mm + maximum_mm) / 2.0
    plan = [
        GapScenarioV1(
            scenario_id="GAP_MIN_MEASURED",
            gap_mm=minimum_mm,
            kind=GapScenarioKind.MEASURED_ENDPOINT,
            source_ids=[source_id],
        ),
        GapScenarioV1(
            scenario_id="GAP_MID_DERIVED",
            gap_mm=midpoint,
            kind=GapScenarioKind.DERIVED_SENSITIVITY,
            source_ids=[source_id],
            derivation=(
                "(minimum_mm + maximum_mm) / 2; sensitivity sample only, "
                "not measured evidence"
            ),
        ),
        GapScenarioV1(
            scenario_id="GAP_MAX_MEASURED",
            gap_mm=maximum_mm,
            kind=GapScenarioKind.MEASURED_ENDPOINT,
            source_ids=[source_id],
        ),
    ]
    validate_gap_sensitivity_plan(plan, minimum_mm=minimum_mm, maximum_mm=maximum_mm)
    return plan


def validate_gap_sensitivity_plan(
    scenarios: list[GapScenarioV1],
    *,
    minimum_mm: float,
    maximum_mm: float,
) -> None:
    if maximum_mm <= minimum_mm:
        raise ValueError("invalid measured GAP range")
    measured = sorted(
        scenario.gap_mm
        for scenario in scenarios
        if scenario.kind == GapScenarioKind.MEASURED_ENDPOINT
    )
    if measured != sorted([minimum_mm, maximum_mm]):
        raise ValueError(
            "measured GAP scenarios must be exactly the reported range endpoints"
        )

    midpoint = (minimum_mm + maximum_mm) / 2.0
    derived_midpoint = [
        scenario
        for scenario in scenarios
        if scenario.kind == GapScenarioKind.DERIVED_SENSITIVITY
        and math.isclose(scenario.gap_mm, midpoint, rel_tol=0, abs_tol=1e-12)
    ]
    if len(derived_midpoint) != 1:
        raise ValueError("GAP midpoint must exist exactly once as DERIVED_SENSITIVITY")


def _candidate_map(
    candidates: Iterable[CylindricalFaceCandidateV1],
) -> dict[tuple[int, int], CylindricalFaceCandidateV1]:
    return {
        (item.solid_index_1based, item.face_index_1based): item
        for item in candidates
    }


def evaluate_geometry_preparation(
    inspection: StepInspectionV1,
    scenarios: list[GapScenarioV1],
    selection: InterfaceSelectionV1 | None = None,
    *,
    test_flange_diameter_mm: float | None = None,
) -> GeometryPreparationV1:
    blockers: list[str] = []

    if selection is None:
        blockers.append("interface:seat_faces_unconfirmed")
    else:
        hub_map = _candidate_map(inspection.hub_cylindrical_candidates)
        if (
            inspection.hub_solid_index_1based,
            selection.hub_face_index_1based,
        ) not in hub_map:
            blockers.append("interface:selected_hub_face_not_candidate")

        segment_map = _candidate_map(inspection.segment_cylindrical_candidates)
        for solid_index in inspection.segment_solid_indices_1based:
            face_indices = selection.segment_face_indices_1based.get(solid_index)
            if not face_indices:
                blockers.append(f"interface:segment_{solid_index}_faces_missing")
                continue

            for face_index in face_indices:
                key = (solid_index, face_index)
                candidate = segment_map.get(key)
                if candidate is None:
                    blockers.append(
                        f"interface:segment_{solid_index}_face_{face_index}_not_candidate"
                    )
                    continue
                if (
                    test_flange_diameter_mm is not None
                    and (2.0 * candidate.radius_mm) + 1e-9
                    < test_flange_diameter_mm
                ):
                    blockers.append(
                        f"interface:segment_{solid_index}_face_{face_index}_diameter_below_test_flange"
                    )

    status = (
        GeometryPreparationStatus.BLOCKED_INTERFACE_SELECTION
        if blockers
        else GeometryPreparationStatus.READY_FOR_PARAMETERIZATION
    )
    return GeometryPreparationV1(
        status=status,
        blockers=sorted(blockers),
        scenarios=scenarios,
    )


def inspect_local_step(
    path: str | Path,
    *,
    expected_sha256: str,
    expected_byte_size: int,
    hub_solid_index_1based: int,
    segment_solid_indices_1based: list[int],
) -> StepInspectionV1:
    candidate = verify_local_step(
        path,
        expected_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
    )

    try:
        import cadquery as cq
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
    except ImportError as exc:
        raise CadBackendUnavailable(
            "CadQuery/OCP is required for local STEP inspection. "
            "The core package intentionally does not auto-install a heavy CAD backend."
        ) from exc

    solids = cq.importers.importStep(str(candidate)).solids().vals()
    expected_solid_count = 1 + len(segment_solid_indices_1based)
    if len(solids) != expected_solid_count:
        raise StepEvidenceError(
            f"unexpected STEP solid count: expected={expected_solid_count} actual={len(solids)}"
        )

    configured_indices = [hub_solid_index_1based, *segment_solid_indices_1based]
    if max(configured_indices) > len(solids):
        raise StepEvidenceError("configured solid index exceeds STEP solid count")
    if len(set(configured_indices)) != len(configured_indices):
        raise StepEvidenceError("hub/segment solid indices must be unique")

    centers: list[tuple[int, float, float]] = []
    for solid_index in segment_solid_indices_1based:
        center = solids[solid_index - 1].Center()
        centers.append((solid_index, center.y, center.z))
    frames, spacing_deviation = build_segment_radial_frames(centers)

    def collect_candidates(indices: list[int]) -> list[CylindricalFaceCandidateV1]:
        candidates: list[CylindricalFaceCandidateV1] = []
        for solid_index in indices:
            solid = solids[solid_index - 1]
            for face_index, face in enumerate(solid.Faces(), 1):
                adaptor = BRepAdaptor_Surface(face.wrapped, True)
                if adaptor.GetType() != GeomAbs_Cylinder:
                    continue
                cylinder = adaptor.Cylinder()
                direction = cylinder.Axis().Direction()
                alignment = abs(direction.X())
                if alignment < 0.999:
                    continue
                radius = cylinder.Radius()
                if radius < 50.0:
                    continue
                bbox = face.BoundingBox()
                candidates.append(
                    CylindricalFaceCandidateV1(
                        solid_index_1based=solid_index,
                        face_index_1based=face_index,
                        radius_mm=radius,
                        area_mm2=face.Area(),
                        axis_alignment_x_abs=alignment,
                        x_min_mm=bbox.xmin,
                        x_max_mm=bbox.xmax,
                    )
                )
        return candidates

    return StepInspectionV1(
        sha256=expected_sha256,
        byte_size=expected_byte_size,
        solid_count=len(solids),
        hub_solid_index_1based=hub_solid_index_1based,
        segment_solid_indices_1based=segment_solid_indices_1based,
        segment_frames=frames,
        hub_cylindrical_candidates=collect_candidates([hub_solid_index_1based]),
        segment_cylindrical_candidates=collect_candidates(segment_solid_indices_1based),
        spacing_deviation_max_deg=spacing_deviation,
    )
