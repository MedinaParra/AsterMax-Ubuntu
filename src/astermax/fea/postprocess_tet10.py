from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

import numpy as np

from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class Tet10VtuEvidenceManifest:
    schema_version: str
    result_class: str
    units: dict[str, str]
    node_count: int
    tet10_count: int
    integration_points_per_element: int
    displacement_max_mm: float
    von_mises_ip_max_mpa: float
    stress_representation: str
    vtu_sha256: str
    converged_claim: bool
    industrial_validation_claim: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fmt(values: np.ndarray) -> str:
    arr = np.asarray(values)
    if np.issubdtype(arr.dtype, np.integer):
        return " ".join(str(int(value)) for value in arr.reshape(-1))
    return " ".join(f"{float(value):.17g}" for value in arr.reshape(-1))


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
    """Write quadratic TET10 solver output without inventing nodal stress.

    VTK cell type 24 (VTK_QUADRATIC_TETRA) is used.  Displacement is genuine
    nodal data.  Stress stays at the four TET10 integration points and is stored
    as 4-component von-Mises and 24-component stress arrays per cell.  The only
    scalar stress contour emitted is the explicit maximum over those four
    integration points; no nodal averaging or extrapolation is performed.
    """
    output = Path(path)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    u = np.asarray(result.displacement_mm, dtype=float)
    ip_stress = np.asarray(result.integration_point_stress_mpa, dtype=float)
    ip_vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10) for TET10")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")
    if u.shape != nodes.shape:
        raise ValueError("displacement field must match node shape")
    if ip_stress.shape != (elems.shape[0], 4, 6):
        raise ValueError("integration-point stress must have shape (m, 4, 6)")
    if ip_vm.shape != (elems.shape[0], 4):
        raise ValueError("integration-point von Mises must have shape (m, 4)")
    if not all(np.all(np.isfinite(value)) for value in (nodes, u, ip_stress, ip_vm)):
        raise ValueError("TET10 VTU export refuses non-finite geometry or solver fields")

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
        Name="ASTERMAX_STRESS_IS_NODAL",
        NumberOfTuples="1",
        format="ascii",
    ).text = "0"
    SubElement(
        field_data,
        "DataArray",
        type="Int32",
        Name="ASTERMAX_TET_ORDER",
        NumberOfTuples="1",
        format="ascii",
    ).text = "2"

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

    cell_data = SubElement(piece, "CellData", Scalars="VON_MISES_IP_MAX_MPa")
    SubElement(
        cell_data,
        "DataArray",
        type="Float64",
        Name="STRESS_IP4_MPa",
        NumberOfComponents="24",
        format="ascii",
    ).text = _fmt(ip_stress.reshape((elems.shape[0], 24)))
    SubElement(
        cell_data,
        "DataArray",
        type="Float64",
        Name="VON_MISES_IP4_MPa",
        NumberOfComponents="4",
        format="ascii",
    ).text = _fmt(ip_vm)
    ip_vm_max = np.max(ip_vm, axis=1) if ip_vm.size else np.zeros(elems.shape[0], dtype=float)
    SubElement(
        cell_data,
        "DataArray",
        type="Float64",
        Name="VON_MISES_IP_MAX_MPa",
        NumberOfComponents="1",
        format="ascii",
    ).text = _fmt(ip_vm_max)

    ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    digest = _sha256(output)
    manifest = Tet10VtuEvidenceManifest(
        schema_version="AsterMaxTet10VtuEvidenceV1",
        result_class=str(result_class),
        units={"length": "mm", "force": "N", "stress": "MPa"},
        node_count=int(nodes.shape[0]),
        tet10_count=int(elems.shape[0]),
        integration_points_per_element=4,
        displacement_max_mm=float(np.max(u_mag)) if u_mag.size else 0.0,
        von_mises_ip_max_mpa=float(np.max(ip_vm)) if ip_vm.size else 0.0,
        stress_representation="FOUR_INTEGRATION_POINTS_PLUS_EXPLICIT_ELEMENT_MAX_NO_NODAL_SMOOTHING",
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
