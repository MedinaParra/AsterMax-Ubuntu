from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .fea.gmsh_bridge import distribute_resultant_on_tri6, fixed_dofs_for_nodes, force_and_moment, unique_surface_nodes
from .fea.mesh_quality import require_mesh_quality, tetra_mesh_quality
from .fea.postprocess_tet10 import write_tet10_linear_static_vtu
from .fea.quality_policy import DEFAULT_TETRA_QUALITY_POLICY
from .fea.selected_mesh import mesh_step_tet10_with_selections
from .fea.solver import solve_linear_static_tet10
from .fea.tet10_geometry import require_tet10_geometry_scope, tet10_geometry_scope
from .fea.tet4 import IsotropicMaterial
from .fea.viewer_tet10 import write_tet10_offline_viewer
from .mesh_inspector import write_mesh_inspector
from .project import read_project, resolve_project_geometry

RESULT_CLASS = "ASTERMAX_PROJECT_UNCONVERGED_NOT_INDUSTRIAL_RESULT"


def run_project(project_path: str | Path, output_dir: str | Path) -> dict:
    project_file = Path(project_path).resolve()
    project = read_project(project_file)
    geometry = resolve_project_geometry(project_file, project)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    mesh = mesh_step_tet10_with_selections(
        geometry,
        project.mesh_size_mm,
        {"SUPPORT": project.support, "LOAD": project.load_surface},
    )

    # Geometry scope and mesh quality are both evaluated before BC/load creation or
    # sparse assembly. The current verified TET10 solver scope remains straight-sided.
    geometry_scope = tet10_geometry_scope(mesh.nodes_mm, mesh.elements)
    quality_policy = DEFAULT_TETRA_QUALITY_POLICY
    mesh_quality = tetra_mesh_quality(mesh.nodes_mm, mesh.elements, policy=quality_policy)

    # Diagnostic evidence is emitted before fail-closed acceptance so rejected meshes
    # remain inspectable. The authoritative geometry/quality gates are deliberately
    # evaluated before the secondary inspector-policy consistency assertion so that a
    # diagnostic artifact can never mask the primary engineering rejection reason.
    inspector = output / "astermax_mesh_inspector.html"
    inspector_manifest = write_mesh_inspector(
        inspector,
        mesh.nodes_mm,
        mesh.elements,
        policy=quality_policy,
    )
    require_tet10_geometry_scope(geometry_scope)
    require_mesh_quality(mesh_quality)

    expected_policy = quality_policy.to_dict()
    if mesh_quality.policy != expected_policy:
        raise RuntimeError("mesh quality report policy drifted from the declared quality policy")
    inspector_policy = inspector_manifest.get("policy")
    inspector_policy_matches_gate = inspector_policy == expected_policy
    if not inspector_policy_matches_gate:
        raise RuntimeError("mesh inspector policy drifted from the fail-closed quality gate")
    inspector_claims = inspector_manifest.get("claims", {})
    inspector_uses_shared_classifier = inspector_claims.get("status_derived_from_shared_classifier") is True
    if not inspector_uses_shared_classifier:
        raise RuntimeError("mesh inspector status is not derived from the shared quality classifier")

    support_nodes = unique_surface_nodes(mesh.surface_triangles["SUPPORT"])
    fixed_dofs = fixed_dofs_for_nodes(support_nodes)
    load = np.asarray(project.resultant_n, dtype=float)
    loads = distribute_resultant_on_tri6(mesh.nodes_mm, mesh.surface_triangles["LOAD"], load)
    applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
    material = IsotropicMaterial(project.young_modulus_mpa, project.poisson_ratio)
    result = solve_linear_static_tet10(mesh.nodes_mm, mesh.elements, material, loads, fixed_dofs)
    reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)
    force_residual = float(np.linalg.norm(reaction_force + applied_force))
    moment_residual = float(np.linalg.norm(reaction_moment + applied_moment))

    vtu = output / "astermax_project_result.vtu"
    viewer = output / "astermax_project_viewer.html"
    vtu_manifest = write_tet10_linear_static_vtu(
        vtu,
        mesh.nodes_mm,
        mesh.elements,
        result,
        result_class=RESULT_CLASS,
        converged_claim=False,
        industrial_validation_claim=False,
    )
    viewer_manifest = write_tet10_offline_viewer(
        viewer,
        mesh.nodes_mm,
        mesh.elements,
        result,
        result_class=RESULT_CLASS,
        converged_claim=False,
        industrial_validation_claim=False,
    )
    summary = {
        "schema": "AsterMaxProjectRunResultV5",
        "project": str(project_file),
        "geometry": str(geometry),
        "selection_mode": "PERSISTENT_CAD_SURFACE_SIGNATURES",
        "scope_contract": {"constraint": "SUPPORT", "load": "LOAD"},
        "mesh": {
            "family": "TET10",
            "target_size_mm": project.mesh_size_mm,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "elements": int(mesh.elements.shape[0]),
            "support_tri6": int(mesh.surface_triangles["SUPPORT"].shape[0]),
            "load_tri6": int(mesh.surface_triangles["LOAD"].shape[0]),
        },
        "tet10_geometry_scope": {
            **asdict(geometry_scope),
            "gate_order": "BEFORE_BC_LOAD_ASSEMBLY_AND_SOLVE",
            "fail_closed": True,
            "curved_tet10_solver_enabled": False,
        },
        "mesh_quality": {
            **asdict(mesh_quality),
            "policy_scope": "STRAIGHT_SIDED_TET10_CORNER_GEOMETRY",
            "gate_order": "INSPECTOR_THEN_PRIMARY_GATES_THEN_POLICY_CONSISTENCY_BEFORE_BC_LOAD_ASSEMBLY_AND_SOLVE",
            "fail_closed": True,
            "inspector_worst_element_index": inspector_manifest["worst_element_index"],
            "inspector_policy": inspector_policy,
            "inspector_policy_matches_gate": inspector_policy_matches_gate,
            "inspector_status_uses_shared_classifier": inspector_uses_shared_classifier,
        },
        "checks": {"force_residual_n": force_residual, "moment_residual_nmm": moment_residual},
        "claims": {
            "converged": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
            "curved_tet10": False,
        },
        "provenance": {
            "geometry_sha256": project.geometry_sha256,
            "support_surface_sha256": project.support.fingerprint_sha256,
            "load_surface_sha256": project.load_surface.fingerprint_sha256,
        },
        "artifacts": {
            "mesh_inspector": str(inspector),
            "mesh_inspector_sha256": inspector_manifest["html_sha256"],
            "vtu": str(vtu),
            "viewer": str(viewer),
            "vtu_sha256": vtu_manifest.vtu_sha256,
            "viewer_sha256": viewer_manifest.html_sha256,
        },
    }
    summary_path = output / "astermax_project_run.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["artifacts"]["summary"] = str(summary_path)
    return summary
