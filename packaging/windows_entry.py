from __future__ import annotations

import json
import math
from pathlib import Path
import sys

from astermax.app import run_step_analysis
from astermax.fast_contour_viewport import windows_desktop_main


def _write_fixture_step(path: Path) -> None:
    import gmsh

    initialized = False
    try:
        gmsh.initialize()
        initialized = True
        gmsh.model.add("astermax_exe_self_test")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        if initialized:
            gmsh.finalize()


def _self_test(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    step = root / "exe_self_test.step"
    results = root / "results"
    _write_fixture_step(step)
    summary = run_step_analysis(
        step,
        results,
        mesh_size_mm=20.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(0.0, -1000.0, 0.0),
    )

    force_residual = float(summary["checks"]["force_residual_n"])
    moment_residual = float(summary["checks"]["moment_residual_nmm"])
    checks = {
        "finite_force_residual": math.isfinite(force_residual),
        "finite_moment_residual": math.isfinite(moment_residual),
        "force_balance": force_residual <= 1.0e-5,
        "moment_balance": moment_residual <= 1.0e-3,
        "converged_claim_false": summary["claims"]["converged"] is False,
        "industrial_validation_false": summary["claims"]["industrial_validation"] is False,
        "ansys_equivalence_false": summary["claims"]["ansys_equivalence"] is False,
        "viewer_exists": Path(summary["artifacts"]["viewer"]).is_file(),
        "vtu_exists": Path(summary["artifacts"]["vtu"]).is_file(),
        "summary_exists": Path(summary["artifacts"]["summary"]).is_file(),
    }
    passed = all(checks.values())
    report = {
        "schema": "AsterMaxWindowsExeSelfTestV1",
        "passed": passed,
        "checks": checks,
        "mesh": summary["mesh"],
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "result_class": summary["result_class"],
    }
    (root / "exe_self_test.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if passed else 2


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        target = Path(sys.argv[2] if len(sys.argv) >= 3 else "astermax_exe_self_test")
        return _self_test(target.resolve())
    return windows_desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
