from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CredibilityVisualizationError(ValueError):
    pass


@dataclass(frozen=True)
class CredibilityVisualizationManifest:
    schema: str
    source_schema: str
    step_sha256: str
    section_sha256: str
    witness_sha256: str
    mesh_sizes_mm: tuple[float, ...]
    rms_relative_errors: tuple[float, ...]
    maximum_relative_errors: tuple[float, ...]
    fixture_convergence_claim: bool
    arbitrary_model_convergence: bool
    industrial_validation: bool
    ansys_equivalence: bool
    html_sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(name: str, value: Any) -> str:
    digest = str(value).lower().strip()
    if not _SHA256_RE.fullmatch(digest):
        raise CredibilityVisualizationError(f"{name} must be a lowercase SHA-256 digest")
    return digest


def _relative_rms(level: dict[str, Any], analytical_sigma_mpa: float) -> float:
    sigma = abs(float(analytical_sigma_mpa))
    if sigma <= 0.0:
        raise CredibilityVisualizationError("analytical_sigma_mpa must be non-zero")
    return abs(float(level["rms_error_mpa"])) / sigma


def validate_c3_2_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema") != "AsterMaxC3_2CadDerivedAxialBenchmarkV1":
        raise CredibilityVisualizationError("unsupported C3.2 benchmark schema")
    provenance = payload.get("provenance") or {}
    witness = payload.get("cad_analytical_witness") or {}
    claims = payload.get("claims") or {}
    _require_hash("source_sha256", provenance.get("source_sha256"))
    _require_hash("section_sha256", provenance.get("section_sha256"))
    _require_hash("witness_sha256", witness.get("witness_sha256"))
    if provenance.get("section_sha256") != witness.get("section_sha256"):
        raise CredibilityVisualizationError("section SHA mismatch between provenance and witness")
    if provenance.get("source_sha256") != witness.get("source_sha256"):
        raise CredibilityVisualizationError("STEP SHA mismatch between provenance and witness")
    if provenance.get("same_step_drives_meshing_and_analytical_reference") is not True:
        raise CredibilityVisualizationError("same STEP must drive analytical reference and FEA mesh")
    levels = payload.get("levels") or []
    if len(levels) != 3:
        raise CredibilityVisualizationError("C4 requires exactly three refinement levels")
    sizes = [float(row["level"]["mesh_size_mm"]) for row in levels]
    if not (sizes[0] > sizes[1] > sizes[2] > 0.0):
        raise CredibilityVisualizationError("refinement levels must be ordered coarse to fine")
    if claims.get("arbitrary_model_convergence") is not False:
        raise CredibilityVisualizationError("C4 refuses arbitrary-model convergence claims")
    if claims.get("industrial_validation") is not False:
        raise CredibilityVisualizationError("C4 refuses industrial-validation claims")
    if claims.get("ansys_equivalence") is not False:
        raise CredibilityVisualizationError("C4 refuses ANSYS-equivalence claims")


def render_credibility_html(payload: dict[str, Any], output_path: str | Path) -> CredibilityVisualizationManifest:
    validate_c3_2_payload(payload)
    output = Path(output_path)
    provenance = payload["provenance"]
    witness = payload["cad_analytical_witness"]
    claims = payload["claims"]
    levels = payload["levels"]
    analytical_sigma = float(witness["analytical_sigma_mpa"])
    sizes = tuple(float(row["level"]["mesh_size_mm"]) for row in levels)
    rms = tuple(_relative_rms(row["level"], analytical_sigma) for row in levels)
    maxerr = tuple(float(row["level"]["maximum_relative_error"]) for row in levels)

    width, height, pad = 520.0, 220.0, 40.0
    ymax = max(max(rms), max(maxerr), 1.0e-12)
    xs = [pad + i * (width - 2 * pad) / (len(sizes) - 1) for i in range(len(sizes))]
    def y(v: float) -> float:
        return height - pad - (v / ymax) * (height - 2 * pad)
    rms_points = " ".join(f"{x:.2f},{y(v):.2f}" for x, v in zip(xs, rms))
    max_points = " ".join(f"{x:.2f},{y(v):.2f}" for x, v in zip(xs, maxerr))
    rows = "".join(
        f"<tr><td>{size:g}</td><td>{100*r:.4f}%</td><td>{100*m:.4f}%</td></tr>"
        for size, r, m in zip(sizes, rms, maxerr)
    )
    status = "PERMITTED" if claims["stress_convergence_for_this_axial_fixture"] else "BLOCKED"
    doc = f"""<!doctype html><html><head><meta charset='utf-8'><title>AsterMax Credibility Chain</title>
<style>body{{font-family:Segoe UI,Arial;background:#111827;color:#e5e7eb;margin:0;padding:28px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card{{background:#1f2937;padding:16px;border-radius:10px}}code{{font-size:11px;word-break:break-all}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #374151;text-align:right}}td:first-child,th:first-child{{text-align:left}}.ok{{color:#86efac}}.blocked{{color:#fca5a5}}svg{{background:#fff;border-radius:8px;width:100%;max-width:640px}}</style></head><body>
<h1>AsterMax — Evidence Chain</h1><p>Fixture-scoped verification. No ANSYS equivalence or industrial validation is claimed.</p>
<div class='grid'><div class='card'><b>STEP identity</b><br><code>{html.escape(provenance['source_sha256'])}</code></div><div class='card'><b>OCC section</b><br>{float(witness['area_mm2']):.6g} mm²<br><code>{html.escape(provenance['section_sha256'])}</code></div><div class='card'><b>Analytical witness</b><br>σ = F/A = {analytical_sigma:.6g} MPa<br><code>{html.escape(witness['witness_sha256'])}</code></div><div class='card'><b>Claim</b><br><span class='{'ok' if status == 'PERMITTED' else 'blocked'}'>{status}</span><br>axial fixture only</div></div>
<h2>Mesh refinement evidence</h2><svg viewBox='0 0 {width:g} {height:g}' aria-label='refinement error plot'><polyline fill='none' stroke='#2563eb' stroke-width='3' points='{rms_points}'/><polyline fill='none' stroke='#dc2626' stroke-width='3' points='{max_points}'/></svg>
<table><thead><tr><th>Mesh size (mm)</th><th>RMS relative error</th><th>Max relative error</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Claim boundary</h2><ul><li>CAD-derived reference: {claims['cad_derived_reference']}</li><li>Fixture stress convergence: {claims['stress_convergence_for_this_axial_fixture']}</li><li>Arbitrary-model convergence: false</li><li>Industrial validation: false</li><li>ANSYS equivalence: false</li></ul>
</body></html>"""
    output.write_text(doc, encoding="utf-8")
    return CredibilityVisualizationManifest(
        schema="AsterMaxCredibilityVisualizationManifestV1",
        source_schema=payload["schema"],
        step_sha256=provenance["source_sha256"],
        section_sha256=provenance["section_sha256"],
        witness_sha256=witness["witness_sha256"],
        mesh_sizes_mm=sizes,
        rms_relative_errors=rms,
        maximum_relative_errors=maxerr,
        fixture_convergence_claim=bool(claims["stress_convergence_for_this_axial_fixture"]),
        arbitrary_model_convergence=False,
        industrial_validation=False,
        ansys_equivalence=False,
        html_sha256=_sha256(output),
    )


def render_from_json(input_path: str | Path, output_path: str | Path) -> CredibilityVisualizationManifest:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    return render_credibility_html(payload, output_path)
