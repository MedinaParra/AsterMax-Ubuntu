from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .persistent_geometry import (
    PersistentFaceSelection,
    PersistentGeometryError,
    capture_face_selection,
    list_face_signatures,
)


@dataclass(frozen=True)
class ShaftEndSelections:
    x_min: PersistentFaceSelection
    x_max: PersistentFaceSelection


def capture_x_axis_shaft_end_faces(
    step_path: str | Path,
    *,
    relative_tolerance: float = 1.0e-9,
) -> ShaftEndSelections:
    inventory = list_face_signatures(step_path)
    if not inventory:
        raise PersistentGeometryError("STEP_HAS_NO_FACES")
    xs_min = min(sig.bbox_mm[0] for _, sig in inventory)
    xs_max = max(sig.bbox_mm[3] for _, sig in inventory)
    diagonal = max(
        np.linalg.norm(np.asarray(sig.bbox_mm[3:]) - np.asarray(sig.bbox_mm[:3]))
        for _, sig in inventory
    )
    tol = max(float(diagonal) * max(relative_tolerance, 1.0e-10) * 100.0, 1.0e-8)

    def candidates(target: float):
        out = []
        for tag, sig in inventory:
            if str(sig.surface_type).strip().lower() != "plane":
                continue
            box = sig.bbox_mm
            if abs(box[3] - box[0]) > tol:
                continue
            x = 0.5 * (box[0] + box[3])
            if abs(x - target) <= tol:
                out.append((tag, sig))
        return out

    left = candidates(xs_min)
    right = candidates(xs_max)
    if len(left) != 1:
        raise PersistentGeometryError("X_MIN_END_FACE_AMBIGUOUS:" + ",".join(str(tag) for tag, _ in left))
    if len(right) != 1:
        raise PersistentGeometryError("X_MAX_END_FACE_AMBIGUOUS:" + ",".join(str(tag) for tag, _ in right))
    if left[0][0] == right[0][0]:
        raise PersistentGeometryError("X_END_FACE_COLLAPSE")

    return ShaftEndSelections(
        x_min=capture_face_selection(
            step_path,
            left[0][0],
            "X_MIN_END",
            relative_tolerance=relative_tolerance,
        ),
        x_max=capture_face_selection(
            step_path,
            right[0][0],
            "X_MAX_END",
            relative_tolerance=relative_tolerance,
        ),
    )
