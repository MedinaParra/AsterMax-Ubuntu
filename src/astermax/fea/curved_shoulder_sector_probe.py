from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .feature_adaptivity import FeatureRefinedTet10Mesh
from .shoulder_probe import _small_diameter_tangency_x
from .shoulder_sector_probe import sectorized_ring_indices
from .tet10 import tet10_shape_functions


class CurvedShoulderSectorProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurvedShoulderSectorSample:
    sector_index: int
    element_index: int
    integration_point_index: int
    coordinate_mm: tuple[float, float, float]
    azimuth_rad: float
    distance_to_probe_ring_mm: float
    von_mises_mpa: float


@dataclass(frozen=True)
class CurvedShoulderSectorProbeResult:
    feature_sha256: str
    mesh_sha256: str
    quadrature_point_count: int
    quadrature_natural_coordinates_sha256: str
    probe_ring_x_mm: float
    probe_ring_radius_mm: float
    sector_count: int
    covered_sector_count: int
    angular_coverage_fraction: float
    maximum_sample_distance_mm: float
    mean_sample_distance_mm: float
    mean_von_mises_mpa: float
    max_von_mises_mpa: float
    samples: tuple[CurvedShoulderSectorSample, ...]
    probe_sha256: str


def curved_tet10_integration_point_coordinates(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    natural_coordinates: np.ndarray,
) -> np.ndarray:
    """Map an arbitrary verified TET10 quadrature rule to physical coordinates.

    Unlike the historical four-point helper this has no hard-coded integration
    point count. C11/C12 therefore preserve the actual 64-point Duffy rule.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    points = np.asarray(natural_coordinates, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be finite with shape (n,3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise ValueError("elements must have shape (m,10) with m>0")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contain out-of-range node indices")
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] == 0 or not np.all(np.isfinite(points)):
        raise ValueError("natural_coordinates must be finite with shape (q,3) and q>0")
    if np.any(points < -1.0e-12) or np.any(np.sum(points, axis=1) > 1.0 + 1.0e-12):
        raise ValueError("natural_coordinates lie outside the reference tetrahedron")

    shape = np.vstack([tet10_shape_functions(point) for point in points])
    out = np.empty((elems.shape[0], points.shape[0], 3), dtype=float)
    for element_index, conn in enumerate(elems):
        out[element_index] = shape @ nodes[conn]
    if not np.all(np.isfinite(out)):
        raise ValueError("mapped integration-point coordinates are non-finite")
    return out


def sample_curved_tet10_sectorized_small_diameter_fillet_ring(
    mesh: FeatureRefinedTet10Mesh,
    feature: XAxisShoulderFeature,
    *,
    integration_point_natural_coordinates: np.ndarray,
    integration_point_von_mises_mpa: np.ndarray,
    sector_count: int = 12,
    maximum_allowed_distance_mm: float = 2.0,
) -> CurvedShoulderSectorProbeResult:
    """Measure one actual curved-TET10 integration point per azimuth sector.

    No nodal recovery, CAD-surface extrapolation, smoothing or peak fitting is
    performed. The quadrature coordinates are part of the probe identity so a
    change in the numerical integration rule invalidates probe provenance.
    """
    if mesh.feature_sha256 != feature.feature_sha256:
        raise CurvedShoulderSectorProbeError("FEATURE_MESH_BINDING_MISMATCH")
    natural = np.asarray(integration_point_natural_coordinates, dtype=float)
    values = np.asarray(integration_point_von_mises_mpa, dtype=float)
    if natural.ndim != 2 or natural.shape[1] != 3 or natural.shape[0] == 0 or not np.all(np.isfinite(natural)):
        raise ValueError("integration_point_natural_coordinates must be finite with shape (q,3)")
    if values.shape != (mesh.elements.shape[0], natural.shape[0]) or not np.all(np.isfinite(values)):
        raise ValueError("integration_point_von_mises_mpa must be finite with shape (m,q)")

    coords = curved_tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements, natural)
    flat_coords = coords.reshape((-1, 3))
    flat_values = values.reshape(-1)
    q = int(natural.shape[0])
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

    samples: list[CurvedShoulderSectorSample] = []
    for sector, flat_index in enumerate(indices.tolist()):
        samples.append(
            CurvedShoulderSectorSample(
                sector_index=int(sector),
                element_index=int(flat_index // q),
                integration_point_index=int(flat_index % q),
                coordinate_mm=tuple(float(v) for v in flat_coords[flat_index]),
                azimuth_rad=float(azimuths[sector]),
                distance_to_probe_ring_mm=float(distances[sector]),
                von_mises_mpa=float(flat_values[flat_index]),
            )
        )
    ordered = tuple(samples)
    stresses = np.asarray([sample.von_mises_mpa for sample in ordered], dtype=float)
    dists = np.asarray([sample.distance_to_probe_ring_mm for sample in ordered], dtype=float)
    natural_sha = hashlib.sha256(np.asarray(natural, dtype="<f8").tobytes(order="C")).hexdigest()

    h = hashlib.sha256()
    h.update(b"AsterMaxCurvedShoulderSectorProbeV1\0")
    h.update(feature.feature_sha256.encode("ascii"))
    h.update(mesh.mesh_sha256.encode("ascii"))
    h.update(natural_sha.encode("ascii"))
    h.update(np.asarray((x0, r0, sector_count, maximum_allowed_distance_mm, q), dtype="<f8").tobytes())
    for sample in ordered:
        h.update(np.asarray((sample.sector_index, sample.element_index, sample.integration_point_index), dtype="<i8").tobytes())
        h.update(
            np.asarray(
                (*sample.coordinate_mm, sample.azimuth_rad, sample.distance_to_probe_ring_mm, sample.von_mises_mpa),
                dtype="<f8",
            ).tobytes()
        )

    return CurvedShoulderSectorProbeResult(
        feature_sha256=feature.feature_sha256,
        mesh_sha256=mesh.mesh_sha256,
        quadrature_point_count=q,
        quadrature_natural_coordinates_sha256=natural_sha,
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
