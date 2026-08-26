from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .gmsh_bridge import GmshBridgeError, _gmsh


@dataclass(frozen=True)
class CadPreflightReport:
    source: str
    gmsh_version: str
    solid_count: int
    surface_count: int
    bbox_mm: tuple[float, float, float, float, float, float]
    dimensions_mm: tuple[float, float, float]
    diagonal_mm: float
    tolerance_mm: float
    tiny_face_area_threshold_mm2: float
    tiny_face_tags: tuple[int, ...]
    tiny_face_areas_mm2: tuple[float, ...]
    axis_scope_counts: dict[str, int]
    warnings: tuple[str, ...]
    certified_single_solid_ready: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _axis_scope_counts(gmsh, surfaces, bbox, tolerance_mm: float) -> dict[str, int]:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    targets = {
        "X_MIN": (0, xmin), "X_MAX": (0, xmax),
        "Y_MIN": (1, ymin), "Y_MAX": (1, ymax),
        "Z_MIN": (2, zmin), "Z_MAX": (2, zmax),
    }
    counts = {name: 0 for name in targets}
    for dim, tag in surfaces:
        sb = gmsh.model.getBoundingBox(dim, tag)
        for name, (axis, value) in targets.items():
            if abs(sb[axis] - value) <= tolerance_mm and abs(sb[axis + 3] - value) <= tolerance_mm:
                counts[name] += 1
    return counts


def preflight_step(step_path: str | Path, *, relative_tolerance: float = 1.0e-6,
                   tiny_face_relative_area: float = 1.0e-6) -> CadPreflightReport:
    """Inspect STEP topology before meshing without healing or mutating source CAD."""
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise GmshBridgeError("preflight input must be an existing STEP/STP file")
    if relative_tolerance <= 0 or tiny_face_relative_area <= 0:
        raise ValueError("preflight tolerances must be positive")

    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_cad_preflight")
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        surfaces = gmsh.model.getEntities(2)
        if not volumes:
            raise GmshBridgeError("STEP contains no 3-D solid")

        boxes = [gmsh.model.getBoundingBox(3, tag) for _, tag in volumes]
        bbox = (
            min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes),
        )
        dims = np.asarray((bbox[3]-bbox[0], bbox[4]-bbox[1], bbox[5]-bbox[2]), dtype=float)
        if np.any(dims <= 0) or not np.all(np.isfinite(dims)):
            raise GmshBridgeError(f"invalid STEP dimensions: {tuple(dims)}")
        diagonal = float(np.linalg.norm(dims))
        tol = max(diagonal * relative_tolerance, np.finfo(float).eps)
        area_threshold = float(np.prod(np.sort(dims)[-2:]) * tiny_face_relative_area)

        tiny_tags: list[int] = []
        tiny_areas: list[float] = []
        for _, tag in surfaces:
            area = float(gmsh.model.occ.getMass(2, tag))
            if not np.isfinite(area) or area <= 0:
                raise GmshBridgeError(f"surface {tag} has invalid area {area}")
            if area < area_threshold:
                tiny_tags.append(int(tag)); tiny_areas.append(area)

        scopes = _axis_scope_counts(gmsh, surfaces, bbox, tol)
        warnings: list[str] = []
        if len(volumes) != 1:
            warnings.append(f"MULTI_SOLID:{len(volumes)}")
        missing = [name for name, count in scopes.items() if count == 0]
        ambiguous = [name for name, count in scopes.items() if count > 1]
        if missing:
            warnings.append("AXIS_SCOPE_MISSING:" + ",".join(missing))
        if ambiguous:
            warnings.append("AXIS_SCOPE_AMBIGUOUS:" + ",".join(ambiguous))
        if tiny_tags:
            warnings.append(f"TINY_FACES:{len(tiny_tags)}")

        ready = len(volumes) == 1 and not missing and not ambiguous and not tiny_tags
        return CadPreflightReport(
            source=path.name, gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
            solid_count=len(volumes), surface_count=len(surfaces),
            bbox_mm=tuple(float(v) for v in bbox), dimensions_mm=tuple(float(v) for v in dims),
            diagonal_mm=diagonal, tolerance_mm=tol,
            tiny_face_area_threshold_mm2=area_threshold,
            tiny_face_tags=tuple(tiny_tags), tiny_face_areas_mm2=tuple(tiny_areas),
            axis_scope_counts=scopes, warnings=tuple(warnings),
            certified_single_solid_ready=ready,
        )
    finally:
        gmsh.finalize()
