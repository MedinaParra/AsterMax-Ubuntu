from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np

from .evidence import sha256_file
from .report_evidence import (
    ReportGradeEvidenceManifestV1,
    verify_report_grade_svg_evidence,
    write_report_grade_svg_evidence,
)
from .results_workspace import AsterMaxProfessionalResultsWorkspaceV1
from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class ProfessionalEvidenceBundleManifestV1:
    schema: str
    workspace_sha256: str
    solve_evidence_sha256: str
    displacement_svg: ReportGradeEvidenceManifestV1
    von_mises_svg: ReportGradeEvidenceManifestV1
    index_html_sha256: str
    manifest_sha256: str
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool


def _manifest_payload(
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    displacement: ReportGradeEvidenceManifestV1,
    von_mises: ReportGradeEvidenceManifestV1,
    index_html_sha256: str,
) -> dict:
    return {
        "schema": "AsterMaxProfessionalEvidenceBundleV1",
        "workspace_sha256": workspace.workspace_sha256,
        "solve_evidence_sha256": workspace.solve_evidence_sha256,
        "files": {
            "displacement_svg": {
                "filename": "displacement.svg",
                "sha256": displacement.svg_sha256,
                "render_view_sha256": displacement.render_view_sha256,
                "field": displacement.field,
                "unit": displacement.unit,
                "value_min": displacement.value_min,
                "value_max": displacement.value_max,
                "deformation_scale": displacement.deformation_scale,
            },
            "von_mises_svg": {
                "filename": "von_mises.svg",
                "sha256": von_mises.svg_sha256,
                "render_view_sha256": von_mises.render_view_sha256,
                "field": von_mises.field,
                "unit": von_mises.unit,
                "value_min": von_mises.value_min,
                "value_max": von_mises.value_max,
                "deformation_scale": von_mises.deformation_scale,
                "stress_representation": von_mises.stress_representation,
            },
            "index_html": {
                "filename": "index.html",
                "sha256": index_html_sha256,
            },
        },
        "claims": {
            "converged": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        },
    }


def _index_html(
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    displacement: ReportGradeEvidenceManifestV1,
    von_mises: ReportGradeEvidenceManifestV1,
) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>AsterMax PMV · Evidence Bundle</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0f1720;color:#e8eef5;margin:0;padding:24px}}
main{{max-width:1500px;margin:auto}} h1{{margin:0 0 6px}} .muted{{color:#9fb3c8}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:22px}}
.card{{background:#16212c;border:1px solid #334a5f;border-radius:10px;padding:14px}}
img{{width:100%;display:block;background:#101820;border-radius:6px}}
code{{word-break:break-all;color:#cdd9e5}} .boundary{{margin-top:22px;padding:14px;border-left:4px solid #ffcf70;background:#1b2732}}
@media(max-width:1000px){{.grid{{grid-template-columns:1fr}}}}
</style></head>
<body><main>
<h1>AsterMax PMV · Professional Evidence Bundle</h1>
<div class=\"muted\">Deterministic postprocess evidence bound to one exact workspace and solve provenance chain.</div>
<div class=\"grid\">
<section class=\"card\"><h2>Displacement magnitude</h2><img src=\"displacement.svg\" alt=\"Displacement evidence\"><p>Range: {displacement.value_min:.9g} to {displacement.value_max:.9g} {displacement.unit}</p></section>
<section class=\"card\"><h2>Von Mises</h2><img src=\"von_mises.svg\" alt=\"Von Mises evidence\"><p>Range: {von_mises.value_min:.9g} to {von_mises.value_max:.9g} {von_mises.unit}</p><p class=\"muted\">{von_mises.stress_representation}</p></section>
</div>
<section class=\"card\"><h2>Provenance</h2><p>Workspace SHA-256<br><code>{workspace.workspace_sha256}</code></p><p>Solve evidence SHA-256<br><code>{workspace.solve_evidence_sha256}</code></p></section>
<section class=\"boundary\"><strong>Claim boundary:</strong> PMV evidence only. converged=false · industrial_validation=false · ANSYS_equivalence=false. No nodal stress smoothing or extrapolation is introduced by this bundle.</section>
</main></body></html>\n"""


def write_professional_evidence_bundle(
    output_dir: str | Path,
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    deformation_scale: float | None = None,
) -> ProfessionalEvidenceBundleManifestV1:
    """Write a deterministic two-field report bundle from one exact solve/workspace.

    The bundle is presentation/evidence infrastructure only. It preserves the
    existing raw-result semantics and always refuses convergence, industrial
    validation and ANSYS-equivalence claims.
    """
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    displacement_path = output / "displacement.svg"
    von_mises_path = output / "von_mises.svg"
    index_path = output / "index.html"
    manifest_path = output / "manifest.json"

    displacement = write_report_grade_svg_evidence(
        displacement_path,
        workspace,
        nodes_mm,
        elements,
        result,
        field="U_MAG",
        deformation_scale=deformation_scale,
    )
    von_mises = write_report_grade_svg_evidence(
        von_mises_path,
        workspace,
        nodes_mm,
        elements,
        result,
        field="VON_MISES_IP_MAX",
        deformation_scale=deformation_scale,
    )
    verify_report_grade_svg_evidence(displacement_path, displacement)
    verify_report_grade_svg_evidence(von_mises_path, von_mises)

    if displacement.workspace_sha256 != von_mises.workspace_sha256:
        raise ValueError("EVIDENCE_BUNDLE_WORKSPACE_MISMATCH")
    if displacement.solve_evidence_sha256 != von_mises.solve_evidence_sha256:
        raise ValueError("EVIDENCE_BUNDLE_SOLVE_MISMATCH")

    index_path.write_text(_index_html(workspace, displacement, von_mises), encoding="utf-8", newline="\n")
    index_sha = sha256_file(index_path)
    payload = _manifest_payload(workspace, displacement, von_mises, index_sha)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    manifest_sha = sha256_file(manifest_path)

    return ProfessionalEvidenceBundleManifestV1(
        schema="AsterMaxProfessionalEvidenceBundleV1",
        workspace_sha256=workspace.workspace_sha256,
        solve_evidence_sha256=workspace.solve_evidence_sha256,
        displacement_svg=displacement,
        von_mises_svg=von_mises,
        index_html_sha256=index_sha,
        manifest_sha256=manifest_sha,
        converged=False,
        industrial_validation=False,
        ansys_equivalence=False,
    )


def verify_professional_evidence_bundle(
    output_dir: str | Path,
    manifest: ProfessionalEvidenceBundleManifestV1,
) -> None:
    output = Path(output_dir).expanduser().resolve()
    displacement_path = output / "displacement.svg"
    von_mises_path = output / "von_mises.svg"
    index_path = output / "index.html"
    manifest_path = output / "manifest.json"

    if manifest.converged or manifest.industrial_validation or manifest.ansys_equivalence:
        raise ValueError("EVIDENCE_BUNDLE_FALSE_CLAIM_REFUSED")
    verify_report_grade_svg_evidence(displacement_path, manifest.displacement_svg)
    verify_report_grade_svg_evidence(von_mises_path, manifest.von_mises_svg)
    if manifest.workspace_sha256 != manifest.displacement_svg.workspace_sha256 or manifest.workspace_sha256 != manifest.von_mises_svg.workspace_sha256:
        raise ValueError("EVIDENCE_BUNDLE_WORKSPACE_MISMATCH")
    if manifest.solve_evidence_sha256 != manifest.displacement_svg.solve_evidence_sha256 or manifest.solve_evidence_sha256 != manifest.von_mises_svg.solve_evidence_sha256:
        raise ValueError("EVIDENCE_BUNDLE_SOLVE_MISMATCH")
    if sha256_file(index_path) != manifest.index_html_sha256:
        raise ValueError("EVIDENCE_BUNDLE_INDEX_TAMPERED")
    if sha256_file(manifest_path) != manifest.manifest_sha256:
        raise ValueError("EVIDENCE_BUNDLE_MANIFEST_TAMPERED")

    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    if persisted != _manifest_payload(workspace=_WorkspaceIdentity(manifest.workspace_sha256, manifest.solve_evidence_sha256), displacement=manifest.displacement_svg, von_mises=manifest.von_mises_svg, index_html_sha256=manifest.index_html_sha256):
        raise ValueError("EVIDENCE_BUNDLE_MANIFEST_CONTENT_MISMATCH")


@dataclass(frozen=True)
class _WorkspaceIdentity:
    workspace_sha256: str
    solve_evidence_sha256: str
