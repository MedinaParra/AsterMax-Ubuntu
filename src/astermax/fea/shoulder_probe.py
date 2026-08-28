from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .feature_adaptivity import FeatureRefinedTet10Mesh
from .tet10_feature_sampling import tet10_integration_point_coordinates


class ShoulderProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShoulderProbeSample:
    element_index: int
    integration_point_index: int
    coordinate_mm: tuple[float, float, float]
    distance_to_probe_ring_mm: float
    von_mises_mpa: float


@dataclass(frozen=True)
class ShoulderProbeRingResult:
    feature_sha256: str
    mesh_sha256: str
    probe_ring_x_mm: float
    probe_ring_radius_mm: float
    sample_count: int
    maximum_sample_distance_mm: float
    mean_sample_distance_mm: float
    mean_von_mises_mpa: float
    max_von_mises_mpa: float
    samples: tuple[ShoulderProbeSample, ...]
    probe_sha256: str


def _small_diameter_tangency_x(feature: XAxisShoulderFeature) -> float:
    if feature.small_side == "X_MIN_SIDE":
        return float(feature.transition_x_mm - feature.fillet_radius_mm)
    if feature.small_side == "X_MAX_SIDE":
        return float(feature.transition_x_mm + feature.fillet_radius_mm)
    raise ShoulderProbeError(f"UNSUPPORTED_SMALL_SIDE:{feature.small_side}")


def sample_tet10_nearest_to_small_diameter_fillet_ring(
    mesh: FeatureRefinedTet10Mesh,
    feature: XAxisShoulderFeature,
    *,
    integration_point_von_mises_mpa: np.ndarray,
    sample_count: int = 12,
    maximum_allowed_distance_mm: float = 4.0,
) -> ShoulderProbeRingResult:
    """Sample a fixed physical probe ring across remeshing.

    The target is the circumference where the declared quarter-round fillet is
    tangent to the small cylindrical shaft. Distance is measured to the ring
    manifold, not to a mesh node. Exactly `sample_count` real TET10 integration
    points nearest to that manifold are used, making the statistic independent
    of the total number of IPs in a changing mesh. No extrapolation to the CAD
    surface and no nodal stress smoothing are performed.
    """
    if mesh.feature_sha256 != feature.feature_sha256:
        raise ShoulderProbeError("FEATURE_MESH_BINDING_MISMATCH")
    count = int(sample_count)
    limit = float(maximum_allowed_distance_mm)
    if count < 4:
        raise ValueError("sample_count must be >= 4")
    if not np.isfinite(limit) or limit <= 0.0:
        raise ValueError("maximum_allowed_distance_mm must be finite and positive")

    values = np.asarray(integration_point_von_mises_mpa, dtype=float)
    if values.shape != (mesh.elements.shape[0], 4) or not np.all(np.isfinite(values)):
        raise ValueError("integration_point_von_mises_mpa must be finite with shape (m,4)")
    coords = tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements)
    total = coords.shape[0] * coords.shape[1]
    if total < count:
        raise ShoulderProbeError(f"NOT_ENOUGH_INTEGRATION_POINTS:{total}<{count}")

    x0 = _small_diameter_tangency_x(feature)
    r0 = float(feature.small_radius_mm)
    cy, cz = feature.axis_center_yz_mm
    flat_coords = coords.reshape((-1, 3))
    flat_values = values.reshape(-1)
    rho = np.sqrt((flat_coords[:, 1] - cy) ** 2 + (flat_coords[:, 2] - cz) ** 2)
    distance = np.sqrt((flat_coords[:, 0] - x0) ** 2 + (rho - r0) ** 2)
    order = np.lexsort((np.arange(total, dtype=np.int64), distance))[:count]

    selected: list[ShoulderProbeSample] = []
    for flat_index in order:
        element_index = int(flat_index // 4)
        ip_index = int(flat_index % 4)
        selected.append(
            ShoulderProbeSample(
                element_index=element_index,
                integration_point_index=ip_index,
                coordinate_mm=tuple(float(v) for v in flat_coords[flat_index]),
                distance_to_probe_ring_mm=float(distance[flat_index]),
                von_mises_mpa=float(flat_values[flat_index]),
            )
        )
    samples = tuple(selected)
    max_distance = max(sample.distance_to_probe_ring_mm for sample in samples)
    if max_distance > limit:
        raise ShoulderProbeError(
            f"PROBE_RING_UNRESOLVED:max_distance={max_distance}:limit={limit}"
        )

    h = hashlib.sha256()
    h.update(b"AsterMaxShoulderProbeRingV1\0")
    h.update(feature.feature_sha256.encode("ascii"))
    h.update(mesh.mesh_sha256.encode("ascii"))
    h.update(np.asarray((x0, r0, count, limit), dtype="<f8").tobytes())
    for sample in samples:
        h.update(np.asarray((sample.element_index, sample.integration_point_index), dtype="<i8").tobytes())
        h.update(np.asarray((*sample.coordinate_mm, sample.distance_to_probe_ring_mm, sample.von_mises_mpa), dtype="<f8").tobytes())
    stresses = np.asarray([sample.von_mises_mpa for sample in samples], dtype=float)
    distances = np.asarray([sample.distance_to_probe_ring_mm for sample in samples], dtype=float)
    return ShoulderProbeRingResult(
        feature_sha256=feature.feature_sha256,
        mesh_sha256=mesh.mesh_sha256,
        probe_ring_x_mm=x0,
        probe_ring_radius_mm=r0,
        sample_count=count,
        maximum_sample_distance_mm=max_distance,
        mean_sample_distance_mm=float(np.mean(distances)),
        mean_von_mises_mpa=float(np.mean(stresses)),
        max_von_mises_mpa=float(np.max(stresses)),
        samples=samples,
        probe_sha256=h.hexdigest(),
    )
