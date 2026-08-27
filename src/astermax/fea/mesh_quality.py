from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .quality_policy import DEFAULT_TETRA_QUALITY_POLICY, TetraQualityPolicy


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
    policy: dict[str, float] | None = None

    @property
    def passed(self) -> bool:
        return self.status != "FAIL"


def tetra_element_metrics(nodes_mm: np.ndarray, elements: np.ndarray) -> dict[str, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    conn = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if conn.ndim != 2 or conn.shape[1] not in (4, 10):
        raise ValueError("elements must have shape (m, 4) or (m, 10)")
    if conn.size and (np.any(conn < 0) or np.any(conn >= len(nodes))):
        raise ValueError("element connectivity contains an out-of-range node")
    xyz = nodes[conn[:, :4]]
    if len(xyz) == 0:
        raise MeshQualityError("mesh contains no tetrahedra")
    e01, e02, e03 = xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0], xyz[:, 3] - xyz[:, 0]
    det = np.einsum("ij,ij->i", e01, np.cross(e02, e03))
    denom = np.linalg.norm(e01, axis=1) * np.linalg.norm(e02, axis=1) * np.linalg.norm(e03, axis=1)
    scaled_jac = np.divide(det, denom, out=np.zeros_like(det), where=denom > 0.0)
    pairs = ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))
    lengths = np.stack([np.linalg.norm(xyz[:, j] - xyz[:, i], axis=1) for i,j in pairs], axis=1)
    shortest, longest = lengths.min(axis=1), lengths.max(axis=1)
    aspect = np.divide(longest, shortest, out=np.full_like(longest, np.inf), where=shortest > 0.0)
    volume = det / 6.0
    sum_l2 = np.sum(lengths * lengths, axis=1)
    mean_ratio = np.zeros_like(volume)
    valid = (volume > 0.0) & (sum_l2 > 0.0)
    mean_ratio[valid] = 12.0 * np.power(3.0 * volume[valid], 2.0 / 3.0) / sum_l2[valid]
    return {"determinant": det, "denominator": denom, "shortest_edge": shortest, "scaled_jacobian": scaled_jac, "mean_ratio": mean_ratio, "edge_aspect_ratio": aspect}


def classify_tetra_metrics(metrics: dict[str, np.ndarray], policy: TetraQualityPolicy = DEFAULT_TETRA_QUALITY_POLICY) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    policy.validate()
    det, denom, shortest = metrics["determinant"], metrics["denominator"], metrics["shortest_edge"]
    sj, mr, aspect = metrics["scaled_jacobian"], metrics["mean_ratio"], metrics["edge_aspect_ratio"]
    degenerate = (denom <= 0.0) | (shortest <= 0.0) | (np.abs(det) <= policy.determinant_epsilon)
    inverted = det < -policy.determinant_epsilon
    fail = degenerate | inverted | (sj < policy.fail_scaled_jacobian) | (mr < policy.fail_mean_ratio) | (aspect > policy.fail_edge_aspect_ratio)
    warn = (~fail) & ((sj < policy.warn_scaled_jacobian) | (mr < policy.warn_mean_ratio) | (aspect > policy.warn_edge_aspect_ratio))
    status = np.where(fail, "FAIL", np.where(warn, "WARN", "PASS"))
    return status, inverted, degenerate


def tetra_mesh_quality(nodes_mm: np.ndarray, elements: np.ndarray, *, policy: TetraQualityPolicy = DEFAULT_TETRA_QUALITY_POLICY) -> MeshQualityReport:
    """Evaluate auditable corner-geometry quality for TET4/TET10 meshes."""
    metrics = tetra_element_metrics(nodes_mm, elements)
    status_by_element, inverted, degenerate = classify_tetra_metrics(metrics, policy)
    fail = status_by_element == "FAIL"
    warn = status_by_element == "WARN"
    status = "FAIL" if np.any(fail) else ("WARN" if np.any(warn) else "PASS")
    return MeshQualityReport(
        element_count=int(len(status_by_element)),
        min_scaled_jacobian=float(np.min(metrics["scaled_jacobian"])),
        min_mean_ratio=float(np.min(metrics["mean_ratio"])),
        max_edge_aspect_ratio=float(np.max(metrics["edge_aspect_ratio"])),
        inverted_elements=int(np.count_nonzero(inverted)),
        degenerate_elements=int(np.count_nonzero(degenerate)),
        warn_elements=int(np.count_nonzero(warn)),
        fail_elements=int(np.count_nonzero(fail)),
        status=status,
        policy=policy.to_dict(),
    )


def require_mesh_quality(report: MeshQualityReport) -> None:
    if report.status == "FAIL":
        raise MeshQualityError(
            "mesh quality gate failed: "
            f"scaled_jacobian_min={report.min_scaled_jacobian:.6g}, "
            f"mean_ratio_min={report.min_mean_ratio:.6g}, "
            f"edge_aspect_max={report.max_edge_aspect_ratio:.6g}, "
            f"inverted={report.inverted_elements}, degenerate={report.degenerate_elements}, "
            f"failed={report.fail_elements}"
        )
