from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.tet10 import TET10_GAUSS_POINTS, tet10_shape_derivatives
from astermax.fea.tet_quality import build_tet10_corner_quality_snapshot


class CodeAsterMeshQualityError(RuntimeError):
    pass


_CENTROID = np.asarray([[0.25, 0.25, 0.25]], dtype=float)
_SAMPLE_POINTS = np.vstack((TET10_GAUSS_POINTS, _CENTROID))


@dataclass(frozen=True)
class Tet10PreSolveQualityThresholds:
    minimum_corner_mean_ratio: float = 0.05
    minimum_jacobian_ratio: float = 0.05
    relative_jacobian_tolerance: float = 1.0e-12

    def validate(self) -> None:
        if not np.isfinite(self.minimum_corner_mean_ratio) or not (0.0 < self.minimum_corner_mean_ratio <= 1.0):
            raise CodeAsterMeshQualityError("MESH_QUALITY_CORNER_THRESHOLD_INVALID")
        if not np.isfinite(self.minimum_jacobian_ratio) or not (0.0 < self.minimum_jacobian_ratio <= 1.0):
            raise CodeAsterMeshQualityError("MESH_QUALITY_JACOBIAN_RATIO_THRESHOLD_INVALID")
        if not np.isfinite(self.relative_jacobian_tolerance) or self.relative_jacobian_tolerance <= 0.0:
            raise CodeAsterMeshQualityError("MESH_QUALITY_JACOBIAN_TOLERANCE_INVALID")


@dataclass(frozen=True)
class Tet10ElementQualityEvidence:
    element_index: int
    corner_mean_ratio: float
    minimum_sampled_det_jacobian_mm3: float
    maximum_sampled_det_jacobian_mm3: float
    sampled_jacobian_ratio: float
    sampled_jacobian_positive: bool


@dataclass(frozen=True)
class Tet10PreSolveQualityReport:
    schema: str
    length_unit: str
    element_type: str
    element_count: int
    sample_point_count_per_element: int
    minimum_corner_mean_ratio: float
    minimum_sampled_det_jacobian_mm3: float
    minimum_sampled_jacobian_ratio: float
    worst_corner_element_index: int
    worst_jacobian_element_index: int
    threshold_corner_mean_ratio: float
    threshold_jacobian_ratio: float
    all_sampled_jacobians_positive: bool
    corner_quality_crosscheck_verified: bool
    solver_gate_passed: bool
    blockers: tuple[str, ...]
    ansys_metric_equivalence: bool
    fea_solve_executed: bool
    numerical_verification: bool
    results_verified: bool
    report_sha256: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _validated_mesh(nodes_mm: np.ndarray, tet10: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(tet10, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or nodes.shape[0] < 10 or not np.all(np.isfinite(nodes)):
        raise CodeAsterMeshQualityError("MESH_QUALITY_NODES_INVALID")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise CodeAsterMeshQualityError("MESH_QUALITY_TET10_CONNECTIVITY_INVALID")
    if np.any(elems < 0) or np.any(elems >= nodes.shape[0]):
        raise CodeAsterMeshQualityError("MESH_QUALITY_NODE_INDEX_OUT_OF_RANGE")
    for index, conn in enumerate(elems):
        if np.unique(conn).size != 10:
            raise CodeAsterMeshQualityError(f"MESH_QUALITY_DUPLICATE_TET10_NODE:{index}")
    return nodes, elems


def _element_jacobian_evidence(
    coords_mm: np.ndarray,
    element_index: int,
    corner_mean_ratio: float,
    relative_tolerance: float,
) -> Tet10ElementQualityEvidence:
    dets: list[float] = []
    for point in _SAMPLE_POINTS:
        dndr = tet10_shape_derivatives(point)
        dets.append(float(np.linalg.det(coords_mm.T @ dndr)))
    values = np.asarray(dets, dtype=float)
    if not np.all(np.isfinite(values)):
        raise CodeAsterMeshQualityError(f"MESH_QUALITY_NONFINITE_JACOBIAN:{element_index}")

    diagonal = float(np.linalg.norm(coords_mm.max(axis=0) - coords_mm.min(axis=0)))
    scale = max(diagonal, 1.0)
    positive_tol = scale**3 * relative_tolerance
    min_det = float(np.min(values))
    max_det = float(np.max(values))
    positive = bool(min_det > positive_tol)
    ratio = float(min_det / max_det) if positive and max_det > 0.0 else 0.0
    return Tet10ElementQualityEvidence(
        element_index=int(element_index),
        corner_mean_ratio=float(corner_mean_ratio),
        minimum_sampled_det_jacobian_mm3=min_det,
        maximum_sampled_det_jacobian_mm3=max_det,
        sampled_jacobian_ratio=ratio,
        sampled_jacobian_positive=positive,
    )


def build_tet10_presolve_quality_report(
    nodes_mm: np.ndarray,
    tet10: np.ndarray,
    *,
    thresholds: Tet10PreSolveQualityThresholds | None = None,
) -> Tet10PreSolveQualityReport:
    """Build a fail-closed TET10 quality report before Code_Aster execution.

    This is an AsterMax pre-solve metric, not an ANSYS Element Quality claim.
    It combines the independently cross-checked corner mean-ratio metric with
    sampled quadratic isoparametric Jacobians at the four symmetric integration
    points plus the centroid.  A valid corner tetrahedron alone is therefore
    insufficient to pass if midside-node geometry causes an internal inversion.
    """
    nodes, elems = _validated_mesh(nodes_mm, tet10)
    limits = thresholds or Tet10PreSolveQualityThresholds()
    limits.validate()

    corner = build_tet10_corner_quality_snapshot(nodes, elems)
    corner_values = []
    evidence: list[Tet10ElementQualityEvidence] = []
    from astermax.fea.tet_quality import tetra_mean_ratio

    for index, conn in enumerate(elems):
        q = float(tetra_mean_ratio(nodes[conn[:4]]))
        corner_values.append(q)
        evidence.append(
            _element_jacobian_evidence(
                nodes[conn],
                index,
                q,
                limits.relative_jacobian_tolerance,
            )
        )

    corner_array = np.asarray(corner_values, dtype=float)
    jacobian_ratios = np.asarray([item.sampled_jacobian_ratio for item in evidence], dtype=float)
    minimum_dets = np.asarray([item.minimum_sampled_det_jacobian_mm3 for item in evidence], dtype=float)
    all_positive = all(item.sampled_jacobian_positive for item in evidence)
    worst_corner = int(np.argmin(corner_array))
    worst_jacobian = int(np.argmin(jacobian_ratios))

    blockers: list[str] = []
    if not corner.crosscheck_verified:
        blockers.append("CORNER_MEAN_RATIO_CROSSCHECK_FAILED")
    if float(np.min(corner_array)) < limits.minimum_corner_mean_ratio:
        blockers.append(f"CORNER_MEAN_RATIO_BELOW_THRESHOLD:{worst_corner}")
    if not all_positive:
        inverted = next(item.element_index for item in evidence if not item.sampled_jacobian_positive)
        blockers.append(f"TET10_JACOBIAN_NONPOSITIVE:{inverted}")
    if float(np.min(jacobian_ratios)) < limits.minimum_jacobian_ratio:
        blockers.append(f"TET10_JACOBIAN_RATIO_BELOW_THRESHOLD:{worst_jacobian}")

    core: dict[str, object] = {
        "schema": "astermax.code-aster-tet10-presolve-quality.v1",
        "length_unit": "mm",
        "element_type": "TET10_GMSH_TYPE_11",
        "element_count": int(elems.shape[0]),
        "sample_point_count_per_element": int(_SAMPLE_POINTS.shape[0]),
        "minimum_corner_mean_ratio": float(np.min(corner_array)),
        "minimum_sampled_det_jacobian_mm3": float(np.min(minimum_dets)),
        "minimum_sampled_jacobian_ratio": float(np.min(jacobian_ratios)),
        "worst_corner_element_index": worst_corner,
        "worst_jacobian_element_index": worst_jacobian,
        "threshold_corner_mean_ratio": limits.minimum_corner_mean_ratio,
        "threshold_jacobian_ratio": limits.minimum_jacobian_ratio,
        "all_sampled_jacobians_positive": bool(all_positive),
        "corner_quality_crosscheck_verified": bool(corner.crosscheck_verified),
        "solver_gate_passed": not blockers,
        "blockers": tuple(blockers),
        "ansys_metric_equivalence": False,
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
    }
    return Tet10PreSolveQualityReport(**core, report_sha256=canonical_sha256(core))


def require_tet10_presolve_quality(report: Tet10PreSolveQualityReport) -> None:
    if report.schema != "astermax.code-aster-tet10-presolve-quality.v1":
        raise CodeAsterMeshQualityError("MESH_QUALITY_REPORT_SCHEMA_UNSUPPORTED")
    if report.length_unit != "mm" or report.element_type != "TET10_GMSH_TYPE_11":
        raise CodeAsterMeshQualityError("MESH_QUALITY_REPORT_CONTRACT_INVALID")
    if report.ansys_metric_equivalence:
        raise CodeAsterMeshQualityError("ANSYS_METRIC_EQUIVALENCE_NOT_DEMONSTRATED")
    if report.fea_solve_executed or report.numerical_verification or report.results_verified:
        raise CodeAsterMeshQualityError("MESH_QUALITY_REPORT_CANNOT_PROMOTE_SOLVER_CLAIMS")
    if not report.solver_gate_passed or report.blockers:
        blocker = report.blockers[0] if report.blockers else "UNKNOWN"
        raise CodeAsterMeshQualityError(f"CODE_ASTER_PRESOLVE_MESH_QUALITY_BLOCKED:{blocker}")
