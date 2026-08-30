from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from types import MappingProxyType
from typing import Any, Callable, Mapping

import numpy as np

from astermax.credibility import canonical_sha256
from .adaptive_hotspot_visualization import (
    AdaptiveHotspotVisualizationV1,
    build_adaptive_hotspot_visualization,
)
from .adaptive_stress_comparison import (
    AdaptiveStressComparisonV1,
    build_verified_adaptive_stress_comparison,
    verify_adaptive_stress_comparison,
)
from .face_ownership import Tet10FaceOwnershipInventory
from .local_refinement_plan import ControlledLocalRefinementPlanV1
from .solution_driven_adaptivity import SolutionDrivenRefinementEvidenceV1
from .solution_driven_local_loop import SolutionDrivenLocalLoopEvidenceV1, SolutionDrivenLocalProposalV1
from .solver import Tet10LinearStaticResult


class AdaptiveExecutionBundleError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptiveExecutionArtifactBundleV1:
    schema: str
    status: str
    loop_evidence_sha256: str
    proposal_sha256: str
    plan_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    refined_solve_evidence_sha256: str
    baseline_indicator_evidence_sha256: str
    refined_indicator_evidence_sha256: str
    baseline_result_field_sha256: str
    refined_result_field_sha256: str
    hotspot_visualization_sha256: str
    stress_comparison_sha256: str
    baseline_mesh: Tet10FaceOwnershipInventory
    refined_mesh: Tet10FaceOwnershipInventory
    baseline_solved: Mapping[str, Any]
    refined_solved: Mapping[str, Any]
    hotspot_view: AdaptiveHotspotVisualizationV1
    stress_view: AdaptiveStressComparisonV1
    claims: dict[str, bool]
    bundle_sha256: str


@dataclass(frozen=True)
class NativeAdaptiveResultsBindingReceiptV1:
    schema: str
    bundle_sha256: str
    bound_tabs: tuple[str, ...]
    hotspot_visualization_sha256: str
    stress_comparison_sha256: str
    receipt_sha256: str


def _array_sha256(array: np.ndarray) -> str:
    value = np.ascontiguousarray(np.asarray(array))
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode("utf-8"))
    digest.update(repr(tuple(int(v) for v in value.shape)).encode("utf-8"))
    digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def _result_field_sha256(result: Tet10LinearStaticResult) -> str:
    if not isinstance(result, Tet10LinearStaticResult):
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_RESULT_TYPE")
    arrays = {
        "displacement_mm": np.asarray(result.displacement_mm),
        "reactions_n": np.asarray(result.reactions_n),
        "integration_point_stress_mpa": np.asarray(result.integration_point_stress_mpa),
        "integration_point_von_mises_mpa": np.asarray(result.integration_point_von_mises_mpa),
    }
    if any(not np.all(np.isfinite(value)) for value in arrays.values()):
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_NONFINITE_RESULT")
    return canonical_sha256({name: _array_sha256(value) for name, value in arrays.items()})


def _freeze_result(result: Tet10LinearStaticResult) -> Tet10LinearStaticResult:
    arrays = []
    for source in (
        result.displacement_mm,
        result.reactions_n,
        result.integration_point_stress_mpa,
        result.integration_point_von_mises_mpa,
    ):
        value = np.array(source, copy=True)
        value.setflags(write=False)
        arrays.append(value)
    return Tet10LinearStaticResult(*arrays)


def _freeze_solved(payload: Mapping[str, Any], expected_solve_sha256: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or "result" not in payload or "solve_evidence" not in payload:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_SOLVED_PAYLOAD")
    evidence = payload["solve_evidence"]
    if getattr(evidence, "solve_evidence_sha256", None) != expected_solve_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_SOLVE_PROVENANCE")
    result = _freeze_result(payload["result"])
    return MappingProxyType({"result": result, "solve_evidence": evidence})


def _verify_hotspot(view: AdaptiveHotspotVisualizationV1) -> None:
    if view.schema != "AsterMaxNativeAdaptiveHotspotVisualizationV1" or view.status != "READY":
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_HOTSPOT_SCHEMA")
    if view.claims.get("estimator_certified") or view.claims.get("solution_error_bound_claimed"):
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_HOTSPOT_OVERCLAIM")
    if view.claims.get("global_analysis_converged") or view.claims.get("industrial_validation") or view.claims.get("ansys_equivalence"):
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_HOTSPOT_VALIDATION_OVERCLAIM")
    core = {
        "schema": view.schema,
        "status": view.status,
        "source_step_sha256": view.source_step_sha256,
        "baseline_mesh_sha256": view.baseline_mesh_sha256,
        "refined_mesh_sha256": view.refined_mesh_sha256,
        "baseline_element_count": view.baseline_element_count,
        "refined_element_count": view.refined_element_count,
        "baseline_max_indicator": view.baseline_max_indicator,
        "refined_max_indicator": view.refined_max_indicator,
        "indicator_relative_change": view.indicator_relative_change,
        "indicator_status": view.indicator_status,
        "qoi_status": view.qoi_status,
        "qoi_relative_change": view.qoi_relative_change,
        "hotspot_markers": [asdict(v) for v in view.hotspot_markers],
        "projection_bounds_mm": view.projection_bounds_mm,
        "claims": view.claims,
    }
    if canonical_sha256(core) != view.visualization_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_HOTSPOT_TAMPERED")


def build_adaptive_execution_artifact_bundle(
    *,
    loop_evidence: SolutionDrivenLocalLoopEvidenceV1,
    proposal: SolutionDrivenLocalProposalV1,
    plan: ControlledLocalRefinementPlanV1,
    baseline_mesh: Tet10FaceOwnershipInventory,
    refined_mesh: Tet10FaceOwnershipInventory,
    baseline_solved: Mapping[str, Any],
    refined_solved: Mapping[str, Any],
    baseline_indicator: SolutionDrivenRefinementEvidenceV1,
    refined_indicator: SolutionDrivenRefinementEvidenceV1,
    displacement_scale: float = 1.0,
) -> AdaptiveExecutionArtifactBundleV1:
    if loop_evidence.schema != "AsterMaxSolutionDrivenLocalLoopEvidenceV1":
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_LOOP_SCHEMA")
    if proposal.proposal_sha256 != loop_evidence.proposal_sha256 or proposal.plan_sha256 != plan.plan_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_PROPOSAL_PLAN_PROVENANCE")
    if baseline_mesh.ownership_sha256 != loop_evidence.baseline_mesh_sha256 or refined_mesh.ownership_sha256 != loop_evidence.refined_mesh_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_MESH_PROVENANCE")
    if baseline_indicator.evidence_sha256 != loop_evidence.baseline_indicator_evidence_sha256 or refined_indicator.evidence_sha256 != loop_evidence.refined_indicator_evidence_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_INDICATOR_PROVENANCE")

    frozen_baseline = _freeze_solved(baseline_solved, loop_evidence.baseline_solve_evidence_sha256)
    frozen_refined = _freeze_solved(refined_solved, loop_evidence.refined_solve_evidence_sha256)
    baseline_field_sha = _result_field_sha256(frozen_baseline["result"])
    refined_field_sha = _result_field_sha256(frozen_refined["result"])

    hotspot = build_adaptive_hotspot_visualization(
        proposal=proposal,
        plan=plan,
        baseline=baseline_mesh,
        refined=refined_mesh,
        baseline_indicator=baseline_indicator,
        loop_evidence=loop_evidence,
    )
    _verify_hotspot(hotspot)
    stress = build_verified_adaptive_stress_comparison(
        loop_evidence=loop_evidence,
        baseline_mesh=baseline_mesh,
        refined_mesh=refined_mesh,
        baseline_solved=frozen_baseline,
        refined_solved=frozen_refined,
        displacement_scale=displacement_scale,
    )
    verify_adaptive_stress_comparison(stress)

    claims = {
        "result_fields_carried_without_replay": True,
        "native_results_views_derived_from_same_execution_artifacts": True,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxAdaptiveExecutionArtifactBundleV1",
        "status": "READY",
        "loop_evidence_sha256": loop_evidence.evidence_sha256,
        "proposal_sha256": proposal.proposal_sha256,
        "plan_sha256": plan.plan_sha256,
        "baseline_mesh_sha256": baseline_mesh.ownership_sha256,
        "refined_mesh_sha256": refined_mesh.ownership_sha256,
        "baseline_solve_evidence_sha256": loop_evidence.baseline_solve_evidence_sha256,
        "refined_solve_evidence_sha256": loop_evidence.refined_solve_evidence_sha256,
        "baseline_indicator_evidence_sha256": baseline_indicator.evidence_sha256,
        "refined_indicator_evidence_sha256": refined_indicator.evidence_sha256,
        "baseline_result_field_sha256": baseline_field_sha,
        "refined_result_field_sha256": refined_field_sha,
        "hotspot_visualization_sha256": hotspot.visualization_sha256,
        "stress_comparison_sha256": stress.comparison_sha256,
        "claims": claims,
    }
    return AdaptiveExecutionArtifactBundleV1(
        **core,
        baseline_mesh=baseline_mesh,
        refined_mesh=refined_mesh,
        baseline_solved=frozen_baseline,
        refined_solved=frozen_refined,
        hotspot_view=hotspot,
        stress_view=stress,
        bundle_sha256=canonical_sha256(core),
    )


def verify_adaptive_execution_artifact_bundle(bundle: AdaptiveExecutionArtifactBundleV1) -> None:
    if bundle.schema != "AsterMaxAdaptiveExecutionArtifactBundleV1" or bundle.status != "READY":
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_SCHEMA_STATUS")
    if bundle.claims.get("global_analysis_converged") or bundle.claims.get("industrial_validation") or bundle.claims.get("ansys_equivalence"):
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_VALIDATION_OVERCLAIM")
    if bundle.baseline_mesh.ownership_sha256 != bundle.baseline_mesh_sha256 or bundle.refined_mesh.ownership_sha256 != bundle.refined_mesh_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_MESH_MUTATED")
    if _result_field_sha256(bundle.baseline_solved["result"]) != bundle.baseline_result_field_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_BASELINE_RESULT_MUTATED")
    if _result_field_sha256(bundle.refined_solved["result"]) != bundle.refined_result_field_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_REFINED_RESULT_MUTATED")
    if getattr(bundle.baseline_solved["solve_evidence"], "solve_evidence_sha256", None) != bundle.baseline_solve_evidence_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_BASELINE_SOLVE_MUTATED")
    if getattr(bundle.refined_solved["solve_evidence"], "solve_evidence_sha256", None) != bundle.refined_solve_evidence_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_REFINED_SOLVE_MUTATED")
    _verify_hotspot(bundle.hotspot_view)
    verify_adaptive_stress_comparison(bundle.stress_view)
    if bundle.hotspot_view.visualization_sha256 != bundle.hotspot_visualization_sha256 or bundle.stress_view.comparison_sha256 != bundle.stress_comparison_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_VIEW_PROVENANCE")
    core = {
        "schema": bundle.schema,
        "status": bundle.status,
        "loop_evidence_sha256": bundle.loop_evidence_sha256,
        "proposal_sha256": bundle.proposal_sha256,
        "plan_sha256": bundle.plan_sha256,
        "baseline_mesh_sha256": bundle.baseline_mesh_sha256,
        "refined_mesh_sha256": bundle.refined_mesh_sha256,
        "baseline_solve_evidence_sha256": bundle.baseline_solve_evidence_sha256,
        "refined_solve_evidence_sha256": bundle.refined_solve_evidence_sha256,
        "baseline_indicator_evidence_sha256": bundle.baseline_indicator_evidence_sha256,
        "refined_indicator_evidence_sha256": bundle.refined_indicator_evidence_sha256,
        "baseline_result_field_sha256": bundle.baseline_result_field_sha256,
        "refined_result_field_sha256": bundle.refined_result_field_sha256,
        "hotspot_visualization_sha256": bundle.hotspot_visualization_sha256,
        "stress_comparison_sha256": bundle.stress_comparison_sha256,
        "claims": bundle.claims,
    }
    if canonical_sha256(core) != bundle.bundle_sha256:
        raise AdaptiveExecutionBundleError("ADAPTIVE_BUNDLE_TAMPERED")


def bind_native_adaptive_results(
    bundle: AdaptiveExecutionArtifactBundleV1,
    *,
    hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
    stress_binder: Callable[[AdaptiveStressComparisonV1], None],
) -> NativeAdaptiveResultsBindingReceiptV1:
    """Verify once, then bind both native Results views from the same artifact bundle."""
    verify_adaptive_execution_artifact_bundle(bundle)
    hotspot_binder(bundle.hotspot_view)
    stress_binder(bundle.stress_view)
    core = {
        "schema": "AsterMaxNativeAdaptiveResultsBindingReceiptV1",
        "bundle_sha256": bundle.bundle_sha256,
        "bound_tabs": ("Adaptive Hotspots", "Stress Compare"),
        "hotspot_visualization_sha256": bundle.hotspot_visualization_sha256,
        "stress_comparison_sha256": bundle.stress_comparison_sha256,
    }
    return NativeAdaptiveResultsBindingReceiptV1(**core, receipt_sha256=canonical_sha256(core))
