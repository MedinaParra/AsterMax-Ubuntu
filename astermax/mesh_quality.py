"""Auditable geometric quality checks for linear tetrahedral meshes.

AsterMax uses a dimensionless tetrahedral mean-ratio metric:

    q = 12 * (3 V)^(2/3) / sum(edge_length^2)

For a regular tetrahedron q=1 and q tends to 0 as the element collapses.  The
metric is independent of the mm scale and is therefore suitable as a pre-solve
shape gate.  It does not replace convergence/error estimation.
"""

from dataclasses import dataclass
from math import dist, isfinite
from statistics import fmean
from typing import Sequence


class MeshQualityError(ValueError):
    """Raised when a tetrahedral mesh is invalid or fails the quality gate."""


@dataclass(frozen=True)
class Tet4MeshQualityReport:
    element_count: int
    minimum: float
    mean: float
    maximum: float
    below_threshold: int
    threshold: float
    worst_element: int

    @property
    def accepted(self) -> bool:
        return self.below_threshold == 0


def _signed_six_volume(nodes: Sequence[Sequence[float]]) -> float:
    a, b, c, d = nodes
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    ad = [d[i] - a[i] for i in range(3)]
    return (
        ab[0] * (ac[1] * ad[2] - ac[2] * ad[1])
        - ab[1] * (ac[0] * ad[2] - ac[2] * ad[0])
        + ab[2] * (ac[0] * ad[1] - ac[1] * ad[0])
    )


def tet4_mean_ratio(nodes: Sequence[Sequence[float]]) -> float:
    """Return a dimensionless TET4 shape quality in [0, 1] for valid geometry."""
    if len(nodes) != 4 or any(len(node) != 3 for node in nodes):
        raise MeshQualityError("TET4 quality requires exactly four 3D nodes")
    points = [tuple(map(float, node)) for node in nodes]
    if any(not isfinite(value) for point in points for value in point):
        raise MeshQualityError("mesh coordinates must be finite")

    volume = abs(_signed_six_volume(points)) / 6.0
    edge_sq_sum = 0.0
    for i in range(4):
        for j in range(i + 1, 4):
            length = dist(points[i], points[j])
            edge_sq_sum += length * length
    if volume <= 0.0 or edge_sq_sum <= 0.0:
        return 0.0

    quality = 12.0 * (3.0 * volume) ** (2.0 / 3.0) / edge_sq_sum
    # Roundoff can produce 1+epsilon for a regular tetrahedron.
    return min(1.0, max(0.0, quality))


def assess_tet4_mesh_quality(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    *,
    minimum_quality: float = 0.05,
) -> Tet4MeshQualityReport:
    """Assess every TET4 and return summary statistics without hiding bad cells."""
    if not (0.0 < minimum_quality <= 1.0):
        raise MeshQualityError("minimum_quality must satisfy 0 < q <= 1")
    if not elements:
        raise MeshQualityError("mesh contains no TET4 elements")

    qualities: list[float] = []
    for element_index, element in enumerate(elements):
        if len(element) != 4:
            raise MeshQualityError(f"element {element_index} is not TET4")
        if any(index < 0 or index >= len(nodes) for index in element):
            raise MeshQualityError(f"element {element_index} references an invalid node")
        qualities.append(tet4_mean_ratio([nodes[index] for index in element]))

    minimum = min(qualities)
    return Tet4MeshQualityReport(
        element_count=len(qualities),
        minimum=minimum,
        mean=fmean(qualities),
        maximum=max(qualities),
        below_threshold=sum(value < minimum_quality for value in qualities),
        threshold=minimum_quality,
        worst_element=qualities.index(minimum),
    )


def require_tet4_mesh_quality(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    *,
    minimum_quality: float = 0.05,
) -> Tet4MeshQualityReport:
    """Fail closed before solve when one or more TET4 cells violate the shape gate."""
    report = assess_tet4_mesh_quality(
        nodes,
        elements,
        minimum_quality=minimum_quality,
    )
    if not report.accepted:
        raise MeshQualityError(
            "TET4 mesh quality gate failed: "
            f"{report.below_threshold}/{report.element_count} elements below "
            f"q={report.threshold:g}; worst element {report.worst_element} "
            f"has q={report.minimum:.6g}"
        )
    return report
