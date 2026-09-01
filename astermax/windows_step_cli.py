"""Headless companion for the AsterMax Windows desktop STEP workflow.

Used by CI to prove that the frozen Windows executable can consume a real STEP file,
mesh it with the bundled Gmsh, solve it and create result/evidence artifacts.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .windows_app import StepCaseConfig, WindowsAppError, run_windows_step_case


def _force(text: str) -> tuple[float, float, float]:
    try:
        values=tuple(float(v.strip()) for v in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("force must be Fx,Fy,Fz") from exc
    if len(values) != 3:
        raise argparse.ArgumentTypeError("force must be Fx,Fy,Fz")
    return values


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Run a verified AsterMax STEP case headlessly")
    parser.add_argument("--run-step", required=True)
    parser.add_argument("--output", default="astermax_step_evidence")
    parser.add_argument("--axis", choices=("x","y","z"), default="x")
    parser.add_argument("--fixed-side", choices=("min","max"), default="min")
    parser.add_argument("--load-side", choices=("min","max"), default="max")
    parser.add_argument("--force", type=_force, default=(100.0,0.0,0.0))
    parser.add_argument("--mesh-size", type=float, default=2.0)
    parser.add_argument("--young", type=float, default=210000.0)
    parser.add_argument("--poisson", type=float, default=0.30)
    parser.add_argument("--minimum-quality", type=float, default=0.05)
    parser.add_argument("--gmsh", default=None)
    args=parser.parse_args(argv)
    config=StepCaseConfig(
        step_path=Path(args.run_step), output_dir=Path(args.output), axis=args.axis,
        fixed_side=args.fixed_side, load_side=args.load_side, force_n=args.force,
        mesh_size_mm=args.mesh_size, young_mpa=args.young, poisson=args.poisson,
        minimum_tet_quality=args.minimum_quality,
    )
    try:
        result=run_windows_step_case(config, gmsh_executable=args.gmsh)
    except WindowsAppError as exc:
        parser.error(str(exc))
    summary=result["summary"]
    manifest=result["manifest"]
    print("ASTERMAX_STEP_SOLVE_OK")
    print(f"nodes={summary['node_count']} tet4={summary['tet4_count']}")
    print(f"max_displacement_mm={summary['max_displacement_mm']}")
    print(f"max_element_von_mises_MPa={summary['max_element_von_mises_MPa']}")
    print(f"free_residual_max_N={summary['free_residual_max_N']}")
    print(f"evidence_fingerprint_sha256={manifest['evidence_fingerprint_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
