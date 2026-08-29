from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re
from typing import Any

import numpy as np

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .curved_shoulder_sector_probe import curved_tet10_integration_point_coordinates
from .tet10 import tet10_shape_derivatives


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CurvedSectionResultantError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurvedSectionResultantSlab:
    schema: str
    mesh_sha256: str
    coordinate_min_mm: float
    coordinate_max_mm: float
    section_area_mm2: float
    section_centroid_mm: tuple[float, float, float]
    section_normal: tuple[float, float, float]
    quadrature_point_count: int
    quadrature_sha256: str
    selected_integration_point_count: int
    sampled_physical_volume_mm3: float
    sampled_effective_thickness_mm: float
    weighted_mean_traction_mpa: tuple[float, float, float]
    resultant_force_n: tuple[float, float, float]
    resultant_moment_nmm: tuple[float, float, float]
    minimum_coordinate_mm: float
    maximum_coordinate_mm: float
    method: str
    evidence_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_sha256")
        return payload


def _unit(vector: np.ndarray, name: str) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1.0e-14:
        raise ValueError(f"{name} must be a finite non-zero vector")
    return vector / norm


def _traction_from_voigt(stress_mpa: np.ndarray, normal: np.ndarray) -> np.ndarray:
    sigma = np.asarray(stress_mpa, dtype=float)
    n = np.asarray(normal, dtype=float)
    sx = sigma[:, 0]
    sy = sigma[:, 1]
    sz = sigma[:, 2]
    txy = sigma[:, 3]
    tyz = sigma[:, 4]
    txz = sigma[:, 5]
    return np.column_stack(
        (
            sx * n[0] + txy * n[1] + txz * n[2],
            txy * n[0] + sy * n[1] + tyz * n[2],
            txz * n[0] + tyz * n[1] + sz * n[2],
        )
    )


def integrate_curved_tet10_section_resultant_slab(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    mesh_sha256: str,
    integration_point_natural_coordinates: np.ndarray,
    integration_point_weights: np.ndarray,
    integration_point_stress_mpa: np.ndarray,
    coordinate_min_mm: float,
    coordinate_max_mm: float,
    section_area_mm2: float,
    section_centroid_mm: np.ndarray | tuple[float, float, float],
    section_normal: np.ndarray | tuple[float, float, float],
) -> CurvedSectionResultantSlab:
    """Recover a section resultant from a finite physical slab around a section.

    This is deliberately not presented as exact integration on a reconstructed
    quadratic cut surface. The solver stress is sampled only at its native TET10
    volume integration points. Values are weighted by w*det(J), averaged over a
    declared slab, then scaled by the exact CAD section area. The moment uses the
    in-plane lever arm about the supplied CAD section centroid.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    natural = np.asarray(integration_point_natural_coordinates, dtype=float)
    weights = np.asarray(integration_point_weights, dtype=float).reshape(-1)
    stress = np.asarray(integration_point_stress_mpa, dtype=float)
    mesh_sha = str(mesh_sha256).strip().lower()
    cmin = float(coordinate_min_mm)
    cmax = float(coordinate_max_mm)
    area = float(section_area_mm2)
    centroid = np.asarray(section_centroid_mm, dtype=float).reshape(-1)
    normal_raw = np.asarray(section_normal, dtype=float).reshape(-1)

    if not _SHA256_RE.fullmatch(mesh_sha):
        raise ValueError("mesh_sha256 must be a lowercase SHA-256 digest")
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be finite with shape (n,3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise ValueError("elements must have shape (m,10) with m>0")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contain out-of-range node indices")
    if natural.ndim != 2 or natural.shape[1] != 3 or natural.shape[0] == 0 or not np.all(np.isfinite(natural)):
        raise ValueError("integration_point_natural_coordinates must be finite with shape (q,3)")
    q = int(natural.shape[0])
    if weights.shape != (q,) or np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
        raise ValueError("integration_point_weights must contain q finite positive values")
    if stress.shape != (elems.shape[0], q, 6) or not np.all(np.isfinite(stress)):
        raise ValueError("integration_point_stress_mpa must be finite with shape (m,q,6)")
    if not math.isfinite(cmin) or not math.isfinite(cmax) or cmax <= cmin:
        raise ValueError("coordinate bounds must be finite and strictly increasing")
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError("section_area_mm2 must be finite and positive")
    if centroid.shape != (3,) or not np.all(np.isfinite(centroid)):
        raise ValueError("section_centroid_mm must contain three finite values")
    if normal_raw.shape != (3,) or not np.all(np.isfinite(normal_raw)):
        raise ValueError("section_normal must contain three finite values")
    normal = _unit(normal_raw, "section_normal")

    coords = curved_tet10_integration_point_coordinates(nodes, elems, natural)
    coordinate = np.einsum("eqj,j->eq", coords, normal)
    selected = (coordinate >= cmin) & (coordinate <= cmax)
    count = int(np.count_nonzero(selected))
    if count == 0:
        raise CurvedSectionResultantError("SECTION_RESULTANT_SLAB_CONTAINS_NO_INTEGRATION_POINTS")

    physical_weights = np.empty((elems.shape[0], q), dtype=float)
    derivatives = tuple(tet10_shape_derivatives(point) for point in natural)
    for element_index, conn in enumerate(elems):
        element_coords = nodes[conn]
        for point_index, dndr in enumerate(derivatives):
            det_j = float(np.linalg.det(element_coords.T @ dndr))
            if not math.isfinite(det_j) or det_j <= 0.0:
                raise CurvedSectionResultantError(
                    f"NONPOSITIVE_JACOBIAN:ELEMENT_{element_index}:IP_{point_index}:DETJ_{det_j}"
                )
            physical_weights[element_index, point_index] = det_j * float(weights[point_index])

    w = physical_weights[selected]
    sigma = stress[selected]
    points = coords[selected]
    selected_coordinate = coordinate[selected]
    volume = float(np.sum(w))
    if not math.isfinite(volume) or volume <= 0.0:
        raise CurvedSectionResultantError("INVALID_SECTION_RESULTANT_SAMPLED_VOLUME")

    traction = _traction_from_voigt(sigma, normal)
    mean_traction = np.sum(w[:, None] * traction, axis=0) / volume

    lever = points - centroid[None, :]
    lever_in_plane = lever - np.outer(lever @ normal, normal)
    moment_density = np.cross(lever_in_plane, traction)
    mean_moment_density = np.sum(w[:, None] * moment_density, axis=0) / volume

    force = area * mean_traction
    moment = area * mean_moment_density
    if not np.all(np.isfinite(force)) or not np.all(np.isfinite(moment)):
        raise CurvedSectionResultantError("NONFINITE_SECTION_RESULTANT")

    quadrature_h = hashlib.sha256()
    quadrature_h.update(np.asarray(natural, dtype="<f8").tobytes(order="C"))
    quadrature_h.update(np.asarray(weights, dtype="<f8").tobytes(order="C"))
    quadrature_sha = quadrature_h.hexdigest()

    payload = {
        "schema": "AsterMaxCurvedSectionResultantSlabV1",
        "mesh_sha256": mesh_sha,
        "coordinate_min_mm": cmin,
        "coordinate_max_mm": cmax,
        "section_area_mm2": area,
        "section_centroid_mm": tuple(float(v) for v in centroid),
        "section_normal": tuple(float(v) for v in normal),
        "quadrature_point_count": q,
        "quadrature_sha256": quadrature_sha,
        "selected_integration_point_count": count,
        "sampled_physical_volume_mm3": volume,
        "sampled_effective_thickness_mm": volume / area,
        "weighted_mean_traction_mpa": tuple(float(v) for v in mean_traction),
        "resultant_force_n": tuple(float(v) for v in force),
        "resultant_moment_nmm": tuple(float(v) for v in moment),
        "minimum_coordinate_mm": float(np.min(selected_coordinate)),
        "maximum_coordinate_mm": float(np.max(selected_coordinate)),
        "method": (
            "ACTUAL_DUFFY_IP_STRESS_WEIGHTED_BY_WEIGHT_TIMES_DETJ_SLAB_AVERAGE_"
            "SCALED_BY_EXACT_CAD_AREA_IN_PLANE_MOMENT_ABOUT_CAD_CENTROID_NO_NODAL_RECOVERY_OR_SMOOTHING"
        ),
    }
    evidence_sha = canonical_sha256(payload)
    return CurvedSectionResultantSlab(**payload, evidence_sha256=evidence_sha)


def curved_section_resultant_evidence(result: CurvedSectionResultantSlab) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"FEA_SECTION_RESULTANT:{result.mesh_sha256[:16]}:{result.evidence_sha256[:16]}",
        kind="FEA_SECTION_RESULTANT_SLAB",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Physical-volume-weighted TET10 integration-point traction and in-plane moment density in a declared slab, scaled by exact CAD section area; no nodal stress recovery or smoothing."
        ),
        payload_sha256=result.evidence_sha256,
        metadata=result.canonical_without_hash(),
    )
