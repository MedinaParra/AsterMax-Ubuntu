#!/usr/bin/env python3
"""Fail-closed contract gate for the pinned PrePoMax native Results renderer seam.

This gate does not claim that a contour was rendered. It proves that the exact pinned
upstream revision exposes the controller/results/legend hooks C8.33 will have to drive.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def require(path: Path, patterns: dict[str, str]) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    found = []
    for label, pattern in patterns.items():
        if re.search(pattern, text, re.MULTILINE) is None:
            raise SystemExit(f"native render contract FAIL: {label} missing in {path}")
        found.append(label)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Bootstrapped pinned PrePoMax source tree")
    ap.add_argument("--output")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    controller = repo / "PrePoMax" / "Controller.cs"
    settings = repo / "PrePoMax" / "Settings" / "SettingsContainer.cs"
    animation = repo / "PrePoMax" / "Forms" / "71_Animation" / "FrmAnimation.cs"
    for p in (controller, settings, animation):
        if not p.exists():
            raise SystemExit(f"native render contract FAIL: missing pinned upstream file {p}")

    checks = []
    checks += require(controller, {
        "results view enum/state": r"ViewGeometryModelResults\s+_currentView",
        "current result field state": r"FieldData\s+_currentFieldData",
        "native results draw entrypoint": r"DrawResults\s*\(",
        "results redraw path": r"Redraw\s*\(",
    })
    checks += require(settings, {
        "automatic legend range": r"MinMaxType\s*=\s*vtkControl\.vtkColorSpectrumMinMaxType\.Automatic",
        "results-aware settings": r"ViewGeometryModelResults\.Results",
    })
    checks += require(animation, {
        "controller current field consumption": r"_controller\.CurrentFieldData",
        "controller current result consumption": r"_controller\.CurrentResult\.GetField",
        "controller DrawResults consumption": r"_controller\.DrawResults\s*\(",
    })

    evidence = {
        "schema": "astermax.native-render-contract.v1",
        "pinned_upstream_contract": True,
        "controller_results_state": True,
        "native_draw_results_entrypoint": True,
        "automatic_legend_range_hook": True,
        "current_field_consumed_by_native_ui": True,
        "current_result_consumed_by_native_ui": True,
        "checks": checks,
        "contour_rendered_from_verified_result": False,
        "rendering_semantics_verified": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    payload = json.dumps(evidence, indent=2, sort_keys=True)
    print(payload)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
