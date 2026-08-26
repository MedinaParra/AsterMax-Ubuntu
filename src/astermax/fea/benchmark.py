from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .gmsh_bridge import (
    distribute_resultant_on_triangles,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet4,
    unique_surface_nodes,
)
from .solver import solve_linear_static
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


def analytical_cantilever_reference(
    *,
    length_mm: float = 100.0,
    width_y_mm: float = 20.0,
    height_z_mm: float = 10.0,
    force_y_n: float = -1000.0,
    young_mpa: float = 200000.0,
) -> CantileverReference:
    """Euler-Bernoulli reference for a rectangular cantilever loaded in Y.

    Units are N, mm and MPa.  This is an analytical verification target, not an
    FEA result.  Bending is about Z, hence I_z = h_z * width_y**3 / 12.
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


def run_cantilever_convergence(
    step_path: str | Path,
    mesh_sizes_mm: Iterable[float] = (25.0, 20.0, 15.0),
) -> tuple[CantileverReference, list[ConvergenceSample]]:
    """Run the same STEP cantilever over several mesh sizes.

    Acceptance is deliberately based on raw numerical evidence.  The function
    reports error and equilibrium residuals but does not relabel the solution as
    validated or converged on its own.
    """
    ref = analytical_cantilever_reference()
    samples: list[ConvergenceSample] = []
    previous = None
    for raw_size in mesh_sizes_mm:
        size = float(raw_size)
        if size <= 0.0:
            raise ValueError("mesh sizes must be positive")
        if previous is not None and size >= previous:
            raise ValueError("mesh sizes must be strictly decreasing")
        previous = size

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


def benchmark_manifest(reference: CantileverReference, samples: list[ConvergenceSample]) -> dict:
    return {
        "result_class": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "analytical_reference": asdict(reference),
        "samples": [asdict(sample) for sample in samples],
        "converged_claim": False,
    }
