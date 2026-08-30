from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from .arbitrary_bc import ArbitraryBcPreparation, solve_arbitrary_bc_model
from .face_ownership import Tet10FaceOwnershipInventory, bind_named_selection_to_owned_faces
from .named_selections import PersistentNamedSelection
from .qoi_convergence import (
    QoiConvergenceAssessmentV1,
    QoiConvergenceCriteriaV1,
    QoiObservationV1,
    assess_qoi_convergence,
    make_qoi_observation,
    verify_qoi_convergence_boundary,
)
from .remesh_face_rebinding import (
    RemeshBoundaryRouteEvidenceV1,
    build_remesh_boundary_route_evidence,
    verify_remesh_boundary_route_evidence,
)
from .tet_quality import build_tet10_corner_quality_snapshot, require_quality_crosscheck


class AdaptiveSecondSolveError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptivePhysicalRouteV1:
    schema: str
    source_step_sha256: str
    support_named_selection_sha256: str
    load_named_selection_sha256: str
    young_modulus_mpa: float
    poisson_ratio: float
    resultant_n: tuple[float, float, float]
    qoi_name: str
    qoi_unit: str
    route_sha256: str


@dataclass(frozen=True)
class AdaptiveSecondSolveEvidenceV1:
    schema: str
    route_sha256: str
    boundary_route_evidence_sha256: str
    baseline_mesh_sha256: str
    remesh_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    remesh_solve_evidence_sha256: str
    baseline_qoi_observation_sha256: str
    remesh_qoi_observation_sha256: str
    qoi_assessment_sha256: str
    qoi_status: str
    baseline_force_residual_n: float
    remesh_force_residual_n: float
    baseline_moment_residual_nmm: float
    remesh_moment_residual_nmm: float
    qoi_discretization_converged: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_sha256: str


def _finite_material(young_modulus_mpa: float, poisson_ratio: float) -> tuple[float, float]:
    young = float(young_modulus_mpa)
    poisson = float(poisson_ratio)
    if not math.isfinite(young) or young <= 0.0:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_YOUNG_MODULUS")
    if not math.isfinite(poisson) or not (-1.0 < poisson < 0.5):
        raise AdaptiveSecondSolveError("SECOND_SOLVE_POISSON_RATIO")
    return young, poisson


def _finite_resultant(resultant_n: tuple[float, float, float]) -> tuple[float, float, float]:
    values = tuple(float(v) for v in resultant_n)
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise AdaptiveSecondSolveError("SECOND_SOLVE_RESULTANT")
    if math.sqrt(sum(v * v for v in values)) <= 0.0:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_RESULTANT_ZERO")
    return values


def build_adaptive_physical_route(
    *,
    source_step_sha256: str,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
    qoi_name: str = "MAX_DISPLACEMENT_MAGNITUDE",
    qoi_unit: str = "mm",
) -> AdaptivePhysicalRouteV1:
    if support.role != "SUPPORT" or load.role != "LOAD":
        raise AdaptiveSecondSolveError("SECOND_SOLVE_SUPPORT_LOAD_ROLES")
    if support.source_sha256 != source_step_sha256 or load.source_sha256 != source_step_sha256:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_SELECTION_SOURCE")
    if support.named_selection_sha256 == load.named_selection_sha256:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_SELECTIONS_DISTINCT")
    young, poisson = _finite_material(young_modulus_mpa, poisson_ratio)
    resultant = _finite_resultant(resultant_n)
    name = qoi_name.strip() if isinstance(qoi_name, str) else ""
    unit = qoi_unit.strip() if isinstance(qoi_unit, str) else ""
    if not name or not unit:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_QOI_REQUIRED")
    core = {
        "schema": "AsterMaxAdaptivePhysicalRouteV1",
        "source_step_sha256": source_step_sha256,
        "support_named_selection_sha256": support.named_selection_sha256,
        "load_named_selection_sha256": load.named_selection_sha256,
        "young_modulus_mpa": young,
        "poisson_ratio": poisson,
        "resultant_n": list(resultant),
        "qoi_name": name,
        "qoi_unit": unit,
    }
    return AdaptivePhysicalRouteV1(
        schema=core["schema"],
        source_step_sha256=source_step_sha256,
        support_named_selection_sha256=support.named_selection_sha256,
        load_named_selection_sha256=load.named_selection_sha256,
        young_modulus_mpa=young,
        poisson_ratio=poisson,
        resultant_n=resultant,
        qoi_name=name,
        qoi_unit=unit,
        route_sha256=canonical_sha256(core),
    )


def prepare_existing_inventory_for_solve(
    step_path: str | Path,
    inventory: Tet10FaceOwnershipInventory,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
) -> dict:
    support_binding, support_triangles = bind_named_selection_to_owned_faces(
        step_path, support, inventory, expected_role="SUPPORT"
    )
    load_binding, load_triangles = bind_named_selection_to_owned_faces(
        step_path, load, inventory, expected_role="LOAD"
    )
    if set(support_binding.face_signature_sha256) & set(load_binding.face_signature_sha256):
        raise AdaptiveSecondSolveError("SECOND_SOLVE_SUPPORT_LOAD_OVERLAP")
    quality = build_tet10_corner_quality_snapshot(inventory.nodes_mm, inventory.elements)
    require_quality_crosscheck(quality)
    core = {
        "schema": "AsterMaxArbitraryBcPreparationV1",
        "source_step_sha256": inventory.source_step_sha256,
        "ownership_sha256": inventory.ownership_sha256,
        "support_named_selection_sha256": support_binding.named_selection_sha256,
        "load_named_selection_sha256": load_binding.named_selection_sha256,
        "support_binding_sha256": support_binding.binding_sha256,
        "load_binding_sha256": load_binding.binding_sha256,
        "support_face_signature_sha256": tuple(support_binding.face_signature_sha256),
        "load_face_signature_sha256": tuple(load_binding.face_signature_sha256),
        "support_tri6_count": int(support_triangles.shape[0]),
        "load_tri6_count": int(load_triangles.shape[0]),
        "node_count": int(inventory.nodes_mm.shape[0]),
        "tet10_count": int(inventory.elements.shape[0]),
        "tetra_quality_sha256": quality.snapshot_sha256,
        "tetra_quality_crosscheck_verified": bool(quality.crosscheck_verified),
    }
    evidence = ArbitraryBcPreparation(**core, preparation_sha256=canonical_sha256(core))
    return {
        "inventory": inventory,
        "support_selection": support,
        "load_selection": load,
        "support_binding": support_binding,
        "load_binding": load_binding,
        "support_triangles": np.asarray(support_triangles, dtype=np.int64),
        "load_triangles": np.asarray(load_triangles, dtype=np.int64),
        "quality": quality,
        "evidence": evidence,
    }


def _max_displacement_mm(result) -> float:
    field = np.asarray(result.displacement_mm, dtype=float)
    if field.ndim != 2 or field.shape[1] != 3 or field.shape[0] == 0 or not np.all(np.isfinite(field)):
        raise AdaptiveSecondSolveError("SECOND_SOLVE_DISPLACEMENT_FIELD")
    return float(np.linalg.norm(field, axis=1).max())


def execute_provenance_matched_second_solve(
    step_path: str | Path,
    baseline: Tet10FaceOwnershipInventory,
    remesh: Tet10FaceOwnershipInventory,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    *,
    baseline_target_size_mm: float,
    remesh_target_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
    maximum_relative_qoi_change: float,
) -> tuple[
    AdaptiveSecondSolveEvidenceV1,
    QoiObservationV1,
    QoiObservationV1,
    QoiConvergenceAssessmentV1,
]:
    boundary: RemeshBoundaryRouteEvidenceV1 = build_remesh_boundary_route_evidence(
        step_path, baseline, remesh, support, load
    )
    verify_remesh_boundary_route_evidence(boundary)
    if not boundary.ready_for_second_solve:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_REBINDING_NOT_READY")

    route = build_adaptive_physical_route(
        source_step_sha256=boundary.source_step_sha256,
        support=support,
        load=load,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    coarse_size = float(baseline_target_size_mm)
    fine_size = float(remesh_target_size_mm)
    if not math.isfinite(coarse_size) or not math.isfinite(fine_size) or coarse_size <= 0.0 or fine_size <= 0.0:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_MESH_TARGET_SIZE")
    if fine_size >= coarse_size:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_REFINEMENT_ORDER")

    baseline_prepared = prepare_existing_inventory_for_solve(step_path, baseline, support, load)
    remesh_prepared = prepare_existing_inventory_for_solve(step_path, remesh, support, load)
    baseline_solved = solve_arbitrary_bc_model(
        baseline_prepared,
        young_modulus_mpa=route.young_modulus_mpa,
        poisson_ratio=route.poisson_ratio,
        resultant_n=route.resultant_n,
    )
    remesh_solved = solve_arbitrary_bc_model(
        remesh_prepared,
        young_modulus_mpa=route.young_modulus_mpa,
        poisson_ratio=route.poisson_ratio,
        resultant_n=route.resultant_n,
    )
    baseline_ev = baseline_solved["solve_evidence"]
    remesh_ev = remesh_solved["solve_evidence"]
    if baseline_ev.solve_evidence_sha256 == remesh_ev.solve_evidence_sha256:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_DISTINCT_SOLVE_EVIDENCE_REQUIRED")

    coarse_qoi = make_qoi_observation(
        source_step_sha256=route.source_step_sha256,
        route_sha256=route.route_sha256,
        solve_evidence_sha256=baseline_ev.solve_evidence_sha256,
        mesh_identity_sha256=baseline.ownership_sha256,
        mesh_target_size_mm=coarse_size,
        element_count=int(baseline.elements.shape[0]),
        qoi_name=route.qoi_name,
        qoi_unit=route.qoi_unit,
        qoi_value=_max_displacement_mm(baseline_solved["result"]),
    )
    fine_qoi = make_qoi_observation(
        source_step_sha256=route.source_step_sha256,
        route_sha256=route.route_sha256,
        solve_evidence_sha256=remesh_ev.solve_evidence_sha256,
        mesh_identity_sha256=remesh.ownership_sha256,
        mesh_target_size_mm=fine_size,
        element_count=int(remesh.elements.shape[0]),
        qoi_name=route.qoi_name,
        qoi_unit=route.qoi_unit,
        qoi_value=_max_displacement_mm(remesh_solved["result"]),
    )
    assessment = assess_qoi_convergence(
        coarse_qoi,
        fine_qoi,
        QoiConvergenceCriteriaV1(maximum_relative_change=float(maximum_relative_qoi_change), require_finer_mesh=True),
    )
    verify_qoi_convergence_boundary(assessment)

    core = {
        "schema": "AsterMaxAdaptiveSecondSolveEvidenceV1",
        "route_sha256": route.route_sha256,
        "boundary_route_evidence_sha256": boundary.evidence_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "remesh_mesh_sha256": remesh.ownership_sha256,
        "baseline_solve_evidence_sha256": baseline_ev.solve_evidence_sha256,
        "remesh_solve_evidence_sha256": remesh_ev.solve_evidence_sha256,
        "baseline_qoi_observation_sha256": coarse_qoi.observation_sha256,
        "remesh_qoi_observation_sha256": fine_qoi.observation_sha256,
        "qoi_assessment_sha256": assessment.assessment_sha256,
        "qoi_status": assessment.status,
        "baseline_force_residual_n": float(baseline_ev.force_residual_n),
        "remesh_force_residual_n": float(remesh_ev.force_residual_n),
        "baseline_moment_residual_nmm": float(baseline_ev.moment_residual_nmm),
        "remesh_moment_residual_nmm": float(remesh_ev.moment_residual_nmm),
        "qoi_discretization_converged": bool(assessment.claims["qoi_discretization_converged"]),
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    evidence = AdaptiveSecondSolveEvidenceV1(**core, evidence_sha256=canonical_sha256(core))
    return evidence, coarse_qoi, fine_qoi, assessment


def verify_second_solve_evidence(evidence: AdaptiveSecondSolveEvidenceV1) -> None:
    if evidence.schema != "AsterMaxAdaptiveSecondSolveEvidenceV1":
        raise AdaptiveSecondSolveError("SECOND_SOLVE_EVIDENCE_SCHEMA")
    if evidence.baseline_mesh_sha256 == evidence.remesh_mesh_sha256:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_DISTINCT_MESH_REQUIRED")
    if evidence.baseline_solve_evidence_sha256 == evidence.remesh_solve_evidence_sha256:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_DISTINCT_SOLVE_REQUIRED")
    for value in (
        evidence.baseline_force_residual_n,
        evidence.remesh_force_residual_n,
        evidence.baseline_moment_residual_nmm,
        evidence.remesh_moment_residual_nmm,
    ):
        if not math.isfinite(value):
            raise AdaptiveSecondSolveError("SECOND_SOLVE_RESIDUAL_NONFINITE")
    if evidence.global_analysis_converged:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_GLOBAL_CONVERGENCE_OVERCLAIM")
    if evidence.industrial_validation or evidence.ansys_equivalence:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_VALIDATION_OVERCLAIM")
    core = evidence.__dict__.copy()
    core.pop("evidence_sha256")
    if canonical_sha256(core) != evidence.evidence_sha256:
        raise AdaptiveSecondSolveError("SECOND_SOLVE_EVIDENCE_TAMPERED")
