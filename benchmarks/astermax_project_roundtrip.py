from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np

from astermax.fea.selections import inspect_step_surfaces
from astermax.project import AsterMaxProject, AsterMaxProjectError, sha256_file, write_project
from astermax.project_runner import run_project


def build_fixture(path: Path) -> None:
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_project_fixture")
        box = gmsh.model.occ.addBox(0, 0, 0, 100, 20, 10)
        gmsh.model.occ.rotate([(3, box)], 0, 0, 0, 0, 0, 1, np.deg2rad(17.0))
        gmsh.model.occ.rotate([(3, box)], 0, 0, 0, 0, 1, 0, np.deg2rad(11.0))
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def main() -> int:
    root = Path("astermax_project_gate")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    step = root / "fixture.step"
    build_fixture(step)

    surfaces = inspect_step_surfaces(step)
    end_faces = sorted(
        [(tag, sig) for tag, sig in surfaces if abs(sig.area_mm2 - 200.0) < 1.0e-6],
        key=lambda item: item[1].centroid_mm,
    )
    if len(end_faces) != 2:
        raise RuntimeError(f"expected two 200 mm2 end faces, found {len(end_faces)}")
    support = end_faces[0][1]
    load = end_faces[1][1]
    project = AsterMaxProject(
        schema="AsterMaxProjectV1",
        geometry_step="fixture.step",
        length_unit="mm",
        mesh_family="TET10",
        mesh_size_mm=15.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        support=support,
        load_surface=load,
        resultant_n=(0.0, -1000.0, 0.0),
        geometry_sha256=sha256_file(step),
    )
    project_file = write_project(root / "rotated_cantilever.astermax", project)
    result = run_project(project_file, root / "results")

    checks = {
        "persistent_selection_mode": result["selection_mode"] == "PERSISTENT_CAD_SURFACE_SIGNATURES",
        "named_support": result["scope_contract"]["constraint"] == "SUPPORT",
        "named_load": result["scope_contract"]["load"] == "LOAD",
        "force_balance": result["checks"]["force_residual_n"] <= 1.0e-5,
        "moment_balance": result["checks"]["moment_residual_nmm"] <= 1.0e-3,
        "support_tri6_present": result["mesh"]["support_tri6"] > 0,
        "load_tri6_present": result["mesh"]["load_tri6"] > 0,
        "unconverged_guard": result["claims"]["converged"] is False,
        "industrial_guard": result["claims"]["industrial_validation"] is False,
        "ansys_guard": result["claims"]["ansys_equivalence"] is False,
    }

    tampered = root / "tampered.step"
    tampered.write_bytes(step.read_bytes() + b"\n# deliberate provenance tamper\n")
    tampered_project = AsterMaxProject(
        **{**project.__dict__, "geometry_step": "tampered.step"}
    )
    tampered_file = write_project(root / "tampered.astermax", tampered_project)
    tamper_blocked = False
    try:
        run_project(tampered_file, root / "tampered_results")
    except AsterMaxProjectError:
        tamper_blocked = True
    checks["geometry_tamper_blocked"] = tamper_blocked

    evidence = {
        "schema": "AsterMaxProjectRoundtripGateV1",
        "classification": "PROJECT_MODEL_PREPARATION_VERIFICATION_NOT_INDUSTRIAL_RESULT",
        "checks": checks,
        "passed": all(checks.values()),
        "project_file": str(project_file),
        "mesh": result["mesh"],
        "force_residual_n": result["checks"]["force_residual_n"],
        "moment_residual_nmm": result["checks"]["moment_residual_nmm"],
        "provenance": result["provenance"],
        "claims": result["claims"],
    }
    Path("astermax_project_roundtrip.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence["passed"]:
        raise SystemExit(".astermax project gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
