from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
import json

import numpy as np

from .solver import assemble_global_stiffness_sparse, solve_linear_static
from .tet4 import IsotropicMaterial


@dataclass(frozen=True)
class ScalingRecord:
    cells: int
    nodes: int
    dofs: int
    tet4: int
    csr_nnz: int
    csr_bytes: int
    dense_equivalent_bytes: int
    compression_ratio: float
    assembly_seconds: float
    solve_seconds: float
    max_displacement_mm: float
    force_residual_n: float


def build_independent_tetra_pack(cells: int, spacing_mm: float = 20.0):
    """Create a deterministic pack of uncoupled tetrahedra for solver scaling tests.

    Each tetra has three fully fixed base nodes and one free apex node. This is a
    synthetic verification fixture only; it is not an engineering component.
    """
    if cells <= 0:
        raise ValueError("cells must be positive")
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")

    nodes = []
    elements = []
    fixed_dofs: list[int] = []
    loads = np.zeros((cells * 4, 3), dtype=float)

    for i in range(cells):
        x = i * spacing_mm
        base = 4 * i
        nodes.extend([
            [x, 0.0, 0.0],
            [x + 10.0, 0.0, 0.0],
            [x, 10.0, 0.0],
            [x, 0.0, 10.0],
        ])
        elements.append([base, base + 1, base + 2, base + 3])
        for node in (base, base + 2, base + 3):
            fixed_dofs.extend([3 * node, 3 * node + 1, 3 * node + 2])
        loads[base + 1, 0] = 1000.0

    return (
        np.asarray(nodes, dtype=float),
        np.asarray(elements, dtype=int),
        loads,
        np.asarray(fixed_dofs, dtype=int),
    )


def csr_storage_bytes(matrix) -> int:
    """Return exact NumPy backing-store bytes for a SciPy CSR matrix."""
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def run_sparse_scaling(
    levels: tuple[int, ...] = (8, 32, 128),
    material: IsotropicMaterial | None = None,
) -> list[ScalingRecord]:
    if not levels or any(level <= 0 for level in levels):
        raise ValueError("levels must contain positive cell counts")
    if tuple(sorted(levels)) != levels or len(set(levels)) != len(levels):
        raise ValueError("levels must be strictly increasing")

    mat = material or IsotropicMaterial(210000.0, 0.3)
    records: list[ScalingRecord] = []

    for cells in levels:
        nodes, elements, loads, fixed = build_independent_tetra_pack(cells)
        ndof = nodes.shape[0] * 3

        t0 = perf_counter()
        k = assemble_global_stiffness_sparse(nodes, elements, mat)
        assembly_seconds = perf_counter() - t0

        t1 = perf_counter()
        result = solve_linear_static(nodes, elements, mat, loads, fixed)
        solve_seconds = perf_counter() - t1

        applied = loads.sum(axis=0)
        reaction = result.reactions_n.sum(axis=0)
        force_residual = float(np.linalg.norm(applied + reaction))
        csr_bytes = csr_storage_bytes(k)
        dense_bytes = int(ndof * ndof * np.dtype(float).itemsize)

        records.append(
            ScalingRecord(
                cells=cells,
                nodes=int(nodes.shape[0]),
                dofs=int(ndof),
                tet4=int(elements.shape[0]),
                csr_nnz=int(k.nnz),
                csr_bytes=csr_bytes,
                dense_equivalent_bytes=dense_bytes,
                compression_ratio=float(csr_bytes / dense_bytes),
                assembly_seconds=float(assembly_seconds),
                solve_seconds=float(solve_seconds),
                max_displacement_mm=float(np.linalg.norm(result.displacement_mm, axis=1).max()),
                force_residual_n=force_residual,
            )
        )

    return records


def scaling_report_json(levels: tuple[int, ...] = (8, 32, 128)) -> str:
    payload = {
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "claim": "SCALABILITY_MEASUREMENT_ONLY",
        "units": {"length": "mm", "force": "N", "stress": "MPa", "time": "s", "memory": "bytes"},
        "records": [asdict(record) for record in run_sparse_scaling(levels)],
    }
    return json.dumps(payload, indent=2, sort_keys=True)
