#!/usr/bin/env python3
"""Build the C10.20 workflow-conformance JSON/HTML report from real evidence files."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path

STATUS = {"PASS", "FAIL", "NOT_EXERCISED"}

p = argparse.ArgumentParser()
p.add_argument("--contract", required=True)
p.add_argument("--session", required=True)
p.add_argument("--outdir", required=True)
args = p.parse_args()
contract_path = Path(args.contract).resolve()
session_path = Path(args.session).resolve()
outdir = Path(args.outdir).resolve()
outdir.mkdir(parents=True, exist_ok=True)
contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
session = json.loads(session_path.read_text(encoding="utf-8-sig"))
raw_rows = {row.get("stage"): row for row in session.get("rows", []) if isinstance(row, dict)}
rows = []

for stage in contract.get("stages", []):
    sid = stage["id"]
    raw = raw_rows.get(sid, {})
    expected_evidence = list(stage.get("evidence", []))
    evidence = []
    all_present = True
    for name in expected_evidence:
        path = outdir / name
        present = path.is_file() and path.stat().st_size > 0
        all_present &= present
        evidence.append({"name": name, "present": present, "bytes": path.stat().st_size if present else 0})
    raw_status = raw.get("status", "NOT_EXERCISED")
    if raw_status not in STATUS:
        raw_status = "FAIL"
    status = "FAIL" if raw_status == "FAIL" else (raw_status if all_present else "NOT_EXERCISED")
    rows.append({
        "id": sid,
        "label": stage.get("label", sid),
        "mandatory": bool(stage.get("mandatory", False)),
        "workflow_state_key": stage.get("workflow_state_key"),
        "status": status,
        "raw_status": raw_status,
        "before": raw.get("before"),
        "after": raw.get("after"),
        "expected": raw.get("expected") or stage.get("postconditions", []),
        "error": raw.get("error"),
        "evidence": evidence,
        "evidence_complete": all_present,
    })

mandatory_failures = sum(1 for row in rows if row["mandatory"] and row["status"] == "FAIL")
mandatory_not_exercised = sum(1 for row in rows if row["mandatory"] and row["status"] == "NOT_EXERCISED")
mandatory_pass = sum(1 for row in rows if row["mandatory"] and row["status"] == "PASS")

cross = session.get("cross_cutting") or {}
cross_checks = cross.get("checks") or []
cross_failures = sum(1 for item in cross_checks if item.get("status") == "FAIL")
cross_not_exercised = sum(1 for item in cross_checks if item.get("status") == "NOT_EXERCISED")
required_cross = set(contract.get("cross_cutting_checks", []))
missing_cross = sorted(required_cross - {item.get("id") for item in cross_checks})
session_failed = (session.get("pass") is not True or bool(session.get("partial")) or
                  bool(session.get("error")) or session.get("process_exit_code", 0) != 0)
release_gate_pass = (not session_failed and mandatory_failures == 0 and
                     mandatory_not_exercised == 0 and cross_failures == 0 and not missing_cross and bool(rows))
closure_candidate = (
    release_gate_pass and not missing_cross and
    mandatory_failures == 0 and mandatory_not_exercised == 0 and
    cross_failures == 0 and cross_not_exercised == 0 and len(rows) == len(contract.get("stages", []))
)

report = {
    "schema": "astermax-workflow-conformance-report/v1",
    "release": "C10.20.5",
    "reference_fixture": session.get("reference_fixture", contract.get("reference", {}).get("fixture_used_when_preferred_absent")),
    "contract": str(contract_path.name),
    "session": str(session_path.name),
    "evidence_rule": contract.get("evidence_rule"),
    "rows": rows,
    "cross_cutting": cross,
    "session_error": session.get("error"),
    "process_exit_code": session.get("process_exit_code"),
    "summary": {
        "session_failed": session_failed,
        "release_gate_pass": release_gate_pass,
        "missing_cross_checks": missing_cross,
        "mandatory_pass": mandatory_pass,
        "mandatory_failures": mandatory_failures,
        "mandatory_not_exercised": mandatory_not_exercised,
        "cross_failures": cross_failures,
        "cross_not_exercised": cross_not_exercised,
        "closure_candidate": closure_candidate,
        "historical_pending_closed": False,
        "reason": "Closure is not asserted by the generator. It requires review of the uploaded Windows CI artifact."
    },
    "claims": {
        "ansys_equivalence": "NOT_CLAIMED",
        "fea_values_invented": False,
        "not_exercised_counts_as_pass": False
    }
}
json_path = outdir / "workflow-conformance-report.json"
json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

def status_cell(value: str) -> str:
    return f'<strong>{html.escape(value)}</strong>'

def evidence_links(items):
    parts = []
    for item in items:
        name = item["name"]
        if item["present"]:
            parts.append(f'<a href="{html.escape(name)}">{html.escape(name)}</a> ({item["bytes"]} B)')
        else:
            parts.append(f'{html.escape(name)} — MISSING')
    return "<br>".join(parts)

stage_html = []
for row in rows:
    stage_html.append(
        "<tr>"
        f"<td>{html.escape(row['label'])}</td>"
        f"<td>{'yes' if row['mandatory'] else 'no'}</td>"
        f"<td>{status_cell(row['status'])}</td>"
        f"<td>{html.escape(str(row['workflow_state_key']))}</td>"
        f"<td>{html.escape(str(row['before']))} → {html.escape(str(row['after']))}</td>"
        f"<td>{evidence_links(row['evidence'])}</td>"
        "</tr>"
    )

cross_html = []
for item in cross_checks:
    cross_html.append(
        "<tr>"
        f"<td>{html.escape(str(item.get('id')))}</td>"
        f"<td>{status_cell(str(item.get('status')))}</td>"
        f"<td>{html.escape(str(item.get('reason', '')))}</td>"
        "</tr>"
    )

html_text = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AsterMax C10.20 Workflow Conformance</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#20252b}} table{{border-collapse:collapse;width:100%;margin:16px 0 28px}}
th,td{{border:1px solid #ccd3da;padding:8px;vertical-align:top}} th{{background:#f0f3f6;text-align:left}}
code{{background:#f4f4f4;padding:2px 4px}} .notice{{padding:12px;border:1px solid #ccd3da;background:#fafafa}}
</style></head><body>
<h1>AsterMax C10.20 — Windows workflow conformance</h1>
<div class="notice">PASS requires all four stage evidence files. Missing evidence is <strong>NOT_EXERCISED</strong>, never PASS. This report does not assert ANSYS equivalence or historical-finding closure.</div>
<p><strong>Reference fixture:</strong> {html.escape(str(report['reference_fixture']))}</p>
<p><strong>Mandatory:</strong> PASS {mandatory_pass}, FAIL {mandatory_failures}, NOT_EXERCISED {mandatory_not_exercised}. <strong>Closure candidate:</strong> {str(closure_candidate).lower()}.</p>
<p><strong>Release gate:</strong> {str(release_gate_pass).lower()}. <strong>Session error:</strong> {html.escape(str(session.get("error") or "none"))}</p>
<h2>Mandatory workflow stages</h2>
<table><thead><tr><th>Stage</th><th>Mandatory</th><th>Status</th><th>Workflow state</th><th>Transition</th><th>Evidence</th></tr></thead>
<tbody>{''.join(stage_html)}</tbody></table>
<h2>Cross-cutting checks</h2>
<table><thead><tr><th>Check</th><th>Status</th><th>Reason / scope</th></tr></thead><tbody>{''.join(cross_html)}</tbody></table>
<h2>Limits</h2>
<p>Ribbon/menu traversal records command surfaces and bindings; it is not a claim that every destructive or modal command completed successfully. A fixed-DPI hosted runner may leave the DPI transition as NOT_EXERCISED. Numerical ANSYS equivalence is outside this report.</p>
</body></html>"""
(outdir / "workflow-conformance-report.html").write_text(html_text, encoding="utf-8")
print(f"WORKFLOW_REPORT_JSON={json_path}")
print(f"MANDATORY_PASS={mandatory_pass}")
print(f"MANDATORY_FAIL={mandatory_failures}")
print(f"MANDATORY_NOT_EXERCISED={mandatory_not_exercised}")
print(f"CLOSURE_CANDIDATE={str(closure_candidate).lower()}")
