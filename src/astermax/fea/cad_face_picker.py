from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .face_ownership import (
    ArbitraryNamedSelectionBinding,
    Tet10FaceOwnershipInventory,
    bind_named_selection_to_owned_faces,
)
from .named_selections import PersistentNamedSelection, capture_named_selection


class CadFacePickerError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectedCadFace:
    face_id: str
    face_tag_provenance: int
    signature_sha256: str
    surface_type: str
    area_mm2: float
    center_mm: tuple[float, float, float]
    projected_center_px: tuple[float, float]
    projected_triangles_px: tuple[tuple[tuple[float, float], ...], ...]
    projected_depth: float
    tri6_count: int


@dataclass(frozen=True)
class CadFacePickerCatalog:
    schema: str
    source_step_sha256: str
    ownership_sha256: str
    viewport_width_px: int
    viewport_height_px: int
    projection_contract: str
    faces: tuple[ProjectedCadFace, ...]
    catalog_sha256: str


@dataclass(frozen=True)
class CadFacePick:
    schema: str
    catalog_sha256: str
    face_id: str
    signature_sha256: str
    click_px: tuple[float, float]
    pick_sha256: str


@dataclass(frozen=True)
class PickerNamedSelectionEvidence:
    schema: str
    catalog_sha256: str
    picked_face_ids: tuple[str, ...]
    picked_signature_sha256: tuple[str, ...]
    named_selection_sha256: str
    binding_sha256: str
    tri6_count: int
    evidence_sha256: str


def _projection(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic oblique engineering projection plus depth coordinate.

    This is intentionally a picker projection, not a CAD tessellation claim. The
    same owned TRI6 corner nodes consumed by BC/load binding are projected.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3 or not np.all(np.isfinite(pts)):
        raise CadFacePickerError("picker points must be finite Nx3 coordinates")
    u = pts[:, 0] + 0.42 * pts[:, 2]
    v = -pts[:, 1] + 0.28 * pts[:, 2]
    depth = 0.35 * pts[:, 0] + 0.25 * pts[:, 1] + pts[:, 2]
    return np.column_stack((u, v)), depth


def _normalize_to_viewport(projected: np.ndarray, width: int, height: int, padding: float) -> np.ndarray:
    if width < 160 or height < 120:
        raise CadFacePickerError("viewport is too small for deterministic face picking")
    if not 0.02 <= padding <= 0.25:
        raise CadFacePickerError("padding must be between 0.02 and 0.25")
    lo = projected.min(axis=0)
    hi = projected.max(axis=0)
    span = hi - lo
    if np.any(span <= 0.0) or not np.all(np.isfinite(span)):
        raise CadFacePickerError("projected CAD extent is degenerate")
    inner_w = width * (1.0 - 2.0 * padding)
    inner_h = height * (1.0 - 2.0 * padding)
    scale = min(inner_w / span[0], inner_h / span[1])
    used = span * scale
    origin = np.array(((width - used[0]) * 0.5, (height - used[1]) * 0.5), dtype=float)
    return origin + (projected - lo) * scale


def build_cad_face_picker_catalog(
    inventory: Tet10FaceOwnershipInventory,
    *,
    viewport_width_px: int = 760,
    viewport_height_px: int = 560,
    padding: float = 0.08,
) -> CadFacePickerCatalog:
    if inventory.schema != "AsterMaxTet10FaceOwnershipInventoryV1":
        raise CadFacePickerError("unsupported face-ownership inventory schema")
    if not inventory.faces:
        raise CadFacePickerError("face-ownership inventory is empty")
    if len({face.signature_sha256 for face in inventory.faces}) != len(inventory.faces):
        raise CadFacePickerError("CAD_FACE_SIGNATURE_NOT_UNIQUE")

    projected_all, depth_all = _projection(inventory.nodes_mm)
    px_all = _normalize_to_viewport(projected_all, int(viewport_width_px), int(viewport_height_px), float(padding))

    ordered = tuple(sorted(inventory.faces, key=lambda item: item.signature_sha256))
    faces: list[ProjectedCadFace] = []
    for index, face in enumerate(ordered, start=1):
        tri = np.asarray(face.triangles, dtype=np.int64)
        if tri.ndim != 2 or tri.shape[1] != 6 or tri.shape[0] <= 0:
            raise CadFacePickerError("owned CAD face does not contain valid TRI6")
        corner = tri[:, :3]
        if np.any(corner < 0) or np.any(corner >= inventory.nodes_mm.shape[0]):
            raise CadFacePickerError("owned TRI6 references invalid node index")
        projected_triangles = tuple(
            tuple((float(px_all[node, 0]), float(px_all[node, 1])) for node in row)
            for row in corner
        )
        unique_nodes = np.unique(corner)
        center_px = px_all[unique_nodes].mean(axis=0)
        depth = float(depth_all[unique_nodes].mean())
        faces.append(
            ProjectedCadFace(
                face_id=f"F{index:03d}",
                face_tag_provenance=int(face.face_tag),
                signature_sha256=face.signature_sha256,
                surface_type=face.surface_type,
                area_mm2=float(face.area_mm2),
                center_mm=tuple(float(v) for v in face.center_mm),
                projected_center_px=(float(center_px[0]), float(center_px[1])),
                projected_triangles_px=projected_triangles,
                projected_depth=depth,
                tri6_count=int(face.tri6_count),
            )
        )

    core = {
        "schema": "AsterMaxCadFacePickerCatalogV1",
        "source_step_sha256": inventory.source_step_sha256,
        "ownership_sha256": inventory.ownership_sha256,
        "viewport_width_px": int(viewport_width_px),
        "viewport_height_px": int(viewport_height_px),
        "projection_contract": "OBLIQUE_X_PLUS_042Z__NEG_Y_PLUS_028Z__OWNED_TRI6_CORNERS",
        "faces": [asdict(face) for face in faces],
    }
    return CadFacePickerCatalog(
        **core,
        faces=tuple(faces),
        catalog_sha256=canonical_sha256(core),
    )


def _point_in_triangle(point: tuple[float, float], triangle: tuple[tuple[float, float], ...], tol: float = 1e-8) -> bool:
    p = np.asarray(point, dtype=float)
    a, b, c = (np.asarray(value, dtype=float) for value in triangle)
    v0 = c - a
    v1 = b - a
    v2 = p - a
    dot00 = float(v0 @ v0)
    dot01 = float(v0 @ v1)
    dot02 = float(v0 @ v2)
    dot11 = float(v1 @ v1)
    dot12 = float(v1 @ v2)
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) <= tol:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return u >= -tol and v >= -tol and u + v <= 1.0 + tol


def pick_cad_face(catalog: CadFacePickerCatalog, x_px: float, y_px: float) -> CadFacePick:
    if catalog.schema != "AsterMaxCadFacePickerCatalogV1":
        raise CadFacePickerError("unsupported picker catalog schema")
    point = (float(x_px), float(y_px))
    if not np.all(np.isfinite(point)):
        raise CadFacePickerError("click coordinates must be finite")
    hits = [
        face
        for face in catalog.faces
        if any(_point_in_triangle(point, triangle) for triangle in face.projected_triangles_px)
    ]
    if not hits:
        raise CadFacePickerError("CAD_FACE_PICK_MISS")
    # Stable visibility contract: larger projected depth wins, then face_id.
    chosen = sorted(hits, key=lambda face: (-face.projected_depth, face.face_id))[0]
    core = {
        "schema": "AsterMaxCadFacePickV1",
        "catalog_sha256": catalog.catalog_sha256,
        "face_id": chosen.face_id,
        "signature_sha256": chosen.signature_sha256,
        "click_px": [point[0], point[1]],
    }
    return CadFacePick(
        schema=core["schema"],
        catalog_sha256=catalog.catalog_sha256,
        face_id=chosen.face_id,
        signature_sha256=chosen.signature_sha256,
        click_px=point,
        pick_sha256=canonical_sha256(core),
    )


def capture_picker_named_selection(
    step_path: str | Path,
    inventory: Tet10FaceOwnershipInventory,
    catalog: CadFacePickerCatalog,
    face_ids: Iterable[str],
    *,
    name: str,
    role: str,
) -> tuple[PersistentNamedSelection, ArbitraryNamedSelectionBinding, np.ndarray, PickerNamedSelectionEvidence]:
    path = Path(step_path)
    if sha256_file(path) != inventory.source_step_sha256 or catalog.source_step_sha256 != inventory.source_step_sha256:
        raise CadFacePickerError("PICKER_SOURCE_IDENTITY_MISMATCH")
    if catalog.ownership_sha256 != inventory.ownership_sha256:
        raise CadFacePickerError("PICKER_OWNERSHIP_STALE")
    ids = tuple(str(value) for value in face_ids)
    if not ids or len(ids) != len(set(ids)):
        raise CadFacePickerError("picker selection must contain unique face IDs")
    by_id = {face.face_id: face for face in catalog.faces}
    if any(value not in by_id for value in ids):
        raise CadFacePickerError("PICKER_FACE_ID_UNKNOWN")
    selected = tuple(by_id[value] for value in ids)
    tags = tuple(face.face_tag_provenance for face in selected)
    named = capture_named_selection(path, tags, name, role)
    picked_signatures = tuple(face.signature_sha256 for face in selected)
    if tuple(face.signature_sha256 for face in named.faces) != picked_signatures:
        raise CadFacePickerError("PICKED_FACE_SIGNATURE_MISMATCH")
    binding, triangles = bind_named_selection_to_owned_faces(path, named, inventory, expected_role=role)
    if binding.face_signature_sha256 != picked_signatures:
        raise CadFacePickerError("PICKED_FACE_BINDING_MISMATCH")
    core = {
        "schema": "AsterMaxPickerNamedSelectionEvidenceV1",
        "catalog_sha256": catalog.catalog_sha256,
        "picked_face_ids": list(ids),
        "picked_signature_sha256": list(picked_signatures),
        "named_selection_sha256": named.named_selection_sha256,
        "binding_sha256": binding.binding_sha256,
        "tri6_count": int(triangles.shape[0]),
    }
    evidence = PickerNamedSelectionEvidence(
        schema=core["schema"],
        catalog_sha256=catalog.catalog_sha256,
        picked_face_ids=ids,
        picked_signature_sha256=picked_signatures,
        named_selection_sha256=named.named_selection_sha256,
        binding_sha256=binding.binding_sha256,
        tri6_count=int(triangles.shape[0]),
        evidence_sha256=canonical_sha256(core),
    )
    return named, binding, np.asarray(triangles, dtype=np.int64), evidence
