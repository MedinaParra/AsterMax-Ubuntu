from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class MeshQualityError(RuntimeError):
    """Raised when a mesh cannot pass the PMV geometric quality gate."""


@dataclass(frozen=True)
class MeshQualityReport:
    element_count: int
    min_scaled_jacobian: float
    min_mean_ratio: float
    max_edge_aspect_ratio: float
    inverted_elements: int
    degenerate_elements: int
    warn_elements: int
    fail_elements: int
    status: str

    @property
    def passed(self) -> bool:
        return self.status != "FAIL"


def _tet4_corner_geometry(nodes_mm: np.ndarray, elements: np.ndarray):
    nodes = np.asarray(nodes_mm, dtype=float)
    conn = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if conn.ndim != 2 or conn.shape[1] not in (4, 10):
        raise ValueError("elements must have shape (m, 4) or (m, 10)")
    if conn.size and (np.any(conn < 0) or np.any(conn >= len(nodes))):
        raise ValueError("element connectivity contains an out-of-range node")
    return nodes[conn[:, :4]]


def tetra_mesh_quality(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    warn_scaled_jacobian: float = 0.20,
    fail_scaled_jacobian: float = 0.05,
    warn_mean_ratio: float = 0.20,
    fail_mean_ratio: float = 0.05,
    warn_edge_aspect_ratio: float = 8.0,
    fail_edge_aspect_ratio: float = 20.0,
) -> MeshQualityReport:
    """Evaluate auditable corner-geometry quality for TET4/TET10 meshes.

    The gate intentionally uses only the four corner nodes. For the current
    straight-sided TET10 verification scope this is exact geometry. Curved
    high-order Jacobian quality requires a separate integration-point gate.

    Metrics:
    - scaled Jacobian = det([e01,e02,e03]) / (|e01||e02||e03|), signed;
    - mean ratio = 12*(3V)^(2/3) / sum(edge_length^2), in [0,1] for valid tets;
    - edge aspect ratio = longest / shortest of the six corner edges.
    """
    if not (0.0 < fail_scaled_jacobian <= warn_scaled_jacobian <= 1.0):
        raise ValueError("scaled-Jacobian thresholds must satisfy 0 < fail <= warn <= 1")
    if not (0.0 < fail_mean_ratio <= warn_mean_ratio <= 1.0):
        raise ValueError("mean-ratio thresholds must satisfy 0 < fail <= warn <= 1")
    if not (1.0 <= warn_edge_aspect_ratio <= fail_edge_aspect_ratio):
        raise ValueError("aspect thresholds must satisfy 1 <= warn <= fail")

    xyz = _tet4_corner_geometry(nodes_mm, elements)
    if len(xyz) == 0:
        raise MeshQualityError("mesh contains no tetrahedra")

    e01 = xyz[:, 1] - xyz[:, 0]
    e02 = xyz[:, 2] - xyz[:, 0]
    e03 = xyz[:, 3] - xyz[:, 0]
    det = np.einsum("ij,ij->i", e01, np.cross(e02, e03))
    denom = np.linalg.norm(e01, axis=1) * np.linalg.norm(e02, axis=1) * np.linalg.norm(e03, axis=1)
    scaled_jac = np.divide(det, denom, out=np.zeros_like(det), where=denom > 0.0)

    pairs = ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))
    lengths = np.stack([np.linalg.norm(xyz[:, j] - xyz[:, i], axis=1) for i,j in pairs], axis=1)
    shortest = lengths.min(axis=1)
    longest = lengths.max(axis=1)
    aspect = np.divide(longest, shortest, out=np.full_like(longest, np.inf), where=shortest > 0.0)

    volume = det / 6.0
    sum_l2 = np.sum(lengths * lengths, axis=1)
    mean_ratio = np.zeros_like(volume)
    valid = (volume > 0.0) & (sum_l2 > 0.0)
    mean_ratio[valid] = 12.0 * np.power(3.0 * volume[valid], 2.0 / 3.0) / sum_l2[valid]

    degenerate = (denom <= 0.0) | (shortest <= 0.0) | (np.abs(det) <= 1.0e-14)
    inverted = det < -1.0e-14
    fail = degenerate | inverted | (scaled_jac < fail_scaled_jacobian) | (mean_ratio < fail_mean_ratio) | (aspect > fail_edge_aspect_ratio)
    warn = (~fail) & ((scaled_jac < warn_scaled_jacobian) | (mean_ratio < warn_mean_ratio) | (aspect > warn_edge_aspect_ratio))

    status = "FAIL" if np.any(fail) else ("WARN" if np.any(warn) else "PASS")
    return MeshQualityReport(
        element_count=int(len(xyz)),
        min_scaled_jacobian=float(np.min(scaled_jac)),
        min_mean_ratio=float(np.min(mean_ratio)),
        max_edge_aspect_ratio=float(np.max(aspect)),
        inverted_elements=int(np.count_nonzero(inverted)),
        degenerate_elements=int(np.count_nonzero(degenerate)),
        warn_elements=int(np.count_nonzero(warn)),
        fail_elements=int(np.count_nonzero(fail)),
        status=status,
    )


def require_mesh_quality(report: MeshQualityReport) -> None:
    """Fail closed before FEA when the declared quality thresholds fail."""
    if report.status == "FAIL":
        raise MeshQualityError(
            "mesh quality gate failed: "
            f"scaled_jacobian_min={report.min_scaled_jacobian:.6g}, "
            f"mean_ratio_min={report.min_mean_ratio:.6g}, "
            f"edge_aspect_max={report.max_edge_aspect_ratio:.6g}, "
            f"inverted={report.inverted_elements}, degenerate={report.degenerate_elements}, "
            f"failed={report.fail_elements}"
        )
