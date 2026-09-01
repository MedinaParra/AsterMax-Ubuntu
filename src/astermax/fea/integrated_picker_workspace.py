from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astermax.credibility import canonical_sha256
from .adaptive_picker_authoring import (
    AdaptivePickerAuthoringEvidenceV1,
    build_adaptive_picker_catalog,
    prepare_adaptive_model_from_picker,
    verify_adaptive_picker_authoring,
)
from .cad_face_picker import CadFacePickerCatalog
from .evidence import sha256_file
from .face_ownership import Tet10FaceOwnershipInventory
from .native_cad_picker_ui import NativeCadPickerAssignment


class IntegratedPickerWorkspaceError(ValueError):
    pass


@dataclass(frozen=True)
class IntegratedPickerInputSnapshotV1:
    schema: str
    source_step_sha256: str
    mesh_size_mm: float
    young_modulus_mpa: float
    poisson_ratio: float
    resultant_n: tuple[float, float, float]
    snapshot_sha256: str


@dataclass(frozen=True)
class IntegratedPickerPreparedV1:
    schema: str
    snapshot_sha256: str
    ownership_sha256: str
    catalog_sha256: str
    support_face_ids: tuple[str, ...]
    load_face_ids: tuple[str, ...]
    authoring_evidence_sha256: str
    prepared: dict[str, Any]
    evidence: AdaptivePickerAuthoringEvidenceV1


def capture_integrated_picker_input_snapshot(
    step_path: str | Path,
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> IntegratedPickerInputSnapshotV1:
    source = Path(step_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_STEP_REQUIRED")
    mesh = float(mesh_size_mm)
    young = float(young_modulus_mpa)
    poisson = float(poisson_ratio)
    load = tuple(float(v) for v in resultant_n)
    if mesh <= 0.0 or young <= 0.0 or not (-1.0 < poisson < 0.5) or len(load) != 3:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_INPUTS_INVALID")
    core = {
        "schema": "AsterMaxIntegratedPickerInputSnapshotV1",
        "source_step_sha256": sha256_file(source),
        "mesh_size_mm": mesh,
        "young_modulus_mpa": young,
        "poisson_ratio": poisson,
        "resultant_n": load,
    }
    return IntegratedPickerInputSnapshotV1(**core, snapshot_sha256=canonical_sha256(core))


def verify_integrated_picker_snapshot(
    snapshot: IntegratedPickerInputSnapshotV1,
    step_path: str | Path,
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> None:
    core = snapshot.__dict__.copy(); core.pop("snapshot_sha256")
    if snapshot.schema != "AsterMaxIntegratedPickerInputSnapshotV1" or canonical_sha256(core) != snapshot.snapshot_sha256:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_SNAPSHOT_TAMPERED")
    current = capture_integrated_picker_input_snapshot(
        step_path,
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    if current.snapshot_sha256 != snapshot.snapshot_sha256:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_CONTEXT_STALE")


def build_integrated_picker_catalog(
    step_path: str | Path,
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
    viewport_width_px: int = 760,
    viewport_height_px: int = 560,
) -> tuple[IntegratedPickerInputSnapshotV1, Tet10FaceOwnershipInventory, CadFacePickerCatalog]:
    snapshot = capture_integrated_picker_input_snapshot(
        step_path,
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    inventory, catalog = build_adaptive_picker_catalog(
        step_path,
        mesh_size_mm=mesh_size_mm,
        viewport_width_px=viewport_width_px,
        viewport_height_px=viewport_height_px,
    )
    if inventory.source_step_sha256 != snapshot.source_step_sha256 or catalog.source_step_sha256 != snapshot.source_step_sha256:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_CATALOG_SOURCE_STALE")
    return snapshot, inventory, catalog


def commit_integrated_picker_assignment(
    step_path: str | Path,
    snapshot: IntegratedPickerInputSnapshotV1,
    inventory: Tet10FaceOwnershipInventory,
    catalog: CadFacePickerCatalog,
    assignment: NativeCadPickerAssignment,
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> IntegratedPickerPreparedV1:
    verify_integrated_picker_snapshot(
        snapshot,
        step_path,
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    if assignment.schema != "AsterMaxNativeCadPickerAssignmentV1":
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_ASSIGNMENT_SCHEMA")
    if inventory.source_step_sha256 != snapshot.source_step_sha256 or catalog.source_step_sha256 != snapshot.source_step_sha256:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_OWNERSHIP_SOURCE_STALE")
    if assignment.support_binding.ownership_sha256 != inventory.ownership_sha256 or assignment.load_binding.ownership_sha256 != inventory.ownership_sha256:
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_ASSIGNMENT_OWNERSHIP_STALE")
    if set(assignment.support_face_ids) & set(assignment.load_face_ids):
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_SUPPORT_LOAD_OVERLAP")

    prepared, evidence = prepare_adaptive_model_from_picker(
        step_path,
        inventory,
        catalog,
        support_face_ids=assignment.support_face_ids,
        load_face_ids=assignment.load_face_ids,
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    verify_adaptive_picker_authoring(prepared, evidence)

    # C6.1 continuity contract: the UI assignment and adaptive authoring may
    # intentionally use different human-readable selection labels. A binding
    # hash includes those authoring labels, so hash equality is too strict for
    # geometric identity. Continuity is instead proven by the immutable mesh
    # ownership identity plus the ordered persistent CAD face signatures.
    support_assignment_signatures = tuple(assignment.support_binding.face_signature_sha256)
    load_assignment_signatures = tuple(assignment.load_binding.face_signature_sha256)
    if support_assignment_signatures != tuple(evidence.support_face_signature_sha256):
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_SUPPORT_REBIND_MISMATCH")
    if load_assignment_signatures != tuple(evidence.load_face_signature_sha256):
        raise IntegratedPickerWorkspaceError("INTEGRATED_PICKER_LOAD_REBIND_MISMATCH")

    return IntegratedPickerPreparedV1(
        schema="AsterMaxIntegratedPickerPreparedV1",
        snapshot_sha256=snapshot.snapshot_sha256,
        ownership_sha256=inventory.ownership_sha256,
        catalog_sha256=catalog.catalog_sha256,
        support_face_ids=tuple(assignment.support_face_ids),
        load_face_ids=tuple(assignment.load_face_ids),
        authoring_evidence_sha256=evidence.evidence_sha256,
        prepared=prepared,
        evidence=evidence,
    )
