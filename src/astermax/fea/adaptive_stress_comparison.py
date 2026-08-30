from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .face_ownership import Tet10FaceOwnershipInventory
from .solution_driven_local_loop import SolutionDrivenLocalLoopEvidenceV1
from .solver import Tet10LinearStaticResult


class AdaptiveStressComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class StressContourElementV1:
    element_index: int
    centroid_mm: tuple[float, float, float]
    deformed_centroid_mm: tuple[float, float, float]
    von_mises_mpa: float


@dataclass(frozen=True)
class VerifiedStressContourFieldV1:
    mesh_identity_sha256: str
    solve_evidence_sha256: str
    element_count: int
    stress_semantics: str
    displacement_scale: float
    stress_min_mpa: float
    stress_max_mpa: float
    displacement_max_mm: float
    elements: tuple[StressContourElementV1, ...]


@dataclass(frozen=True)
class AdaptiveStressComparisonV1:
    schema: str
    semantics: str
    status: str
    baseline: VerifiedStressContourFieldV1
    refined: VerifiedStressContourFieldV1
    common_scale_min_mpa: float
    common_scale_max_mpa: float
    baseline_peak_mpa: float
    refined_peak_mpa: float
    peak_relative_change: float
    qoi_status: str
    qoi_relative_change: float
    indicator_status: str
    indicator_relative_change: float
    claims: dict[str, bool]
    comparison_sha256: str


def _require_solved(solved: Any, mesh: Tet10FaceOwnershipInventory, expected_solve_sha: str, displacement_scale: float) -> VerifiedStressContourFieldV1:
    # C5.5q carries solved payloads as MappingProxyType to make accidental mutation
    # impossible. Accept the Mapping protocol rather than only mutable dicts, while
    # still requiring the exact result/evidence keys and provenance below.
    if not isinstance(solved, Mapping) or "result" not in solved or "solve_evidence" not in solved:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_SOLVED_PAYLOAD")
    result = solved["result"]
    evidence = solved["solve_evidence"]
    if not isinstance(result, Tet10LinearStaticResult):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_RESULT_TYPE")
    if getattr(evidence, "solve_evidence_sha256", None) != expected_solve_sha:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_SOLVE_PROVENANCE")

    nodes = np.asarray(mesh.nodes_mm, dtype=float)
    elems = np.asarray(mesh.elements, dtype=np.int64)
    disp = np.asarray(result.displacement_mm, dtype=float)
    vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_NODES")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_TET10")
    if disp.shape != nodes.shape or not np.all(np.isfinite(disp)):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_DISPLACEMENT")
    if vm.shape != (elems.shape[0], 4) or not np.all(np.isfinite(vm)) or np.any(vm < 0.0):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_VM_IP")
    scale = float(displacement_scale)
    if not math.isfinite(scale) or scale < 0.0:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_DEFORMATION_SCALE")

    element_vm = np.mean(vm, axis=1)
    rows: list[StressContourElementV1] = []
    for index, conn in enumerate(elems):
        corners = conn[:4]
        centroid = np.mean(nodes[corners], axis=0)
        mean_disp = np.mean(disp[corners], axis=0)
        deformed = centroid + scale * mean_disp
        rows.append(
            StressContourElementV1(
                element_index=int(index),
                centroid_mm=tuple(float(v) for v in centroid),
                deformed_centroid_mm=tuple(float(v) for v in deformed),
                von_mises_mpa=float(element_vm[index]),
            )
        )
    disp_max = float(np.linalg.norm(disp, axis=1).max())
    return VerifiedStressContourFieldV1(
        mesh_identity_sha256=mesh.ownership_sha256,
        solve_evidence_sha256=expected_solve_sha,
        element_count=int(elems.shape[0]),
        stress_semantics="ELEMENT_MEAN_OF_4_TET10_INTEGRATION_POINT_VON_MISES_MPA_NO_NODAL_SMOOTHING",
        displacement_scale=scale,
        stress_min_mpa=float(np.min(element_vm)),
        stress_max_mpa=float(np.max(element_vm)),
        displacement_max_mm=disp_max,
        elements=tuple(rows),
    )


def build_verified_adaptive_stress_comparison(
    *,
    loop_evidence: SolutionDrivenLocalLoopEvidenceV1,
    baseline_mesh: Tet10FaceOwnershipInventory,
    refined_mesh: Tet10FaceOwnershipInventory,
    baseline_solved: Mapping[str, Any],
    refined_solved: Mapping[str, Any],
    displacement_scale: float = 1.0,
) -> AdaptiveStressComparisonV1:
    if loop_evidence.schema != "AsterMaxSolutionDrivenLocalLoopEvidenceV1":
        raise AdaptiveStressComparisonError("STRESS_COMPARE_LOOP_SCHEMA")
    if loop_evidence.baseline_mesh_sha256 != baseline_mesh.ownership_sha256:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_BASELINE_MESH_PROVENANCE")
    if loop_evidence.refined_mesh_sha256 != refined_mesh.ownership_sha256:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_REFINED_MESH_PROVENANCE")
    baseline = _require_solved(baseline_solved, baseline_mesh, loop_evidence.baseline_solve_evidence_sha256, displacement_scale)
    refined = _require_solved(refined_solved, refined_mesh, loop_evidence.refined_solve_evidence_sha256, displacement_scale)

    scale_min = 0.0
    scale_max = max(float(baseline.stress_max_mpa), float(refined.stress_max_mpa))
    if not math.isfinite(scale_max) or scale_max <= 0.0:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_COMMON_SCALE")
    peak_change = (refined.stress_max_mpa - baseline.stress_max_mpa) / baseline.stress_max_mpa if baseline.stress_max_mpa > 0.0 else 0.0
    numeric = (
        peak_change,
        loop_evidence.qoi_relative_change,
        loop_evidence.indicator_relative_change,
        baseline.displacement_max_mm,
        refined.displacement_max_mm,
    )
    if not all(math.isfinite(float(v)) for v in numeric):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_NONFINITE")

    claims = {
        "same_stress_scale_used_for_both_views": True,
        "stress_from_computed_tet10_integration_points": True,
        "nodal_stress_smoothing_used": False,
        "pointwise_mesh_to_mesh_delta_claimed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxVerifiedAdaptiveStressComparisonV1",
        "status": "READY",
        "baseline": asdict(baseline),
        "refined": asdict(refined),
        "common_scale_min_mpa": scale_min,
        "common_scale_max_mpa": scale_max,
        "baseline_peak_mpa": baseline.stress_max_mpa,
        "refined_peak_mpa": refined.stress_max_mpa,
        "peak_relative_change": float(peak_change),
        "qoi_status": loop_evidence.qoi_status,
        "qoi_relative_change": float(loop_evidence.qoi_relative_change),
        "indicator_status": loop_evidence.indicator_status,
        "indicator_relative_change": float(loop_evidence.indicator_relative_change),
        "claims": claims,
    }
    return AdaptiveStressComparisonV1(
        schema=core["schema"],
        semantics="presentation_only_verified_baseline_vs_refined_tet10_stress_comparison_with_shared_mpa_scale",
        status="READY",
        baseline=baseline,
        refined=refined,
        common_scale_min_mpa=scale_min,
        common_scale_max_mpa=scale_max,
        baseline_peak_mpa=baseline.stress_max_mpa,
        refined_peak_mpa=refined.stress_max_mpa,
        peak_relative_change=float(peak_change),
        qoi_status=loop_evidence.qoi_status,
        qoi_relative_change=float(loop_evidence.qoi_relative_change),
        indicator_status=loop_evidence.indicator_status,
        indicator_relative_change=float(loop_evidence.indicator_relative_change),
        claims=claims,
        comparison_sha256=canonical_sha256(core),
    )


def verify_adaptive_stress_comparison(view: AdaptiveStressComparisonV1) -> None:
    if view.schema != "AsterMaxVerifiedAdaptiveStressComparisonV1" or view.status != "READY":
        raise AdaptiveStressComparisonError("STRESS_COMPARE_SCHEMA_STATUS")
    if view.common_scale_min_mpa != 0.0 or view.common_scale_max_mpa <= 0.0:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_SCALE")
    if view.claims.get("nodal_stress_smoothing_used") or view.claims.get("pointwise_mesh_to_mesh_delta_claimed"):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_OVERCLAIM")
    if view.claims.get("global_analysis_converged") or view.claims.get("industrial_validation") or view.claims.get("ansys_equivalence"):
        raise AdaptiveStressComparisonError("STRESS_COMPARE_VALIDATION_OVERCLAIM")
    core = {
        "schema": view.schema,
        "status": view.status,
        "baseline": asdict(view.baseline),
        "refined": asdict(view.refined),
        "common_scale_min_mpa": view.common_scale_min_mpa,
        "common_scale_max_mpa": view.common_scale_max_mpa,
        "baseline_peak_mpa": view.baseline_peak_mpa,
        "refined_peak_mpa": view.refined_peak_mpa,
        "peak_relative_change": view.peak_relative_change,
        "qoi_status": view.qoi_status,
        "qoi_relative_change": view.qoi_relative_change,
        "indicator_status": view.indicator_status,
        "indicator_relative_change": view.indicator_relative_change,
        "claims": view.claims,
    }
    if canonical_sha256(core) != view.comparison_sha256:
        raise AdaptiveStressComparisonError("STRESS_COMPARE_TAMPERED")


def install_adaptive_stress_comparison_tab(notebook: Any):
    import tkinter as tk
    from tkinter import ttk

    panel = ttk.Frame(notebook, padding=12)
    notebook.add(panel, text="Stress Compare")
    panel.columnconfigure(0, weight=1); panel.columnconfigure(1, weight=1); panel.columnconfigure(2, weight=0)
    panel.rowconfigure(2, weight=1)
    ttk.Label(panel, text="Verified Baseline vs Refined Stress", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(panel, text="Same MPa scale · TET10 integration-point stress · no nodal smoothing · deformation display is visual only", wraplength=1050).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 8))
    base_canvas = tk.Canvas(panel, background="#20252b", highlightthickness=1); base_canvas.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
    fine_canvas = tk.Canvas(panel, background="#20252b", highlightthickness=1); fine_canvas.grid(row=2, column=1, sticky="nsew", padx=(6, 10))
    info = tk.Text(panel, width=42, height=30, wrap="word", state="disabled"); info.grid(row=2, column=2, sticky="nsew")

    def color(value: float, maximum: float) -> str:
        t = max(0.0, min(1.0, value / maximum))
        r = int(40 + 215 * t); g = int(70 + 100 * (1.0 - abs(2.0 * t - 1.0))); b = int(220 - 190 * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def draw(canvas, field: VerifiedStressContourFieldV1, maximum: float, title: str):
        canvas.delete("all"); w=max(canvas.winfo_width(),480); h=max(canvas.winfo_height(),430); m=35
        pts=np.asarray([row.deformed_centroid_mm for row in field.elements], dtype=float)
        low=pts.min(axis=0); high=pts.max(axis=0); span=np.maximum(high-low,1e-12)
        canvas.create_text(m,18,anchor="w",fill="#ffffff",text=title,font=("Segoe UI",11,"bold"))
        for row,p in zip(field.elements,pts):
            q=(p-low)/span; x=m+q[0]*(w-2*m); y=h-m-q[2]*(h-2*m)
            c=color(row.von_mises_mpa, maximum); canvas.create_oval(x-3,y-3,x+3,y+3,fill=c,outline="")
        canvas.create_text(m,h-14,anchor="w",fill="#c5ccd3",text=f"0 → {maximum:.5g} MPa · {field.element_count} TET10")

    def bind(view: AdaptiveStressComparisonV1):
        verify_adaptive_stress_comparison(view)
        draw(base_canvas, view.baseline, view.common_scale_max_mpa, "BASELINE")
        draw(fine_canvas, view.refined, view.common_scale_max_mpa, "REFINED")
        lines=[
            "Shared contour scale",
            f"0 → {view.common_scale_max_mpa:.6g} MPa",
            "",
            f"Baseline peak: {view.baseline_peak_mpa:.6g} MPa",
            f"Refined peak: {view.refined_peak_mpa:.6g} MPa",
            f"Peak Δrel: {100*view.peak_relative_change:+.4g}%",
            "",
            f"QoI: {view.qoi_status} · Δrel={100*view.qoi_relative_change:.4g}%",
            f"Indicator: {view.indicator_status} · Δrel={100*view.indicator_relative_change:+.4g}%",
            "",
            f"Baseline Umax: {view.baseline.displacement_max_mm:.6g} mm",
            f"Refined Umax: {view.refined.displacement_max_mm:.6g} mm",
            "",
            "Stress semantics",
            view.baseline.stress_semantics,
            "",
            "Evidence boundary",
            "No nodal smoothing.",
            "No pointwise Δ-stress claim across nonmatching meshes.",
            "Global convergence=false · Industrial validation=false · ANSYS equivalence=false",
            "",
            f"Comparison SHA\n{view.comparison_sha256}",
        ]
        info.configure(state="normal"); info.delete("1.0","end"); info.insert("1.0","\n".join(lines)); info.configure(state="disabled")
    return bind
