from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

import numpy as np

from astermax.solver.errors import SolverEvidenceError
from astermax.solver.med_result import CONVERTER_VERSION, MedResult


@dataclass(frozen=True)
class VtuFieldEvidence:
    source_field_name: str
    source_association: str
    source_dataset_path: str
    components: tuple[str, ...]
    unit: str | None
    raw_shape: tuple[int, ...]
    vtk_array_name: str
    vtk_scope: str
    derived_vtk_array_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class VtuExportEvidence:
    relative_path: str
    sha256: str
    byte_size: int
    converter_version: str
    source_sha256: str
    point_count: int
    cell_count: int
    fields: tuple[VtuFieldEvidence, ...]


def _format_ascii(values: np.ndarray) -> str:
    array = np.asarray(values).reshape(-1)
    if np.issubdtype(array.dtype, np.integer):
        return " ".join(str(int(value)) for value in array)
    return " ".join(format(float(value), ".17g") for value in array)


def _data_array(
    parent: Element,
    vtk_type: str,
    name: str,
    values: np.ndarray,
    *,
    components: int = 1,
    tuples: int | None = None,
) -> Element:
    attrs = {"type": vtk_type, "Name": name, "format": "ascii"}
    if components != 1:
        attrs["NumberOfComponents"] = str(components)
    if tuples is not None:
        attrs["NumberOfTuples"] = str(tuples)
    element = SubElement(parent, "DataArray", **attrs)
    element.text = _format_ascii(values)
    return element


def _safe_vtk_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "_.-" else "_" for char in value)
    return cleaned or "FIELD"


def _von_mises(stress: np.ndarray, components: tuple[str, ...]) -> np.ndarray:
    required = ("SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ")
    if components != required:
        raise SolverEvidenceError(f"cannot derive von Mises: expected components {required}, got {components}")
    sxx, syy, szz, sxy, sxz, syz = (stress[..., index] for index in range(6))
    return np.sqrt(
        0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
        + 3.0 * (sxy**2 + sxz**2 + syz**2)
    )


def _global_cell_ids(result: MedResult, med_type: str) -> np.ndarray:
    offset = 0
    for block in result.cell_blocks:
        count = block.connectivity.shape[0]
        if block.med_type == med_type:
            return np.arange(offset, offset + count, dtype=np.int64)
        offset += count
    raise SolverEvidenceError(f"field references missing MED cell type {med_type}")


def write_vtu(result: MedResult, output_path: Path, *, relative_path: str | None = None) -> VtuExportEvidence:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    root = Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    grid = SubElement(root, "UnstructuredGrid")
    field_data = SubElement(grid, "FieldData")
    piece = SubElement(
        grid,
        "Piece",
        NumberOfPoints=str(result.points.shape[0]),
        NumberOfCells=str(result.number_of_cells),
    )
    point_data = SubElement(piece, "PointData")
    cell_data = SubElement(piece, "CellData")
    points = SubElement(piece, "Points")
    _data_array(points, "Float64", "Points", result.points, components=3)

    connectivity: list[int] = []
    offsets: list[int] = []
    cell_types: list[int] = []
    cursor = 0
    for block in result.cell_blocks:
        for row in block.connectivity:
            connectivity.extend(int(value) for value in row)
            cursor += len(row)
            offsets.append(cursor)
            cell_types.append(block.vtk_type)
    cells = SubElement(piece, "Cells")
    _data_array(cells, "Int64", "connectivity", np.asarray(connectivity, dtype=np.int64))
    _data_array(cells, "Int64", "offsets", np.asarray(offsets, dtype=np.int64))
    _data_array(cells, "UInt8", "types", np.asarray(cell_types, dtype=np.uint8))

    evidence: list[VtuFieldEvidence] = []
    for field_name in sorted(result.fields):
        field = result.fields[field_name]
        safe_name = _safe_vtk_name(field.name)
        raw_name = f"ASTERMAX_RAW__{safe_name}"
        if field.association == "NOE":
            if field.values.ndim != 2 or field.values.shape[0] != result.points.shape[0]:
                raise SolverEvidenceError(f"nodal field {field.name} does not align with mesh points")
            _data_array(point_data, "Float64", raw_name, field.values, components=field.values.shape[1])
            derived: list[str] = []
            if field.components[:3] == ("DX", "DY", "DZ") and field.values.shape[1] >= 3:
                translation_name = f"ASTERMAX_VIEW__{safe_name}__TRANSLATION"
                translation = field.values[:, :3]
                _data_array(point_data, "Float64", translation_name, translation, components=3)
                magnitude_name = f"ASTERMAX_DERIVED__{safe_name}__TRANSLATION_MAGNITUDE"
                _data_array(point_data, "Float64", magnitude_name, np.linalg.norm(translation, axis=1))
                derived.extend((translation_name, magnitude_name))
                if field.values.shape[1] >= 6 and field.components[3:6] == ("DRX", "DRY", "DRZ"):
                    rotation_name = f"ASTERMAX_VIEW__{safe_name}__ROTATION"
                    _data_array(point_data, "Float64", rotation_name, field.values[:, 3:6], components=3)
                    derived.append(rotation_name)
            evidence.append(
                VtuFieldEvidence(
                    source_field_name=field.name,
                    source_association=field.association,
                    source_dataset_path=field.source_path,
                    components=field.components,
                    unit=field.common_unit,
                    raw_shape=tuple(field.values.shape),
                    vtk_array_name=raw_name,
                    vtk_scope="PointData",
                    derived_vtk_array_names=tuple(derived),
                )
            )
            continue

        if field.association.startswith("NOE.") and field.med_cell_type:
            if field.values.ndim != 3:
                raise SolverEvidenceError(f"element-nodal field {field.name} must be rank 3")
            cell_ids = _global_cell_ids(result, field.med_cell_type)
            if field.values.shape[0] != len(cell_ids):
                raise SolverEvidenceError(f"element-nodal field {field.name} does not align with its cell block")
            flattened = field.values.reshape(field.values.shape[0], -1)
            raw_field_name = f"{raw_name}__{field.med_cell_type}__ELEMENT_NODAL"
            cell_id_name = f"ASTERMAX_MAP__{safe_name}__GLOBAL_CELL_ID"
            _data_array(
                field_data,
                "Float64",
                raw_field_name,
                flattened,
                components=flattened.shape[1],
                tuples=flattened.shape[0],
            )
            _data_array(field_data, "Int64", cell_id_name, cell_ids, tuples=len(cell_ids))
            derived: list[str] = []
            if field.components == ("SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ"):
                vm = _von_mises(field.values, field.components)
                vm_max = vm.max(axis=1)
                view_name = f"ASTERMAX_DERIVED__{safe_name}__VON_MISES_MAX"
                mask_name = f"ASTERMAX_MASK__{safe_name}__APPLICABLE"
                view = np.zeros(result.number_of_cells, dtype=np.float64)
                mask = np.zeros(result.number_of_cells, dtype=np.uint8)
                view[cell_ids] = vm_max
                mask[cell_ids] = 1
                _data_array(cell_data, "Float64", view_name, view)
                _data_array(cell_data, "UInt8", mask_name, mask)
                derived.extend((view_name, mask_name))
            evidence.append(
                VtuFieldEvidence(
                    source_field_name=field.name,
                    source_association=field.association,
                    source_dataset_path=field.source_path,
                    components=field.components,
                    unit=field.common_unit,
                    raw_shape=tuple(field.values.shape),
                    vtk_array_name=raw_field_name,
                    vtk_scope="FieldData",
                    derived_vtk_array_names=tuple(derived),
                )
            )
            continue

        raise SolverEvidenceError(f"unsupported field association during VTU export: {field.association}")

    ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    payload = output_path.read_bytes()
    return VtuExportEvidence(
        relative_path=relative_path or output_path.name,
        sha256=sha256(payload).hexdigest(),
        byte_size=len(payload),
        converter_version=CONVERTER_VERSION,
        source_sha256=result.source_sha256,
        point_count=result.points.shape[0],
        cell_count=result.number_of_cells,
        fields=tuple(evidence),
    )
