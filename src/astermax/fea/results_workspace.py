from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np

from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class AsterMaxResultProbeV1:
    kind: str
    entity_id: int
    value: float
    unit: str


@dataclass(frozen=True)
class AsterMaxProfessionalResultsWorkspaceV1:
    schema_version: str
    result_class: str
    solve_evidence_sha256: str
    node_count: int
    tet10_count: int
    deformation_scale: float
    displacement_min_mm: float
    displacement_max_mm: float
    von_mises_ip_max_min_mpa: float
    von_mises_ip_max_max_mpa: float
    max_displacement_node_id: int
    max_von_mises_element_id: int
    stress_representation: str
    converged_claim: bool
    industrial_validation_claim: bool
    ansys_equivalence_claim: bool
    workspace_sha256: str


def _canonical_sha256(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_professional_results_workspace(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    solve_evidence_sha256: str,
    deformation_scale: float = 1.0,
    result_class: str = "PMV_UNCONVERGED_USER_MODEL_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
    ansys_equivalence_claim: bool = False,
) -> AsterMaxProfessionalResultsWorkspaceV1:
    """Build deterministic, provenance-bound result metadata for the desktop viewer.

    Stress remains at the four TET10 integration points. The workspace exposes
    only the explicit per-element maximum von Mises value; it does not perform
    nodal extrapolation, averaging or smoothing.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    u = np.asarray(result.displacement_mm, dtype=float)
    ip_vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("RESULTS_WORKSPACE_NODES_SHAPE")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("RESULTS_WORKSPACE_TET10_SHAPE")
    if u.shape != nodes.shape:
        raise ValueError("RESULTS_WORKSPACE_DISPLACEMENT_SHAPE")
    if ip_vm.shape != (elems.shape[0], 4):
        raise ValueError("RESULTS_WORKSPACE_VM_IP_SHAPE")
    if not solve_evidence_sha256 or len(str(solve_evidence_sha256)) != 64:
        raise ValueError("RESULTS_WORKSPACE_SOLVE_EVIDENCE_REQUIRED")
    if not np.isfinite(deformation_scale) or deformation_scale < 0.0:
        raise ValueError("RESULTS_WORKSPACE_DEFORMATION_SCALE")
    if not all(np.all(np.isfinite(value)) for value in (nodes, u, ip_vm)):
        raise ValueError("RESULTS_WORKSPACE_NONFINITE_FIELD")
    if industrial_validation_claim:
        raise ValueError("RESULTS_WORKSPACE_INDUSTRIAL_CLAIM_REFUSED")
    if ansys_equivalence_claim:
        raise ValueError("RESULTS_WORKSPACE_ANSYS_EQUIVALENCE_REFUSED")

    u_mag = np.linalg.norm(u, axis=1)
    vm_max = np.max(ip_vm, axis=1) if ip_vm.size else np.zeros(elems.shape[0], dtype=float)
    max_u_id = int(np.argmax(u_mag)) if u_mag.size else -1
    max_vm_id = int(np.argmax(vm_max)) if vm_max.size else -1

    core = {
        "schema_version": "AsterMaxProfessionalResultsWorkspaceV1",
        "result_class": str(result_class),
        "solve_evidence_sha256": str(solve_evidence_sha256),
        "node_count": int(nodes.shape[0]),
        "tet10_count": int(elems.shape[0]),
        "deformation_scale": float(deformation_scale),
        "displacement_min_mm": float(np.min(u_mag)) if u_mag.size else 0.0,
        "displacement_max_mm": float(np.max(u_mag)) if u_mag.size else 0.0,
        "von_mises_ip_max_min_mpa": float(np.min(vm_max)) if vm_max.size else 0.0,
        "von_mises_ip_max_max_mpa": float(np.max(vm_max)) if vm_max.size else 0.0,
        "max_displacement_node_id": max_u_id,
        "max_von_mises_element_id": max_vm_id,
        "stress_representation": "FOUR_INTEGRATION_POINTS_PRESERVED_ELEMENT_MAX_ONLY_NO_NODAL_SMOOTHING",
        "converged_claim": bool(converged_claim),
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    return AsterMaxProfessionalResultsWorkspaceV1(**core, workspace_sha256=_canonical_sha256(core))


def deformed_coordinates_mm(
    nodes_mm: np.ndarray,
    result: Tet10LinearStaticResult,
    deformation_scale: float,
) -> np.ndarray:
    nodes = np.asarray(nodes_mm, dtype=float)
    displacement = np.asarray(result.displacement_mm, dtype=float)
    scale = float(deformation_scale)
    if nodes.shape != displacement.shape or nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("RESULTS_WORKSPACE_DEFORMED_SHAPE")
    if not np.isfinite(scale) or scale < 0.0:
        raise ValueError("RESULTS_WORKSPACE_DEFORMATION_SCALE")
    return nodes + scale * displacement


def probe_result(
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    result: Tet10LinearStaticResult,
    *,
    kind: str,
    entity_id: int,
) -> AsterMaxResultProbeV1:
    idx = int(entity_id)
    if kind == "U_MAG":
        values = np.linalg.norm(np.asarray(result.displacement_mm, dtype=float), axis=1)
        unit = "mm"
    elif kind == "VON_MISES_IP_MAX":
        values = np.max(np.asarray(result.integration_point_von_mises_mpa, dtype=float), axis=1)
        unit = "MPa"
    else:
        raise ValueError("RESULTS_WORKSPACE_UNKNOWN_PROBE")
    if idx < 0 or idx >= values.shape[0]:
        raise ValueError("RESULTS_WORKSPACE_PROBE_OUT_OF_RANGE")
    return AsterMaxResultProbeV1(kind=kind, entity_id=idx, value=float(values[idx]), unit=unit)


def workspace_to_json(workspace: AsterMaxProfessionalResultsWorkspaceV1) -> str:
    return json.dumps(asdict(workspace), indent=2, sort_keys=True, allow_nan=False) + "\n"
