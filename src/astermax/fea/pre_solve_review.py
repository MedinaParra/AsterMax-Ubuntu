from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .gmsh_bridge import mesh_step_tet10
from .live_analysis_evidence import file_sha256
from .model_preparation_evidence import build_model_preparation_evidence
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
    mesh_target_size_mm: float
    node_count: int
    tet10_count: int
    minimum_det_jacobian_mm3: float
    edge_ratio_minimum: float
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


def _validated_analysis_inputs(
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> tuple[float, float, float, np.ndarray]:
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
) -> dict[str, Any]:
    source = Path(step_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"STEP file not found: {source}")
    if source.suffix.lower() not in {".step", ".stp"}:
        raise PreSolveReviewError("source geometry must be a .step or .stp file")
    mesh_size, young, poisson, load = _validated_analysis_inputs(
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    step_sha = file_sha256(source)
    mesh = mesh_step_tet10(source, mesh_size)
    preparation = build_model_preparation_evidence(
        source,
        step_sha256=step_sha,
        bbox_mm=mesh.bbox_mm,
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
    )
    visual = build_visual_model_preparation_snapshot(
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        surface_triangles=mesh.surface_triangles,
        preparation=asdict(preparation),
    )
    core = {
        "schema": "AsterMaxPreSolveReviewV1",
        "step_sha256": step_sha,
        "preparation_sha256": preparation.snapshot_sha256,
        "visual_preparation_sha256": visual.snapshot_sha256,
        "constraint_selection_sha256": preparation.constraint_selection_sha256,
        "load_selection_sha256": preparation.load_selection_sha256,
        "mesh_target_size_mm": mesh_size,
        "node_count": int(mesh.nodes_mm.shape[0]),
        "tet10_count": int(mesh.elements.shape[0]),
        "minimum_det_jacobian_mm3": float(preparation.mesh_gate.minimum_det_jacobian_mm3),
        "edge_ratio_minimum": float(visual.edge_ratio_minimum),
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
        "review": review,
    }


def accept_model_preparation(review: PreSolveReviewSnapshot) -> ModelPreparationAcceptance:
    if review.schema != "AsterMaxPreSolveReviewV1" or review.state != "REVIEW_REQUIRED":
        raise PreSolveReviewError("MODEL_PREPARATION_REVIEW_NOT_ACCEPTABLE")
    if review.converged or review.industrial_validation or review.ansys_equivalence:
        raise PreSolveReviewError("MODEL_PREPARATION_REVIEW_ILLEGAL_CLAIM")
    core = {
        "schema": "AsterMaxModelPreparationAcceptanceV1",
        "review_sha256": review.review_sha256,
        "state": "MODEL_PREPARATION_ACCEPTED",
    }
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
    expected = canonical_sha256({
        "schema": acceptance.schema,
        "review_sha256": acceptance.review_sha256,
        "state": acceptance.state,
    })
    if acceptance.acceptance_sha256 != expected:
        raise PreSolveReviewError("MODEL_PREPARATION_ACCEPTANCE_TAMPERED")


def visual_preparation_payload(prepared: dict[str, Any]) -> dict[str, Any]:
    mesh = prepared["mesh"]
    preparation = prepared["preparation"]
    return {
        "nodes_mm": mesh.nodes_mm,
        "elements": mesh.elements,
        "surface_triangles": mesh.surface_triangles,
        "preparation": asdict(preparation),
    }
