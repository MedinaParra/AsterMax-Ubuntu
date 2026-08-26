from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

import numpy as np

from .solver import Tet10LinearStaticResult
from .tet10 import TET10_GAUSS_POINTS, tet10_shape_functions


@dataclass(frozen=True)
class Tet10VtuEvidenceManifest:
    schema_version: str
    result_class: str
    units: dict[str, str]
    element_family: str
    vtk_cell_type: int
    node_count: int
    tet10_count: int
    integration_points_per_element: int
    stress_location: str
    nodal_stress_smoothing: bool
    displacement_max_mm: float
    von_mises_max_mpa: float
    hotspot_element_index: int | None
    hotspot_integration_point_index: int | None
    hotspot_coordinates_mm: list[float] | None
    vtu_sha256: str
    converged_claim: bool
    industrial_validation_claim: bool


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _fmt(values: np.ndarray) -> str:
    arr = np.asarray(values)
    if np.issubdtype(arr.dtype, np.integer):
        return " ".join(str(int(v)) for v in arr.reshape(-1))
    return " ".join(f"{float(v):.17g}" for v in arr.reshape(-1))


def tet10_hotspot(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
) -> dict[str, object] | None:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)
    if vm.size == 0:
        return None
    flat_index = int(np.argmax(vm))
    element_index, ip_index = np.unravel_index(flat_index, vm.shape)
    conn = elems[int(element_index)]
    shape = tet10_shape_functions(TET10_GAUSS_POINTS[int(ip_index)])
    coordinates = shape @ nodes[conn]
    displaced = shape @ (nodes[conn] + np.asarray(result.displacement_mm, dtype=float)[conn])
    return {
        "element_index": int(element_index),
        "integration_point_index": int(ip_index),
        "von_mises_mpa": float(vm[element_index, ip_index]),
        "natural_coordinates": TET10_GAUSS_POINTS[int(ip_index)].tolist(),
        "coordinates_mm": np.asarray(coordinates, dtype=float).tolist(),
        "displaced_coordinates_mm": np.asarray(displaced, dtype=float).tolist(),
    }


def write_tet10_linear_static_vtu(
    path: str | Path,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    result_class: str = "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
) -> Tet10VtuEvidenceManifest:
    """Write authentic quadratic tetrahedra to VTU without stress smoothing.

    VTK cell type 24 is VTK_QUADRATIC_TETRA. Stress is exported at the four
    integration points as 24 components per cell (4 points x 6 tensor terms),
    plus four integration-point von-Mises values and a cell maximum used only
    for visualization. No integration-point value is promoted to a nodal stress.
    """
    output = Path(path)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    u = np.asarray(result.displacement_mm, dtype=float)
    stress = np.asarray(result.integration_point_stress_mpa, dtype=float)
    vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("TET10 connectivity contains an out-of-range node index")
    if u.shape != nodes.shape:
        raise ValueError("displacement field must match node shape")
    if stress.shape != (elems.shape[0], 4, 6):
        raise ValueError("integration-point stress field must have shape (m, 4, 6)")
    if vm.shape != (elems.shape[0], 4):
        raise ValueError("integration-point von Mises field must have shape (m, 4)")
    if not all(np.all(np.isfinite(value)) for value in (nodes, u, stress, vm)):
        raise ValueError("TET10 VTU export refuses non-finite solver fields")

    output.parent.mkdir(parents=True, exist_ok=True)
    root = Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    grid = SubElement(root, "UnstructuredGrid")
    piece = SubElement(
        grid,
        "Piece",
        NumberOfPoints=str(nodes.shape[0]),
        NumberOfCells=str(elems.shape[0]),
    )

    field_data = SubElement(piece, "FieldData")
    SubElement(
        field_data,
        "DataArray",
        type="Int32",
        Name="ASTERMAX_CONVERGED_CLAIM",
        NumberOfTuples="1",
        format="ascii",
    ).text = "1" if converged_claim else "0"
    SubElement(
        field_data,
        "DataArray",
        type="Int32",
        Name="ASTERMAX_INDUSTRIAL_VALIDATION_CLAIM",
        NumberOfTuples="1",
        format="ascii",
    ).text = "1" if industrial_validation_claim else "0"
    SubElement(
        field_data,
        "DataArray",
        type="Int32",
        Name="ASTERMAX_TET10_INTEGRATION_POINTS",
        NumberOfTuples="1",
        format="ascii",
    ).text = "4"
    SubElement(
        field_data,
        "DataArray",
        type="Int32",
        Name="ASTERMAX_NODAL_STRESS_SMOOTHING",
        NumberOfTuples="1",
        format="ascii",
    ).text = "0"

    points = SubElement(piece, "Points")
    SubElement(
        points,
        "DataArray",
        type="Float64",
        NumberOfComponents="3",
        Name="Coordinates_mm",
        format="ascii",
    ).text = _fmt(nodes)

    cells = SubElement(piece, "Cells")
    SubElement(cells, "DataArray", type="Int64", Name="connectivity", format="ascii").text = _fmt(elems)
    SubElement(cells, "DataArray", type="Int64", Name="offsets", format="ascii").text = _fmt(
        np.arange(1, elems.shape[0] + 1, dtype=np.int64) * 10
    )
    # VTK_QUADRATIC_TETRA = 24.
    SubElement(cells, "DataArray", type="UInt8", Name="types", format="ascii").text = _fmt(
        np.full(elems.shape[0], 24, dtype=np.uint8)
    )

    point_data = SubElement(piece, "PointData", Vectors="U_mm", Scalars="U_MAG_mm")
    SubElement(
        point_data,
        "DataArray",
        type="Float64",
        Name="U_mm",
        NumberOfComponents="3",
        format="ascii",
    ).text = _fmt(u)
    u_mag = np.linalg.norm(u, axis=1)
    SubElement(
        point_data,
        "DataArray",
        type="Float64",
        Name="U_MAG_mm",
        NumberOfComponents="1",
        format="ascii",
    ).text = _fmt(u_mag)

    cell_data = SubElement(piece, "CellData", Scalars="VON_MISES_MAX_MPa")
    SubElement(
        cell_data,
        "DataArray",
        type="Float64",
        Name="IP_STRESS_MPa",
        NumberOfComponents="24",
        format="ascii",
    ).text = _fmt(stress.reshape((elems.shape[0], 24)))
    SubElement(
        cell_data,
        "DataArray",
        type="Float64",
        Name="IP_VON_MISES_MPa",
        NumberOfComponents="4",
        format="ascii",
    ).text = _fmt(vm)
    vm_max = np.max(vm, axis=1) if vm.size else np.empty((0,), dtype=float)
    SubElement(
        cell_data,
        "DataArray",
        type="Float64",
        Name="VON_MISES_MAX_MPa",
        NumberOfComponents="1",
        format="ascii",
    ).text = _fmt(vm_max)

    ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    digest = _sha256(output)
    hotspot = tet10_hotspot(nodes, elems, result)
    manifest = Tet10VtuEvidenceManifest(
        schema_version="AsterMaxTet10VtuEvidenceV1",
        result_class=result_class,
        units={"length": "mm", "force": "N", "stress": "MPa"},
        element_family="TET10_QUADRATIC",
        vtk_cell_type=24,
        node_count=int(nodes.shape[0]),
        tet10_count=int(elems.shape[0]),
        integration_points_per_element=4,
        stress_location="INTEGRATION_POINT",
        nodal_stress_smoothing=False,
        displacement_max_mm=float(np.max(u_mag)) if u_mag.size else 0.0,
        von_mises_max_mpa=float(np.max(vm)) if vm.size else 0.0,
        hotspot_element_index=None if hotspot is None else int(hotspot["element_index"]),
        hotspot_integration_point_index=None if hotspot is None else int(hotspot["integration_point_index"]),
        hotspot_coordinates_mm=None if hotspot is None else list(hotspot["coordinates_mm"]),
        vtu_sha256=digest,
        converged_claim=bool(converged_claim),
        industrial_validation_claim=bool(industrial_validation_claim),
    )
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest
