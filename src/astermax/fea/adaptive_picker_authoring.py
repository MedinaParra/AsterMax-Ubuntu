from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from astermax.credibility import canonical_sha256
from .cad_face_picker import CadFacePickerCatalog, build_cad_face_picker_catalog, capture_picker_named_selection
from .evidence import sha256_file
from .face_ownership import Tet10FaceOwnershipInventory, mesh_step_tet10_with_face_ownership
from .pre_solve_review import PreSolveReviewSnapshot
from .tet_quality import build_tet10_corner_quality_snapshot, require_quality_crosscheck


class AdaptivePickerAuthoringError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptivePickerAuthoringEvidenceV1:
    schema: str
    source_step_sha256: str
    ownership_sha256: str
    catalog_sha256: str
    support_picker_evidence_sha256: str
    load_picker_evidence_sha256: str
    support_face_signature_sha256: tuple[str, ...]
    load_face_signature_sha256: tuple[str, ...]
    support_binding_sha256: str
    load_binding_sha256: str
    mesh_target_size_mm: float
    minimum_det_jacobian_mm3: float
    material_young_modulus_mpa: float
    material_poisson_ratio: float
    resultant_n: tuple[float, float, float]
    review_sha256: str
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_sha256: str


def _validate_inputs(mesh_size_mm: float, young_modulus_mpa: float, poisson_ratio: float, resultant_n: tuple[float, float, float]) -> tuple[float, float, float, tuple[float, float, float]]:
    mesh = float(mesh_size_mm)
    young = float(young_modulus_mpa)
    poisson = float(poisson_ratio)
    load = np.asarray(resultant_n, dtype=float)
    if not np.isfinite(mesh) or mesh <= 0.0:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_MESH_SIZE")
    if not np.isfinite(young) or young <= 0.0:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_YOUNG_MODULUS")
    if not np.isfinite(poisson) or not (-1.0 < poisson < 0.5):
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_POISSON_RATIO")
    if load.shape != (3,) or not np.all(np.isfinite(load)) or float(np.linalg.norm(load)) == 0.0:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_RESULTANT")
    return mesh, young, poisson, tuple(float(v) for v in load)


def _minimum_corner_det_jacobian_mm3(inventory: Tet10FaceOwnershipInventory) -> float:
    elements = np.asarray(inventory.elements, dtype=np.int64)
    nodes = np.asarray(inventory.nodes_mm, dtype=float)
    if elements.ndim != 2 or elements.shape[1] != 10 or elements.shape[0] == 0:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_TET10_INVENTORY_INVALID")
    corners = elements[:, :4]
    if np.any(corners < 0) or np.any(corners >= nodes.shape[0]):
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_TET10_CONNECTIVITY_INVALID")
    xyz = nodes[corners]
    edge_matrix = np.stack((xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0], xyz[:, 3] - xyz[:, 0]), axis=1)
    det = np.linalg.det(edge_matrix)
    absolute_det = np.abs(det)
    if not np.all(np.isfinite(absolute_det)) or np.any(absolute_det <= 0.0):
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_NONPOSITIVE_CORNER_JACOBIAN")
    return float(absolute_det.min())


def build_adaptive_picker_catalog(step_path: str | Path, *, mesh_size_mm: float, viewport_width_px: int = 760, viewport_height_px: int = 560) -> tuple[Tet10FaceOwnershipInventory, CadFacePickerCatalog]:
    source = Path(step_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_STEP_REQUIRED")
    mesh = float(mesh_size_mm)
    if not np.isfinite(mesh) or mesh <= 0.0:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_MESH_SIZE")
    inventory = mesh_step_tet10_with_face_ownership(source, mesh)
    catalog = build_cad_face_picker_catalog(
        inventory,
        viewport_width_px=int(viewport_width_px),
        viewport_height_px=int(viewport_height_px),
    )
    if catalog.source_step_sha256 != sha256_file(source) or catalog.ownership_sha256 != inventory.ownership_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_CATALOG_STALE")
    return inventory, catalog


def prepare_adaptive_model_from_picker(
    step_path: str | Path,
    inventory: Tet10FaceOwnershipInventory,
    catalog: CadFacePickerCatalog,
    *,
    support_face_ids: Iterable[str],
    load_face_ids: Iterable[str],
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> tuple[dict[str, Any], AdaptivePickerAuthoringEvidenceV1]:
    """Create the reviewed payload consumed by native adaptive FEA from arbitrary picked CAD faces.

    Persistent FaceSignatures, not axis MIN/MAX aliases, become the actual SUPPORT/LOAD
    named selections used by the baseline and refined solve chain.
    """
    source = Path(step_path).expanduser().resolve()
    mesh, young, poisson, load = _validate_inputs(mesh_size_mm, young_modulus_mpa, poisson_ratio, resultant_n)
    if sha256_file(source) != inventory.source_step_sha256 or catalog.source_step_sha256 != inventory.source_step_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_SOURCE_IDENTITY_MISMATCH")
    if catalog.ownership_sha256 != inventory.ownership_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_OWNERSHIP_STALE")

    support, support_binding, support_triangles, support_pick = capture_picker_named_selection(
        source, inventory, catalog, tuple(support_face_ids), name="Picked Support", role="SUPPORT"
    )
    load_selection, load_binding, load_triangles, load_pick = capture_picker_named_selection(
        source, inventory, catalog, tuple(load_face_ids), name="Picked Load", role="LOAD"
    )
    support_signatures = tuple(support_binding.face_signature_sha256)
    load_signatures = tuple(load_binding.face_signature_sha256)
    if set(support_signatures) & set(load_signatures):
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_SUPPORT_LOAD_OVERLAP")

    quality = build_tet10_corner_quality_snapshot(inventory.nodes_mm, inventory.elements)
    require_quality_crosscheck(quality)
    minimum_det = _minimum_corner_det_jacobian_mm3(inventory)
    preparation_core = {
        "schema": "AsterMaxAdaptivePickerPreparationV1",
        "source_step_sha256": inventory.source_step_sha256,
        "ownership_sha256": inventory.ownership_sha256,
        "catalog_sha256": catalog.catalog_sha256,
        "support_picker_evidence_sha256": support_pick.evidence_sha256,
        "load_picker_evidence_sha256": load_pick.evidence_sha256,
        "tetra_quality_sha256": quality.snapshot_sha256,
        "minimum_det_jacobian_mm3": minimum_det,
    }
    preparation_sha = canonical_sha256(preparation_core)
    review_core = {
        "schema": "AsterMaxPreSolveReviewV3",
        "step_sha256": inventory.source_step_sha256,
        "preparation_sha256": preparation_sha,
        "visual_preparation_sha256": catalog.catalog_sha256,
        "constraint_selection_sha256": support.named_selection_sha256,
        "load_selection_sha256": load_selection.named_selection_sha256,
        "support_named_selection_sha256": support.named_selection_sha256,
        "load_named_selection_sha256": load_selection.named_selection_sha256,
        "support_binding_sha256": support_binding.binding_sha256,
        "load_binding_sha256": load_binding.binding_sha256,
        "support_surface_keys": tuple(f"FACE:{sha}" for sha in support_signatures),
        "load_surface_keys": tuple(f"FACE:{sha}" for sha in load_signatures),
        "mesh_target_size_mm": mesh,
        "node_count": int(inventory.nodes_mm.shape[0]),
        "tet10_count": int(inventory.elements.shape[0]),
        "minimum_det_jacobian_mm3": minimum_det,
        "edge_ratio_minimum": float(quality.minimum),
        "tetra_mean_ratio_minimum": float(quality.minimum),
        "tetra_mean_ratio_p10": float(quality.percentile_10),
        "tetra_mean_ratio_median": float(quality.median),
        "tetra_quality_sha256": quality.snapshot_sha256,
        "tetra_quality_crosscheck_verified": bool(quality.crosscheck_verified),
        "material_young_modulus_mpa": young,
        "material_poisson_ratio": poisson,
        "resultant_n": load,
        "state": "REVIEW_REQUIRED",
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    review = PreSolveReviewSnapshot(**review_core, review_sha256=canonical_sha256(review_core))
    prepared = {
        "source": source,
        "mesh": inventory,
        "quality": quality,
        "support_selection": support,
        "load_named_selection": load_selection,
        "support_binding": support_binding,
        "load_binding": load_binding,
        "support_triangles": np.asarray(support_triangles, dtype=np.int64),
        "load_triangles": np.asarray(load_triangles, dtype=np.int64),
        "review": review,
        "picker_catalog": catalog,
        "support_picker_evidence": support_pick,
        "load_picker_evidence": load_pick,
    }
    core = {
        "schema": "AsterMaxAdaptivePickerAuthoringEvidenceV1",
        "source_step_sha256": inventory.source_step_sha256,
        "ownership_sha256": inventory.ownership_sha256,
        "catalog_sha256": catalog.catalog_sha256,
        "support_picker_evidence_sha256": support_pick.evidence_sha256,
        "load_picker_evidence_sha256": load_pick.evidence_sha256,
        "support_face_signature_sha256": support_signatures,
        "load_face_signature_sha256": load_signatures,
        "support_binding_sha256": support_binding.binding_sha256,
        "load_binding_sha256": load_binding.binding_sha256,
        "mesh_target_size_mm": mesh,
        "minimum_det_jacobian_mm3": minimum_det,
        "material_young_modulus_mpa": young,
        "material_poisson_ratio": poisson,
        "resultant_n": load,
        "review_sha256": review.review_sha256,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return prepared, AdaptivePickerAuthoringEvidenceV1(**core, evidence_sha256=canonical_sha256(core))


def verify_adaptive_picker_authoring(prepared: dict[str, Any], evidence: AdaptivePickerAuthoringEvidenceV1) -> None:
    if evidence.schema != "AsterMaxAdaptivePickerAuthoringEvidenceV1":
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_EVIDENCE_SCHEMA")
    if evidence.global_analysis_converged or evidence.industrial_validation or evidence.ansys_equivalence:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_EVIDENCE_OVERCLAIM")
    review = prepared.get("review")
    support_binding = prepared.get("support_binding")
    load_binding = prepared.get("load_binding")
    catalog = prepared.get("picker_catalog")
    if not isinstance(review, PreSolveReviewSnapshot):
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_REVIEW_MISSING")
    if review.review_sha256 != evidence.review_sha256 or review.minimum_det_jacobian_mm3 != evidence.minimum_det_jacobian_mm3:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_REVIEW_STALE")
    if support_binding.binding_sha256 != evidence.support_binding_sha256 or load_binding.binding_sha256 != evidence.load_binding_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_BINDING_STALE")
    if tuple(support_binding.face_signature_sha256) != evidence.support_face_signature_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_SUPPORT_SIGNATURE_STALE")
    if tuple(load_binding.face_signature_sha256) != evidence.load_face_signature_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_LOAD_SIGNATURE_STALE")
    if catalog.catalog_sha256 != evidence.catalog_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_CATALOG_STALE")
    core = evidence.__dict__.copy(); core.pop("evidence_sha256")
    if canonical_sha256(core) != evidence.evidence_sha256:
        raise AdaptivePickerAuthoringError("ADAPTIVE_PICKER_EVIDENCE_TAMPERED")
