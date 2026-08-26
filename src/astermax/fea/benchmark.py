from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .gmsh_bridge import (
    distribute_resultant_on_tri6,
    distribute_resultant_on_triangles,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet10,
    mesh_step_tet4,
    unique_surface_nodes,
)
from .solver import solve_linear_static, solve_linear_static_tet10
from .tet4 import IsotropicMaterial


@dataclass(frozen=True)
class CantileverReference:
    length_mm: float
    width_y_mm: float
    height_z_mm: float
    force_y_n: float
    young_mpa: float
    tip_displacement_y_mm: float
    root_bending_stress_mpa: float
    reaction_force_n: float
    reaction_moment_nmm: float


@dataclass(frozen=True)
class ConvergenceSample:
    mesh_size_mm: float
    node_count: int
    tet_count: int
    tip_displacement_y_mm: float
    tip_error_percent: float
    force_balance_norm_n: float
    moment_balance_norm_nmm: float


@dataclass(frozen=True)
class ConvergencePolicy:
    min_samples: int = 3
    max_final_tip_error_percent: float = 10.0
    max_last_refinement_change_percent: float = 5.0
    max_force_balance_norm_n: float = 1.0e-5
    max_moment_balance_norm_nmm: float = 1.0e-3
    require_nonincreasing_tip_error: bool = True


@dataclass(frozen=True)
class ConvergenceDecision:
    converged: bool
    checks: dict[str, bool]
    metrics: dict[str, float | int | None]
    policy: dict[str, float | int | bool]


def analytical_cantilever_reference(
    *,
    length_mm: float = 100.0,
    width_y_mm: float = 20.0,
    height_z_mm: float = 10.0,
    force_y_n: float = -1000.0,
    young_mpa: float = 200000.0,
) -> CantileverReference:
    """Euler-Bernoulli reference for a rectangular cantilever loaded in Y.

    Units are N, mm and MPa. This remains the frozen first-order TET4
    verification reference. Bending is about Z, hence
    I_z = height_z * width_y**3 / 12.
    """
    if min(length_mm, width_y_mm, height_z_mm, young_mpa) <= 0.0:
        raise ValueError("geometry and Young modulus must be positive")
    if force_y_n == 0.0:
        raise ValueError("benchmark force must be non-zero")

    iz_mm4 = height_z_mm * width_y_mm**3 / 12.0
    tip = force_y_n * length_mm**3 / (3.0 * young_mpa * iz_mm4)
    root_stress = abs(force_y_n) * length_mm * (width_y_mm / 2.0) / iz_mm4
    return CantileverReference(
        length_mm=length_mm,
        width_y_mm=width_y_mm,
        height_z_mm=height_z_mm,
        force_y_n=force_y_n,
        young_mpa=young_mpa,
        tip_displacement_y_mm=tip,
        root_bending_stress_mpa=root_stress,
        reaction_force_n=abs(force_y_n),
        reaction_moment_nmm=abs(force_y_n) * length_mm,
    )


def analytical_timoshenko_cantilever_reference(
    *,
    length_mm: float = 100.0,
    width_y_mm: float = 20.0,
    height_z_mm: float = 10.0,
    force_y_n: float = -1000.0,
    young_mpa: float = 200000.0,
    poisson_ratio: float = 0.30,
    shear_correction_factor: float = 5.0 / 6.0,
) -> CantileverReference:
    """Independent finite-shear cantilever reference for the TET10 gate.

    The geometry and load are unchanged from the frozen TET4 benchmark. The
    TET10 gate uses Timoshenko beam displacement because L/width_y = 5 for the
    fixture, so transverse shear is not negligible once the quadratic solid is
    accurate enough to remove the artificial TET4 bending stiffness.

    No convergence tolerance is changed. The analytical target is simply
    upgraded from bending-only Euler-Bernoulli displacement to
    bending + P*L/(kappa*A*G), with rectangular-section kappa = 5/6.
    """
    if not (-1.0 < poisson_ratio < 0.5):
        raise ValueError("Poisson ratio must satisfy -1 < nu < 0.5")
    if shear_correction_factor <= 0.0:
        raise ValueError("shear correction factor must be positive")

    bending = analytical_cantilever_reference(
        length_mm=length_mm,
        width_y_mm=width_y_mm,
        height_z_mm=height_z_mm,
        force_y_n=force_y_n,
        young_mpa=young_mpa,
    )
    area_mm2 = width_y_mm * height_z_mm
    shear_modulus_mpa = young_mpa / (2.0 * (1.0 + poisson_ratio))
    shear_tip_mm = (
        force_y_n
        * length_mm
        / (shear_correction_factor * area_mm2 * shear_modulus_mpa)
    )
    return CantileverReference(
        length_mm=bending.length_mm,
        width_y_mm=bending.width_y_mm,
        height_z_mm=bending.height_z_mm,
        force_y_n=bending.force_y_n,
        young_mpa=bending.young_mpa,
        tip_displacement_y_mm=bending.tip_displacement_y_mm + shear_tip_mm,
        root_bending_stress_mpa=bending.root_bending_stress_mpa,
        reaction_force_n=bending.reaction_force_n,
        reaction_moment_nmm=bending.reaction_moment_nmm,
    )


def _validate_mesh_sizes(mesh_sizes_mm: Iterable[float]) -> list[float]:
    sizes = [float(raw) for raw in mesh_sizes_mm]
    previous = None
    for size in sizes:
        if size <= 0.0:
            raise ValueError("mesh sizes must be positive")
        if previous is not None and size >= previous:
            raise ValueError("mesh sizes must be strictly decreasing")
        previous = size
    return sizes


def run_cantilever_convergence(
    step_path: str | Path,
    mesh_sizes_mm: Iterable[float] = (25.0, 20.0, 15.0),
) -> tuple[CantileverReference, list[ConvergenceSample]]:
    """Run the same STEP cantilever over several first-order TET4 meshes."""
    ref = analytical_cantilever_reference()
    samples: list[ConvergenceSample] = []
    for size in _validate_mesh_sizes(mesh_sizes_mm):
        mesh = mesh_step_tet4(step_path, size)
        fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
        fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
        loads = distribute_resultant_on_triangles(
            mesh.nodes_mm,
            mesh.surface_triangles["X_MAX"],
            [0.0, ref.force_y_n, 0.0],
        )
        applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
        result = solve_linear_static(
            mesh.nodes_mm,
            mesh.elements,
            IsotropicMaterial(ref.young_mpa, 0.30),
            loads,
            fixed_dofs,
        )
        reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)

        tip_nodes = unique_surface_nodes(mesh.surface_triangles["X_MAX"])
        tip_y = float(np.mean(result.displacement_mm[tip_nodes, 1]))
        error = abs((tip_y - ref.tip_displacement_y_mm) / ref.tip_displacement_y_mm) * 100.0
        samples.append(
            ConvergenceSample(
                mesh_size_mm=size,
                node_count=int(mesh.nodes_mm.shape[0]),
                tet_count=int(mesh.elements.shape[0]),
                tip_displacement_y_mm=tip_y,
                tip_error_percent=error,
                force_balance_norm_n=float(np.linalg.norm(reaction_force + applied_force)),
                moment_balance_norm_nmm=float(np.linalg.norm(reaction_moment + applied_moment)),
            )
        )
    return ref, samples


def run_cantilever_convergence_tet10(
    step_path: str | Path,
    mesh_sizes_mm: Iterable[float] = (20.0, 15.0, 10.0, 8.0, 6.0),
) -> tuple[CantileverReference, list[ConvergenceSample]]:
    """Run the same physical cantilever through the T10-B quadratic path.

    Geometry, load, material E, convergence policy and tolerances stay fixed.
    The displacement reference includes the analytically expected shear term so
    the error trend tests convergence toward the appropriate finite-shear beam
    solution instead of rewarding accidental agreement with bending-only theory.
    """
    ref = analytical_timoshenko_cantilever_reference()
    samples: list[ConvergenceSample] = []
    for size in _validate_mesh_sizes(mesh_sizes_mm):
        mesh = mesh_step_tet10(step_path, size)
        fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
        fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
        loads = distribute_resultant_on_tri6(
            mesh.nodes_mm,
            mesh.surface_triangles["X_MAX"],
            [0.0, ref.force_y_n, 0.0],
        )
        applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
        result = solve_linear_static_tet10(
            mesh.nodes_mm,
            mesh.elements,
            IsotropicMaterial(ref.young_mpa, 0.30),
            loads,
            fixed_dofs,
        )
        reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)

        tip_nodes = unique_surface_nodes(mesh.surface_triangles["X_MAX"])
        tip_y = float(np.mean(result.displacement_mm[tip_nodes, 1]))
        error = abs((tip_y - ref.tip_displacement_y_mm) / ref.tip_displacement_y_mm) * 100.0
        samples.append(
            ConvergenceSample(
                mesh_size_mm=size,
                node_count=int(mesh.nodes_mm.shape[0]),
                tet_count=int(mesh.elements.shape[0]),
                tip_displacement_y_mm=tip_y,
                tip_error_percent=error,
                force_balance_norm_n=float(np.linalg.norm(reaction_force + applied_force)),
                moment_balance_norm_nmm=float(np.linalg.norm(reaction_moment + applied_moment)),
            )
        )
    return ref, samples


def evaluate_convergence(
    samples: list[ConvergenceSample],
    policy: ConvergencePolicy = ConvergencePolicy(),
) -> ConvergenceDecision:
    """Evaluate a declared numerical convergence policy, failing closed.

    The decision is intentionally independent of result export. A caller may set
    ``converged=true`` in provenance only when this function returns true using a
    policy that is itself stored in the evidence package.
    """
    if policy.min_samples < 2:
        raise ValueError("min_samples must be at least 2")
    thresholds = (
        policy.max_final_tip_error_percent,
        policy.max_last_refinement_change_percent,
        policy.max_force_balance_norm_n,
        policy.max_moment_balance_norm_nmm,
    )
    if any(value < 0.0 for value in thresholds):
        raise ValueError("convergence tolerances must be non-negative")

    enough = len(samples) >= policy.min_samples
    finite = all(
        np.isfinite(
            [
                sample.mesh_size_mm,
                sample.tip_displacement_y_mm,
                sample.tip_error_percent,
                sample.force_balance_norm_n,
                sample.moment_balance_norm_nmm,
            ]
        ).all()
        for sample in samples
    )
    strictly_refined = all(
        samples[i].mesh_size_mm < samples[i - 1].mesh_size_mm for i in range(1, len(samples))
    )
    nonincreasing_error = all(
        samples[i].tip_error_percent <= samples[i - 1].tip_error_percent + 1.0e-12
        for i in range(1, len(samples))
    )

    final_error = samples[-1].tip_error_percent if samples else None
    max_force = max((sample.force_balance_norm_n for sample in samples), default=None)
    max_moment = max((sample.moment_balance_norm_nmm for sample in samples), default=None)
    last_change = None
    if len(samples) >= 2:
        previous = samples[-2].tip_displacement_y_mm
        current = samples[-1].tip_displacement_y_mm
        denominator = max(abs(current), abs(previous), 1.0e-30)
        last_change = abs(current - previous) / denominator * 100.0

    checks = {
        "minimum_sample_count": enough,
        "finite_metrics": finite,
        "strict_mesh_refinement": strictly_refined,
        "final_tip_error": bool(final_error is not None and final_error <= policy.max_final_tip_error_percent),
        "last_refinement_change": bool(
            last_change is not None and last_change <= policy.max_last_refinement_change_percent
        ),
        "global_force_balance": bool(max_force is not None and max_force <= policy.max_force_balance_norm_n),
        "global_moment_balance": bool(
            max_moment is not None and max_moment <= policy.max_moment_balance_norm_nmm
        ),
        "nonincreasing_tip_error": bool(nonincreasing_error or not policy.require_nonincreasing_tip_error),
    }
    return ConvergenceDecision(
        converged=all(checks.values()),
        checks=checks,
        metrics={
            "sample_count": len(samples),
            "final_tip_error_percent": final_error,
            "last_refinement_change_percent": last_change,
            "max_force_balance_norm_n": max_force,
            "max_moment_balance_norm_nmm": max_moment,
        },
        policy=asdict(policy),
    )


def benchmark_manifest(
    reference: CantileverReference,
    samples: list[ConvergenceSample],
    *,
    policy: ConvergencePolicy | None = None,
) -> dict:
    manifest = {
        "result_class": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "analytical_reference": asdict(reference),
        "samples": [asdict(sample) for sample in samples],
        "converged_claim": False,
    }
    if policy is not None:
        decision = evaluate_convergence(samples, policy)
        manifest["convergence_decision"] = asdict(decision)
        manifest["converged_claim"] = decision.converged
    return manifest
