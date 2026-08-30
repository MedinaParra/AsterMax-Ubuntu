from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .face_ownership import Tet10FaceOwnershipInventory
from .gmsh_local_refinement import GmshLocalRemeshEvidenceV1, verify_gmsh_local_remesh_evidence


class AdaptiveMeshProvenanceError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptiveMeshProvenanceBridgeV1:
    schema: str
    local_remesh_evidence_sha256: str
    source_step_sha256: str
    route_sha256: str
    baseline_mesh_sha256: str
    output_mesh_file_sha256: str
    ownership_sha256: str
    node_count: int
    tet10_count: int
    exact_output_file_verified: bool
    source_identity_verified: bool
    ready_for_second_solve: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    bridge_sha256: str


def build_adaptive_mesh_provenance_bridge(
    *,
    local_remesh: GmshLocalRemeshEvidenceV1,
    output_mesh_path: str | Path,
    inventory: Tet10FaceOwnershipInventory,
) -> AdaptiveMeshProvenanceBridgeV1:
    """Bind an ownership inventory to the exact approved Gmsh mesh artifact.

    The inventory builder may evolve independently, so this bridge deliberately
    requires the caller to prove the consumed `.msh` bytes are exactly the bytes
    emitted by the approved local-remesh action. It does not infer provenance
    from counts, filenames or mesh statistics.
    """
    verify_gmsh_local_remesh_evidence(local_remesh)
    path = Path(output_mesh_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_OUTPUT_REQUIRED")
    actual_mesh_sha = sha256_file(path)
    if actual_mesh_sha != local_remesh.output_mesh_sha256:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_OUTPUT_SHA_MISMATCH")
    if inventory.source_step_sha256 != local_remesh.source_step_sha256:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_SOURCE_STEP_MISMATCH")
    if inventory.ownership_sha256 == local_remesh.baseline_mesh_sha256:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_REFINEMENT_NOT_DISTINCT")
    node_count = int(inventory.nodes_mm.shape[0])
    tet10_count = int(inventory.elements.shape[0])
    if node_count <= 0 or tet10_count <= 0:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_INVENTORY_EMPTY")
    if inventory.elements.ndim != 2 or inventory.elements.shape[1] != 10:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_TET10_REQUIRED")

    core = {
        "schema": "AsterMaxAdaptiveMeshProvenanceBridgeV1",
        "local_remesh_evidence_sha256": local_remesh.evidence_sha256,
        "source_step_sha256": local_remesh.source_step_sha256,
        "route_sha256": local_remesh.route_sha256,
        "baseline_mesh_sha256": local_remesh.baseline_mesh_sha256,
        "output_mesh_file_sha256": actual_mesh_sha,
        "ownership_sha256": inventory.ownership_sha256,
        "node_count": node_count,
        "tet10_count": tet10_count,
        "exact_output_file_verified": True,
        "source_identity_verified": True,
        "ready_for_second_solve": True,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return AdaptiveMeshProvenanceBridgeV1(**core, bridge_sha256=canonical_sha256(core))


def verify_adaptive_mesh_provenance_bridge(evidence: AdaptiveMeshProvenanceBridgeV1) -> None:
    if evidence.schema != "AsterMaxAdaptiveMeshProvenanceBridgeV1":
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_BRIDGE_SCHEMA")
    if not evidence.exact_output_file_verified or not evidence.source_identity_verified:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_BRIDGE_IDENTITY_REQUIRED")
    if not evidence.ready_for_second_solve:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_SECOND_SOLVE_NOT_READY")
    if evidence.node_count <= 0 or evidence.tet10_count <= 0:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_BRIDGE_EMPTY")
    if evidence.global_analysis_converged:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_GLOBAL_CONVERGENCE_OVERCLAIM")
    if evidence.industrial_validation or evidence.ansys_equivalence:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_VALIDATION_OVERCLAIM")
    core = evidence.__dict__.copy()
    core.pop("bridge_sha256")
    if canonical_sha256(core) != evidence.bridge_sha256:
        raise AdaptiveMeshProvenanceError("ADAPTIVE_MESH_BRIDGE_TAMPERED")
