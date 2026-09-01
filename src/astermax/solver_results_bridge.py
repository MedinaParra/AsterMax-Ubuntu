from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .results_scene import ResultsFieldBinding, ResultsScene, build_results_scene
from .fea.solver import Tet10LinearStaticResult


STRESS_REPRESENTATION = "INCIDENT_ELEMENT_MAX_OF_TET10_IP_VON_MISES_NO_SMOOTHING"


@dataclass(frozen=True)
class SolverResultsBridgeEvidence:
    node_count: int
    element_count: int
    displacement_source: str
    stress_source: str
    stress_representation: str
    workspace_sha256: str
    solve_evidence_sha256: str


def incident_element_ipmax_to_nodes(
    elements: np.ndarray,
    integration_point_von_mises_mpa: np.ndarray,
    node_count: int,
) -> np.ndarray:
    """Create a conservative display scalar from verified TET10 integration-point stress.

    For each element, first take max(VM) across its four integration points. Each
    incident node receives the maximum of those element maxima. This is explicitly
    a visualization projection: it is not nodal stress recovery, extrapolation,
    averaging, smoothing, or a new FEA result.
    """
    elems = np.asarray(elements, dtype=int)
    ip_vm = np.asarray(integration_point_von_mises_mpa, dtype=float)
    if elems.ndim != 2 or elems.shape[1] != 10 or len(elems) == 0:
        raise ValueError("SOLVER_RESULTS_TET10_ELEMENTS_REQUIRED")
    if node_count <= 0:
        raise ValueError("SOLVER_RESULTS_NODE_COUNT_INVALID")
    if elems.min() < 0 or elems.max() >= node_count:
        raise ValueError("SOLVER_RESULTS_CONNECTIVITY_OUT_OF_RANGE")
    if ip_vm.shape != (len(elems), 4):
        raise ValueError("SOLVER_RESULTS_IP_VON_MISES_SHAPE_INVALID")
    if not np.isfinite(ip_vm).all() or np.any(ip_vm < -1e-12):
        raise ValueError("SOLVER_RESULTS_IP_VON_MISES_INVALID")

    element_max = ip_vm.max(axis=1)
    nodal = np.full(node_count, -np.inf, dtype=float)
    for element_index, conn in enumerate(elems):
        nodal[conn] = np.maximum(nodal[conn], element_max[element_index])
    if not np.isfinite(nodal).all():
        raise ValueError("SOLVER_RESULTS_ORPHAN_NODE_STRESS_UNDEFINED")
    return nodal


def bind_verified_tet10_solver_results(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    workspace_sha256: str,
    solve_evidence_sha256: str,
) -> tuple[ResultsFieldBinding, SolverResultsBridgeEvidence]:
    if not isinstance(result, Tet10LinearStaticResult):
        raise ValueError("SOLVER_RESULTS_TET10_RESULT_REQUIRED")
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or len(nodes) == 0:
        raise ValueError("SOLVER_RESULTS_NODES_REQUIRED")
    displacement = np.asarray(result.displacement_mm, dtype=float)
    if displacement.shape != nodes.shape or not np.isfinite(displacement).all():
        raise ValueError("SOLVER_RESULTS_DISPLACEMENT_INVALID")

    nodal_vm = incident_element_ipmax_to_nodes(
        elems,
        result.integration_point_von_mises_mpa,
        len(nodes),
    )
    binding = ResultsFieldBinding(
        displacement_mm=displacement.copy(),
        von_mises_mpa=nodal_vm,
        workspace_sha256=workspace_sha256,
        solve_evidence_sha256=solve_evidence_sha256,
        stress_representation=STRESS_REPRESENTATION,
    )
    build_results_scene(nodes, binding, deformation_scale=1.0)
    evidence = SolverResultsBridgeEvidence(
        node_count=int(len(nodes)),
        element_count=int(len(elems)),
        displacement_source="Tet10LinearStaticResult.displacement_mm",
        stress_source="Tet10LinearStaticResult.integration_point_von_mises_mpa",
        stress_representation=STRESS_REPRESENTATION,
        workspace_sha256=workspace_sha256,
        solve_evidence_sha256=solve_evidence_sha256,
    )
    return binding, evidence


def build_results_scene_from_desktop_summary(
    summary: dict,
    *,
    deformation_scale: float = 1.0,
) -> tuple[ResultsScene, SolverResultsBridgeEvidence]:
    """Cut over the existing desktop solve runtime into the evidence-bound scene.

    The desktop summary already carries the exact runtime nodes/elements/result plus
    production workspace and solve hashes. This adapter refuses stale/missing
    provenance before exposing deformation or Von Mises display modes.
    """
    if not isinstance(summary, dict):
        raise ValueError("SOLVER_RESULTS_DESKTOP_SUMMARY_REQUIRED")
    runtime = summary.get("_runtime_results")
    production = summary.get("production_results")
    solve = summary.get("solve_evidence")
    if not isinstance(runtime, dict) or not isinstance(production, dict) or not isinstance(solve, dict):
        raise ValueError("SOLVER_RESULTS_DESKTOP_PROVENANCE_REQUIRED")
    workspace_sha = production.get("workspace_sha256")
    solve_sha = solve.get("solve_evidence_sha256")
    runtime_workspace = runtime.get("workspace")
    if runtime_workspace is None or getattr(runtime_workspace, "workspace_sha256", None) != workspace_sha:
        raise ValueError("SOLVER_RESULTS_DESKTOP_WORKSPACE_STALE")
    if production.get("solve_evidence_sha256") != solve_sha:
        raise ValueError("SOLVER_RESULTS_DESKTOP_SOLVE_STALE")

    nodes = runtime.get("nodes_mm")
    elements = runtime.get("elements")
    result = runtime.get("result")
    binding, evidence = bind_verified_tet10_solver_results(
        nodes,
        elements,
        result,
        workspace_sha256=workspace_sha,
        solve_evidence_sha256=solve_sha,
    )
    return build_results_scene(nodes, binding, deformation_scale=deformation_scale), evidence
