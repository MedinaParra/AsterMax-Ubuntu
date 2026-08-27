from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any


PASSPORT_SCHEMA = "AsterMaxAnalysisPassportV1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_analysis_passport(summary: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic evidence vector from an AsterMax project result.

    This function never upgrades convergence, validation or equivalence claims.
    It only summarizes evidence already present in the project result.
    """
    claims = dict(summary.get("claims", {}))
    sampled = summary.get("tet10_sampled_jacobian", {})
    dense = summary.get("tet10_reference_jacobian", {})
    adaptive = summary.get("tet10_adaptive_jacobian", {})
    geometry_scope = summary.get("tet10_geometry_scope", {})
    mesh_quality = summary.get("mesh_quality", {})
    checks = summary.get("checks", {})
    provenance = summary.get("provenance", {})
    artifacts = summary.get("artifacts", {})

    geometry_provenance = bool(provenance.get("geometry_sha256"))
    persistent_scopes = bool(
        provenance.get("support_surface_sha256")
        and provenance.get("load_surface_sha256")
        and summary.get("selection_mode") == "PERSISTENT_CAD_SURFACE_SIGNATURES"
    )
    jacobian_v1 = sampled.get("status") == "PASS"
    jacobian_v2 = dense.get("status") == "PASS"
    jacobian_v3 = adaptive.get("status") == "PASS"
    straight_scope = geometry_scope.get("status") == "PASS"
    mesh_pass = mesh_quality.get("status") == "PASS"

    force_residual = float(checks.get("force_residual_n", float("inf")))
    moment_residual = float(checks.get("moment_residual_nmm", float("inf")))
    force_balance = force_residual <= 1.0e-5
    moment_balance = moment_residual <= 1.0e-3
    equilibrium = force_balance and moment_balance

    computed = bool(artifacts.get("vtu") and artifacts.get("viewer"))
    geometry_mesh_verified = all(
        [geometry_provenance, persistent_scopes, jacobian_v1, jacobian_v2, jacobian_v3, straight_scope, mesh_pass]
    )

    if equilibrium and geometry_mesh_verified and computed:
        highest_demonstrated_stage = "EQUILIBRIUM_VERIFIED"
    elif geometry_mesh_verified and computed:
        highest_demonstrated_stage = "GEOMETRY_AND_MESH_VERIFIED"
    elif computed:
        highest_demonstrated_stage = "COMPUTED"
    else:
        highest_demonstrated_stage = "INCOMPLETE"

    evidence_vector = {
        "geometry_provenance": {"status": "VERIFIED" if geometry_provenance else "MISSING"},
        "persistent_cad_scopes": {"status": "VERIFIED" if persistent_scopes else "MISSING"},
        "tet10_jacobian_v1": {"status": "PASS" if jacobian_v1 else "FAIL_OR_MISSING"},
        "tet10_jacobian_v2": {"status": "PASS" if jacobian_v2 else "FAIL_OR_MISSING"},
        "tet10_jacobian_v3": {"status": "PASS" if jacobian_v3 else "FAIL_OR_MISSING"},
        "tet10_solver_scope": {"status": "PASS" if straight_scope else "FAIL_OR_MISSING"},
        "mesh_quality": {"status": "PASS" if mesh_pass else str(mesh_quality.get("status", "MISSING"))},
        "force_balance": {"status": "PASS" if force_balance else "FAIL", "residual_n": force_residual},
        "moment_balance": {"status": "PASS" if moment_balance else "FAIL", "residual_nmm": moment_residual},
        "solution_convergence": {"status": "VERIFIED" if claims.get("converged") is True else "NOT_DEMONSTRATED"},
        "industrial_validation": {"status": "VERIFIED" if claims.get("industrial_validation") is True else "NOT_DEMONSTRATED"},
        "ansys_equivalence": {"status": "VERIFIED" if claims.get("ansys_equivalence") is True else "NOT_CLAIMED"},
        "curved_tet10": {"status": "ENABLED" if claims.get("curved_tet10") is True else "OUT_OF_SCOPE"},
        "global_jacobian_positivity": {
            "status": "PROVED" if claims.get("global_jacobian_positivity_proved") is True else "NOT_PROVED"
        },
    }

    return {
        "schema": PASSPORT_SCHEMA,
        "result_class": summary.get("result_class", "ASTERMAX_PROJECT_UNCONVERGED_NOT_INDUSTRIAL_RESULT"),
        "highest_demonstrated_stage": highest_demonstrated_stage,
        "evidence_vector": evidence_vector,
        "claim_guards": {
            "converged": claims.get("converged") is True,
            "industrial_validation": claims.get("industrial_validation") is True,
            "ansys_equivalence": claims.get("ansys_equivalence") is True,
            "curved_tet10": claims.get("curved_tet10") is True,
            "global_jacobian_positivity_proved": claims.get("global_jacobian_positivity_proved") is True,
        },
        "provenance": provenance,
        "evidence_boundary": (
            "PASSPORT_SUMMARIZES_RECORDED_EVIDENCE_ONLY;_NO_TRUST_SCORE;_"
            "NO_AUTOMATIC_CONVERGENCE_VALIDATION_OR_EQUIVALENCE_UPGRADE"
        ),
    }


def write_analysis_passport(path: str | Path, summary: dict[str, Any]) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    passport = build_analysis_passport(summary)
    rows = []
    for name, record in passport["evidence_vector"].items():
        status = str(record["status"])
        detail = ""
        if "residual_n" in record:
            detail = f"{record['residual_n']:.6g} N"
        elif "residual_nmm" in record:
            detail = f"{record['residual_nmm']:.6g} N·mm"
        rows.append(
            "<tr><td>" + html.escape(name.replace("_", " ").title()) + "</td>"
            + "<td><strong>" + html.escape(status) + "</strong></td>"
            + "<td>" + html.escape(detail) + "</td></tr>"
        )
    provenance_rows = "".join(
        f"<li><code>{html.escape(str(k))}</code>: <code>{html.escape(str(v))}</code></li>"
        for k, v in passport["provenance"].items()
    )
    payload = json.dumps(passport, indent=2, sort_keys=True)
    document = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>AsterMax Analysis Passport</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#11151a;color:#eef2f5;margin:0}}
main{{max-width:1050px;margin:auto;padding:32px}} .hero{{border:1px solid #38424d;border-radius:14px;padding:24px;background:#171d23}}
.stage{{font-size:28px;font-weight:700;margin:8px 0 18px}} table{{width:100%;border-collapse:collapse;margin-top:22px}}
th,td{{padding:11px;border-bottom:1px solid #303942;text-align:left}} th{{color:#aeb9c4}}
.note{{margin-top:22px;padding:14px;border-left:4px solid #8b98a5;background:#1b2229}}
code{{font-family:Consolas,monospace;font-size:12px;word-break:break-all}} details{{margin-top:24px}}
</style></head><body><main>
<section class='hero'><div>ASTERMAX ANALYSIS PASSPORT</div><div class='stage'>{html.escape(passport['highest_demonstrated_stage'])}</div>
<div>Evidence vector — no scalar trust score.</div></section>
<table><thead><tr><th>Evidence dimension</th><th>Status</th><th>Metric</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class='note'><strong>Evidence boundary.</strong> {html.escape(passport['evidence_boundary'])}</div>
<h3>Provenance</h3><ul>{provenance_rows}</ul>
<details><summary>Machine-readable passport</summary><pre>{html.escape(payload)}</pre></details>
</main></body></html>"""
    target.write_text(document, encoding="utf-8")
    return {**passport, "html_sha256": _sha256_file(target), "path": str(target)}
