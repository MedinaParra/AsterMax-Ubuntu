from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from astermax.geometry.step_intake import (
    GapScenarioKind,
    GapScenarioV1,
    StepEvidenceError,
    verify_local_step,
)


class PlanarInterfaceError(RuntimeError):
    """Raised when the posterior mounting plane cannot be established uniquely."""


class GapVariantEvidenceClass(StrEnum):
    MEASURED_ENDPOINT = "MEASURED_ENDPOINT"
    DERIVED_SENSITIVITY = "DERIVED_SENSITIVITY"


class PlanarSegmentSupportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solid_index_1based: int = Field(gt=0)
    face_index_1based: int = Field(gt=0)
    support_area_mm2: float = Field(gt=0)


class PlanarInterfaceEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="PlanarInterfaceEvidenceV1",
        pattern=r"^PlanarInterfaceEvidenceV1$",
    )
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_byte_size: int = Field(gt=0)
    analysis_unit: str = Field(default="mm", pattern=r"^mm$")
    assembly_axis: str = Field(default="X", pattern=r"^X$")
    plane_x_mm: float
    outward_normal_xyz: tuple[float, float, float]
    hub_solid_index_1based: int = Field(gt=0)
    hub_face_index_1based: int = Field(gt=0)
    segment_supports: list[PlanarSegmentSupportV1] = Field(min_length=1)
    support_area_total_mm2: float = Field(gt=0)
    support_area_mean_per_segment_mm2: float = Field(gt=0)
    unique_shared_plane: bool
    nominal_step_gap_mm: float = Field(default=0.0, ge=0)
    solver_result_claimed: bool = False


class GapVariantRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    gap_mm: float = Field(gt=0)
    evidence_class: GapVariantEvidenceClass
    translation_xyz_mm: tuple[float, float, float]
    output_file: str = Field(min_length=1)
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_byte_size: int = Field(gt=0)
    solid_count: int = Field(gt=0)


class GapVariantManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="GapVariantManifestV1",
        pattern=r"^GapVariantManifestV1$",
    )
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_byte_size: int = Field(gt=0)
    interface: PlanarInterfaceEvidenceV1
    variants: list[GapVariantRecordV1] = Field(min_length=1)
    cad_bytes_committed: bool = False
    fea: bool = False
    solver_result_claimed: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _x_normal_planar_faces(solid, *, min_area_mm2: float):
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
    except ImportError as exc:  # pragma: no cover - optional local CAD backend
        raise PlanarInterfaceError("OCP is required for local planar-interface inspection") from exc

    result = []
    for face_index, face in enumerate(solid.Faces(), 1):
        if face.Area() < min_area_mm2:
            continue
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        if adaptor.GetType() != GeomAbs_Plane:
            continue
        direction = adaptor.Plane().Axis().Direction()
        if abs(direction.X()) < 0.999999:
            continue
        center = face.Center()
        result.append((face_index, face, center.x))
    return result


def _derive_outward_normal(
    *,
    plane_x_mm: float,
    hub_center_x_mm: float,
    segment_center_x_values_mm: Iterable[float],
) -> tuple[float, float, float]:
    values = list(segment_center_x_values_mm)
    if not values:
        raise PlanarInterfaceError("no segment centers available for interface orientation")

    segment_side = -1.0 if all(value < plane_x_mm for value in values) else 1.0
    if not (
        all(value < plane_x_mm for value in values)
        or all(value > plane_x_mm for value in values)
    ):
        raise PlanarInterfaceError("segment centers do not lie consistently on one side of mounting plane")

    hub_side = -1.0 if hub_center_x_mm < plane_x_mm else 1.0
    if hub_side == segment_side:
        raise PlanarInterfaceError("hub and segments do not lie on opposite sides of mounting plane")

    return (segment_side, 0.0, 0.0)


def identify_planar_mounting_interface(
    path: str | Path,
    *,
    expected_sha256: str,
    expected_byte_size: int,
    hub_solid_index_1based: int,
    segment_solid_indices_1based: list[int],
    plane_tolerance_mm: float = 1e-7,
    min_face_area_mm2: float = 1000.0,
    min_overlap_area_mm2: float = 1.0,
) -> PlanarInterfaceEvidenceV1:
    source = verify_local_step(
        path,
        expected_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
    )

    try:
        import cadquery as cq
    except ImportError as exc:  # pragma: no cover - optional local CAD backend
        raise PlanarInterfaceError("CadQuery is required for local planar-interface inspection") from exc

    solids = cq.importers.importStep(str(source)).solids().vals()
    configured = [hub_solid_index_1based, *segment_solid_indices_1based]
    if max(configured) > len(solids):
        raise StepEvidenceError("configured solid index exceeds STEP solid count")

    hub = solids[hub_solid_index_1based - 1]
    hub_faces = _x_normal_planar_faces(hub, min_area_mm2=min_face_area_mm2)
    accepted = []

    for hub_face_index, hub_face, plane_x in hub_faces:
        segment_supports: list[PlanarSegmentSupportV1] = []
        valid = True
        for solid_index in segment_solid_indices_1based:
            segment = solids[solid_index - 1]
            candidates = [
                item
                for item in _x_normal_planar_faces(
                    segment,
                    min_area_mm2=min_face_area_mm2,
                )
                if abs(item[2] - plane_x) <= plane_tolerance_mm
            ]

            overlaps = []
            for face_index, face, _ in candidates:
                overlap = face.intersect(hub_face)
                area = overlap.Area()
                if area >= min_overlap_area_mm2:
                    overlaps.append((area, face_index))

            if not overlaps:
                valid = False
                break

            overlaps.sort(reverse=True)
            best_area, best_face_index = overlaps[0]
            segment_supports.append(
                PlanarSegmentSupportV1(
                    solid_index_1based=solid_index,
                    face_index_1based=best_face_index,
                    support_area_mm2=best_area,
                )
            )

        if valid:
            accepted.append((hub_face_index, plane_x, segment_supports))

    if len(accepted) != 1:
        raise PlanarInterfaceError(
            f"expected exactly one shared posterior mounting plane, found {len(accepted)}"
        )

    hub_face_index, plane_x, supports = accepted[0]
    normal = _derive_outward_normal(
        plane_x_mm=plane_x,
        hub_center_x_mm=hub.Center().x,
        segment_center_x_values_mm=[
            solids[index - 1].Center().x for index in segment_solid_indices_1based
        ],
    )
    total = sum(item.support_area_mm2 for item in supports)

    return PlanarInterfaceEvidenceV1(
        source_sha256=expected_sha256,
        source_byte_size=expected_byte_size,
        plane_x_mm=plane_x,
        outward_normal_xyz=normal,
        hub_solid_index_1based=hub_solid_index_1based,
        hub_face_index_1based=hub_face_index,
        segment_supports=supports,
        support_area_total_mm2=total,
        support_area_mean_per_segment_mm2=total / len(supports),
        unique_shared_plane=True,
        nominal_step_gap_mm=0.0,
    )


def translation_for_gap(
    interface: PlanarInterfaceEvidenceV1,
    gap_mm: float,
) -> tuple[float, float, float]:
    if gap_mm <= 0:
        raise ValueError("GAP variant must use a positive separation")
    return tuple(component * gap_mm for component in interface.outward_normal_xyz)


def generate_local_gap_variants(
    source_path: str | Path,
    output_directory: str | Path,
    *,
    interface: PlanarInterfaceEvidenceV1,
    scenarios: list[GapScenarioV1],
    segment_solid_indices_1based: list[int],
) -> GapVariantManifestV1:
    source = verify_local_step(
        source_path,
        expected_sha256=interface.source_sha256,
        expected_byte_size=interface.source_byte_size,
    )

    try:
        import cadquery as cq
    except ImportError as exc:  # pragma: no cover - optional local CAD backend
        raise PlanarInterfaceError("CadQuery is required for local GAP variant generation") from exc

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    solids = cq.importers.importStep(str(source)).solids().vals()
    expected_solid_count = len(solids)
    segment_zero_based = {value - 1 for value in segment_solid_indices_1based}

    records: list[GapVariantRecordV1] = []
    for scenario in scenarios:
        translation = translation_for_gap(interface, scenario.gap_mm)
        moved = []
        for index, solid in enumerate(solids):
            if index in segment_zero_based:
                moved.append(solid.translate(cq.Vector(*translation)))
            else:
                moved.append(solid)

        compound = cq.Compound.makeCompound(moved)
        safe_id = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in scenario.scenario_id
        )
        output_path = output_dir / f"AsterMax_{safe_id}.step"
        cq.exporters.export(compound, str(output_path))

        reopened = cq.importers.importStep(str(output_path)).solids().vals()
        if len(reopened) != expected_solid_count:
            raise StepEvidenceError(
                "generated GAP variant failed read-back solid-count validation"
            )

        evidence_class = (
            GapVariantEvidenceClass.MEASURED_ENDPOINT
            if scenario.kind == GapScenarioKind.MEASURED_ENDPOINT
            else GapVariantEvidenceClass.DERIVED_SENSITIVITY
        )
        records.append(
            GapVariantRecordV1(
                scenario_id=scenario.scenario_id,
                gap_mm=scenario.gap_mm,
                evidence_class=evidence_class,
                translation_xyz_mm=translation,
                output_file=output_path.name,
                output_sha256=_sha256(output_path),
                output_byte_size=output_path.stat().st_size,
                solid_count=len(reopened),
            )
        )

    return GapVariantManifestV1(
        source_sha256=interface.source_sha256,
        source_byte_size=interface.source_byte_size,
        interface=interface,
        variants=records,
    )
