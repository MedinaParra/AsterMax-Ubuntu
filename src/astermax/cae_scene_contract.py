from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .persistent_viewport import extract_tet10_surface
from .results_scene import normalized_scalar
from .solver_results_bridge import build_results_scene_from_desktop_summary


@dataclass(frozen=True)
class CaeSceneContract:
    undeformed_nodes_mm: np.ndarray
    deformed_nodes_mm: np.ndarray
    surface_triangles: np.ndarray
    nodal_von_mises_mpa: np.ndarray
    triangle_von_mises_mpa: np.ndarray
    triangle_scalar_normalized: np.ndarray
    displacement_magnitude_mm: np.ndarray
    scalar_min_mpa: float
    scalar_max_mpa: float
    deformation_scale: float
    length_unit: str
    stress_unit: str
    stress_representation: str
    workspace_sha256: str
    solve_evidence_sha256: str
    displacement_vector_mm: np.ndarray | None = None


def validate_cae_scene_contract(scene: CaeSceneContract) -> None:
    u = np.asarray(scene.undeformed_nodes_mm, dtype=float)
    d = np.asarray(scene.deformed_nodes_mm, dtype=float)
    tri = np.asarray(scene.surface_triangles, dtype=int)
    nodal_vm = np.asarray(scene.nodal_von_mises_mpa, dtype=float)
    tri_vm = np.asarray(scene.triangle_von_mises_mpa, dtype=float)
    tri_norm = np.asarray(scene.triangle_scalar_normalized, dtype=float)
    disp = np.asarray(scene.displacement_magnitude_mm, dtype=float)
    if u.ndim != 2 or u.shape[1] != 3 or len(u) == 0:
        raise ValueError("CAE_SCENE_NODES_REQUIRED")
    if d.shape != u.shape or not np.isfinite(d).all() or not np.isfinite(u).all():
        raise ValueError("CAE_SCENE_DEFORMED_NODES_INVALID")
    if tri.ndim != 2 or tri.shape[1] != 3 or len(tri) == 0:
        raise ValueError("CAE_SCENE_TRIANGLES_REQUIRED")
    if tri.min() < 0 or tri.max() >= len(u):
        raise ValueError("CAE_SCENE_TRIANGLE_CONNECTIVITY_INVALID")
    if nodal_vm.shape != (len(u),) or not np.isfinite(nodal_vm).all() or np.any(nodal_vm < -1e-12):
        raise ValueError("CAE_SCENE_NODAL_SCALAR_INVALID")
    if tri_vm.shape != (len(tri),) or not np.isfinite(tri_vm).all() or np.any(tri_vm < -1e-12):
        raise ValueError("CAE_SCENE_TRIANGLE_SCALAR_INVALID")
    if tri_norm.shape != (len(tri),) or not np.isfinite(tri_norm).all() or np.any(tri_norm < -1e-12) or np.any(tri_norm > 1.0 + 1e-12):
        raise ValueError("CAE_SCENE_NORMALIZED_SCALAR_INVALID")
    if disp.shape != (len(u),) or not np.isfinite(disp).all() or np.any(disp < -1e-12):
        raise ValueError("CAE_SCENE_DISPLACEMENT_INVALID")
    if scene.displacement_vector_mm is not None:
        vector = np.asarray(scene.displacement_vector_mm, dtype=float)
        if vector.shape != u.shape or not np.isfinite(vector).all():
            raise ValueError("CAE_SCENE_DISPLACEMENT_VECTOR_INVALID")
        vector_mag = np.linalg.norm(vector, axis=1)
        if not np.allclose(vector_mag, disp, rtol=1e-10, atol=1e-12):
            raise ValueError("CAE_SCENE_DISPLACEMENT_VECTOR_MAGNITUDE_MISMATCH")
        expected_deformed = u + float(scene.deformation_scale) * vector
        if not np.allclose(expected_deformed, d, rtol=1e-10, atol=1e-12):
            raise ValueError("CAE_SCENE_DEFORMED_VECTOR_INCONSISTENT")
    if scene.length_unit != "mm" or scene.stress_unit != "MPa":
        raise ValueError("CAE_SCENE_UNITS_INVALID")
    if not math.isfinite(scene.deformation_scale) or scene.deformation_scale < 0.0:
        raise ValueError("CAE_SCENE_DEFORMATION_SCALE_INVALID")
    if not math.isfinite(scene.scalar_min_mpa) or not math.isfinite(scene.scalar_max_mpa) or scene.scalar_min_mpa > scene.scalar_max_mpa:
        raise ValueError("CAE_SCENE_RANGE_INVALID")
    if not isinstance(scene.stress_representation, str) or not scene.stress_representation.strip():
        raise ValueError("CAE_SCENE_STRESS_REPRESENTATION_REQUIRED")
    if not isinstance(scene.workspace_sha256, str) or len(scene.workspace_sha256.strip()) < 6:
        raise ValueError("CAE_SCENE_WORKSPACE_PROVENANCE_REQUIRED")
    if not isinstance(scene.solve_evidence_sha256, str) or len(scene.solve_evidence_sha256.strip()) < 6:
        raise ValueError("CAE_SCENE_SOLVE_PROVENANCE_REQUIRED")


def build_cae_scene_contract(summary: dict, *, deformation_scale: float = 1.0) -> CaeSceneContract:
    results_scene, evidence = build_results_scene_from_desktop_summary(summary, deformation_scale=deformation_scale)
    runtime = summary.get("_runtime_results")
    if not isinstance(runtime, dict):
        raise ValueError("CAE_SCENE_RUNTIME_REQUIRED")
    nodes = np.asarray(runtime.get("nodes_mm"), dtype=float)
    elements = np.asarray(runtime.get("elements"), dtype=int)
    _, triangles = extract_tet10_surface(type("Inventory", (), {"nodes_mm": nodes, "elements": elements})())
    nodal_vm = np.asarray(results_scene.von_mises_mpa, dtype=float)
    tri_vm = nodal_vm[triangles].mean(axis=1)
    nodal_norm = normalized_scalar(nodal_vm)
    tri_norm = nodal_norm[triangles].mean(axis=1)
    scene = CaeSceneContract(
        undeformed_nodes_mm=nodes.copy(),
        deformed_nodes_mm=np.asarray(results_scene.deformed_nodes_mm, dtype=float).copy(),
        surface_triangles=np.asarray(triangles, dtype=int).copy(),
        nodal_von_mises_mpa=nodal_vm.copy(),
        triangle_von_mises_mpa=np.asarray(tri_vm, dtype=float),
        triangle_scalar_normalized=np.asarray(tri_norm, dtype=float),
        displacement_magnitude_mm=np.asarray(results_scene.displacement_magnitude_mm, dtype=float).copy(),
        scalar_min_mpa=float(results_scene.scalar_min),
        scalar_max_mpa=float(results_scene.scalar_max),
        deformation_scale=float(results_scene.deformation_scale),
        length_unit="mm",
        stress_unit="MPa",
        stress_representation=evidence.stress_representation,
        workspace_sha256=evidence.workspace_sha256,
        solve_evidence_sha256=evidence.solve_evidence_sha256,
    )
    validate_cae_scene_contract(scene)
    return scene


def renderer_capabilities() -> tuple[str, ...]:
    return (
        "undeformed_geometry",
        "deformed_geometry",
        "surface_triangles",
        "von_mises_display_scalar",
        "displacement_magnitude",
        "native_displacement_vector_when_available",
        "mm_units",
        "mpa_units",
        "workspace_provenance",
        "solve_provenance",
    )
