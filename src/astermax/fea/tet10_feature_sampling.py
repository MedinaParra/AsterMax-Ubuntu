from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .feature_adaptivity import FeatureRefinedTet10Mesh, shoulder_local_box
from .tet10 import TET10_GAUSS_POINTS, tet10_shape_functions


class Tet10FeatureSamplingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tet10IpSample:
    element_index: int
    integration_point_index: int
    coordinate_mm: tuple[float, float, float]
    von_mises_mpa: float | None


@dataclass(frozen=True)
class Tet10ShoulderNeighborhood:
    feature_sha256: str
    mesh_sha256: str
    sampling_box_mm: tuple[float, float, float, float, float, float]
    stress_representation: str
    sample_count: int
    samples: tuple[Tet10IpSample, ...]
    neighborhood_sha256: str


def tet10_integration_point_coordinates(nodes_mm: np.ndarray, elements: np.ndarray) -> np.ndarray:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contain out-of-range node indices")
    if not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm contains non-finite coordinates")

    out = np.empty((elems.shape[0], 4, 3), dtype=float)
    shape = np.vstack([tet10_shape_functions(point) for point in TET10_GAUSS_POINTS])
    for element_index, conn in enumerate(elems):
        out[element_index] = shape @ nodes[conn]
    return out


def _neighborhood_hash(
    feature_sha256: str,
    mesh_sha256: str,
    box: tuple[float, ...],
    samples: tuple[Tet10IpSample, ...],
) -> str:
    h = hashlib.sha256()
    h.update(b"AsterMaxTet10ShoulderNeighborhoodV1\0")
    h.update(feature_sha256.encode("ascii"))
    h.update(mesh_sha256.encode("ascii"))
    h.update(np.asarray(box, dtype="<f8").tobytes(order="C"))
    for sample in samples:
        h.update(np.asarray((sample.element_index, sample.integration_point_index), dtype="<i8").tobytes())
        h.update(np.asarray(sample.coordinate_mm, dtype="<f8").tobytes())
        if sample.von_mises_mpa is None:
            h.update(b"NO_STRESS_VALUE")
        else:
            h.update(np.asarray((sample.von_mises_mpa,), dtype="<f8").tobytes())
    return h.hexdigest()


def sample_tet10_shoulder_neighborhood(
    mesh: FeatureRefinedTet10Mesh,
    feature: XAxisShoulderFeature,
    *,
    padding_mm: float,
    integration_point_von_mises_mpa: np.ndarray | None = None,
) -> Tet10ShoulderNeighborhood:
    """Select real TET10 integration points around the recognized shoulder.

    No nodal extrapolation, no stress averaging and no peak smoothing are
    performed. When stress is omitted this function is geometry-only and the
    resulting neighborhood explicitly contains no stress values.
    """
    if mesh.feature_sha256 != feature.feature_sha256:
        raise Tet10FeatureSamplingError("FEATURE_MESH_BINDING_MISMATCH")
    box = shoulder_local_box(feature, padding_mm=padding_mm)
    ip_coords = tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements)

    values = None
    if integration_point_von_mises_mpa is not None:
        values = np.asarray(integration_point_von_mises_mpa, dtype=float)
        if values.shape != (mesh.elements.shape[0], 4):
            raise ValueError("integration_point_von_mises_mpa must have shape (m, 4)")
        if not np.all(np.isfinite(values)):
            raise ValueError("integration-point stress values must be finite")

    b = np.asarray(box, dtype=float)
    selected: list[Tet10IpSample] = []
    for element_index in range(ip_coords.shape[0]):
        for ip_index in range(4):
            coordinate = ip_coords[element_index, ip_index]
            if np.all(coordinate >= b[:3]) and np.all(coordinate <= b[3:]):
                selected.append(
                    Tet10IpSample(
                        element_index=element_index,
                        integration_point_index=ip_index,
                        coordinate_mm=tuple(float(v) for v in coordinate),
                        von_mises_mpa=None if values is None else float(values[element_index, ip_index]),
                    )
                )
    if not selected:
        raise Tet10FeatureSamplingError("NO_TET10_INTEGRATION_POINTS_IN_SHOULDER_NEIGHBORHOOD")
    ordered = tuple(sorted(selected, key=lambda s: (s.element_index, s.integration_point_index)))
    digest = _neighborhood_hash(feature.feature_sha256, mesh.mesh_sha256, box, ordered)
    return Tet10ShoulderNeighborhood(
        feature_sha256=feature.feature_sha256,
        mesh_sha256=mesh.mesh_sha256,
        sampling_box_mm=box,
        stress_representation=(
            "FOUR_TET10_INTEGRATION_POINTS_NO_NODAL_SMOOTHING"
            if values is not None
            else "GEOMETRY_ONLY_NO_STRESS_VALUES"
        ),
        sample_count=len(ordered),
        samples=ordered,
        neighborhood_sha256=digest,
    )
