from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class ResultsFieldBinding:
    displacement_mm: np.ndarray
    von_mises_mpa: np.ndarray
    workspace_sha256: str
    solve_evidence_sha256: str


@dataclass(frozen=True)
class ResultsScene:
    deformed_nodes_mm: np.ndarray
    displacement_magnitude_mm: np.ndarray
    von_mises_mpa: np.ndarray
    scalar_min: float
    scalar_max: float
    deformation_scale: float
    workspace_sha256: str
    solve_evidence_sha256: str


def _require_hash(value: str | None, code: str) -> str:
    if not isinstance(value, str) or len(value.strip()) < 6:
        raise ValueError(code)
    return value.strip()


def validate_results_binding(nodes_mm: np.ndarray, binding: ResultsFieldBinding) -> None:
    nodes = np.asarray(nodes_mm, dtype=float)
    disp = np.asarray(binding.displacement_mm, dtype=float)
    vm = np.asarray(binding.von_mises_mpa, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or len(nodes) == 0:
        raise ValueError("RESULTS_SCENE_NODES_REQUIRED")
    if disp.shape != nodes.shape:
        raise ValueError("RESULTS_SCENE_DISPLACEMENT_SHAPE_MISMATCH")
    if vm.shape != (len(nodes),):
        raise ValueError("RESULTS_SCENE_VON_MISES_SHAPE_MISMATCH")
    if not np.isfinite(nodes).all() or not np.isfinite(disp).all() or not np.isfinite(vm).all():
        raise ValueError("RESULTS_SCENE_NONFINITE_FIELD")
    if np.any(vm < -1e-12):
        raise ValueError("RESULTS_SCENE_VON_MISES_NEGATIVE")
    _require_hash(binding.workspace_sha256, "RESULTS_SCENE_WORKSPACE_PROVENANCE_REQUIRED")
    _require_hash(binding.solve_evidence_sha256, "RESULTS_SCENE_SOLVE_PROVENANCE_REQUIRED")


def build_results_scene(nodes_mm: np.ndarray, binding: ResultsFieldBinding, *, deformation_scale: float = 1.0) -> ResultsScene:
    validate_results_binding(nodes_mm, binding)
    if not math.isfinite(deformation_scale) or deformation_scale < 0.0:
        raise ValueError("RESULTS_SCENE_DEFORMATION_SCALE_INVALID")
    nodes = np.asarray(nodes_mm, dtype=float)
    disp = np.asarray(binding.displacement_mm, dtype=float)
    vm = np.asarray(binding.von_mises_mpa, dtype=float)
    mag = np.linalg.norm(disp, axis=1)
    deformed = nodes + disp * float(deformation_scale)
    return ResultsScene(
        deformed_nodes_mm=deformed,
        displacement_magnitude_mm=mag,
        von_mises_mpa=vm,
        scalar_min=float(vm.min()),
        scalar_max=float(vm.max()),
        deformation_scale=float(deformation_scale),
        workspace_sha256=binding.workspace_sha256,
        solve_evidence_sha256=binding.solve_evidence_sha256,
    )


def normalized_scalar(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    if data.ndim != 1 or len(data) == 0 or not np.isfinite(data).all():
        raise ValueError("RESULTS_SCENE_SCALAR_INVALID")
    lo = float(data.min()); hi = float(data.max())
    if math.isclose(lo, hi, rel_tol=0.0, abs_tol=1e-15):
        return np.zeros_like(data)
    return (data - lo) / (hi - lo)


def result_scene_modes(binding_present: bool) -> tuple[str, ...]:
    base = ("surface", "wireframe", "surface+edges")
    if not binding_present:
        return base
    return base + ("total_deformation", "von_mises")
