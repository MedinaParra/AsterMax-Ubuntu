from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .persistent_geometry import (
    FaceResolution,
    PersistentFaceSelection,
    PersistentGeometryError,
    _assert_source,
    _import,
    _resolve_current,
    _step,
)
from .gmsh_bridge import _gmsh


@dataclass(frozen=True)
class PlanarSectionProperties:
    schema: str
    selection_id: str
    source_sha256: str
    face_signature_sha256: str
    area_mm2: float
    centroid_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    axis_u: tuple[float, float, float]
    axis_v: tuple[float, float, float]
    i_u_mm4: float
    i_v_mm4: float
    i_uv_mm4: float
    principal_i_min_mm4: float
    principal_i_max_mm4: float
    polar_i_n_mm4: float
    polar_identity_relative_residual: float
    method: str
    section_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("section_sha256")
        return payload


def _unit(vector: np.ndarray, name: str) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1.0e-14:
        raise PersistentGeometryError(f"invalid {name}")
    return np.asarray(vector, dtype=float) / norm


def _section_axes(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = _unit(normal, "section normal")
    basis = np.eye(3)
    reference = basis[int(np.argmin(np.abs(basis @ n)))]
    u = _unit(np.cross(n, reference), "section axis u")
    v = _unit(np.cross(n, u), "section axis v")
    if abs(float(np.dot(u, v))) > 1.0e-12:
        raise PersistentGeometryError("section axes are not orthogonal")
    return u, v


def _normal_at_center(gmsh, tag: int, center: tuple[float, float, float]) -> np.ndarray:
    try:
        uv = gmsh.model.getParametrization(2, int(tag), list(center))
        normal = gmsh.model.getNormal(int(tag), uv)
    except Exception as exc:
        raise PersistentGeometryError("PLANAR_FACE_NORMAL_EVALUATION_FAILED") from exc
    values = np.asarray(normal, dtype=float).reshape(-1)
    if values.size < 3:
        raise PersistentGeometryError("PLANAR_FACE_NORMAL_EVALUATION_FAILED")
    return _unit(values[:3], "section normal")


def _section_from_current_model(
    gmsh,
    selection: PersistentFaceSelection,
    resolution: FaceResolution,
) -> PlanarSectionProperties:
    surface_type = str(gmsh.model.getType(2, int(resolution.resolved_tag)))
    if surface_type.strip().lower() != "plane":
        raise PersistentGeometryError(f"SECTION_WITNESS_OUT_OF_DOMAIN:{surface_type}")

    area = float(gmsh.model.occ.getMass(2, int(resolution.resolved_tag)))
    center = tuple(float(v) for v in gmsh.model.occ.getCenterOfMass(2, int(resolution.resolved_tag)))
    tensor = np.asarray(
        gmsh.model.occ.getMatrixOfInertia(2, int(resolution.resolved_tag)), dtype=float
    ).reshape(3, 3)
    tensor = 0.5 * (tensor + tensor.T)
    normal = _normal_at_center(gmsh, resolution.resolved_tag, center)
    u, v = _section_axes(normal)

    i_u = float(u @ tensor @ u)
    i_v = float(v @ tensor @ v)
    i_uv = float(-(u @ tensor @ v))
    polar = float(normal @ tensor @ normal)
    if min(area, i_u, i_v, polar) <= 0.0 or not np.all(np.isfinite(tensor)):
        raise PersistentGeometryError("INVALID_CAD_SECTION_PROPERTIES")

    expected_polar = i_u + i_v
    residual = abs(polar - expected_polar) / max(abs(polar), abs(expected_polar), 1.0e-30)
    if residual > 1.0e-8:
        raise PersistentGeometryError(f"SECTION_INERTIA_IDENTITY_FAILED:{residual:.17g}")

    average = 0.5 * (i_u + i_v)
    radius = float(np.hypot(0.5 * (i_u - i_v), i_uv))
    principal_min = average - radius
    principal_max = average + radius
    if principal_min <= 0.0:
        raise PersistentGeometryError("SECTION_PRINCIPAL_INERTIA_NONPOSITIVE")

    payload = {
        "schema": "AsterMaxPlanarSectionPropertiesV1",
        "selection_id": selection.selection_id,
        "source_sha256": selection.source_sha256,
        "face_signature_sha256": resolution.signature_sha256,
        "area_mm2": area,
        "centroid_mm": center,
        "normal": tuple(float(x) for x in normal),
        "axis_u": tuple(float(x) for x in u),
        "axis_v": tuple(float(x) for x in v),
        "i_u_mm4": i_u,
        "i_v_mm4": i_v,
        "i_uv_mm4": i_uv,
        "principal_i_min_mm4": principal_min,
        "principal_i_max_mm4": principal_max,
        "polar_i_n_mm4": polar,
        "polar_identity_relative_residual": residual,
        "method": "OPENCASCADE_SURFACE_MASS_COM_INERTIA_PROJECTED_TO_LOCAL_PLANE",
    }
    return PlanarSectionProperties(**payload, section_sha256=canonical_sha256(payload))


def planar_section_properties(
    step_path: str | Path,
    selection: PersistentFaceSelection,
) -> PlanarSectionProperties:
    source = _step(step_path)
    _assert_source(source, selection)
    gmsh = _gmsh(); gmsh.initialize()
    try:
        diagonal = _import(gmsh, source, "astermax_planar_section")
        resolution = _resolve_current(gmsh, selection, diagonal)
        return _section_from_current_model(gmsh, selection, resolution)
    finally:
        gmsh.finalize()


def persistent_face_identity_evidence(
    selection: PersistentFaceSelection,
    resolution: FaceResolution,
) -> EvidenceRecord:
    if selection.selection_id != resolution.selection_id or selection.selection_sha256 != resolution.selection_sha256:
        raise ValueError("selection and resolution do not share the same identity")
    return EvidenceRecord(
        evidence_id=f"FACE_IDENTITY:{selection.selection_id}",
        kind="CAD_FACE_IDENTITY",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Persistent CAD face resolved uniquely against the exact STEP source.",
        payload_sha256=selection.selection_sha256,
        metadata={
            "selection_id": selection.selection_id,
            "source_sha256": selection.source_sha256,
            "signature_sha256": resolution.signature_sha256,
            "capture_tag_is_identity": False,
            "resolved_tag_runtime_only": resolution.resolved_tag,
        },
    )


def section_properties_evidence(properties: PlanarSectionProperties) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SECTION_PROPERTIES:{properties.selection_id}",
        kind="CAD_SECTION_PROPERTIES",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Planar section area, centroid and second moments derived from the resolved CAD face.",
        payload_sha256=properties.section_sha256,
        metadata={
            "selection_id": properties.selection_id,
            "source_sha256": properties.source_sha256,
            "face_signature_sha256": properties.face_signature_sha256,
            "area_mm2": properties.area_mm2,
            "centroid_mm": list(properties.centroid_mm),
            "i_u_mm4": properties.i_u_mm4,
            "i_v_mm4": properties.i_v_mm4,
            "i_uv_mm4": properties.i_uv_mm4,
            "principal_i_min_mm4": properties.principal_i_min_mm4,
            "principal_i_max_mm4": properties.principal_i_max_mm4,
            "method": properties.method,
        },
    )
