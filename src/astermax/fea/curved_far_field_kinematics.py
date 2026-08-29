from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re
from typing import Any

import numpy as np

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .curved_shoulder_sector_probe import curved_tet10_integration_point_coordinates
from .tet10 import tet10_shape_derivatives, tet10_shape_functions


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CurvedFarFieldKinematicsError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurvedFarFieldAxialKinematics:
    schema: str
    mesh_sha256: str
    x_min_mm: float
    x_max_mm: float
    quadrature_point_count: int
    quadrature_sha256: str
    selected_integration_point_count: int
    sampled_physical_volume_mm3: float
    weighted_mean_x_mm: float
    weighted_mean_ux_mm: float
    axial_displacement_gradient: float
    axial_displacement_intercept_mm: float
    weighted_residual_rms_mm: float
    weighted_r_squared: float
    fitted_extension_over_declared_span_mm: float
    minimum_x_mm: float
    maximum_x_mm: float
    method: str
    evidence_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_sha256")
        return payload


def fit_curved_tet10_far_field_axial_kinematics(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    mesh_sha256: str,
    displacement_mm: np.ndarray,
    integration_point_natural_coordinates: np.ndarray,
    integration_point_weights: np.ndarray,
    x_min_mm: float,
    x_max_mm: float,
) -> CurvedFarFieldAxialKinematics:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    displacement = np.asarray(displacement_mm, dtype=float)
    natural = np.asarray(integration_point_natural_coordinates, dtype=float)
    weights = np.asarray(integration_point_weights, dtype=float).reshape(-1)
    mesh_sha = str(mesh_sha256).strip().lower()
    x_min = float(x_min_mm)
    x_max = float(x_max_mm)

    if not _SHA256_RE.fullmatch(mesh_sha):
        raise ValueError("mesh_sha256 must be a lowercase SHA-256 digest")
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be finite with shape (n,3)")
    if displacement.shape != nodes.shape or not np.all(np.isfinite(displacement)):
        raise ValueError("displacement_mm must be finite and match nodes_mm shape")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise ValueError("elements must have shape (m,10) with m>0")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contain out-of-range node indices")
    if natural.ndim != 2 or natural.shape[1] != 3 or natural.shape[0] == 0 or not np.all(np.isfinite(natural)):
        raise ValueError("integration_point_natural_coordinates must be finite with shape (q,3)")
    q = int(natural.shape[0])
    if weights.shape != (q,) or np.any(weights <= 0.0) or not np.all(np.isfinite(weights)):
        raise ValueError("integration_point_weights must contain q finite positive values")
    if not math.isfinite(x_min) or not math.isfinite(x_max) or x_max <= x_min:
        raise ValueError("x bounds must be finite and strictly increasing")

    coords = curved_tet10_integration_point_coordinates(nodes, elems, natural)
    selected = (coords[:, :, 0] >= x_min) & (coords[:, :, 0] <= x_max)
    count = int(np.count_nonzero(selected))
    if count < 2:
        raise CurvedFarFieldKinematicsError("FAR_FIELD_REGION_NEEDS_AT_LEAST_TWO_INTEGRATION_POINTS")

    physical_weights = np.empty((elems.shape[0], q), dtype=float)
    ux_ip = np.empty((elems.shape[0], q), dtype=float)
    derivatives = tuple(tet10_shape_derivatives(point) for point in natural)
    shapes = tuple(tet10_shape_functions(point) for point in natural)
    for element_index, conn in enumerate(elems):
        element_coords = nodes[conn]
        element_ux = displacement[conn, 0]
        for point_index, (dndr, shape) in enumerate(zip(derivatives, shapes)):
            det_j = float(np.linalg.det(element_coords.T @ dndr))
            if not math.isfinite(det_j) or det_j <= 0.0:
                raise CurvedFarFieldKinematicsError(
                    f"NONPOSITIVE_JACOBIAN:ELEMENT_{element_index}:IP_{point_index}:DETJ_{det_j}"
                )
            physical_weights[element_index, point_index] = det_j * float(weights[point_index])
            ux_ip[element_index, point_index] = float(shape @ element_ux)

    w = physical_weights[selected]
    x = coords[:, :, 0][selected]
    ux = ux_ip[selected]
    volume = float(np.sum(w))
    if not math.isfinite(volume) or volume <= 0.0:
        raise CurvedFarFieldKinematicsError("INVALID_FAR_FIELD_SAMPLED_VOLUME")

    x_bar = float(np.sum(w * x) / volume)
    ux_bar = float(np.sum(w * ux) / volume)
    dx = x - x_bar
    du = ux - ux_bar
    denom = float(np.sum(w * dx * dx))
    if not math.isfinite(denom) or denom <= max(volume, 1.0) * 1.0e-18:
        raise CurvedFarFieldKinematicsError("FAR_FIELD_X_VARIANCE_TOO_SMALL_FOR_KINEMATIC_FIT")
    slope = float(np.sum(w * dx * du) / denom)
    intercept = float(ux_bar - slope * x_bar)
    residual = ux - (intercept + slope * x)
    residual_rms = float(math.sqrt(np.sum(w * residual * residual) / volume))
    sst = float(np.sum(w * du * du))
    sse = float(np.sum(w * residual * residual))
    if sst <= 1.0e-30:
        r_squared = 1.0 if sse <= 1.0e-30 else 0.0
    else:
        r_squared = float(1.0 - sse / sst)
    if not all(math.isfinite(v) for v in (slope, intercept, residual_rms, r_squared)):
        raise CurvedFarFieldKinematicsError("NONFINITE_FAR_FIELD_KINEMATIC_FIT")

    quadrature_h = hashlib.sha256()
    quadrature_h.update(np.asarray(natural, dtype="<f8").tobytes(order="C"))
    quadrature_h.update(np.asarray(weights, dtype="<f8").tobytes(order="C"))
    quadrature_sha = quadrature_h.hexdigest()

    payload = {
        "schema": "AsterMaxCurvedFarFieldAxialKinematicsV1",
        "mesh_sha256": mesh_sha,
        "x_min_mm": x_min,
        "x_max_mm": x_max,
        "quadrature_point_count": q,
        "quadrature_sha256": quadrature_sha,
        "selected_integration_point_count": count,
        "sampled_physical_volume_mm3": volume,
        "weighted_mean_x_mm": x_bar,
        "weighted_mean_ux_mm": ux_bar,
        "axial_displacement_gradient": slope,
        "axial_displacement_intercept_mm": intercept,
        "weighted_residual_rms_mm": residual_rms,
        "weighted_r_squared": r_squared,
        "fitted_extension_over_declared_span_mm": slope * (x_max - x_min),
        "minimum_x_mm": float(np.min(x)),
        "maximum_x_mm": float(np.max(x)),
        "method": "ACTUAL_DUFFY_IP_TET10_UX_INTERPOLATION_PHYSICAL_VOLUME_WEIGHTED_LINEAR_FIT_NO_STRESS_RECOVERY",
    }
    evidence_sha = canonical_sha256(payload)
    return CurvedFarFieldAxialKinematics(**payload, evidence_sha256=evidence_sha)


def curved_far_field_kinematics_evidence(result: CurvedFarFieldAxialKinematics) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"FEA_FAR_FIELD_KINEMATICS:{result.mesh_sha256[:16]}:{result.evidence_sha256[:16]}",
        kind="FEA_FAR_FIELD_AXIAL_KINEMATICS",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Physical-volume-weighted linear fit of TET10-interpolated axial displacement at actual volume integration points in a declared far-field slab; independent of stress recovery."
        ),
        payload_sha256=result.evidence_sha256,
        metadata=result.canonical_without_hash(),
    )
