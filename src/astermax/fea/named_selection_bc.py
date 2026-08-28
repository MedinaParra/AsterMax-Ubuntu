from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from astermax.credibility import canonical_sha256
from .model_preparation_evidence import _axis_face_tag
from .named_selections import PersistentNamedSelection, capture_named_selection, resolve_named_selection


class NamedSelectionBindingError(ValueError):
    pass


_AXIS_KEYS = ("X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX")
_AXIS_SPEC = {
    "X_MIN": (0, 0, "MIN"), "X_MAX": (0, 3, "MAX"),
    "Y_MIN": (1, 1, "MIN"), "Y_MAX": (1, 4, "MAX"),
    "Z_MIN": (2, 2, "MIN"), "Z_MAX": (2, 5, "MAX"),
}


@dataclass(frozen=True)
class NamedSelectionMeshBinding:
    schema: str
    name: str
    role: str
    named_selection_sha256: str
    resolution_sha256: str
    surface_keys: tuple[str, ...]
    resolved_face_tags: tuple[int, ...]
    tri6_count: int
    binding_sha256: str


def _validate_bbox(bbox_mm: tuple[float, float, float, float, float, float]) -> tuple[float, ...]:
    bbox = tuple(float(v) for v in bbox_mm)
    if len(bbox) != 6 or not np.all(np.isfinite(np.asarray(bbox))):
        raise NamedSelectionBindingError("bbox_mm must contain six finite values")
    dims = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
    if np.any(dims <= 0.0):
        raise NamedSelectionBindingError("bbox_mm must have positive dimensions")
    return bbox


def capture_axis_named_selection(
    step_path: str | Path,
    bbox_mm: tuple[float, float, float, float, float, float],
    surface_keys: Iterable[str],
    *,
    name: str,
    role: str,
) -> PersistentNamedSelection:
    """Author a persistent named selection from one or more PMV boundary faces.

    C5.1 intentionally supports the six unique axis-boundary CAD faces exposed by
    the current single-solid STEP mesher. This is broader than the legacy
    X_MIN/X_MAX contract while remaining fail-closed for unsupported arbitrary
    sloped/internal faces.
    """
    bbox = _validate_bbox(bbox_mm)
    keys = tuple(str(v).strip().upper() for v in surface_keys)
    if not keys or any(key not in _AXIS_SPEC for key in keys):
        raise NamedSelectionBindingError("surface_keys must use X/Y/Z MIN/MAX boundary keys")
    if len(set(keys)) != len(keys):
        raise NamedSelectionBindingError("surface_keys contains duplicates")
    dims = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
    tol = max(float(np.linalg.norm(dims)) * 1.0e-8, 1.0e-9)
    tags: list[int] = []
    for key in keys:
        axis, bbox_index, side = _AXIS_SPEC[key]
        tag, _ = _axis_face_tag(
            step_path,
            axis=axis,
            side=side,
            expected_coordinate_mm=bbox[bbox_index],
            tolerance_mm=tol,
        )
        tags.append(int(tag))
    return capture_named_selection(step_path, tags, name, role)


def _surface_key_for_member(member, bbox: tuple[float, ...]) -> str:
    signature = member.signature
    dims = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
    tol = max(float(np.linalg.norm(dims)) * 1.0e-8, 1.0e-9)
    matches: list[str] = []
    for key, (axis, bbox_index, _side) in _AXIS_SPEC.items():
        low = float(signature.bbox_mm[axis])
        high = float(signature.bbox_mm[axis + 3])
        value = float(bbox[bbox_index])
        if abs(low - value) <= tol and abs(high - value) <= tol:
            matches.append(key)
    if len(matches) != 1:
        raise NamedSelectionBindingError("NAMED_SELECTION_FACE_OUTSIDE_AXIS_BOUNDARY_SCOPE")
    return matches[0]


def bind_named_selection_to_mesh(
    step_path: str | Path,
    selection: PersistentNamedSelection,
    *,
    bbox_mm: tuple[float, float, float, float, float, float],
    surface_triangles: dict[str, np.ndarray],
    expected_role: str,
) -> tuple[NamedSelectionMeshBinding, np.ndarray]:
    bbox = _validate_bbox(bbox_mm)
    role = str(expected_role).strip().upper()
    if role not in {"SUPPORT", "LOAD"} or selection.role != role:
        raise NamedSelectionBindingError("named selection role does not match BC binding")
    resolution = resolve_named_selection(step_path, selection)
    keys = tuple(_surface_key_for_member(member, bbox) for member in selection.member_selections)
    if len(set(keys)) != len(keys):
        raise NamedSelectionBindingError("named selection maps duplicate mesh boundary groups")
    blocks: list[np.ndarray] = []
    for key in keys:
        block = np.asarray(surface_triangles.get(key), dtype=np.int64)
        if block.ndim != 2 or block.shape[1] != 6 or block.shape[0] == 0:
            raise NamedSelectionBindingError(f"mesh boundary {key} does not contain TRI6 data")
        blocks.append(block)
    triangles = np.vstack(blocks)
    core = {
        "schema": "AsterMaxNamedSelectionMeshBindingV1",
        "name": selection.name,
        "role": selection.role,
        "named_selection_sha256": selection.named_selection_sha256,
        "resolution_sha256": resolution.resolution_sha256,
        "surface_keys": list(keys),
        "resolved_face_tags": list(resolution.resolved_tags),
        "tri6_count": int(triangles.shape[0]),
    }
    binding = NamedSelectionMeshBinding(**core, binding_sha256=canonical_sha256(core))
    return binding, triangles


def supported_axis_surface_keys() -> tuple[str, ...]:
    return _AXIS_KEYS
