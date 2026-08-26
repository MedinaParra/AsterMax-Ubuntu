from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping

import h5py
import numpy as np

from astermax.solver.errors import SolverEvidenceError

CONVERTER_VERSION = "astermax-med3-v1"

MED_TO_VTK_CELL_TYPE: Mapping[str, int] = {
    "SE2": 3,
    "SE3": 21,
    "TR3": 5,
    "TR6": 22,
    "TR7": 34,
    "QU4": 9,
    "QU8": 23,
    "TE4": 10,
    "TE10": 24,
    "HE8": 12,
    "HE20": 25,
}
NODES_PER_CELL: Mapping[str, int] = {
    "SE2": 2,
    "SE3": 3,
    "TR3": 3,
    "TR6": 6,
    "TR7": 7,
    "QU4": 4,
    "QU8": 8,
    "TE4": 4,
    "TE10": 10,
    "HE8": 8,
    "HE20": 20,
}
_NO_PROFILE = "MED_NO_PROFILE_INTERNAL"
_FIXED_WIDTH = 16


@dataclass(frozen=True)
class MedCellBlock:
    med_type: str
    vtk_type: int
    connectivity: np.ndarray
    source_path: str


@dataclass(frozen=True)
class MedField:
    name: str
    association: str
    components: tuple[str, ...]
    component_units: tuple[str | None, ...]
    values: np.ndarray
    source_path: str
    med_cell_type: str | None = None

    @property
    def common_unit(self) -> str | None:
        known = {unit for unit in self.component_units if unit}
        return next(iter(known)) if len(known) == 1 and len(known) == len(set(self.component_units)) else None


@dataclass(frozen=True)
class MedResult:
    source_path: Path
    source_sha256: str
    med_version: tuple[int, int, int]
    mesh_name: str
    points: np.ndarray
    cell_blocks: tuple[MedCellBlock, ...]
    fields: Mapping[str, MedField]

    @property
    def number_of_cells(self) -> int:
        return sum(block.connectivity.shape[0] for block in self.cell_blocks)

    def field_by_suffix(self, suffix: str) -> MedField:
        matches = [field for name, field in self.fields.items() if name.endswith(suffix)]
        if len(matches) != 1:
            raise SolverEvidenceError(f"expected exactly one MED field ending with {suffix!r}; found {len(matches)}")
        return matches[0]


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: object) -> str:
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8")
    return str(value)


def _fixed_strings(value: object, count: int) -> tuple[str, ...]:
    text = _text(value)
    expected = count * _FIXED_WIDTH
    if len(text) != expected:
        raise SolverEvidenceError(
            f"MED fixed-width attribute has length {len(text)}; expected {expected} for {count} components"
        )
    return tuple(text[index * _FIXED_WIDTH : (index + 1) * _FIXED_WIDTH].strip() for index in range(count))


def _only_child(group: h5py.Group, label: str) -> tuple[str, h5py.Group]:
    names = list(group.keys())
    if len(names) != 1:
        raise SolverEvidenceError(f"unsupported MED layout: {label} must contain exactly one child, found {len(names)}")
    name = names[0]
    child = group[name]
    if not isinstance(child, h5py.Group):
        raise SolverEvidenceError(f"unsupported MED layout: {label}/{name} is not a group")
    return name, child


def _require_no_profile(group: h5py.Group, label: str) -> tuple[str, h5py.Group]:
    profile_attr = _text(group.attrs.get("PFL", "")).strip()
    if profile_attr != _NO_PROFILE:
        raise SolverEvidenceError(f"unsupported MED profile in {label}: {profile_attr!r}")
    profile_name, profile = _only_child(group, label)
    if profile_name != _NO_PROFILE:
        raise SolverEvidenceError(f"unsupported MED profile group in {label}: {profile_name!r}")
    return profile_name, profile


def read_code_aster_rmed(path: Path, *, expected_sha256: str | None = None) -> MedResult:
    path = path.resolve()
    if not path.is_file():
        raise SolverEvidenceError(f"missing MED/RMED artifact: {path}")
    actual_sha256 = sha256_file(path)
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise SolverEvidenceError(
            f"MED/RMED SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    try:
        handle = h5py.File(path, "r")
    except OSError as exc:
        raise SolverEvidenceError(f"artifact is not a readable HDF5 MED file: {path}") from exc

    with handle as med:
        required_roots = {"CHA", "ENS_MAA", "INFOS_GENERALES"}
        missing = sorted(required_roots - set(med.keys()))
        if missing:
            raise SolverEvidenceError(f"unsupported MED layout: missing root groups {missing}")
        info = med["INFOS_GENERALES"]
        version = tuple(int(info.attrs.get(name, -1)) for name in ("MAJ", "MIN", "REL"))
        if version[0] != 3:
            raise SolverEvidenceError(f"unsupported MED major version: {version[0]}")

        fields_group = med["CHA"]
        field_names = sorted(fields_group.keys())
        if not field_names:
            raise SolverEvidenceError("MED/RMED contains no result fields")
        mesh_names = {_text(fields_group[name].attrs.get("MAI", "")).strip() for name in field_names}
        if len(mesh_names) != 1 or "" in mesh_names:
            raise SolverEvidenceError(f"unsupported MED result: fields reference inconsistent meshes {sorted(mesh_names)}")
        mesh_name = next(iter(mesh_names))
        meshes = med["ENS_MAA"]
        if mesh_name not in meshes:
            raise SolverEvidenceError(f"MED result references missing mesh {mesh_name!r}")
        mesh = meshes[mesh_name]
        if int(mesh.attrs.get("DIM", -1)) != 3 or int(mesh.attrs.get("ESP", -1)) != 3:
            raise SolverEvidenceError("W2B supports only 3D MED mesh coordinates")
        mesh_step_name, mesh_step = _only_child(mesh, f"ENS_MAA/{mesh_name}")
        if "NOE" not in mesh_step or "MAI" not in mesh_step:
            raise SolverEvidenceError("unsupported MED mesh: NOE and MAI groups are required")
        node_group = mesh_step["NOE"]
        if _text(node_group.attrs.get("PFL", "")).strip() != _NO_PROFILE:
            raise SolverEvidenceError("unsupported MED nodal profile")
        if "COO" not in node_group:
            raise SolverEvidenceError("unsupported MED mesh: missing NOE/COO")
        coordinate_dataset = node_group["COO"]
        node_count = int(coordinate_dataset.attrs.get("NBR", -1))
        coordinate_values = np.asarray(coordinate_dataset[...], dtype=np.float64)
        if node_count <= 0 or coordinate_values.size != 3 * node_count:
            raise SolverEvidenceError("MED coordinate dataset has inconsistent size")
        points = coordinate_values.reshape(3, node_count).T.copy()

        cell_blocks: list[MedCellBlock] = []
        cell_counts: dict[str, int] = {}
        for med_type in sorted(mesh_step["MAI"].keys()):
            if med_type not in MED_TO_VTK_CELL_TYPE:
                raise SolverEvidenceError(f"unsupported MED cell type: {med_type}")
            block_group = mesh_step["MAI"][med_type]
            if _text(block_group.attrs.get("PFL", "")).strip() != _NO_PROFILE:
                raise SolverEvidenceError(f"unsupported MED cell profile for {med_type}")
            if "NOD" not in block_group:
                raise SolverEvidenceError(f"MED cell block {med_type} has no NOD connectivity")
            dataset = block_group["NOD"]
            cell_count = int(dataset.attrs.get("NBR", -1))
            nodes_per_cell = NODES_PER_CELL[med_type]
            raw = np.asarray(dataset[...], dtype=np.int64)
            if cell_count < 0 or raw.size != cell_count * nodes_per_cell:
                raise SolverEvidenceError(f"MED connectivity size mismatch for {med_type}")
            connectivity = raw.reshape(nodes_per_cell, cell_count).T.copy() - 1
            if connectivity.size and (int(connectivity.min()) < 0 or int(connectivity.max()) >= node_count):
                raise SolverEvidenceError(f"MED connectivity references an invalid node in {med_type}")
            cell_counts[med_type] = cell_count
            cell_blocks.append(
                MedCellBlock(
                    med_type=med_type,
                    vtk_type=MED_TO_VTK_CELL_TYPE[med_type],
                    connectivity=connectivity,
                    source_path=f"/ENS_MAA/{mesh_name}/{mesh_step_name}/MAI/{med_type}/NOD",
                )
            )

        parsed_fields: dict[str, MedField] = {}
        for field_name in field_names:
            field_group = fields_group[field_name]
            component_count = int(field_group.attrs.get("NCO", -1))
            if component_count <= 0:
                raise SolverEvidenceError(f"MED field {field_name} has invalid component count")
            components = _fixed_strings(field_group.attrs.get("NOM", b""), component_count)
            raw_units = _fixed_strings(field_group.attrs.get("UNI", b""), component_count)
            component_units = tuple(unit or None for unit in raw_units)
            field_step_name, field_step = _only_child(field_group, f"CHA/{field_name}")
            association_name, association_group = _only_child(field_step, f"CHA/{field_name}/{field_step_name}")
            profile_name, profile = _require_no_profile(
                association_group, f"CHA/{field_name}/{field_step_name}/{association_name}"
            )
            if "CO" not in profile:
                raise SolverEvidenceError(f"MED field {field_name} profile has no CO dataset")
            raw = np.asarray(profile["CO"][...], dtype=np.float64)
            source_path = f"/CHA/{field_name}/{field_step_name}/{association_name}/{profile_name}/CO"

            med_cell_type: str | None = None
            if association_name == "NOE":
                if int(profile.attrs.get("NBR", -1)) != node_count or int(profile.attrs.get("NGA", -1)) != 1:
                    raise SolverEvidenceError(f"MED nodal field {field_name} has inconsistent profile dimensions")
                expected = component_count * node_count
                if raw.size != expected:
                    raise SolverEvidenceError(f"MED nodal field {field_name} has {raw.size} values; expected {expected}")
                values = raw.reshape(component_count, node_count).T.copy()
            elif association_name.startswith("NOE."):
                med_cell_type = association_name.split(".", 1)[1]
                if med_cell_type not in cell_counts:
                    raise SolverEvidenceError(
                        f"MED element-nodal field {field_name} references absent cell block {med_cell_type}"
                    )
                cell_count = cell_counts[med_cell_type]
                nodes_per_cell = NODES_PER_CELL[med_cell_type]
                if int(profile.attrs.get("NBR", -1)) != cell_count or int(profile.attrs.get("NGA", -1)) != nodes_per_cell:
                    raise SolverEvidenceError(f"MED element-nodal field {field_name} has inconsistent profile dimensions")
                expected = component_count * cell_count * nodes_per_cell
                if raw.size != expected:
                    raise SolverEvidenceError(
                        f"MED element-nodal field {field_name} has {raw.size} values; expected {expected}"
                    )
                values = raw.reshape(component_count, cell_count, nodes_per_cell).transpose(1, 2, 0).copy()
            else:
                raise SolverEvidenceError(f"unsupported MED field association for {field_name}: {association_name}")

            parsed_fields[field_name] = MedField(
                name=field_name,
                association=association_name,
                components=components,
                component_units=component_units,
                values=values,
                source_path=source_path,
                med_cell_type=med_cell_type,
            )

    return MedResult(
        source_path=path,
        source_sha256=actual_sha256,
        med_version=version,
        mesh_name=mesh_name,
        points=points,
        cell_blocks=tuple(cell_blocks),
        fields=parsed_fields,
    )
