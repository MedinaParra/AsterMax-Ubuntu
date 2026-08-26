from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

import numpy as np

from .solver import LinearStaticResult


@dataclass(frozen=True)
class VtuEvidenceManifest:
    schema_version: str
    result_class: str
    units: dict[str, str]
    node_count: int
    tet4_count: int
    displacement_max_mm: float
    von_mises_max_mpa: float
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


def write_linear_static_vtu(
    path: str | Path,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: LinearStaticResult,
    *,
    result_class: str = "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
) -> VtuEvidenceManifest:
    """Write solver fields to a dependency-free ASCII VTU plus provenance manifest.

    The exporter does not promote numerical output to validated engineering evidence.
    Callers must opt into claims explicitly; verification harnesses keep both claims false.
    """
    output = Path(path)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    u = np.asarray(result.displacement_mm, dtype=float)
    stress = np.asarray(result.element_stress_mpa, dtype=float)
    vm = np.asarray(result.element_von_mises_mpa, dtype=float)

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 4:
        raise ValueError("elements must have shape (m, 4)")
    if u.shape != nodes.shape:
        raise ValueError("displacement field must match node shape")
    if stress.shape != (elems.shape[0], 6):
        raise ValueError("element stress field must have shape (m, 6)")
    if vm.shape != (elems.shape[0],):
        raise ValueError("von Mises field must have one value per element")
    if not all(np.all(np.isfinite(x)) for x in (nodes, u, stress, vm)):
        raise ValueError("VTU export refuses non-finite solver fields")

    output.parent.mkdir(parents=True, exist_ok=True)
    root = Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    grid = SubElement(root, "UnstructuredGrid")
    piece = SubElement(grid, "Piece", NumberOfPoints=str(nodes.shape[0]), NumberOfCells=str(elems.shape[0]))

    field_data = SubElement(piece, "FieldData")
    SubElement(field_data, "DataArray", type="Int32", Name="ASTERMAX_CONVERGED_CLAIM", NumberOfTuples="1", format="ascii").text = "1" if converged_claim else "0"
    SubElement(field_data, "DataArray", type="Int32", Name="ASTERMAX_INDUSTRIAL_VALIDATION_CLAIM", NumberOfTuples="1", format="ascii").text = "1" if industrial_validation_claim else "0"

    points = SubElement(piece, "Points")
    SubElement(points, "DataArray", type="Float64", NumberOfComponents="3", Name="Coordinates_mm", format="ascii").text = _fmt(nodes)

    cells = SubElement(piece, "Cells")
    SubElement(cells, "DataArray", type="Int64", Name="connectivity", format="ascii").text = _fmt(elems)
    SubElement(cells, "DataArray", type="Int64", Name="offsets", format="ascii").text = _fmt(np.arange(1, elems.shape[0] + 1, dtype=np.int64) * 4)
    SubElement(cells, "DataArray", type="UInt8", Name="types", format="ascii").text = _fmt(np.full(elems.shape[0], 10, dtype=np.uint8))

    point_data = SubElement(piece, "PointData", Vectors="U_mm", Scalars="U_MAG_mm")
    SubElement(point_data, "DataArray", type="Float64", Name="U_mm", NumberOfComponents="3", format="ascii").text = _fmt(u)
    u_mag = np.linalg.norm(u, axis=1)
    SubElement(point_data, "DataArray", type="Float64", Name="U_MAG_mm", NumberOfComponents="1", format="ascii").text = _fmt(u_mag)

    cell_data = SubElement(piece, "CellData", Scalars="VON_MISES_MPa")
    SubElement(cell_data, "DataArray", type="Float64", Name="STRESS_MPa", NumberOfComponents="6", format="ascii").text = _fmt(stress)
    SubElement(cell_data, "DataArray", type="Float64", Name="VON_MISES_MPa", NumberOfComponents="1", format="ascii").text = _fmt(vm)

    ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    digest = _sha256(output)
    manifest = VtuEvidenceManifest(
        schema_version="AsterMaxVtuEvidenceV1",
        result_class=result_class,
        units={"length": "mm", "force": "N", "stress": "MPa"},
        node_count=int(nodes.shape[0]),
        tet4_count=int(elems.shape[0]),
        displacement_max_mm=float(np.max(u_mag)) if u_mag.size else 0.0,
        von_mises_max_mpa=float(np.max(vm)) if vm.size else 0.0,
        vtu_sha256=digest,
        converged_claim=bool(converged_claim),
        industrial_validation_claim=bool(industrial_validation_claim),
    )
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
