from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .face_ownership import (
    ArbitraryNamedSelectionBinding,
    Tet10FaceOwnershipInventory,
    bind_named_selection_to_owned_faces,
)
from .named_selections import PersistentNamedSelection


class RemeshFaceRebindingError(ValueError):
    pass


@dataclass(frozen=True)
class RemeshNamedSelectionRebindingV1:
    schema: str
    name: str
    role: str
    source_step_sha256: str
    named_selection_sha256: str
    baseline_ownership_sha256: str
    remesh_ownership_sha256: str
    face_signature_sha256: tuple[str, ...]
    baseline_tri6_count: int
    remesh_tri6_count: int
    same_geometric_identity: bool
    same_physics_role: bool
    rebinding_sha256: str


@dataclass(frozen=True)
class RemeshBoundaryRouteEvidenceV1:
    schema: str
    source_step_sha256: str
    baseline_ownership_sha256: str
    remesh_ownership_sha256: str
    support_rebinding_sha256: str
    load_rebinding_sha256: str
    support_signatures: tuple[str, ...]
    load_signatures: tuple[str, ...]
    ready_for_second_solve: bool
    qoi_convergence_claimed: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_sha256: str


def _validate_inventory_pair(
    step_path: str | Path,
    baseline: Tet10FaceOwnershipInventory,
    remesh: Tet10FaceOwnershipInventory,
) -> str:
    path = Path(step_path)
    if not path.is_file():
        raise RemeshFaceRebindingError("REBIND_STEP_REQUIRED")
    source_sha = sha256_file(path)
    if baseline.schema != "AsterMaxTet10FaceOwnershipInventoryV1" or remesh.schema != baseline.schema:
        raise RemeshFaceRebindingError("REBIND_OWNERSHIP_SCHEMA")
    if baseline.source_step_sha256 != source_sha or remesh.source_step_sha256 != source_sha:
        raise RemeshFaceRebindingError("REBIND_SOURCE_IDENTITY_MISMATCH")
    if baseline.ownership_sha256 == remesh.ownership_sha256:
        raise RemeshFaceRebindingError("REBIND_DISTINCT_MESH_REQUIRED")
    return source_sha


def rebind_named_selection_after_remesh(
    step_path: str | Path,
    selection: PersistentNamedSelection,
    baseline: Tet10FaceOwnershipInventory,
    remesh: Tet10FaceOwnershipInventory,
) -> tuple[RemeshNamedSelectionRebindingV1, ArbitraryNamedSelectionBinding, np.ndarray]:
    source_sha = _validate_inventory_pair(step_path, baseline, remesh)
    if selection.source_sha256 != source_sha:
        raise RemeshFaceRebindingError("REBIND_SELECTION_SOURCE_MISMATCH")
    expected = tuple(face.signature_sha256 for face in selection.faces)
    baseline_binding, baseline_triangles = bind_named_selection_to_owned_faces(
        step_path, selection, baseline, expected_role=selection.role
    )
    remesh_binding, remesh_triangles = bind_named_selection_to_owned_faces(
        step_path, selection, remesh, expected_role=selection.role
    )
    if baseline_binding.face_signature_sha256 != expected or remesh_binding.face_signature_sha256 != expected:
        raise RemeshFaceRebindingError("REBIND_GEOMETRIC_IDENTITY_MISMATCH")
    if baseline_triangles.shape[0] <= 0 or remesh_triangles.shape[0] <= 0:
        raise RemeshFaceRebindingError("REBIND_TRI6_REQUIRED")
    core = {
        "schema": "AsterMaxRemeshNamedSelectionRebindingV1",
        "name": selection.name,
        "role": selection.role,
        "source_step_sha256": source_sha,
        "named_selection_sha256": selection.named_selection_sha256,
        "baseline_ownership_sha256": baseline.ownership_sha256,
        "remesh_ownership_sha256": remesh.ownership_sha256,
        "face_signature_sha256": list(expected),
        "baseline_tri6_count": int(baseline_triangles.shape[0]),
        "remesh_tri6_count": int(remesh_triangles.shape[0]),
        "same_geometric_identity": True,
        "same_physics_role": True,
    }
    evidence = RemeshNamedSelectionRebindingV1(
        schema=core["schema"], name=selection.name, role=selection.role,
        source_step_sha256=source_sha, named_selection_sha256=selection.named_selection_sha256,
        baseline_ownership_sha256=baseline.ownership_sha256, remesh_ownership_sha256=remesh.ownership_sha256,
        face_signature_sha256=expected, baseline_tri6_count=int(baseline_triangles.shape[0]),
        remesh_tri6_count=int(remesh_triangles.shape[0]), same_geometric_identity=True,
        same_physics_role=True, rebinding_sha256=canonical_sha256(core),
    )
    return evidence, remesh_binding, np.asarray(remesh_triangles, dtype=np.int64)


def build_remesh_boundary_route_evidence(
    step_path: str | Path,
    baseline: Tet10FaceOwnershipInventory,
    remesh: Tet10FaceOwnershipInventory,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
) -> RemeshBoundaryRouteEvidenceV1:
    source_sha = _validate_inventory_pair(step_path, baseline, remesh)
    if support.role != "SUPPORT" or load.role != "LOAD":
        raise RemeshFaceRebindingError("REBIND_SUPPORT_LOAD_ROLES_REQUIRED")
    support_ev, _, _ = rebind_named_selection_after_remesh(step_path, support, baseline, remesh)
    load_ev, _, _ = rebind_named_selection_after_remesh(step_path, load, baseline, remesh)
    if set(support_ev.face_signature_sha256) & set(load_ev.face_signature_sha256):
        raise RemeshFaceRebindingError("REBIND_SUPPORT_LOAD_OVERLAP")
    core = {
        "schema": "AsterMaxRemeshBoundaryRouteEvidenceV1",
        "source_step_sha256": source_sha,
        "baseline_ownership_sha256": baseline.ownership_sha256,
        "remesh_ownership_sha256": remesh.ownership_sha256,
        "support_rebinding_sha256": support_ev.rebinding_sha256,
        "load_rebinding_sha256": load_ev.rebinding_sha256,
        "support_signatures": list(support_ev.face_signature_sha256),
        "load_signatures": list(load_ev.face_signature_sha256),
        "ready_for_second_solve": True,
        "qoi_convergence_claimed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return RemeshBoundaryRouteEvidenceV1(
        schema=core["schema"], source_step_sha256=source_sha,
        baseline_ownership_sha256=baseline.ownership_sha256, remesh_ownership_sha256=remesh.ownership_sha256,
        support_rebinding_sha256=support_ev.rebinding_sha256, load_rebinding_sha256=load_ev.rebinding_sha256,
        support_signatures=support_ev.face_signature_sha256, load_signatures=load_ev.face_signature_sha256,
        ready_for_second_solve=True, qoi_convergence_claimed=False, global_analysis_converged=False,
        industrial_validation=False, ansys_equivalence=False, evidence_sha256=canonical_sha256(core),
    )


def verify_remesh_boundary_route_evidence(evidence: RemeshBoundaryRouteEvidenceV1) -> None:
    if evidence.schema != "AsterMaxRemeshBoundaryRouteEvidenceV1":
        raise RemeshFaceRebindingError("REBIND_ROUTE_SCHEMA")
    if evidence.baseline_ownership_sha256 == evidence.remesh_ownership_sha256:
        raise RemeshFaceRebindingError("REBIND_ROUTE_DISTINCT_MESH_REQUIRED")
    if not evidence.ready_for_second_solve:
        raise RemeshFaceRebindingError("REBIND_ROUTE_NOT_READY")
    if not evidence.support_signatures or not evidence.load_signatures:
        raise RemeshFaceRebindingError("REBIND_ROUTE_SELECTIONS_REQUIRED")
    if set(evidence.support_signatures) & set(evidence.load_signatures):
        raise RemeshFaceRebindingError("REBIND_ROUTE_SUPPORT_LOAD_OVERLAP")
    if evidence.qoi_convergence_claimed or evidence.global_analysis_converged:
        raise RemeshFaceRebindingError("REBIND_ROUTE_CONVERGENCE_OVERCLAIM")
    if evidence.industrial_validation or evidence.ansys_equivalence:
        raise RemeshFaceRebindingError("REBIND_ROUTE_VALIDATION_OVERCLAIM")
    core = asdict(evidence); core.pop("evidence_sha256")
    if canonical_sha256(core) != evidence.evidence_sha256:
        raise RemeshFaceRebindingError("REBIND_ROUTE_EVIDENCE_TAMPERED")
