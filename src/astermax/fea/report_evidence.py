from __future__ import annotations

from dataclasses import dataclass
from html import escape
import math
from pathlib import Path
import re

import numpy as np

from .evidence import canonical_sha256, sha256_file
from .results_workspace import AsterMaxProfessionalResultsWorkspaceV1
from .results_workspace_ui import ResultsRenderPayloadV1, build_results_render_payload
from .solver import Tet10LinearStaticResult

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReportGradeEvidenceManifestV1:
    schema: str
    field: str
    unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    render_view_sha256: str
    svg_sha256: str
    width_px: int
    height_px: int
    deformation_scale: float
    value_min: float
    value_max: float
    stress_representation: str
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool


def _validate_sha(value: str, code: str) -> None:
    if not _SHA256_RE.fullmatch(str(value)):
        raise ValueError(code)


def _canvas_transform(points: np.ndarray, width: float, height: float, margin: float = 72.0) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or not np.all(np.isfinite(pts)):
        raise ValueError("REPORT_EVIDENCE_PROJECTED_POINTS_INVALID")
    if pts.size == 0:
        return pts.copy()
    low = np.min(pts, axis=0)
    high = np.max(pts, axis=0)
    span = np.maximum(high - low, 1.0e-12)
    sx = max(width - 2.0 * margin, 1.0) / span[0]
    sy = max(height - 2.0 * margin, 1.0) / span[1]
    scale = min(sx, sy)
    out = (pts - low) * scale
    out[:, 0] += margin + 0.5 * max(width - 2.0 * margin - span[0] * scale, 0.0)
    out[:, 1] += margin + 0.5 * max(height - 2.0 * margin - span[1] * scale, 0.0)
    return out


def _scalar_hex(value: float, low: float, high: float) -> str:
    if not math.isfinite(value):
        raise ValueError("REPORT_EVIDENCE_NONFINITE_SCALAR")
    t = 0.5 if high <= low else min(max((value - low) / (high - low), 0.0), 1.0)
    stops = (
        (0.00, (31, 78, 121)),
        (0.25, (46, 134, 171)),
        (0.50, (171, 221, 164)),
        (0.75, (253, 174, 97)),
        (1.00, (215, 25, 28)),
    )
    for (ta, ca), (tb, cb) in zip(stops[:-1], stops[1:], strict=True):
        if t <= tb:
            q = (t - ta) / (tb - ta)
            rgb = tuple(round(a + q * (b - a)) for a, b in zip(ca, cb, strict=True))
            return "#%02x%02x%02x" % rgb
    return "#d7191c"


def _view_payload(payload: ResultsRenderPayloadV1, width_px: int, height_px: int) -> dict:
    return {
        "schema": "AsterMaxReportGradeViewV1",
        "field": payload.field,
        "unit": payload.unit,
        "workspace_sha256": payload.workspace_sha256,
        "solve_evidence_sha256": payload.solve_evidence_sha256,
        "deformation_scale": payload.deformation_scale,
        "value_min": payload.value_min,
        "value_max": payload.value_max,
        "width_px": int(width_px),
        "height_px": int(height_px),
        "projected_nodes_xy": [list(point) for point in payload.projected_nodes_xy],
        "undeformed_nodes_xy": [list(point) for point in payload.undeformed_nodes_xy],
        "triangles": [
            {
                "element_id": tri.element_id,
                "node_ids": list(tri.node_ids),
                "value": tri.value,
            }
            for tri in payload.triangles
        ],
    }


def write_report_grade_svg_evidence(
    path: str | Path,
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    field: str = "U_MAG",
    deformation_scale: float | None = None,
    width_px: int = 1280,
    height_px: int = 720,
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
    ansys_equivalence_claim: bool = False,
) -> ReportGradeEvidenceManifestV1:
    """Write a deterministic, provenance-bound SVG results evidence plate.

    This is report/render evidence, not validation of the FEA physics. The SVG is
    built only from the same raw solver-derived render payload used by the native
    Results tab. Von Mises preserves the explicit per-element max of four TET10
    integration points; no nodal extrapolation, averaging or smoothing is added.
    """
    if converged_claim or industrial_validation_claim or ansys_equivalence_claim:
        raise ValueError("REPORT_EVIDENCE_FALSE_CLAIM_REFUSED")
    if int(width_px) < 640 or int(height_px) < 360:
        raise ValueError("REPORT_EVIDENCE_CANVAS_TOO_SMALL")
    _validate_sha(workspace.workspace_sha256, "REPORT_EVIDENCE_WORKSPACE_SHA_INVALID")
    _validate_sha(workspace.solve_evidence_sha256, "REPORT_EVIDENCE_SOLVE_SHA_INVALID")

    payload = build_results_render_payload(
        workspace,
        nodes_mm,
        elements,
        result,
        field=field,
        deformation_scale=deformation_scale,
    )
    if payload.workspace_sha256 != workspace.workspace_sha256:
        raise ValueError("REPORT_EVIDENCE_WORKSPACE_STALE")
    if payload.solve_evidence_sha256 != workspace.solve_evidence_sha256:
        raise ValueError("REPORT_EVIDENCE_SOLVE_STALE")

    render_view_sha256 = canonical_sha256(_view_payload(payload, width_px, height_px))
    mapped = _canvas_transform(np.asarray(payload.projected_nodes_xy, dtype=float), width_px * 0.72, height_px - 150.0)
    undeformed = _canvas_transform(np.asarray(payload.undeformed_nodes_xy, dtype=float), width_px * 0.72, height_px - 150.0)

    plot_x = 28.0
    plot_y = 92.0
    plot_w = width_px * 0.72
    plot_h = height_px - 120.0
    side_x = plot_x + plot_w + 34.0
    field_label = escape(f"{payload.field} [{payload.unit}]")
    stress_representation = (
        "FOUR_INTEGRATION_POINTS_PRESERVED_ELEMENT_MAX_ONLY_NO_NODAL_SMOOTHING"
        if payload.field == "VON_MISES_IP_MAX"
        else "NODAL_DISPLACEMENT_MAGNITUDE_FROM_SOLVER"
    )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}">',
        '<rect width="100%" height="100%" fill="#101820"/>',
        '<text x="28" y="38" fill="#f4f7fa" font-family="Segoe UI,Arial" font-size="24" font-weight="700">AsterMax PMV · Report-grade result evidence</text>',
        f'<text x="28" y="65" fill="#9fb3c8" font-family="Consolas,monospace" font-size="12">view={render_view_sha256} · workspace={workspace.workspace_sha256} · solve={workspace.solve_evidence_sha256}</text>',
        f'<rect x="{plot_x:.3f}" y="{plot_y:.3f}" width="{plot_w:.3f}" height="{plot_h:.3f}" rx="8" fill="#111c26" stroke="#334a5f"/>',
    ]

    for tri in sorted(payload.triangles, key=lambda item: item.element_id, reverse=True):
        pts = " ".join(f"{plot_x + mapped[nid, 0]:.6f},{plot_y + mapped[nid, 1]:.6f}" for nid in tri.node_ids)
        color = _scalar_hex(tri.value, payload.value_min, payload.value_max)
        lines.append(
            f'<polygon points="{pts}" fill="{color}" stroke="#26394b" stroke-width="1" data-element="{tri.element_id}" data-value="{tri.value:.17g}"/>'
        )
    for tri in payload.triangles:
        pts = " ".join(f"{plot_x + undeformed[nid, 0]:.6f},{plot_y + undeformed[nid, 1]:.6f}" for nid in tri.node_ids)
        lines.append(f'<polygon points="{pts}" fill="none" stroke="#d6e0e8" stroke-width="0.8" stroke-dasharray="4 4" opacity="0.75"/>')

    lines.extend([
        f'<text x="{side_x:.3f}" y="118" fill="#f4f7fa" font-family="Segoe UI,Arial" font-size="18" font-weight="700">{field_label}</text>',
        f'<text x="{side_x:.3f}" y="150" fill="#d9e3ec" font-family="Segoe UI,Arial" font-size="14">min = {payload.value_min:.9g} {escape(payload.unit)}</text>',
        f'<text x="{side_x:.3f}" y="174" fill="#d9e3ec" font-family="Segoe UI,Arial" font-size="14">max = {payload.value_max:.9g} {escape(payload.unit)}</text>',
        f'<text x="{side_x:.3f}" y="198" fill="#d9e3ec" font-family="Segoe UI,Arial" font-size="14">deformation scale = {payload.deformation_scale:.9g}</text>',
        f'<text x="{side_x:.3f}" y="238" fill="#8fa8bd" font-family="Consolas,monospace" font-size="11">workspace</text>',
        f'<text x="{side_x:.3f}" y="255" fill="#d9e3ec" font-family="Consolas,monospace" font-size="10">{workspace.workspace_sha256}</text>',
        f'<text x="{side_x:.3f}" y="286" fill="#8fa8bd" font-family="Consolas,monospace" font-size="11">solve evidence</text>',
        f'<text x="{side_x:.3f}" y="303" fill="#d9e3ec" font-family="Consolas,monospace" font-size="10">{workspace.solve_evidence_sha256}</text>',
        f'<text x="{side_x:.3f}" y="346" fill="#ffcf70" font-family="Segoe UI,Arial" font-size="12">PMV evidence only</text>',
        f'<text x="{side_x:.3f}" y="365" fill="#c7d3dd" font-family="Segoe UI,Arial" font-size="11">converged = false</text>',
        f'<text x="{side_x:.3f}" y="383" fill="#c7d3dd" font-family="Segoe UI,Arial" font-size="11">industrial validation = false</text>',
        f'<text x="{side_x:.3f}" y="401" fill="#c7d3dd" font-family="Segoe UI,Arial" font-size="11">ANSYS equivalence = false</text>',
        f'<text x="{side_x:.3f}" y="438" fill="#8fa8bd" font-family="Segoe UI,Arial" font-size="10">{escape(stress_representation)}</text>',
        '</svg>',
    ])

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    svg_sha256 = sha256_file(target)
    return ReportGradeEvidenceManifestV1(
        schema="AsterMaxReportGradeEvidenceV1",
        field=payload.field,
        unit=payload.unit,
        workspace_sha256=workspace.workspace_sha256,
        solve_evidence_sha256=workspace.solve_evidence_sha256,
        render_view_sha256=render_view_sha256,
        svg_sha256=svg_sha256,
        width_px=int(width_px),
        height_px=int(height_px),
        deformation_scale=payload.deformation_scale,
        value_min=payload.value_min,
        value_max=payload.value_max,
        stress_representation=stress_representation,
        converged=False,
        industrial_validation=False,
        ansys_equivalence=False,
    )


def verify_report_grade_svg_evidence(path: str | Path, manifest: ReportGradeEvidenceManifestV1) -> None:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError("REPORT_EVIDENCE_SVG_MISSING")
    _validate_sha(manifest.render_view_sha256, "REPORT_EVIDENCE_VIEW_SHA_INVALID")
    _validate_sha(manifest.svg_sha256, "REPORT_EVIDENCE_SVG_SHA_INVALID")
    if sha256_file(target) != manifest.svg_sha256:
        raise ValueError("REPORT_EVIDENCE_SVG_TAMPERED")
    if manifest.converged or manifest.industrial_validation or manifest.ansys_equivalence:
        raise ValueError("REPORT_EVIDENCE_FALSE_CLAIM_REFUSED")
