"""Auditable postprocessing for AsterMax verification models.

Provides invariant-based Von Mises stress and an ASCII legacy-VTK unstructured-grid
export that can be opened in ParaView. The writer intentionally stays dependency-free
so the verification harness can inspect the exact artifact produced by the PMV.
"""

from math import sqrt
from pathlib import Path
from typing import Sequence

from .global_static import GlobalStaticResult


class PostprocessError(ValueError):
    """Raised when result data cannot be postprocessed consistently."""


def von_mises(stress: Sequence[float]) -> float:
    """Return 3D Von Mises stress for [xx, yy, zz, xy, yz, xz]."""
    if len(stress) != 6:
        raise PostprocessError("3D stress must contain six components")
    sx, sy, sz, txy, tyz, txz = map(float, stress)
    value = 0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
    value += 3.0 * (txy * txy + tyz * tyz + txz * txz)
    return sqrt(max(0.0, value))


def element_von_mises(result: GlobalStaticResult) -> tuple[float, ...]:
    return tuple(von_mises(element.stress) for element in result.element_results)


def displacement_vectors(result: GlobalStaticResult, node_count: int) -> tuple[tuple[float, float, float], ...]:
    if node_count < 1 or len(result.displacements) != 3 * node_count:
        raise PostprocessError("displacement vector length does not match node count")
    return tuple(
        tuple(result.displacements[3 * node + component] for component in range(3))
        for node in range(node_count)
    )


def write_legacy_vtk(
    path: str | Path,
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    result: GlobalStaticResult,
) -> Path:
    """Write TET4 geometry, displacement vectors and cell stresses to ASCII VTK.

    Geometry remains undeformed; displacement is stored as POINT_DATA so ParaView can
    apply a Warp By Vector filter without losing the original engineering geometry.
    Stress and Von Mises are CELL_DATA because a linear TET4 has constant stress.
    """
    if not nodes or any(len(node) != 3 for node in nodes):
        raise PostprocessError("nodes must contain 3D coordinates")
    if len(elements) != len(result.element_results):
        raise PostprocessError("element count does not match solver results")
    for element in elements:
        if len(element) != 4 or any(index < 0 or index >= len(nodes) for index in element):
            raise PostprocessError("VTK export requires valid four-node tetrahedra")

    vectors = displacement_vectors(result, len(nodes))
    vm = element_von_mises(result)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# vtk DataFile Version 3.0",
        "AsterMax verified linear-static result",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {len(nodes)} double",
    ]
    lines.extend(" ".join(f"{float(value):.17g}" for value in node) for node in nodes)
    lines.append(f"CELLS {len(elements)} {5 * len(elements)}")
    lines.extend("4 " + " ".join(str(int(index)) for index in element) for element in elements)
    lines.append(f"CELL_TYPES {len(elements)}")
    lines.extend("10" for _ in elements)  # VTK_TETRA

    lines.append(f"POINT_DATA {len(nodes)}")
    lines.append("VECTORS displacement_mm double")
    lines.extend(" ".join(f"{value:.17g}" for value in vector) for vector in vectors)

    lines.append(f"CELL_DATA {len(elements)}")
    lines.append("SCALARS von_mises_MPa double 1")
    lines.append("LOOKUP_TABLE default")
    lines.extend(f"{value:.17g}" for value in vm)
    lines.append("TENSORS stress_MPa double")
    for element in result.element_results:
        sx, sy, sz, txy, tyz, txz = element.stress
        lines.extend([
            f"{sx:.17g} {txy:.17g} {txz:.17g}",
            f"{txy:.17g} {sy:.17g} {tyz:.17g}",
            f"{txz:.17g} {tyz:.17g} {sz:.17g}",
        ])

    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
