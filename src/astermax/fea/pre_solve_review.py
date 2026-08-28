from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .gmsh_bridge import mesh_step_tet10
from .live_analysis_evidence import file_sha256
from .model_preparation_evidence import build_model_preparation_evidence
from .named_selection_bc import bind_named_selection_to_mesh, capture_axis_named_selection
from .tet_quality import build_tet10_corner_quality_snapshot, require_quality_crosscheck
from .visual_model_preparation import build_visual_model_preparation_snapshot


class PreSolveReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PreSolveReviewSnapshot:
    schema: str
    step_sha256: str
    preparation_sha256: str
    visual_preparation_sha256: str
    constraint_selection_sha256: str
    load_selection_sha256: str
    support_named_selection_sha256: str
    load_named_selection_sha256: str
    support_binding_sha256: str
    load_binding_sha256: str
    support_surface_keys: tuple[str, ...]
    load_surface_keys: tuple[str, ...]
    mesh_target_size_mm: float
    node_count: int
    tet10_count: int
    minimum_det_jacobian_mm3: float
    edge_ratio_minimum: float
    tetra_mean_ratio_minimum: float
    tetra_mean_ratio_p10: float
    tetra_mean_ratio_median: float
    tetra_quality_sha256: str
    tetra_quality_crosscheck_verified: bool
    material_young_modulus_mpa: float
    material_poisson_ratio: float
    resultant_n: tuple[float, float, float]
    state: str
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    review_sha256: str


@dataclass(frozen=True)
class ModelPreparationAcceptance:
    schema: str
    review_sha256: str
    state: str
    acceptance_sha256: str


def _validated_analysis_inputs(*, mesh_size_mm: float, young_modulus_mpa: float, poisson_ratio: float, resultant_n: tuple[float, float, float]) -> tuple[float, float, float, np.ndarray]:
    mesh_size = float(mesh_size_mm)
    young = float(young_modulus_mpa)
    poisson = float(poisson_ratio)
    load = np.asarray(resultant_n, dtype=float)
    if not np.isfinite(mesh_size) or mesh_size <= 0.0:
        raise PreSolveReviewError("mesh_size_mm must be finite and positive")
    if not np.isfinite(young) or young <= 0.0:
        raise PreSolveReviewError("young_modulus_mpa must be finite and positive")
    if not np.isfinite(poisson) or not (-1.0 < poisson < 0.5):
        raise PreSolveReviewError("poisson_ratio must satisfy -1 < nu < 0.5")
    if load.shape != (3,) or not np.all(np.isfinite(load)) or float(np.linalg.norm(load)) == 0.0:
        raise PreSolveReviewError("resultant_n must contain three finite components and be non-zero")
    return mesh_size, young, poisson, load


def prepare_model_for_review(
    step_path: str | Path,
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
    support_surface_keys: tuple[str, ...] = ("X_MIN",),
    load_surface_keys: tuple[str, ...] = ("X_MAX",),
) -> dict[str, Any]:
    source = Path(step_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"STEP file not found: {source}")
    if source.suffix.lower() not in {".step", ".stp"}:
        raise PreSolveReviewError("source geometry must be a .step or .stp file")
    mesh_size, young, poisson, load = _validated_analysis_inputs(mesh_size_mm=mesh_size_mm, young_modulus_mpa=young_modulus_mpa, poisson_ratio=poisson_ratio, resultant_n=resultant_n)
    step_sha = file_sha256(source)
    mesh = mesh_step_tet10(source, mesh_size)
    preparation = build_model_preparation_evidence(source, step_sha256=step_sha, bbox_mm=mesh.bbox_mm, nodes_mm=mesh.nodes_mm, elements=mesh.elements)
    visual = build_visual_model_preparation_snapshot(nodes_mm=mesh.nodes_mm, elements=mesh.elements, surface_triangles=mesh.surface_triangles, preparation=asdict(preparation))
    quality = build_tet10_corner_quality_snapshot(mesh.nodes_mm, mesh.elements)
    require_quality_crosscheck(quality)

    support_selection = capture_axis_named_selection(source, mesh.bbox_mm, support_surface_keys, name="Support", role="SUPPORT")
    load_selection = capture_axis_named_selection(source, mesh.bbox_mm, load_surface_keys, name="Load", role="LOAD")
    if support_selection.named_selection_sha256 == load_selection.named_selection_sha256:
        raise PreSolveReviewError("support and load named selections must be distinct")
    support_binding, support_triangles = bind_named_selection_to_mesh(
        source,
        support_selection,
        bbox_mm=mesh.bbox_mm,
        surface_triangles=mesh.surface_triangles,
        expected_role="SUPPORT",
    )
    load_binding, load_triangles = bind_named_selection_to_mesh(
        source,
        load_selection,
        bbox_mm=mesh.bbox_mm,
        surface_triangles=mesh.surface_triangles,
        expected_role="LOAD",
    )
    if set(support_binding.surface_keys) & set(load_binding.surface_keys):
        raise PreSolveReviewError("support and load named selections overlap")

    core = {
        "schema": "AsterMaxPreSolveReviewV3",
        "step_sha256": step_sha,
        "preparation_sha256": preparation.snapshot_sha256,
        "visual_preparation_sha256": visual.snapshot_sha256,
        "constraint_selection_sha256": preparation.constraint_selection_sha256,
        "load_selection_sha256": preparation.load_selection_sha256,
        "support_named_selection_sha256": support_selection.named_selection_sha256,
        "load_named_selection_sha256": load_selection.named_selection_sha256,
        "support_binding_sha256": support_binding.binding_sha256,
        "load_binding_sha256": load_binding.binding_sha256,
        "support_surface_keys": support_binding.surface_keys,
        "load_surface_keys": load_binding.surface_keys,
        "mesh_target_size_mm": mesh_size,
        "node_count": int(mesh.nodes_mm.shape[0]),
        "tet10_count": int(mesh.elements.shape[0]),
        "minimum_det_jacobian_mm3": float(preparation.mesh_gate["minimum_det_jacobian_mm3"]),
        "edge_ratio_minimum": float(visual.edge_ratio_minimum),
        "tetra_mean_ratio_minimum": quality.minimum,
        "tetra_mean_ratio_p10": quality.percentile_10,
        "tetra_mean_ratio_median": quality.median,
        "tetra_quality_sha256": quality.snapshot_sha256,
        "tetra_quality_crosscheck_verified": quality.crosscheck_verified,
        "material_young_modulus_mpa": young,
        "material_poisson_ratio": poisson,
        "resultant_n": tuple(float(v) for v in load),
        "state": "REVIEW_REQUIRED",
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    review = PreSolveReviewSnapshot(**core, review_sha256=canonical_sha256(core))
    return {
        "source": source,
        "mesh": mesh,
        "preparation": preparation,
        "visual": visual,
        "quality": quality,
        "support_selection": support_selection,
        "load_named_selection": load_selection,
        "support_binding": support_binding,
        "load_binding": load_binding,
        "support_triangles": support_triangles,
        "load_triangles": load_triangles,
        "review": review,
    }


def accept_model_preparation(review: PreSolveReviewSnapshot) -> ModelPreparationAcceptance:
    if review.schema != "AsterMaxPreSolveReviewV3" or review.state != "REVIEW_REQUIRED":
        raise PreSolveReviewError("MODEL_PREPARATION_REVIEW_NOT_ACCEPTABLE")
    if not review.tetra_quality_crosscheck_verified or review.tetra_mean_ratio_minimum <= 0.0:
        raise PreSolveReviewError("MODEL_PREPARATION_TETRA_QUALITY_NOT_VERIFIED")
    if review.support_named_selection_sha256 == review.load_named_selection_sha256:
        raise PreSolveReviewError("MODEL_PREPARATION_NAMED_SELECTIONS_NOT_DISTINCT")
    if set(review.support_surface_keys) & set(review.load_surface_keys):
        raise PreSolveReviewError("MODEL_PREPARATION_NAMED_SELECTIONS_OVERLAP")
    if review.converged or review.industrial_validation or review.ansys_equivalence:
        raise PreSolveReviewError("MODEL_PREPARATION_REVIEW_ILLEGAL_CLAIM")
    core = {"schema": "AsterMaxModelPreparationAcceptanceV1", "review_sha256": review.review_sha256, "state": "MODEL_PREPARATION_ACCEPTED"}
    return ModelPreparationAcceptance(**core, acceptance_sha256=canonical_sha256(core))


def verify_acceptance(prepared: dict[str, Any], acceptance: ModelPreparationAcceptance) -> None:
    review = prepared.get("review")
    source = prepared.get("source")
    if not isinstance(review, PreSolveReviewSnapshot) or not isinstance(source, Path):
        raise PreSolveReviewError("prepared model payload is incomplete")
    if acceptance.schema != "AsterMaxModelPreparationAcceptanceV1" or acceptance.state != "MODEL_PREPARATION_ACCEPTED":
        raise PreSolveReviewError("MODEL_PREPARATION_NOT_ACCEPTED")
    if acceptance.review_sha256 != review.review_sha256:
        raise PreSolveReviewError("MODEL_PREPARATION_ACCEPTANCE_STALE")
    if file_sha256(source) != review.step_sha256:
        raise PreSolveReviewError("STEP_CHANGED_AFTER_MODEL_PREPARATION_REVIEW")
    support_binding = prepared.get("support_binding")
    load_binding = prepared.get("load_binding")
    if support_binding is None or load_binding is None:
        raise PreSolveReviewError("MODEL_PREPARATION_NAMED_SELECTION_BINDING_MISSING")
    if support_binding.binding_sha256 != review.support_binding_sha256 or load_binding.binding_sha256 != review.load_binding_sha256:
        raise PreSolveReviewError("MODEL_PREPARATION_NAMED_SELECTION_BINDING_STALE")
    expected = canonical_sha256({"schema": acceptance.schema, "review_sha256": acceptance.review_sha256, "state": acceptance.state})
    if acceptance.acceptance_sha256 != expected:
        raise PreSolveReviewError("MODEL_PREPARATION_ACCEPTANCE_TAMPERED")


def visual_preparation_payload(prepared: dict[str, Any]) -> dict[str, Any]:
    mesh = prepared["mesh"]
    preparation = prepared["preparation"]
    quality = prepared["quality"]
    return {
        "nodes_mm": mesh.nodes_mm,
        "elements": mesh.elements,
        "surface_triangles": mesh.surface_triangles,
        "preparation": asdict(preparation),
        "tetra_quality": asdict(quality),
        "named_selections": {
            "support": asdict(prepared["support_binding"]),
            "load": asdict(prepared["load_binding"]),
        },
    }
