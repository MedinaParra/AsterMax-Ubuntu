"""Auditable STEP -> mesh -> BC/load -> linear-static FEA -> viewer/evidence pipeline.

Accepts an actual STEP Part 21 file, gates units to mm, meshes with Gmsh/OpenCASCADE,
applies either explicit bounding-box selectors or topology-robust semantic surface
intents, solves verified linear elastic TET4 FEA, exports VTK and a self-contained
browser viewer, then fingerprints every artifact. Numerical values are recovered from
the actual solve; no industrial result is invented. Units: mm, N, MPa.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Sequence

from .global_static import solve_linear_static
from .gmsh_pipeline import GmshPipelineError, SurfaceBox, mesh_step_with_gmsh
from .mesh_bc import fixed_surface_constraints, resultant_from_nodal_loads, surface_total_force_loads
from .postprocess import element_von_mises, write_legacy_vtk
from .semantic_surface import SemanticSurfaceError, SemanticSurfaceIntent, apply_semantic_surfaces
from .static_result_viewer import StaticResultViewerError, write_static_result_viewer
from .step_units import require_step_mm


class StepStaticDemoError(RuntimeError):
    """Raised when a STEP static demo cannot produce trustworthy evidence."""


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vec3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise StepStaticDemoError(f"{name} must contain three components")
    result = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in result):
        raise StepStaticDemoError(f"{name} must be finite")
    return result


def run_step_static_demo(
    step_path: str | Path,
    output_dir: str | Path,
    *,
    fixed_box: SurfaceBox | None = None,
    load_box: SurfaceBox | None = None,
    fixed_intent: SemanticSurfaceIntent | None = None,
    load_intent: SemanticSurfaceIntent | None = None,
    total_force_n: Sequence[float],
    mesh_size_mm: float,
    young_mpa: float,
    poisson: float,
    gmsh_executable: str = "gmsh",
    minimum_tet_quality: float = 0.05,
) -> dict:
    """Run real STEP -> preparation -> mesh -> static solve -> viewer -> evidence."""
    source = Path(step_path)
    if not source.is_file():
        raise StepStaticDemoError(f"STEP file does not exist: {source}")
    force = _vec3(total_force_n, "total_force_n")
    if not math.isfinite(float(young_mpa)) or float(young_mpa) <= 0.0:
        raise StepStaticDemoError("young_mpa must be finite and positive")
    if not math.isfinite(float(poisson)) or not (-1.0 < float(poisson) < 0.5):
        raise StepStaticDemoError("poisson must satisfy -1 < nu < 0.5")

    box_mode = fixed_box is not None or load_box is not None
    semantic_mode = fixed_intent is not None or load_intent is not None
    if box_mode == semantic_mode:
        raise StepStaticDemoError("choose exactly one surface preparation mode: boxes or semantic intents")
    if box_mode:
        if fixed_box is None or load_box is None:
            raise StepStaticDemoError("both FIXED and LOAD bounding boxes are required")
        if fixed_box.name != "FIXED" or load_box.name != "LOAD":
            raise StepStaticDemoError("surface selectors must be named FIXED and LOAD")
        surface_mode = "explicit_bounding_boxes"
    else:
        if fixed_intent is None or load_intent is None:
            raise StepStaticDemoError("both FIXED and LOAD semantic intents are required")
        if fixed_intent.name != "FIXED" or load_intent.name != "LOAD":
            raise StepStaticDemoError("semantic intents must be named FIXED and LOAD")
        surface_mode = "semantic_normalized_boundary_intent"

    try:
        unit = require_step_mm(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise StepStaticDemoError(f"STEP unit gate failed: {exc}") from exc

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    msh_path = root / "model.msh"
    vtk_path = root / "result.vtk"
    semantic_resolution = None
    try:
        if box_mode:
            mesh = mesh_step_with_gmsh(
                source, msh_path, surface_boxes=(fixed_box, load_box),
                mesh_size_mm=float(mesh_size_mm), gmsh_executable=gmsh_executable,
                minimum_tet_quality=float(minimum_tet_quality),
            )
        else:
            raw_mesh = mesh_step_with_gmsh(
                source, msh_path, surface_boxes=(), include_all_boundary=True,
                mesh_size_mm=float(mesh_size_mm), gmsh_executable=gmsh_executable,
                minimum_tet_quality=float(minimum_tet_quality),
            )
            mesh, semantic_resolution = apply_semantic_surfaces(
                raw_mesh, (fixed_intent, load_intent), boundary_group="ALL_BOUNDARY"
            )
        constraints = fixed_surface_constraints(mesh, "FIXED")
        loads = surface_total_force_loads(mesh, "LOAD", force)
        result = solve_linear_static(
            mesh.nodes, mesh.elements, young=float(young_mpa), poisson=float(poisson),
            constraints=constraints, loads=loads,
        )
    except (GmshPipelineError, SemanticSurfaceError, ValueError) as exc:
        raise StepStaticDemoError(str(exc)) from exc

    applied = resultant_from_nodal_loads(loads)
    reaction = [0.0, 0.0, 0.0]
    for dof, value in enumerate(result.reactions):
        reaction[dof % 3] += float(value)
    free_residual_max = max(
        (abs(float(value)) for dof, value in enumerate(result.residual) if dof not in constraints),
        default=0.0,
    )
    displacement_magnitudes = []
    for node in range(len(mesh.nodes)):
        base = 3 * node
        displacement_magnitudes.append(
            math.sqrt(sum(float(result.displacements[base+i]) ** 2 for i in range(3)))
        )
    vm = tuple(float(value) for value in element_von_mises(result))
    finite_values = (*applied, *reaction, free_residual_max, *displacement_magnitudes, *vm)
    if not all(math.isfinite(v) for v in finite_values):
        raise StepStaticDemoError("non-finite solve output cannot enter evidence bundle")

    write_legacy_vtk(vtk_path, mesh.nodes, mesh.elements, result)
    summary = {
        "scope": "verified linear-static STEP demo; not an industrial certification result",
        "unit_system": "mm-N-MPa",
        "step_unit": unit.name,
        "step_sha256": _sha256_file(source),
        "surface_selection_mode": surface_mode,
        "node_count": len(mesh.nodes),
        "tet4_count": len(mesh.elements),
        "fixed_surface_triangle_count": len(mesh.surface_group("FIXED").triangles),
        "load_surface_triangle_count": len(mesh.surface_group("LOAD").triangles),
        "young_MPa": float(young_mpa),
        "poisson": float(poisson),
        "mesh_size_mm": float(mesh_size_mm),
        "requested_force_N": list(force),
        "recovered_applied_force_N": list(applied),
        "reaction_resultant_N": reaction,
        "free_residual_max_N": free_residual_max,
        "max_displacement_mm": max(displacement_magnitudes, default=0.0),
        "max_element_von_mises_MPa": max(vm, default=0.0),
    }
    if semantic_resolution is not None:
        summary["semantic_surfaces"] = [
            {
                "name": resolution.intent.name,
                "axis": resolution.intent.axis,
                "side": resolution.intent.side,
                "band_fraction": float(resolution.intent.band_fraction),
                "minimum_normal_alignment": float(resolution.intent.minimum_normal_alignment),
                "selected_triangle_count": int(resolution.selected_triangle_count),
                "selected_area_mm2": float(resolution.selected_area),
            }
            for resolution in semantic_resolution
        ]

    summary_path = root / "summary.json"
    summary_path.write_text(_canonical_json(summary) + "\n", encoding="utf-8")
    summary_sha = _sha256_file(summary_path)
    viewer_path = root / "astermax_step_viewer.html"
    try:
        write_static_result_viewer(
            viewer_path, mesh.nodes, mesh.elements, result, summary,
            summary_sha256=summary_sha,
        )
    except StaticResultViewerError as exc:
        raise StepStaticDemoError(f"viewer generation failed: {exc}") from exc

    artifacts = {}
    for path in (msh_path, vtk_path, summary_path, viewer_path):
        artifacts[path.name] = {"sha256": _sha256_file(path), "bytes": path.stat().st_size}
    fingerprint = sha256(_canonical_json(artifacts).encode("utf-8")).hexdigest()
    manifest = {
        "format_version": 3,
        "source_step_sha256": summary["step_sha256"],
        "surface_selection_mode": surface_mode,
        "artifacts": artifacts,
        "evidence_fingerprint_sha256": fingerprint,
    }
    (root / "manifest.json").write_text(_canonical_json(manifest) + "\n", encoding="utf-8")
    return {"summary": summary, "manifest": manifest}


def _parse_box(text: str, name: str) -> SurfaceBox:
    try:
        values = tuple(float(v.strip()) for v in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("box must contain six comma-separated numbers") from exc
    if len(values) != 6:
        raise argparse.ArgumentTypeError("box must contain xmin,ymin,zmin,xmax,ymax,zmax")
    return SurfaceBox(name, values[:3], values[3:])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run AsterMax verified STEP linear-static demo")
    parser.add_argument("step")
    parser.add_argument("--output", default="astermax_step_evidence")
    parser.add_argument("--fixed-box")
    parser.add_argument("--load-box")
    parser.add_argument(
        "--semantic-x-ends", action="store_true",
        help="persist FIXED at X-min and LOAD at X-max using normalized boundary intent",
    )
    parser.add_argument("--force", default="100,0,0", help="Fx,Fy,Fz total N")
    parser.add_argument("--mesh-size", type=float, required=True)
    parser.add_argument("--young", type=float, default=210000.0)
    parser.add_argument("--poisson", type=float, default=0.30)
    args = parser.parse_args(argv)
    try:
        force = tuple(float(v.strip()) for v in args.force.split(","))
        kwargs = {}
        if args.semantic_x_ends:
            if args.fixed_box or args.load_box:
                raise StepStaticDemoError("semantic mode cannot be combined with bounding boxes")
            kwargs.update(
                fixed_intent=SemanticSurfaceIntent("FIXED", "x", "min"),
                load_intent=SemanticSurfaceIntent("LOAD", "x", "max"),
            )
        else:
            if not args.fixed_box or not args.load_box:
                raise StepStaticDemoError("provide --fixed-box/--load-box or use --semantic-x-ends")
            kwargs.update(
                fixed_box=_parse_box(args.fixed_box, "FIXED"),
                load_box=_parse_box(args.load_box, "LOAD"),
            )
        evidence = run_step_static_demo(
            args.step, args.output, total_force_n=force,
            mesh_size_mm=args.mesh_size, young_mpa=args.young, poisson=args.poisson,
            **kwargs,
        )
    except (ValueError, StepStaticDemoError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    print(f"evidence_fingerprint_sha256={evidence['manifest']['evidence_fingerprint_sha256']}")
    print(f"surface_selection_mode={evidence['summary']['surface_selection_mode']}")
    print(f"viewer={Path(args.output) / 'astermax_step_viewer.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
