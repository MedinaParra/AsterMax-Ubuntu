from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pow

import numpy as np

from astermax.credibility import canonical_sha256


class TetQualityError(ValueError):
    pass


_EDGE_PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


def _vertices(coords: np.ndarray) -> np.ndarray:
    v = np.asarray(coords, dtype=float)
    if v.shape != (4, 3) or not np.all(np.isfinite(v)):
        raise TetQualityError("tetra vertices must have finite shape (4, 3)")
    return v


def _edge_squared_sum(v: np.ndarray) -> float:
    return float(sum(np.dot(v[j] - v[i], v[j] - v[i]) for i, j in _EDGE_PAIRS))


def tetra_mean_ratio(vertices_mm: np.ndarray) -> float:
    """Normalized tetrahedral mean-ratio quality in [0,1] for valid tets.

    q = 12 (3 V)^(2/3) / sum_{six edges} l_e^2.
    A regular tetrahedron has q=1. Degenerate tetrahedra approach q=0.
    This is a documented AsterMax metric and is not labelled as ANSYS Element Quality.
    """
    v = _vertices(vertices_mm)
    volume6 = abs(float(np.linalg.det(np.column_stack((v[1] - v[0], v[2] - v[0], v[3] - v[0])))))
    if volume6 <= 0.0:
        return 0.0
    volume = volume6 / 6.0
    edge2 = _edge_squared_sum(v)
    if edge2 <= 0.0:
        return 0.0
    q = 12.0 * pow(3.0 * volume, 2.0 / 3.0) / edge2
    return float(min(1.0, max(0.0, q)))


def tetra_mean_ratio_cayley_menger(vertices_mm: np.ndarray) -> float:
    """Independent cross-check using Cayley-Menger volume, not a triple product."""
    v = _vertices(vertices_mm)
    d2 = np.zeros((4, 4), dtype=float)
    for i in range(4):
        for j in range(i + 1, 4):
            value = float(np.dot(v[j] - v[i], v[j] - v[i]))
            d2[i, j] = value
            d2[j, i] = value
    cm = np.ones((5, 5), dtype=float)
    cm[0, 0] = 0.0
    cm[1:, 1:] = d2
    volume2 = float(np.linalg.det(cm)) / 288.0
    if volume2 <= 0.0:
        return 0.0
    volume = float(np.sqrt(volume2))
    edge2 = float(np.sum(np.triu(d2, 1)))
    q = 12.0 * pow(3.0 * volume, 2.0 / 3.0) / edge2
    return float(min(1.0, max(0.0, q)))


@dataclass(frozen=True)
class TetQualitySnapshot:
    schema: str
    metric: str
    element_count: int
    minimum: float
    percentile_10: float
    median: float
    maximum: float
    crosscheck_max_abs_delta: float
    crosscheck_tolerance: float
    crosscheck_verified: bool
    ansys_metric_equivalence: bool
    snapshot_sha256: str


def build_tet10_corner_quality_snapshot(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    crosscheck_tolerance: float = 1.0e-10,
) -> TetQualitySnapshot:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise TetQualityError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise TetQualityError("elements must contain TET10 connectivity")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise TetQualityError("elements contains out-of-range node index")
    tol = float(crosscheck_tolerance)
    if not np.isfinite(tol) or tol <= 0.0:
        raise TetQualityError("crosscheck_tolerance must be finite and positive")

    primary = []
    secondary = []
    for conn in elems:
        vertices = nodes[conn[:4]]
        primary.append(tetra_mean_ratio(vertices))
        secondary.append(tetra_mean_ratio_cayley_menger(vertices))
    q = np.asarray(primary, dtype=float)
    qc = np.asarray(secondary, dtype=float)
    delta = float(np.max(np.abs(q - qc)))
    verified = bool(delta <= tol)
    core = {
        "schema": "AsterMaxTetMeanRatioQualityV1",
        "metric": "TETRA_MEAN_RATIO_12_TIMES_3V_TO_2_OVER_3_DIV_SUM_EDGE_SQUARED",
        "element_count": int(q.size),
        "minimum": float(np.min(q)),
        "percentile_10": float(np.percentile(q, 10.0)),
        "median": float(np.median(q)),
        "maximum": float(np.max(q)),
        "crosscheck_max_abs_delta": delta,
        "crosscheck_tolerance": tol,
        "crosscheck_verified": verified,
        "ansys_metric_equivalence": False,
    }
    return TetQualitySnapshot(**core, snapshot_sha256=canonical_sha256(core))


def require_quality_crosscheck(snapshot: TetQualitySnapshot) -> None:
    if snapshot.schema != "AsterMaxTetMeanRatioQualityV1":
        raise TetQualityError("unsupported tetra quality schema")
    if snapshot.ansys_metric_equivalence:
        raise TetQualityError("ANSYS_METRIC_EQUIVALENCE_NOT_DEMONSTRATED")
    if not snapshot.crosscheck_verified:
        raise TetQualityError("TETRA_MEAN_RATIO_CROSSCHECK_FAILED")
    if snapshot.minimum <= 0.0:
        raise TetQualityError("NONPOSITIVE_TETRA_MEAN_RATIO")
