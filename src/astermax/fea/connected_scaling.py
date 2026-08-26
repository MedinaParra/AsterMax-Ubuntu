from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
import json

import numpy as np

from .solver import assemble_global_stiffness_sparse, solve_linear_static
from .tet4 import IsotropicMaterial, tet4_B_matrix


@dataclass(frozen=True)
class ConnectedScalingRecord:
    nx: int
    ny: int
    nz: int
    nodes: int
    dofs: int
    tet4: int
    csr_nnz: int
    csr_bytes: int
    dense_equivalent_bytes: int
    compression_ratio: float
    assembly_seconds: float
    solve_seconds: float
    volume_mm3: float
    max_displacement_mm: float
    max_von_mises_mpa: float
    force_residual_n: float
    moment_residual_nmm: float


def build_structured_bar(
    nx: int,
    ny: int = 2,
    nz: int = 1,
    length_mm: float = 100.0,
    width_mm: float = 20.0,
    height_mm: float = 10.0,
    total_tip_load_n: float = -1000.0,
):
    """Build a connected structured solid split into deterministic TET4 cells.

    The x=0 face is fully constrained. A total Y load is distributed equally
    across nodes on x=length. This is a verification/scaling fixture only and is
    not an industrial design model.
    """
    if min(nx, ny, nz) <= 0:
        raise ValueError("nx, ny and nz must be positive")
    if min(length_mm, width_mm, height_mm) <= 0.0:
        raise ValueError("fixture dimensions must be positive")
    if not np.isfinite(total_tip_load_n):
        raise ValueError("total_tip_load_n must be finite")

    xs = np.linspace(0.0, length_mm, nx + 1)
    ys = np.linspace(0.0, width_mm, ny + 1)
    zs = np.linspace(0.0, height_mm, nz + 1)

    def node_index(i: int, j: int, k: int) -> int:
        return (i * (ny + 1) + j) * (nz + 1) + k

    nodes: list[list[float]] = []
    for x in xs:
        for y in ys:
            for z in zs:
                nodes.append([float(x), float(y), float(z)])

    elements: list[list[int]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                p000 = node_index(i, j, k)
                p100 = node_index(i + 1, j, k)
                p010 = node_index(i, j + 1, k)
                p110 = node_index(i + 1, j + 1, k)
                p001 = node_index(i, j, k + 1)
                p101 = node_index(i + 1, j, k + 1)
                p011 = node_index(i, j + 1, k + 1)
                p111 = node_index(i + 1, j + 1, k + 1)
                # Six tetrahedra share the p000-p111 body diagonal and exactly
                # partition each structured hexahedral cell.
                elements.extend([
                    [p000, p100, p110, p111],
                    [p000, p110, p010, p111],
                    [p000, p010, p011, p111],
                    [p000, p011, p001, p111],
                    [p000, p001, p101, p111],
                    [p000, p101, p100, p111],
                ])

    nodes_array = np.asarray(nodes, dtype=float)
    elements_array = np.asarray(elements, dtype=int)
    loads = np.zeros_like(nodes_array)

    tip_nodes = np.flatnonzero(np.isclose(nodes_array[:, 0], length_mm))
    loads[tip_nodes, 1] = total_tip_load_n / tip_nodes.size

    fixed_nodes = np.flatnonzero(np.isclose(nodes_array[:, 0], 0.0))
    fixed_dofs = np.asarray(
        [3 * node + dof for node in fixed_nodes for dof in range(3)], dtype=int
    )
    return nodes_array, elements_array, loads, fixed_dofs


def _csr_storage_bytes(matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def run_connected_scaling(
    levels: tuple[int, ...] = (2, 4, 8),
    ny: int = 2,
    nz: int = 1,
    material: IsotropicMaterial | None = None,
) -> list[ConnectedScalingRecord]:
    if not levels or any(level <= 0 for level in levels):
        raise ValueError("levels must contain positive nx counts")
    if tuple(sorted(levels)) != levels or len(set(levels)) != len(levels):
        raise ValueError("levels must be strictly increasing")

    mat = material or IsotropicMaterial(210000.0, 0.3)
    records: list[ConnectedScalingRecord] = []

    for nx in levels:
        nodes, elements, loads, fixed = build_structured_bar(nx, ny=ny, nz=nz)
        ndof = nodes.shape[0] * 3

        volume = float(sum(tet4_B_matrix(nodes[conn])[1] for conn in elements))

        t0 = perf_counter()
        stiffness = assemble_global_stiffness_sparse(nodes, elements, mat)
        assembly_seconds = perf_counter() - t0

        t1 = perf_counter()
        result = solve_linear_static(nodes, elements, mat, loads, fixed)
        solve_seconds = perf_counter() - t1

        force_residual = float(
            np.linalg.norm(loads.sum(axis=0) + result.reactions_n.sum(axis=0))
        )
        applied_moment = np.cross(nodes, loads).sum(axis=0)
        reaction_moment = np.cross(nodes, result.reactions_n).sum(axis=0)
        moment_residual = float(np.linalg.norm(applied_moment + reaction_moment))

        csr_bytes = _csr_storage_bytes(stiffness)
        dense_bytes = int(ndof * ndof * np.dtype(float).itemsize)

        records.append(
            ConnectedScalingRecord(
                nx=nx,
                ny=ny,
                nz=nz,
                nodes=int(nodes.shape[0]),
                dofs=int(ndof),
                tet4=int(elements.shape[0]),
                csr_nnz=int(stiffness.nnz),
                csr_bytes=csr_bytes,
                dense_equivalent_bytes=dense_bytes,
                compression_ratio=float(csr_bytes / dense_bytes),
                assembly_seconds=float(assembly_seconds),
                solve_seconds=float(solve_seconds),
                volume_mm3=volume,
                max_displacement_mm=float(
                    np.linalg.norm(result.displacement_mm, axis=1).max()
                ),
                max_von_mises_mpa=float(result.element_von_mises_mpa.max()),
                force_residual_n=force_residual,
                moment_residual_nmm=moment_residual,
            )
        )

    return records


def connected_scaling_report_json(levels: tuple[int, ...] = (2, 4, 8)) -> str:
    payload = {
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "claim": "CONNECTED_MESH_SCALABILITY_MEASUREMENT_ONLY",
        "fixture": {
            "topology": "CONNECTED_STRUCTURED_TET4_BAR",
            "dimensions_mm": [100.0, 20.0, 10.0],
            "constraint": "X_MIN_FIXED",
            "load": "TOTAL_-1000_N_Y_ON_X_MAX_NODES",
        },
        "units": {
            "length": "mm",
            "force": "N",
            "moment": "N*mm",
            "stress": "MPa",
            "time": "s",
            "memory": "bytes",
        },
        "records": [asdict(record) for record in run_connected_scaling(levels)],
    }
    return json.dumps(payload, indent=2, sort_keys=True)
