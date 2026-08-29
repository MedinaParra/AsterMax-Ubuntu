from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .curved_shoulder_sector_probe import curved_tet10_integration_point_coordinates
from .feature_adaptivity import FeatureRefinedTet10Mesh
from .shoulder_probe import _small_diameter_tangency_x
from .tet10 import tet10_shape_derivatives


class CurvedNeighborhoodIntegralError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurvedNeighborhoodIntegralResult:
    feature_sha256: str
    mesh_sha256: str
    quadrature_point_count: int
    quadrature_sha256: str
    probe_ring_x_mm: float
    probe_ring_radius_mm: float
    maximum_meridional_distance_mm: float
    selected_integration_point_count: int
    sampled_physical_volume_mm3: float
    weighted_mean_von_mises_mpa: float
    weighted_rms_von_mises_mpa: float
    weighted_std_von_mises_mpa: float
    minimum_von_mises_mpa: float
    maximum_von_mises_mpa: float
    maximum_selected_distance_mm: float
    integral_sha256: str


def integrate_curved_tet10_fixed_tangency_neighborhood(
    mesh: FeatureRefinedTet10Mesh,
    feature: XAxisShoulderFeature,
    *,
    integration_point_natural_coordinates: np.ndarray,
    integration_point_weights: np.ndarray,
    integration_point_von_mises_mpa: np.ndarray,
    maximum_meridional_distance_mm: float,
) -> CurvedNeighborhoodIntegralResult:
    """Volume-weighted stress witness over one fixed physical toroidal neighborhood.

    The region is defined in physical x-rho space around the small-diameter
    fillet-tangency ring. Only actual volume integration points inside that fixed
    region contribute. Each contribution uses its physical quadrature weight
    `det(J) * w`; no nodal recovery, smoothing or CAD-surface extrapolation is
    performed. This is an integral witness, not a surface-peak estimator.
    """
    if mesh.feature_sha256 != feature.feature_sha256:
        raise CurvedNeighborhoodIntegralError("FEATURE_MESH_BINDING_MISMATCH")
    natural = np.asarray(integration_point_natural_coordinates, dtype=float)
    weights = np.asarray(integration_point_weights, dtype=float).reshape(-1)
    values = np.asarray(integration_point_von_mises_mpa, dtype=float)
    limit = float(maximum_meridional_distance_mm)
    if natural.ndim != 2 or natural.shape[1] != 3 or natural.shape[0] == 0 or not np.all(np.isfinite(natural)):
        raise ValueError("integration_point_natural_coordinates must be finite with shape (q,3)")
    q = int(natural.shape[0])
    if weights.shape != (q,) or not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("integration_point_weights must contain q finite positive values")
    if values.shape != (mesh.elements.shape[0], q) or not np.all(np.isfinite(values)):
        raise ValueError("integration_point_von_mises_mpa must be finite with shape (m,q)")
    if not math.isfinite(limit) or limit <= 0.0:
        raise ValueError("maximum_meridional_distance_mm must be finite and positive")

    coords = curved_tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements, natural)
    x0 = _small_diameter_tangency_x(feature)
    r0 = float(feature.small_radius_mm)
    cy, cz = feature.axis_center_yz_mm
    rho = np.sqrt((coords[:, :, 1] - cy) ** 2 + (coords[:, :, 2] - cz) ** 2)
    distance = np.sqrt((coords[:, :, 0] - x0) ** 2 + (rho - r0) ** 2)
    selected = distance <= limit
    count = int(np.count_nonzero(selected))
    if count == 0:
        raise CurvedNeighborhoodIntegralError("FIXED_NEIGHBORHOOD_CONTAINS_NO_INTEGRATION_POINTS")

    physical_weights = np.empty_like(values, dtype=float)
    derivatives = tuple(tet10_shape_derivatives(point) for point in natural)
    for element_index, conn in enumerate(mesh.elements):
        element_coords = mesh.nodes_mm[conn]
        for point_index, dndr in enumerate(derivatives):
            det_j = float(np.linalg.det(element_coords.T @ dndr))
            if not math.isfinite(det_j) or det_j <= 0.0:
                raise CurvedNeighborhoodIntegralError(
                    f"NONPOSITIVE_JACOBIAN:ELEMENT_{element_index}:IP_{point_index}:DETJ_{det_j}"
                )
            physical_weights[element_index, point_index] = det_j * float(weights[point_index])

    w = physical_weights[selected]
    vm = values[selected]
    volume = float(np.sum(w))
    if not math.isfinite(volume) or volume <= 0.0:
        raise CurvedNeighborhoodIntegralError("INVALID_SAMPLED_PHYSICAL_VOLUME")
    mean = float(np.sum(w * vm) / volume)
    rms = float(math.sqrt(np.sum(w * vm * vm) / volume))
    std = float(math.sqrt(max(np.sum(w * (vm - mean) ** 2) / volume, 0.0)))

    quadrature_h = hashlib.sha256()
    quadrature_h.update(np.asarray(natural, dtype="<f8").tobytes(order="C"))
    quadrature_h.update(np.asarray(weights, dtype="<f8").tobytes(order="C"))
    quadrature_sha = quadrature_h.hexdigest()

    h = hashlib.sha256()
    h.update(b"AsterMaxCurvedFixedTangencyNeighborhoodIntegralV1\0")
    h.update(feature.feature_sha256.encode("ascii"))
    h.update(mesh.mesh_sha256.encode("ascii"))
    h.update(quadrature_sha.encode("ascii"))
    h.update(np.asarray((x0, r0, limit), dtype="<f8").tobytes())
    h.update(np.asarray(selected, dtype=np.uint8).tobytes(order="C"))
    h.update(np.asarray(w, dtype="<f8").tobytes(order="C"))
    h.update(np.asarray(vm, dtype="<f8").tobytes(order="C"))

    return CurvedNeighborhoodIntegralResult(
        feature_sha256=feature.feature_sha256,
        mesh_sha256=mesh.mesh_sha256,
        quadrature_point_count=q,
        quadrature_sha256=quadrature_sha,
        probe_ring_x_mm=float(x0),
        probe_ring_radius_mm=r0,
        maximum_meridional_distance_mm=limit,
        selected_integration_point_count=count,
        sampled_physical_volume_mm3=volume,
        weighted_mean_von_mises_mpa=mean,
        weighted_rms_von_mises_mpa=rms,
        weighted_std_von_mises_mpa=std,
        minimum_von_mises_mpa=float(np.min(vm)),
        maximum_von_mises_mpa=float(np.max(vm)),
        maximum_selected_distance_mm=float(np.max(distance[selected])),
        integral_sha256=h.hexdigest(),
    )
