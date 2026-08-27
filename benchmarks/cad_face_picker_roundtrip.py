from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np

from astermax.face_picker import build_project_from_face_fingerprints, write_face_picker_html
from astermax.fea.selections import inspect_step_surfaces
from astermax.project import read_project
from astermax.project_runner import run_project


def build_fixture(path: Path) -> None:
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_picker_fixture")
        box = gmsh.model.occ.addBox(0, 0, 0, 100, 20, 10)
        gmsh.model.occ.rotate([(3, box)], 0, 0, 0, 0, 0, 1, np.deg2rad(23.0))
        gmsh.model.occ.rotate([(3, box)], 0, 0, 0, 0, 1, 0, np.deg2rad(13.0))
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def main() -> int:
    root = Path("cad_face_picker_gate")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    step = root / "picker_fixture.step"
    build_fixture(step)

    picker = write_face_picker_html(step, root / "astermax_face_picker.html", display_mesh_size_mm=12.0)
    surfaces = inspect_step_surfaces(step)
    end_faces = [(tag, sig) for tag, sig in surfaces if abs(sig.area_mm2 - 200.0) <= 1.0e-6]
    if len(end_faces) != 2:
        raise RuntimeError(f"expected two end faces, found {len(end_faces)}")
    # Simulated picker choices use CAD fingerprints, never transient Gmsh tags.
    end_faces.sort(key=lambda item: item[1].centroid_mm)
    support = end_faces[0][1]
    load = end_faces[1][1]
    project_path = root / "picker_fixture.astermax"
    build_project_from_face_fingerprints(
        step,
        project_path,
        support.fingerprint_sha256,
        load.fingerprint_sha256,
        mesh_size_mm=15.0,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    saved = read_project(project_path)
    result = run_project(project_path, root / "results")
    html = (root / "astermax_face_picker.html").read_text(encoding="utf-8")

    checks = {
        "picker_payload_schema": picker["schema"] == "AsterMaxFacePickerPayloadV1",
        "all_six_box_faces_exposed": picker["faces"] == 6,
        "display_triangles_present": picker["triangles"] > 0,
        "offline_html_contains_click_handler": "c.onclick" in html,
        "offline_html_contains_support_assignment": "Assign as Fixed Support" in html,
        "offline_html_contains_load_assignment": "Assign as Force Surface" in html,
        "offline_html_contains_project_download": "Download .astermax project" in html,
        "saved_support_matches_click_fingerprint": saved.support.fingerprint_sha256 == support.fingerprint_sha256,
        "saved_load_matches_click_fingerprint": saved.load_surface.fingerprint_sha256 == load.fingerprint_sha256,
        "distinct_faces": saved.support.fingerprint_sha256 != saved.load_surface.fingerprint_sha256,
        "solver_named_support": result["scope_contract"]["constraint"] == "SUPPORT",
        "solver_named_load": result["scope_contract"]["load"] == "LOAD",
        "support_tri6_present": result["mesh"]["support_tri6"] > 0,
        "load_tri6_present": result["mesh"]["load_tri6"] > 0,
        "force_balance": result["checks"]["force_residual_n"] <= 1.0e-5,
        "moment_balance": result["checks"]["moment_residual_nmm"] <= 1.0e-3,
        "unconverged_guard": result["claims"]["converged"] is False,
        "industrial_guard": result["claims"]["industrial_validation"] is False,
        "ansys_guard": result["claims"]["ansys_equivalence"] is False,
    }
    evidence = {
        "schema": "AsterMaxCadFacePickerGateV1",
        "classification": "INTERACTIVE_MODEL_PREPARATION_VERIFICATION_NOT_INDUSTRIAL_RESULT",
        "interaction_evidence_boundary": "CI verifies picker geometry-to-fingerprint mapping and the exact project/solve path. It does not automate a human mouse click in a browser.",
        "checks": checks,
        "passed": all(checks.values()),
        "picker": picker,
        "selected_surface_fingerprints": {"SUPPORT": support.fingerprint_sha256, "LOAD": load.fingerprint_sha256},
        "mesh": result["mesh"],
        "force_residual_n": result["checks"]["force_residual_n"],
        "moment_residual_nmm": result["checks"]["moment_residual_nmm"],
        "claims": result["claims"],
    }
    Path("cad_face_picker_gate.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence["passed"]:
        raise SystemExit("CAD face picker gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
