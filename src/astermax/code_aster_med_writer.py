from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import h5py
import meshio
import numpy as np


class CodeAsterMedWriterError(RuntimeError):
    pass


# Code_Aster catalog keywords GROUP_MA/GROUP_NO accept strings of length <= 24.
# Keep the MED-side contract at the solver limit instead of the broader MED limit.
_GROUP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,23}$")


@dataclass(frozen=True)
class CodeAsterMedGroupEvidence:
    path: Path
    support_group: str
    load_group: str
    volume_group: str
    support_family: int
    load_family: int
    volume_family: int
    support_tri6_count: int
    load_tri6_count: int
    tet10_count: int
    med_sha256: str
    med_family_names_verified: bool = True
    fea_solve_executed: bool = False
    results_verified: bool = False


def _name(value: str) -> str:
    name = str(value).strip()
    if not _GROUP_RE.fullmatch(name):
        raise CodeAsterMedWriterError("CODE_ASTER_MED_GROUP_NAME_INVALID")
    return name


def _validate(
    nodes_mm: np.ndarray,
    tet10: np.ndarray,
    support_tri6: np.ndarray,
    load_tri6: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    tet = np.asarray(tet10, dtype=int)
    support = np.asarray(support_tri6, dtype=int)
    load = np.asarray(load_tri6, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or nodes.shape[0] < 10 or not np.isfinite(nodes).all():
        raise CodeAsterMedWriterError("CODE_ASTER_MED_NODES_INVALID")
    if tet.ndim != 2 or tet.shape[1] != 10 or tet.shape[0] < 1:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_TET10_INVALID")
    for conn, label in ((support, "SUPPORT_TRI6"), (load, "LOAD_TRI6")):
        if conn.ndim != 2 or conn.shape[1] != 6 or conn.shape[0] < 1:
            raise CodeAsterMedWriterError(f"CODE_ASTER_MED_{label}_INVALID")
    for conn, label in ((tet, "TET10"), (support, "SUPPORT_TRI6"), (load, "LOAD_TRI6")):
        if conn.min() < 0 or conn.max() >= nodes.shape[0]:
            raise CodeAsterMedWriterError(f"CODE_ASTER_MED_{label}_CONNECTIVITY_OUT_OF_RANGE")
        if any(len(set(map(int, row))) != row.size for row in conn):
            raise CodeAsterMedWriterError(f"CODE_ASTER_MED_{label}_REPEATED_NODE")
    support_faces = {tuple(sorted(map(int, row[:3]))) for row in support}
    load_faces = {tuple(sorted(map(int, row[:3]))) for row in load}
    if len(support_faces) != support.shape[0] or len(load_faces) != load.shape[0]:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_DUPLICATE_TRI6_FACE")
    if support_faces & load_faces:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_SUPPORT_LOAD_FACE_OVERLAP")
    return nodes, tet, support, load


def _decode_med_name(row: np.ndarray) -> str:
    return "".join(chr(int(v)) for v in np.asarray(row).reshape(-1)).rstrip("\x00").strip()


def _read_hdf5_families(path: Path) -> dict[int, tuple[str, ...]]:
    families: dict[int, tuple[str, ...]] = {}
    with h5py.File(path, "r") as handle:
        if "FAS" not in handle:
            raise CodeAsterMedWriterError("CODE_ASTER_MED_FAS_MISSING")
        fas = handle["FAS"]
        mesh_names = list(fas.keys())
        if len(mesh_names) != 1:
            raise CodeAsterMedWriterError("CODE_ASTER_MED_MESH_FAMILY_ROOT_NOT_UNIQUE")
        mesh_families = fas[mesh_names[0]]
        if "ELEME" not in mesh_families:
            raise CodeAsterMedWriterError("CODE_ASTER_MED_ELEMENT_FAMILIES_MISSING")
        for family in mesh_families["ELEME"].values():
            family_id = int(family.attrs["NUM"])
            if "GRO" not in family or "NOM" not in family["GRO"]:
                raise CodeAsterMedWriterError("CODE_ASTER_MED_FAMILY_GROUP_NAMES_MISSING")
            names = tuple(_decode_med_name(row) for row in family["GRO"]["NOM"][()])
            families[family_id] = names
    return families


def _read_family_counts(path: Path) -> dict[int, int]:
    counts: dict[int, int] = {}
    with h5py.File(path, "r") as handle:
        meshes = handle.get("ENS_MAA")
        if meshes is None or len(meshes.keys()) != 1:
            raise CodeAsterMedWriterError("CODE_ASTER_MED_MESH_NOT_UNIQUE")
        mesh = meshes[next(iter(meshes.keys()))]
        steps = [key for key in mesh.keys() if key.startswith("-")]
        if len(steps) != 1:
            raise CodeAsterMedWriterError("CODE_ASTER_MED_TIMESTEP_NOT_UNIQUE")
        mai = mesh[steps[0]].get("MAI")
        if mai is None:
            raise CodeAsterMedWriterError("CODE_ASTER_MED_ELEMENTS_MISSING")
        for cell_group in mai.values():
            fam = cell_group.get("FAM")
            if fam is None:
                continue
            for raw in np.asarray(fam[()]).reshape(-1):
                family_id = int(raw)
                counts[family_id] = counts.get(family_id, 0) + 1
    return counts


def write_code_aster_med(
    destination: str | Path,
    *,
    nodes_mm: np.ndarray,
    tet10: np.ndarray,
    support_tri6: np.ndarray,
    load_tri6: np.ndarray,
    support_group: str = "FIXED_FACE",
    load_group: str = "LOAD_FACE",
    volume_group: str = "SOLID",
) -> Path:
    """Write a MED file with explicit MED family/group semantics for Code_Aster.

    This implementation intentionally targets meshio 5.3.5's MED backend, whose
    writer serializes ``mesh.cell_data['cell_tags']`` into element FAM datasets
    and ``mesh.cell_tags`` into FAS/<mesh>/ELEME family/group names. The exact
    meshio version is pinned in pyproject.toml because this is an external file
    format contract, not a generic convenience dependency.
    """
    nodes, tet, support, load = _validate(nodes_mm, tet10, support_tri6, load_tri6)
    fixed_name, load_name, solid_name = _name(support_group), _name(load_group), _name(volume_group)
    if len({fixed_name, load_name, solid_name}) != 3:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_GROUP_NAMES_MUST_DIFFER")

    path = Path(destination).resolve()
    if path.suffix.lower() != ".med":
        raise CodeAsterMedWriterError("CODE_ASTER_MED_EXTENSION_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)

    surface = np.vstack((support, load))
    fixed_family, load_family, solid_family = -1, -2, -3
    surface_tags = np.concatenate((
        np.full(support.shape[0], fixed_family, dtype=np.int64),
        np.full(load.shape[0], load_family, dtype=np.int64),
    ))
    volume_tags = np.full(tet.shape[0], solid_family, dtype=np.int64)

    mesh = meshio.Mesh(
        points=nodes,
        cells=[("triangle6", surface), ("tetra10", tet)],
        cell_data={"cell_tags": [surface_tags, volume_tags]},
    )
    mesh.cell_tags = {
        fixed_family: [fixed_name],
        load_family: [load_name],
        solid_family: [solid_name],
    }
    try:
        meshio.write(path, mesh, file_format="med")
    except Exception as exc:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_WRITE_FAILED") from exc
    if not path.is_file() or path.stat().st_size <= 0:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_WRITE_EMPTY")
    return path


def verify_code_aster_med_groups(
    path: str | Path,
    *,
    support_group: str = "FIXED_FACE",
    load_group: str = "LOAD_FACE",
    volume_group: str = "SOLID",
    expected_support_tri6: int,
    expected_load_tri6: int,
    expected_tet10: int,
) -> CodeAsterMedGroupEvidence:
    med = Path(path).resolve()
    if not med.is_file() or med.stat().st_size <= 0:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_FILE_MISSING")
    fixed_name, load_name, solid_name = _name(support_group), _name(load_group), _name(volume_group)
    families = _read_hdf5_families(med)
    counts = _read_family_counts(med)

    by_name: dict[str, int] = {}
    for family_id, names in families.items():
        for name in names:
            if name in by_name:
                raise CodeAsterMedWriterError("CODE_ASTER_MED_GROUP_NAME_NOT_UNIQUE")
            by_name[name] = family_id
    for name in (fixed_name, load_name, solid_name):
        if name not in by_name:
            raise CodeAsterMedWriterError(f"CODE_ASTER_MED_GROUP_MISSING:{name}")

    fixed_family = by_name[fixed_name]
    load_family = by_name[load_name]
    solid_family = by_name[solid_name]
    if len({fixed_family, load_family, solid_family}) != 3:
        raise CodeAsterMedWriterError("CODE_ASTER_MED_FAMILY_BINDING_NOT_DISTINCT")
    if counts.get(fixed_family, 0) != int(expected_support_tri6):
        raise CodeAsterMedWriterError("CODE_ASTER_MED_SUPPORT_COUNT_MISMATCH")
    if counts.get(load_family, 0) != int(expected_load_tri6):
        raise CodeAsterMedWriterError("CODE_ASTER_MED_LOAD_COUNT_MISMATCH")
    if counts.get(solid_family, 0) != int(expected_tet10):
        raise CodeAsterMedWriterError("CODE_ASTER_MED_VOLUME_COUNT_MISMATCH")

    return CodeAsterMedGroupEvidence(
        path=med,
        support_group=fixed_name,
        load_group=load_name,
        volume_group=solid_name,
        support_family=fixed_family,
        load_family=load_family,
        volume_family=solid_family,
        support_tri6_count=int(expected_support_tri6),
        load_tri6_count=int(expected_load_tri6),
        tet10_count=int(expected_tet10),
        med_sha256=sha256(med.read_bytes()).hexdigest(),
    )
