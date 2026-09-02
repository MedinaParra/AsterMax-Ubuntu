from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .cae_scene_contract import CaeSceneContract, validate_cae_scene_contract


class ProfessionalPostprocessError(RuntimeError):
    pass


@dataclass(frozen=True)
class LegendContract:
    field: str
    unit: str
    minimum: float
    maximum: float
    levels: tuple[float, ...]
    field_location: str
    provenance: str


@dataclass(frozen=True)
class ProbeResult:
    node_index: int
    position_mm: tuple[float, float, float]
    field: str
    value: float
    unit: str
    field_location: str
    workspace_sha256: str
    solve_evidence_sha256: str


@dataclass(frozen=True)
class ClipPlaneContract:
    origin_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    kept_triangle_indices: np.ndarray
    rejected_triangle_indices: np.ndarray
    criterion: str = "UNDEFORMED_TRIANGLE_CENTROID_SIGNED_DISTANCE_GE_ZERO"


@dataclass(frozen=True)
class ProfessionalPostprocessView:
    field: str
    unit: str
    field_location: str
    nodal_scalar: np.ndarray
    triangle_scalar: np.ndarray
    triangle_scalar_normalized: np.ndarray
    display_nodes_mm: np.ndarray
    surface_triangles: np.ndarray
    legend: LegendContract
    deformation_scale: float
    workspace_sha256: str
    solve_evidence_sha256: str


def _field(scene: CaeSceneContract, field: str) -> tuple[np.ndarray, str, str, str]:
    key = str(field).strip().upper()
    if key == "SIEQ_NOEU":
        return (
            np.asarray(scene.nodal_von_mises_mpa, dtype=float),
            "MPa",
            "NOEU",
            scene.stress_representation,
        )
    if key in {"DEPL_MAG", "DEPL_MAGNITUDE"}:
        return (
            np.asarray(scene.displacement_magnitude_mm, dtype=float),
            "mm",
            "NOEU_DERIVED_FROM_DEPL",
            "ASTERMAX_NORM_OF_NATIVE_CODE_ASTER_DEPL_NOEU",
        )
    raise ProfessionalPostprocessError(f"POSTPROCESS_FIELD_UNSUPPORTED:{key}")


def _normalized(values: np.ndarray) -> np.ndarray:
    lo = float(np.min(values))
    hi = float(np.max(values))
    if hi <= lo:
        return np.zeros(values.shape, dtype=float)
    return (values - lo) / (hi - lo)


def build_professional_postprocess_view(
    scene: CaeSceneContract,
    *,
    field: str = "SIEQ_NOEU",
    deformation_scale: float | None = None,
    legend_levels: int = 9,
) -> ProfessionalPostprocessView:
    """Create a renderer-neutral professional results view without changing solver data.

    Native Code_Aster SIEQ_NOEU stays labelled NOEU. Displacement magnitude is an
    explicitly derived AsterMax display quantity from native DEPL components; it is
    never presented as a solver-native scalar field. Triangle values are display-only
    arithmetic means of nodal values and remain separate from the nodal evidence.
    """
    validate_cae_scene_contract(scene)
    if not isinstance(legend_levels, int) or not (2 <= legend_levels <= 21):
        raise ProfessionalPostprocessError("POSTPROCESS_LEGEND_LEVELS_INVALID")
    scale = scene.deformation_scale if deformation_scale is None else float(deformation_scale)
    if not math.isfinite(scale) or scale < 0.0:
        raise ProfessionalPostprocessError("POSTPROCESS_DEFORMATION_SCALE_INVALID")

    nodal, unit, location, provenance = _field(scene, field)
    if nodal.shape != (len(scene.undeformed_nodes_mm),) or not np.isfinite(nodal).all():
        raise ProfessionalPostprocessError("POSTPROCESS_NODAL_FIELD_INVALID")
    triangles = np.asarray(scene.surface_triangles, dtype=int)
    tri_scalar = nodal[triangles].mean(axis=1)
    tri_normalized = _normalized(tri_scalar)

    undeformed = np.asarray(scene.undeformed_nodes_mm, dtype=float)
    displacement = np.asarray(scene.deformed_nodes_mm, dtype=float) - undeformed
    if scene.deformation_scale > 0.0:
        displacement = displacement / scene.deformation_scale
    elif scale != 0.0 and np.any(np.asarray(scene.displacement_magnitude_mm) > 0.0):
        raise ProfessionalPostprocessError("POSTPROCESS_NATIVE_DISPLACEMENT_VECTOR_UNRECOVERABLE")
    display_nodes = undeformed + scale * displacement

    minimum = float(np.min(nodal))
    maximum = float(np.max(nodal))
    levels = tuple(float(v) for v in np.linspace(minimum, maximum, legend_levels))
    legend = LegendContract(
        field=str(field).strip().upper(),
        unit=unit,
        minimum=minimum,
        maximum=maximum,
        levels=levels,
        field_location=location,
        provenance=provenance,
    )
    return ProfessionalPostprocessView(
        field=legend.field,
        unit=unit,
        field_location=location,
        nodal_scalar=nodal.copy(),
        triangle_scalar=np.asarray(tri_scalar, dtype=float),
        triangle_scalar_normalized=np.asarray(tri_normalized, dtype=float),
        display_nodes_mm=np.asarray(display_nodes, dtype=float),
        surface_triangles=triangles.copy(),
        legend=legend,
        deformation_scale=scale,
        workspace_sha256=scene.workspace_sha256,
        solve_evidence_sha256=scene.solve_evidence_sha256,
    )


def probe_nearest_node(
    scene: CaeSceneContract,
    point_mm: tuple[float, float, float] | np.ndarray,
    *,
    field: str = "SIEQ_NOEU",
) -> ProbeResult:
    validate_cae_scene_contract(scene)
    point = np.asarray(point_mm, dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ProfessionalPostprocessError("POSTPROCESS_PROBE_POINT_INVALID")
    nodal, unit, location, _ = _field(scene, field)
    nodes = np.asarray(scene.undeformed_nodes_mm, dtype=float)
    distances2 = np.sum((nodes - point) ** 2, axis=1)
    index = int(np.argmin(distances2))
    return ProbeResult(
        node_index=index,
        position_mm=tuple(float(v) for v in nodes[index]),
        field=str(field).strip().upper(),
        value=float(nodal[index]),
        unit=unit,
        field_location=location,
        workspace_sha256=scene.workspace_sha256,
        solve_evidence_sha256=scene.solve_evidence_sha256,
    )


def build_clip_plane(
    scene: CaeSceneContract,
    *,
    origin_mm: tuple[float, float, float] | np.ndarray,
    normal: tuple[float, float, float] | np.ndarray,
) -> ClipPlaneContract:
    """Return a deterministic display clip mask using undeformed triangle centroids."""
    validate_cae_scene_contract(scene)
    origin = np.asarray(origin_mm, dtype=float)
    vector = np.asarray(normal, dtype=float)
    if origin.shape != (3,) or vector.shape != (3,) or not np.isfinite(origin).all() or not np.isfinite(vector).all():
        raise ProfessionalPostprocessError("POSTPROCESS_CLIP_PLANE_INVALID")
    norm = float(np.linalg.norm(vector))
    if norm <= 1.0e-15:
        raise ProfessionalPostprocessError("POSTPROCESS_CLIP_NORMAL_ZERO")
    unit_normal = vector / norm
    triangles = np.asarray(scene.surface_triangles, dtype=int)
    nodes = np.asarray(scene.undeformed_nodes_mm, dtype=float)
    centroids = nodes[triangles].mean(axis=1)
    signed = (centroids - origin) @ unit_normal
    kept = np.flatnonzero(signed >= -1.0e-12).astype(int)
    rejected = np.flatnonzero(signed < -1.0e-12).astype(int)
    return ClipPlaneContract(
        origin_mm=tuple(float(v) for v in origin),
        normal=tuple(float(v) for v in unit_normal),
        kept_triangle_indices=kept,
        rejected_triangle_indices=rejected,
    )
