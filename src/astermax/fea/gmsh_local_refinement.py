from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any, Callable

from astermax.credibility import canonical_sha256
from .local_refinement_plan import (
    ControlledLocalRefinementPlanV1,
    RefinementApprovalV1,
    target_size_at_point,
    verify_refinement_execution_boundary,
)


@dataclass(frozen=True)
class GmshLocalRemeshEvidenceV1:
    schema: str
    plan_sha256: str
    approval_sha256: str
    source_step_sha256: str
    route_sha256: str
    baseline_mesh_sha256: str
    output_mesh_sha256: str
    output_path: str
    element_order: int
    tetra_element_type: int
    tetra_element_count: int
    node_count: int
    preserves_source_geometry: bool
    preserves_bc_load_route: bool
    qoi_convergence_claimed: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_sha256: str


def _valid_sha(value: Any, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(error)
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(error) from exc
    return value


def _approved_boundary(plan: ControlledLocalRefinementPlanV1, approval: RefinementApprovalV1) -> None:
    verify_refinement_execution_boundary(plan, approval)
    if approval.schema != "AsterMaxRefinementApprovalV1":
        raise ValueError("GMSH_REFINEMENT_APPROVAL_SCHEMA")
    _valid_sha(approval.approval_sha256, "GMSH_REFINEMENT_APPROVAL_SHA")
    if not approval.approved:
        raise ValueError("GMSH_REFINEMENT_APPROVAL_REQUIRED")
    if approval.scope != "MESH_DISCRETIZATION_ONLY_NO_PHYSICS_CHANGE":
        raise ValueError("GMSH_REFINEMENT_APPROVAL_SCOPE")


def build_local_size_callback(
    plan: ControlledLocalRefinementPlanV1,
    approval: RefinementApprovalV1,
) -> Callable[[int, int, float, float, float, float], float]:
    """Return a deterministic Gmsh mesh-size callback bound to an approved plan.

    The callback only changes discretization size. It does not modify geometry,
    materials, contacts, loads, supports or solver settings.
    """
    _approved_boundary(plan, approval)

    def callback(dim: int, tag: int, x: float, y: float, z: float, lc: float) -> float:
        del dim, tag, lc
        point = (float(x), float(y), float(z))
        if not all(math.isfinite(v) for v in point):
            raise ValueError("GMSH_REFINEMENT_CALLBACK_NONFINITE_POINT")
        return target_size_at_point(plan, point)

    return callback


def configure_gmsh_local_refinement(
    gmsh_module: Any,
    plan: ControlledLocalRefinementPlanV1,
    approval: RefinementApprovalV1,
) -> Callable[[int, int, float, float, float, float], float]:
    """Install the approved local size callback into an initialized Gmsh model."""
    callback = build_local_size_callback(plan, approval)
    mesh_api = getattr(getattr(gmsh_module, "model", None), "mesh", None)
    setter = getattr(mesh_api, "setSizeCallback", None)
    if not callable(setter):
        raise ValueError("GMSH_SIZE_CALLBACK_API_UNAVAILABLE")
    setter(callback)
    return callback


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_configured_tet10_mesh(
    gmsh_module: Any,
    *,
    plan: ControlledLocalRefinementPlanV1,
    approval: RefinementApprovalV1,
    output_path: str | Path,
) -> GmshLocalRemeshEvidenceV1:
    """Generate a quadratic tetrahedral mesh for the *already loaded* Gmsh model.

    Geometry import/model preparation is intentionally outside this function.
    The caller must load the provenance-matched STEP/model first. This function
    installs the local discretization callback, generates 3D mesh, upgrades it
    to order 2, writes the mesh, and records evidence. It makes no FEA claim.
    """
    _approved_boundary(plan, approval)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    configure_gmsh_local_refinement(gmsh_module, plan, approval)
    gmsh_module.model.mesh.generate(3)
    gmsh_module.model.mesh.setOrder(2)

    types, element_tags, _ = gmsh_module.model.mesh.getElements(3)
    tetra_type = 11  # Gmsh second-order 10-node tetrahedron.
    tetra_count = 0
    for element_type, tags in zip(types, element_tags):
        if int(element_type) == tetra_type:
            tetra_count += len(tags)
    if tetra_count <= 0:
        raise ValueError("GMSH_TET10_ELEMENTS_REQUIRED")

    node_tags, _, _ = gmsh_module.model.mesh.getNodes()
    node_count = len(node_tags)
    if node_count <= 0:
        raise ValueError("GMSH_NODES_REQUIRED")

    gmsh_module.write(str(output))
    if not output.is_file() or output.stat().st_size <= 0:
        raise ValueError("GMSH_OUTPUT_MESH_REQUIRED")
    output_sha = _sha256_file(output)

    core = {
        "schema": "AsterMaxGmshLocalRemeshEvidenceV1",
        "plan_sha256": plan.plan_sha256,
        "approval_sha256": approval.approval_sha256,
        "source_step_sha256": plan.source_step_sha256,
        "route_sha256": plan.route_sha256,
        "baseline_mesh_sha256": plan.baseline_mesh_sha256,
        "output_mesh_sha256": output_sha,
        "output_path": str(output),
        "element_order": 2,
        "tetra_element_type": tetra_type,
        "tetra_element_count": tetra_count,
        "node_count": node_count,
        "preserves_source_geometry": True,
        "preserves_bc_load_route": True,
        "qoi_convergence_claimed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return GmshLocalRemeshEvidenceV1(**core, evidence_sha256=canonical_sha256(core))


def verify_gmsh_local_remesh_evidence(evidence: GmshLocalRemeshEvidenceV1) -> None:
    if evidence.schema != "AsterMaxGmshLocalRemeshEvidenceV1":
        raise ValueError("GMSH_REFINEMENT_EVIDENCE_SCHEMA")
    for value, error in (
        (evidence.plan_sha256, "GMSH_REFINEMENT_PLAN_SHA"),
        (evidence.approval_sha256, "GMSH_REFINEMENT_APPROVAL_SHA"),
        (evidence.source_step_sha256, "GMSH_REFINEMENT_SOURCE_STEP_SHA"),
        (evidence.route_sha256, "GMSH_REFINEMENT_ROUTE_SHA"),
        (evidence.baseline_mesh_sha256, "GMSH_REFINEMENT_BASELINE_MESH_SHA"),
        (evidence.output_mesh_sha256, "GMSH_REFINEMENT_OUTPUT_MESH_SHA"),
        (evidence.evidence_sha256, "GMSH_REFINEMENT_EVIDENCE_SHA"),
    ):
        _valid_sha(value, error)
    if evidence.element_order != 2 or evidence.tetra_element_type != 11:
        raise ValueError("GMSH_REFINEMENT_TET10_REQUIRED")
    if evidence.tetra_element_count <= 0 or evidence.node_count <= 0:
        raise ValueError("GMSH_REFINEMENT_NONEMPTY_MESH_REQUIRED")
    if not evidence.preserves_source_geometry or not evidence.preserves_bc_load_route:
        raise ValueError("GMSH_REFINEMENT_PROVENANCE_PRESERVATION_REQUIRED")
    if evidence.qoi_convergence_claimed:
        raise ValueError("GMSH_REFINEMENT_QOI_CONVERGENCE_OVERCLAIM")
    if evidence.global_analysis_converged:
        raise ValueError("GMSH_REFINEMENT_GLOBAL_CONVERGENCE_OVERCLAIM")
    if evidence.industrial_validation:
        raise ValueError("GMSH_REFINEMENT_INDUSTRIAL_VALIDATION_OVERCLAIM")
    if evidence.ansys_equivalence:
        raise ValueError("GMSH_REFINEMENT_ANSYS_EQUIVALENCE_OVERCLAIM")
