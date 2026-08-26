from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np


class SurfaceSelectionError(RuntimeError):
    """Raised when a persistent CAD surface selection cannot be resolved safely."""


@dataclass(frozen=True)
class SurfaceSignature:
    """Mesh-independent identity for one STEP surface.

    The signature deliberately excludes the transient Gmsh entity tag and any
    mesh node/element identifiers.  It is built only from OCC/CAD properties
    available before meshing so it can be persisted in a project file and
    resolved again after remeshing.
    """

    schema: str
    surface_type: str
    area_mm2: float
    centroid_mm: tuple[float, float, float]
    bbox_mm: tuple[float, float, float, float, float, float]
    model_diagonal_mm: float
    fingerprint_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SurfaceSignature":
        if data.get("schema") != "AsterMaxSurfaceSignatureV1":
            raise SurfaceSelectionError("unsupported surface signature schema")
        return cls(
            schema=str(data["schema"]),
            surface_type=str(data["surface_type"]),
            area_mm2=float(data["area_mm2"]),
            centroid_mm=tuple(float(v) for v in data["centroid_mm"]),
            bbox_mm=tuple(float(v) for v in data["bbox_mm"]),
            model_diagonal_mm=float(data["model_diagonal_mm"]),
            fingerprint_sha256=str(data["fingerprint_sha256"]),
        )


@dataclass(frozen=True)
class ResolvedSurface:
    entity_tag: int
    signature: SurfaceSignature
    normalized_distance: float


def _gmsh():
    try:
        import gmsh  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SurfaceSelectionError("gmsh is required for STEP surface selection") from exc
    return gmsh


def _canonical_payload(surface_type: str, area_mm2: float, centroid_mm, bbox_mm, model_diagonal_mm: float) -> dict:
    scale = max(float(model_diagonal_mm), 1.0)
    # Quantization is used only for the human/audit fingerprint. Resolution
    # below compares the unrounded geometric values with explicit tolerances.
    return {
        "schema": "AsterMaxSurfaceSignatureV1",
        "surface_type": str(surface_type),
        "area_over_diag2": round(float(area_mm2) / (scale * scale), 12),
        "centroid_over_diag": [round(float(v) / scale, 12) for v in centroid_mm],
        "bbox_over_diag": [round(float(v) / scale, 12) for v in bbox_mm],
    }


def surface_signature_for_entity(gmsh, entity_tag: int, model_bbox_mm) -> SurfaceSignature:
    bbox_model = tuple(float(v) for v in model_bbox_mm)
    model_span = np.asarray(bbox_model[3:]) - np.asarray(bbox_model[:3])
    diagonal = float(np.linalg.norm(model_span))
    if not np.isfinite(diagonal) or diagonal <= 0.0:
        raise SurfaceSelectionError("invalid model diagonal for surface signature")

    area = float(gmsh.model.occ.getMass(2, int(entity_tag)))
    centroid = tuple(float(v) for v in gmsh.model.occ.getCenterOfMass(2, int(entity_tag)))
    bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(2, int(entity_tag)))
    surface_type = str(gmsh.model.getType(2, int(entity_tag)))
    values = np.asarray((area, *centroid, *bbox), dtype=float)
    if area <= 0.0 or not np.all(np.isfinite(values)):
        raise SurfaceSelectionError(f"invalid CAD properties for surface tag {entity_tag}")

    payload = _canonical_payload(surface_type, area, centroid, bbox, diagonal)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    return SurfaceSignature(
        schema="AsterMaxSurfaceSignatureV1",
        surface_type=surface_type,
        area_mm2=area,
        centroid_mm=centroid,
        bbox_mm=bbox,
        model_diagonal_mm=diagonal,
        fingerprint_sha256=fingerprint,
    )


def _signature_distance(reference: SurfaceSignature, candidate: SurfaceSignature) -> float:
    if candidate.surface_type != reference.surface_type:
        return float("inf")
    scale = max(reference.model_diagonal_mm, candidate.model_diagonal_mm, 1.0)
    area_scale = max(reference.area_mm2, candidate.area_mm2, scale * scale * 1.0e-12)
    area_term = abs(candidate.area_mm2 - reference.area_mm2) / area_scale
    centroid_term = float(np.linalg.norm(np.asarray(candidate.centroid_mm) - np.asarray(reference.centroid_mm))) / scale
    bbox_term = float(np.max(np.abs(np.asarray(candidate.bbox_mm) - np.asarray(reference.bbox_mm)))) / scale
    return max(area_term, centroid_term, bbox_term)


def resolve_surface_signature_in_model(
    gmsh,
    signature: SurfaceSignature,
    model_bbox_mm,
    *,
    relative_tolerance: float = 1.0e-8,
) -> ResolvedSurface:
    if relative_tolerance <= 0.0 or not np.isfinite(relative_tolerance):
        raise SurfaceSelectionError("relative_tolerance must be finite and positive")
    candidates: list[ResolvedSurface] = []
    for dim, tag in gmsh.model.getEntities(2):
        if dim != 2:
            continue
        candidate = surface_signature_for_entity(gmsh, int(tag), model_bbox_mm)
        distance = _signature_distance(signature, candidate)
        if np.isfinite(distance) and distance <= relative_tolerance:
            candidates.append(ResolvedSurface(int(tag), candidate, float(distance)))

    if not candidates:
        raise SurfaceSelectionError(
            "persistent surface selection did not resolve: no CAD face matches the stored signature"
        )
    candidates.sort(key=lambda item: (item.normalized_distance, item.entity_tag))
    if len(candidates) > 1:
        first, second = candidates[0], candidates[1]
        # A genuinely duplicated/symmetric face signature must not silently pick
        # one entity.  The user/model preparation layer has to disambiguate it.
        if second.normalized_distance <= relative_tolerance:
            raise SurfaceSelectionError(
                "persistent surface selection is ambiguous: multiple CAD faces match the stored signature"
            )
    return candidates[0]


def inspect_step_surfaces(step_path: str | Path) -> list[tuple[int, SurfaceSignature]]:
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise SurfaceSelectionError("surface inspection requires an existing STEP/STP file")
    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_surface_inspection")
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise SurfaceSelectionError(f"PMV surface inspection requires exactly one solid; found {len(volumes)}")
        model_bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, volumes[0][1]))
        return [
            (int(tag), surface_signature_for_entity(gmsh, int(tag), model_bbox))
            for dim, tag in gmsh.model.getEntities(2)
            if dim == 2
        ]
    finally:
        gmsh.finalize()


def resolve_step_surface(step_path: str | Path, signature: SurfaceSignature, *, relative_tolerance: float = 1.0e-8) -> ResolvedSurface:
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise SurfaceSelectionError("surface resolution requires an existing STEP/STP file")
    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_surface_resolution")
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise SurfaceSelectionError(f"PMV surface resolution requires exactly one solid; found {len(volumes)}")
        model_bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, volumes[0][1]))
        return resolve_surface_signature_in_model(
            gmsh,
            signature,
            model_bbox,
            relative_tolerance=relative_tolerance,
        )
    finally:
        gmsh.finalize()
