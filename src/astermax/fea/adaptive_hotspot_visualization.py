from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .face_ownership import Tet10FaceOwnershipInventory
from .local_refinement_plan import ControlledLocalRefinementPlanV1
from .solution_driven_adaptivity import SolutionDrivenRefinementEvidenceV1
from .solution_driven_local_loop import SolutionDrivenLocalLoopEvidenceV1, SolutionDrivenLocalProposalV1


class AdaptiveHotspotVisualizationError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptiveHotspotMarkerV1:
    rank: int
    element_index: int
    centroid_mm: tuple[float, float, float]
    normalized_indicator: float
    mean_von_mises_mpa: float
    refinement_radius_mm: float
    refinement_target_size_mm: float


@dataclass(frozen=True)
class AdaptiveHotspotVisualizationV1:
    schema: str
    semantics: str
    status: str
    source_step_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    baseline_element_count: int
    refined_element_count: int
    baseline_max_indicator: float
    refined_max_indicator: float
    indicator_relative_change: float
    indicator_status: str
    qoi_status: str
    qoi_relative_change: float
    hotspot_markers: tuple[AdaptiveHotspotMarkerV1, ...]
    projection_bounds_mm: tuple[tuple[float, float, float], tuple[float, float, float]]
    claims: dict[str, bool]
    visualization_sha256: str


def build_adaptive_hotspot_visualization(
    *,
    proposal: SolutionDrivenLocalProposalV1,
    plan: ControlledLocalRefinementPlanV1,
    baseline: Tet10FaceOwnershipInventory,
    refined: Tet10FaceOwnershipInventory,
    baseline_indicator: SolutionDrivenRefinementEvidenceV1,
    loop_evidence: SolutionDrivenLocalLoopEvidenceV1,
) -> AdaptiveHotspotVisualizationV1:
    if proposal.schema != "AsterMaxSolutionDrivenLocalProposalV1":
        raise AdaptiveHotspotVisualizationError("HOTSPOT_PROPOSAL_SCHEMA")
    if plan.schema != "AsterMaxControlledLocalRefinementPlanV1":
        raise AdaptiveHotspotVisualizationError("HOTSPOT_PLAN_SCHEMA")
    if baseline_indicator.schema != "AsterMaxSolutionDrivenRefinementEvidenceV1":
        raise AdaptiveHotspotVisualizationError("HOTSPOT_INDICATOR_SCHEMA")
    if loop_evidence.schema != "AsterMaxSolutionDrivenLocalLoopEvidenceV1":
        raise AdaptiveHotspotVisualizationError("HOTSPOT_LOOP_SCHEMA")
    if proposal.baseline_mesh_sha256 != baseline.ownership_sha256 or plan.baseline_mesh_sha256 != baseline.ownership_sha256:
        raise AdaptiveHotspotVisualizationError("HOTSPOT_BASELINE_PROVENANCE")
    if loop_evidence.baseline_mesh_sha256 != baseline.ownership_sha256 or loop_evidence.refined_mesh_sha256 != refined.ownership_sha256:
        raise AdaptiveHotspotVisualizationError("HOTSPOT_LOOP_MESH_PROVENANCE")
    if proposal.solution_indicator_evidence_sha256 != baseline_indicator.evidence_sha256 or loop_evidence.baseline_indicator_evidence_sha256 != baseline_indicator.evidence_sha256:
        raise AdaptiveHotspotVisualizationError("HOTSPOT_INDICATOR_PROVENANCE")
    if proposal.plan_sha256 != plan.plan_sha256 or tuple(proposal.candidate_element_indices) != tuple(baseline_indicator.candidate_element_indices):
        raise AdaptiveHotspotVisualizationError("HOTSPOT_PLAN_CANDIDATES")
    if len(plan.regions) != len(baseline_indicator.candidates):
        raise AdaptiveHotspotVisualizationError("HOTSPOT_REGION_ALIGNMENT")

    markers = []
    for rank, (candidate, region) in enumerate(zip(baseline_indicator.candidates, plan.regions), start=1):
        if candidate.element_index != region.element_index:
            raise AdaptiveHotspotVisualizationError("HOTSPOT_REGION_ELEMENT_MISMATCH")
        if not np.allclose(candidate.centroid_mm, region.centroid_mm, rtol=0.0, atol=1.0e-12):
            raise AdaptiveHotspotVisualizationError("HOTSPOT_REGION_CENTROID_MISMATCH")
        markers.append(AdaptiveHotspotMarkerV1(
            rank=rank,
            element_index=candidate.element_index,
            centroid_mm=tuple(float(v) for v in candidate.centroid_mm),
            normalized_indicator=float(candidate.normalized_indicator),
            mean_von_mises_mpa=float(candidate.mean_von_mises_mpa),
            refinement_radius_mm=float(region.radius_mm),
            refinement_target_size_mm=float(region.target_size_mm),
        ))

    points = np.vstack((np.asarray(baseline.nodes_mm, dtype=float), np.asarray(refined.nodes_mm, dtype=float)))
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise AdaptiveHotspotVisualizationError("HOTSPOT_POINTS")
    low = tuple(float(v) for v in points.min(axis=0)); high = tuple(float(v) for v in points.max(axis=0))
    numeric = (loop_evidence.baseline_max_indicator, loop_evidence.refined_max_indicator, loop_evidence.indicator_relative_change, loop_evidence.qoi_relative_change)
    if not all(math.isfinite(float(v)) for v in numeric):
        raise AdaptiveHotspotVisualizationError("HOTSPOT_NONFINITE")
    claims = {
        "hotspots_from_computed_solution": True,
        "refinement_regions_executed": True,
        "estimator_certified": False,
        "solution_error_bound_claimed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxNativeAdaptiveHotspotVisualizationV1",
        "status": "READY",
        "source_step_sha256": plan.source_step_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "refined_mesh_sha256": refined.ownership_sha256,
        "baseline_element_count": int(baseline.elements.shape[0]),
        "refined_element_count": int(refined.elements.shape[0]),
        "baseline_max_indicator": float(loop_evidence.baseline_max_indicator),
        "refined_max_indicator": float(loop_evidence.refined_max_indicator),
        "indicator_relative_change": float(loop_evidence.indicator_relative_change),
        "indicator_status": loop_evidence.indicator_status,
        "qoi_status": loop_evidence.qoi_status,
        "qoi_relative_change": float(loop_evidence.qoi_relative_change),
        "hotspot_markers": [asdict(v) for v in markers],
        "projection_bounds_mm": (low, high),
        "claims": claims,
    }
    return AdaptiveHotspotVisualizationV1(
        schema=core["schema"], semantics="native_results_projection_of_solution_driven_hotspots_and_executed_refinement_regions_no_physics_recomputation",
        status="READY", source_step_sha256=plan.source_step_sha256,
        baseline_mesh_sha256=baseline.ownership_sha256, refined_mesh_sha256=refined.ownership_sha256,
        baseline_element_count=core["baseline_element_count"], refined_element_count=core["refined_element_count"],
        baseline_max_indicator=core["baseline_max_indicator"], refined_max_indicator=core["refined_max_indicator"],
        indicator_relative_change=core["indicator_relative_change"], indicator_status=loop_evidence.indicator_status,
        qoi_status=loop_evidence.qoi_status, qoi_relative_change=core["qoi_relative_change"],
        hotspot_markers=tuple(markers), projection_bounds_mm=(low, high), claims=claims,
        visualization_sha256=canonical_sha256(core),
    )


def install_adaptive_hotspot_tab(notebook: Any):
    import tkinter as tk
    from tkinter import ttk
    panel = ttk.Frame(notebook, padding=14); notebook.add(panel, text="Adaptive Hotspots")
    panel.columnconfigure(0, weight=3); panel.columnconfigure(1, weight=2); panel.rowconfigure(2, weight=1)
    ttk.Label(panel, text="Solution-Driven Adaptive Hotspots", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(panel, text="Computed-solution hotspot markers and executed local refinement regions. Presentation only; no solver work occurs here.", wraplength=900).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))
    canvas = tk.Canvas(panel, background="#20252b", highlightthickness=1); canvas.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
    info = tk.Text(panel, width=48, height=30, wrap="word", state="disabled"); info.grid(row=2, column=1, sticky="nsew")

    def bind(view: AdaptiveHotspotVisualizationV1):
        canvas.delete("all"); w=max(canvas.winfo_width(),640); h=max(canvas.winfo_height(),460); m=45
        low=np.asarray(view.projection_bounds_mm[0]); high=np.asarray(view.projection_bounds_mm[1]); span=np.maximum(high-low,1e-12)
        def project(p):
            q=(np.asarray(p)-low)/span; return m+q[0]*(w-2*m), h-m-q[2]*(h-2*m)
        canvas.create_rectangle(m,m,w-m,h-m,outline="#65717e",dash=(4,3))
        for row in view.hotspot_markers:
            x,y=project(row.centroid_mm); r=max(6.0,min(24.0,8.0+10.0*row.normalized_indicator))
            canvas.create_oval(x-r,y-r,x+r,y+r,outline="#ffb000",width=3)
            canvas.create_text(x+r+5,y,anchor="w",fill="#ffffff",text=f"E{row.element_index} · I={row.normalized_indicator:.3g}")
        text=[
            f"Baseline TET10: {view.baseline_element_count}", f"Refined TET10: {view.refined_element_count}", "",
            f"Indicator max: {view.baseline_max_indicator:.6g} → {view.refined_max_indicator:.6g}",
            f"Indicator Δrel: {100*view.indicator_relative_change:+.4g}% · {view.indicator_status}",
            f"QoI Δrel: {100*view.qoi_relative_change:.4g}% · {view.qoi_status}", "",
            "Refinement hotspots",
        ]
        for row in view.hotspot_markers:
            text.append(f"#{row.rank} E{row.element_index} · VM={row.mean_von_mises_mpa:.5g} MPa · I={row.normalized_indicator:.5g} · radius={row.refinement_radius_mm:.4g} mm · h={row.refinement_target_size_mm:.4g} mm")
        text += ["", "Evidence boundary", "Heuristic hotspot visualization only.", "No certified error estimator or solution error bound.", "Global convergence=false · Industrial validation=false · ANSYS equivalence=false", "", f"Visualization SHA\n{view.visualization_sha256}"]
        info.configure(state="normal"); info.delete("1.0","end"); info.insert("1.0","\n".join(text)); info.configure(state="disabled")
    return bind
