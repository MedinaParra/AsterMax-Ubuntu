from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .feature_adaptivity import FeatureRefinedTet10Mesh
from .shoulder_probe import _small_diameter_tangency_x
from .tet10_feature_sampling import tet10_integration_point_coordinates


class ShoulderSectorProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShoulderSectorSample:
    sector_index: int
    element_index: int
    integration_point_index: int
    coordinate_mm: tuple[float, float, float]
    azimuth_rad: float
    distance_to_probe_ring_mm: float
    von_mises_mpa: float


@dataclass(frozen=True)
class ShoulderSectorProbeResult:
    feature_sha256: str
    mesh_sha256: str
    probe_ring_x_mm: float
    probe_ring_radius_mm: float
    sector_count: int
    covered_sector_count: int
    angular_coverage_fraction: float
    maximum_sample_distance_mm: float
    mean_sample_distance_mm: float
    mean_von_mises_mpa: float
    max_von_mises_mpa: float
    samples: tuple[ShoulderSectorSample, ...]
    probe_sha256: str


def _normalized_azimuth(y: np.ndarray, z: np.ndarray, cy: float, cz: float) -> np.ndarray:
    theta = np.arctan2(z - cz, y - cy)
    return np.mod(theta, 2.0 * math.pi)


def sectorized_ring_indices(
    coordinates_mm: np.ndarray,
    *,
    center_yz_mm: tuple[float, float],
    ring_x_mm: float,
    ring_radius_mm: float,
    sector_count: int,
    maximum_allowed_distance_mm: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return one deterministic nearest point per equal azimuth sector.

    This is a geometry-only selector. Every sector must contain at least one
    candidate within the declared ring-distance limit; otherwise it fails
    closed instead of silently changing angular coverage between remeshes.
    """
    coords = np.asarray(coordinates_mm, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 3 or not np.all(np.isfinite(coords)):
        raise ValueError("coordinates_mm must be finite with shape (n,3)")
    sectors = int(sector_count)
    limit = float(maximum_allowed_distance_mm)
    x0 = float(ring_x_mm)
    r0 = float(ring_radius_mm)
    cy, cz = (float(center_yz_mm[0]), float(center_yz_mm[1]))
    if sectors < 4:
        raise ValueError("sector_count must be >= 4")
    if not math.isfinite(limit) or limit <= 0.0:
        raise ValueError("maximum_allowed_distance_mm must be finite and positive")
    if not math.isfinite(x0) or not math.isfinite(r0) or r0 <= 0.0:
        raise ValueError("ring geometry must be finite with positive radius")

    rho = np.sqrt((coords[:, 1] - cy) ** 2 + (coords[:, 2] - cz) ** 2)
    distance = np.sqrt((coords[:, 0] - x0) ** 2 + (rho - r0) ** 2)
    azimuth = _normalized_azimuth(coords[:, 1], coords[:, 2], cy, cz)
    width = 2.0 * math.pi / sectors
    sector_index = np.floor(azimuth / width).astype(np.int64)
    sector_index = np.minimum(sector_index, sectors - 1)

    selected: list[int] = []
    for sector in range(sectors):
        candidates = np.flatnonzero((sector_index == sector) & (distance <= limit))
        if candidates.size == 0:
            raise ShoulderSectorProbeError(f"UNRESOLVED_AZIMUTH_SECTOR:{sector}")
        order = np.lexsort((candidates, distance[candidates]))
        selected.append(int(candidates[int(order[0])]))
    indices = np.asarray(selected, dtype=np.int64)
    return indices, distance[indices], azimuth[indices]


def sample_tet10_sectorized_small_diameter_fillet_ring(
    mesh: FeatureRefinedTet10Mesh,
    feature: XAxisShoulderFeature,
    *,
    integration_point_von_mises_mpa: np.ndarray,
    sector_count: int = 12,
    maximum_allowed_distance_mm: float = 4.0,
) -> ShoulderSectorProbeResult:
    """Measure the same physical fillet-tangency ring with full azimuth coverage.

    Exactly one real TET10 integration point is selected per equal angular
    sector. No nodal stress recovery, extrapolation to the CAD surface or
    smoothing is performed.
    """
    if mesh.feature_sha256 != feature.feature_sha256:
        raise ShoulderSectorProbeError("FEATURE_MESH_BINDING_MISMATCH")
    values = np.asarray(integration_point_von_mises_mpa, dtype=float)
    if values.shape != (mesh.elements.shape[0], 4) or not np.all(np.isfinite(values)):
        raise ValueError("integration_point_von_mises_mpa must be finite with shape (m,4)")

    coords = tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements)
    flat_coords = coords.reshape((-1, 3))
    flat_values = values.reshape(-1)
    x0 = _small_diameter_tangency_x(feature)
    r0 = float(feature.small_radius_mm)
    indices, distances, azimuths = sectorized_ring_indices(
        flat_coords,
        center_yz_mm=feature.axis_center_yz_mm,
        ring_x_mm=x0,
        ring_radius_mm=r0,
        sector_count=sector_count,
        maximum_allowed_distance_mm=maximum_allowed_distance_mm,
    )

    samples: list[ShoulderSectorSample] = []
    for sector, flat_index in enumerate(indices.tolist()):
        samples.append(
            ShoulderSectorSample(
                sector_index=sector,
                element_index=int(flat_index // 4),
                integration_point_index=int(flat_index % 4),
                coordinate_mm=tuple(float(v) for v in flat_coords[flat_index]),
                azimuth_rad=float(azimuths[sector]),
                distance_to_probe_ring_mm=float(distances[sector]),
                von_mises_mpa=float(flat_values[flat_index]),
            )
        )
    ordered = tuple(samples)
    stresses = np.asarray([s.von_mises_mpa for s in ordered], dtype=float)
    dists = np.asarray([s.distance_to_probe_ring_mm for s in ordered], dtype=float)

    h = hashlib.sha256()
    h.update(b"AsterMaxShoulderSectorProbeRingV1\0")
    h.update(feature.feature_sha256.encode("ascii"))
    h.update(mesh.mesh_sha256.encode("ascii"))
    h.update(np.asarray((x0, r0, sector_count, maximum_allowed_distance_mm), dtype="<f8").tobytes())
    for s in ordered:
        h.update(np.asarray((s.sector_index, s.element_index, s.integration_point_index), dtype="<i8").tobytes())
        h.update(np.asarray((*s.coordinate_mm, s.azimuth_rad, s.distance_to_probe_ring_mm, s.von_mises_mpa), dtype="<f8").tobytes())

    return ShoulderSectorProbeResult(
        feature_sha256=feature.feature_sha256,
        mesh_sha256=mesh.mesh_sha256,
        probe_ring_x_mm=float(x0),
        probe_ring_radius_mm=r0,
        sector_count=int(sector_count),
        covered_sector_count=int(sector_count),
        angular_coverage_fraction=1.0,
        maximum_sample_distance_mm=float(np.max(dists)),
        mean_sample_distance_mm=float(np.mean(dists)),
        mean_von_mises_mpa=float(np.mean(stresses)),
        max_von_mises_mpa=float(np.max(stresses)),
        samples=ordered,
        probe_sha256=h.hexdigest(),
    )
