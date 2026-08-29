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


class CurvedFarFieldStressError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurvedFarFieldStressTensor:
    schema: str
    mesh_sha256: str
    x_min_mm: float
    x_max_mm: float
    quadrature_point_count: int
    quadrature_sha256: str
    selected_integration_point_count: int
    sampled_physical_volume_mm3: float
    weighted_mean_stress_mpa: tuple[float, float, float, float, float, float]
    weighted_rms_stress_mpa: tuple[float, float, float, float, float, float]
    weighted_std_stress_mpa: tuple[float, float, float, float, float, float]
    weighted_mean_von_mises_mpa: float
    weighted_rms_von_mises_mpa: float
    minimum_x_mm: float
    maximum_x_mm: float
    method: str
    evidence_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_sha256")
        return payload


def integrate_curved_tet10_far_field_stress(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    mesh_sha256: str,
    integration_point_natural_coordinates: np.ndarray,
    integration_point_weights: np.ndarray,
    integration_point_stress_mpa: np.ndarray,
    integration_point_von_mises_mpa: np.ndarray,
    x_min_mm: float,
    x_max_mm: float,
) -> CurvedFarFieldStressTensor:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    natural = np.asarray(integration_point_natural_coordinates, dtype=float)
    weights = np.asarray(integration_point_weights, dtype=float).reshape(-1)
    stress = np.asarray(integration_point_stress_mpa, dtype=float)
    mises = np.asarray(integration_point_von_mises_mpa, dtype=float)
    mesh_sha = str(mesh_sha256).strip().lower()
    x_min = float(x_min_mm); x_max = float(x_max_mm)

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
    if mises.shape != (elems.shape[0], q) or not np.all(np.isfinite(mises)):
        raise ValueError("integration_point_von_mises_mpa must be finite with shape (m,q)")
    if not math.isfinite(x_min) or not math.isfinite(x_max) or x_max <= x_min:
        raise ValueError("x bounds must be finite and strictly increasing")

    coords = curved_tet10_integration_point_coordinates(nodes, elems, natural)
    selected = (coords[:, :, 0] >= x_min) & (coords[:, :, 0] <= x_max)
    count = int(np.count_nonzero(selected))
    if count == 0:
        raise CurvedFarFieldStressError("FAR_FIELD_REGION_CONTAINS_NO_INTEGRATION_POINTS")

    physical_weights = np.empty((elems.shape[0], q), dtype=float)
    derivatives = tuple(tet10_shape_derivatives(point) for point in natural)
    for element_index, conn in enumerate(elems):
        element_coords = nodes[conn]
        for point_index, dndr in enumerate(derivatives):
            det_j = float(np.linalg.det(element_coords.T @ dndr))
            if not math.isfinite(det_j) or det_j <= 0.0:
                raise CurvedFarFieldStressError(
                    f"NONPOSITIVE_JACOBIAN:ELEMENT_{element_index}:IP_{point_index}:DETJ_{det_j}"
                )
            physical_weights[element_index, point_index] = det_j * float(weights[point_index])

    w = physical_weights[selected]
    sigma = stress[selected]
    vm = mises[selected]
    volume = float(np.sum(w))
    if not math.isfinite(volume) or volume <= 0.0:
        raise CurvedFarFieldStressError("INVALID_FAR_FIELD_SAMPLED_VOLUME")

    mean = np.sum(w[:, None] * sigma, axis=0) / volume
    rms = np.sqrt(np.sum(w[:, None] * sigma * sigma, axis=0) / volume)
    std = np.sqrt(np.maximum(np.sum(w[:, None] * (sigma - mean) ** 2, axis=0) / volume, 0.0))
    mean_vm = float(np.sum(w * vm) / volume)
    rms_vm = float(math.sqrt(np.sum(w * vm * vm) / volume))
    selected_x = coords[:, :, 0][selected]

    quadrature_h = hashlib.sha256()
    quadrature_h.update(np.asarray(natural, dtype="<f8").tobytes(order="C"))
    quadrature_h.update(np.asarray(weights, dtype="<f8").tobytes(order="C"))
    quadrature_sha = quadrature_h.hexdigest()

    payload = {
        "schema": "AsterMaxCurvedFarFieldStressTensorV1",
        "mesh_sha256": mesh_sha,
        "x_min_mm": x_min,
        "x_max_mm": x_max,
        "quadrature_point_count": q,
        "quadrature_sha256": quadrature_sha,
        "selected_integration_point_count": count,
        "sampled_physical_volume_mm3": volume,
        "weighted_mean_stress_mpa": tuple(float(v) for v in mean),
        "weighted_rms_stress_mpa": tuple(float(v) for v in rms),
        "weighted_std_stress_mpa": tuple(float(v) for v in std),
        "weighted_mean_von_mises_mpa": mean_vm,
        "weighted_rms_von_mises_mpa": rms_vm,
        "minimum_x_mm": float(np.min(selected_x)),
        "maximum_x_mm": float(np.max(selected_x)),
        "method": "ACTUAL_DUFFY_IP_X_SLAB_WEIGHTED_BY_WEIGHT_TIMES_DETJ_NO_RECOVERY_OR_SMOOTHING",
    }
    evidence_sha = canonical_sha256(payload)
    return CurvedFarFieldStressTensor(**payload, evidence_sha256=evidence_sha)


def curved_far_field_stress_evidence(result: CurvedFarFieldStressTensor) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"FEA_FAR_FIELD:{result.mesh_sha256[:16]}:{result.evidence_sha256[:16]}",
        kind="FEA_FAR_FIELD_STRESS_TENSOR",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Physical-volume-weighted curved-TET10 integration-point stress tensor in a declared far-field x slab; "
            "no nodal recovery, stress smoothing or CAD-surface extrapolation."
        ),
        payload_sha256=result.evidence_sha256,
        metadata=result.canonical_without_hash(),
    )
