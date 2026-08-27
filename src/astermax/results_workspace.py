from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any


WORKSPACE_SCHEMA = "AsterMaxResultsEvidenceWorkspaceV1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_child(workspace: Path, child: Path) -> str:
    resolved_parent = workspace.parent.resolve()
    resolved_child = child.resolve()
    try:
        return resolved_child.relative_to(resolved_parent).as_posix()
    except ValueError as exc:
        raise ValueError("workspace child artifact must be inside the workspace output directory") from exc


def build_results_workspace_manifest(summary: dict[str, Any], workspace_path: str | Path) -> dict[str, Any]:
    workspace = Path(workspace_path)
    artifacts = dict(summary.get("artifacts", {}))
    required = {
        "results": ("viewer", "viewer_sha256"),
        "mesh": ("mesh_inspector", "mesh_inspector_sha256"),
        "evidence": ("analysis_passport", "analysis_passport_sha256"),
    }
    panels: dict[str, dict[str, Any]] = {}
    for panel, (path_key, hash_key) in required.items():
        raw_path = artifacts.get(path_key)
        expected_hash = artifacts.get(hash_key)
        if not raw_path or not expected_hash:
            raise ValueError(f"missing required workspace artifact metadata: {path_key}/{hash_key}")
        child = Path(str(raw_path))
        if not child.is_file():
            raise ValueError(f"missing required workspace artifact: {child}")
        actual_hash = _sha256_file(child)
        if actual_hash != expected_hash:
            raise ValueError(f"workspace artifact hash mismatch: {path_key}")
        panels[panel] = {
            "relative_path": _relative_child(workspace, child),
            "sha256": actual_hash,
        }

    passport = dict(summary.get("analysis_passport", {}))
    return {
        "schema": WORKSPACE_SCHEMA,
        "result_class": summary.get("result_class"),
        "highest_demonstrated_stage": passport.get("highest_demonstrated_stage", "INCOMPLETE"),
        "panels": panels,
        "claims": dict(summary.get("claims", {})),
        "workspace_contract": {
            "offline_only": True,
            "child_hashes_verified_before_render": True,
            "results_panel_is_original_viewer": True,
            "mesh_panel_is_original_inspector": True,
            "evidence_panel_is_original_passport": True,
            "workspace_does_not_upgrade_claims": True,
        },
        "evidence_boundary": (
            "WORKSPACE_IS_A_PRESENTATION_SHELL_OVER_HASH_VERIFIED_EXISTING_ARTIFACTS;_"
            "NO_RESULT_RECOMPUTATION;_NO_CLAIM_UPGRADE"
        ),
    }


def write_results_workspace(path: str | Path, summary: dict[str, Any]) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_results_workspace_manifest(summary, target)
    panels = manifest["panels"]
    payload = json.dumps(manifest, indent=2, sort_keys=True)
    stage = html.escape(str(manifest["highest_demonstrated_stage"]))

    def button(panel: str, label: str) -> str:
        return f"<button data-panel='{panel}' onclick=\"showPanel('{panel}')\">{html.escape(label)}</button>"

    frames = []
    for panel in ("results", "mesh", "evidence"):
        src = html.escape(panels[panel]["relative_path"], quote=True)
        frames.append(
            f"<iframe id='panel-{panel}' data-panel='{panel}' src='{src}' "
            + ("class='active'" if panel == "results" else "")
            + " sandbox='allow-scripts allow-same-origin'></iframe>"
        )

    document = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>AsterMax Results + Evidence</title>
<style>
html,body{{height:100%;margin:0;font-family:Segoe UI,Arial,sans-serif;background:#0f1419;color:#eef2f5}}
body{{display:grid;grid-template-rows:auto auto 1fr}}
header{{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #303943;background:#151b21}}
.brand{{font-weight:700;letter-spacing:.04em}} .stage{{font-size:12px;padding:6px 10px;border:1px solid #46515d;border-radius:999px}}
nav{{display:flex;gap:8px;padding:10px 14px;border-bottom:1px solid #303943;background:#11171d}}
button{{border:1px solid #39434d;background:#1a222a;color:#eef2f5;border-radius:8px;padding:8px 14px;cursor:pointer}}
button.active{{background:#2b3640}} main{{min-height:0;position:relative}}
iframe{{display:none;width:100%;height:100%;border:0;background:white}} iframe.active{{display:block}}
.meta{{font-size:11px;color:#aeb9c4;margin-left:auto;padding-left:18px}}
details{{position:absolute;right:14px;bottom:14px;z-index:5;background:#141b21;border:1px solid #39434d;border-radius:8px;padding:8px;max-width:520px;max-height:45%;overflow:auto}}
pre{{white-space:pre-wrap;font-size:10px}}
</style></head><body>
<header><div class='brand'>ASTERMAX · RESULTS + EVIDENCE</div><div class='meta'>Hash-verified offline workspace</div><div class='stage'>{stage}</div></header>
<nav>{button('results','Results')}{button('mesh','Mesh Inspector')}{button('evidence','Analysis Passport')}</nav>
<main>{''.join(frames)}<details><summary>Workspace manifest</summary><pre>{html.escape(payload)}</pre></details></main>
<script>
function showPanel(name){{
 document.querySelectorAll('iframe').forEach(x=>x.classList.toggle('active',x.dataset.panel===name));
 document.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x.dataset.panel===name));
}}
showPanel('results');
</script></body></html>"""
    target.write_text(document, encoding="utf-8")
    return {**manifest, "html_sha256": _sha256_file(target), "path": str(target)}
