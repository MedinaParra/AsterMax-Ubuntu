from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import numpy as np


class MedPhysicalGroupError(RuntimeError):
    pass


_GROUP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,23}$")


@dataclass(frozen=True)
class MedPhysicalGroupEvidence:
    path: Path
    group_name: str
    dimension: int
    entity_count: int
    element_count: int
    med_sha256: str
    verified: bool = True
    fea_solve_executed: bool = False
    results_verified: bool = False


def _validate_group_name(name: str) -> str:
    value = str(name).strip()
    if not _GROUP_RE.fullmatch(value):
        raise MedPhysicalGroupError("MED_GROUP_NAME_INVALID")
    return value


def _validate_mesh(nodes_mm: np.ndarray, tetra4: np.ndarray, surface_tri3: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    volume = np.asarray(tetra4, dtype=int)
    surface = np.asarray(surface_tri3, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or nodes.shape[0] < 4 or not np.isfinite(nodes).all():
        raise MedPhysicalGroupError("MED_NODES_INVALID")
    if volume.ndim != 2 or volume.shape[1] != 4 or volume.shape[0] < 1:
        raise MedPhysicalGroupError("MED_TETRA4_INVALID")
    if surface.ndim != 2 or surface.shape[1] != 3 or surface.shape[0] < 1:
        raise MedPhysicalGroupError("MED_TRI3_INVALID")
    for conn, label in ((volume, "TETRA4"), (surface, "TRI3")):
        if conn.min() < 0 or conn.max() >= nodes.shape[0]:
            raise MedPhysicalGroupError(f"MED_{label}_CONNECTIVITY_OUT_OF_RANGE")
    canonical = np.sort(surface, axis=1)
    if np.unique(canonical, axis=0).shape[0] != canonical.shape[0]:
        raise MedPhysicalGroupError("MED_TRI3_DUPLICATE")
    return nodes, volume, surface


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_med_with_surface_group(
    destination: str | Path,
    *,
    nodes_mm: np.ndarray,
    tetra4: np.ndarray,
    surface_tri3: np.ndarray,
    surface_group: str,
    volume_group: str = "SOLID",
) -> Path:
    """Write a real MED file with a named surface physical group using Gmsh.

    C7.7 intentionally uses linear TET4/TRI3 as a minimal transport proof. It
    proves physical-group persistence in MED; it does not claim production
    TET10 export or a Code_Aster solve.
    """
    nodes, volume, surface = _validate_mesh(nodes_mm, tetra4, surface_tri3)
    surf_name = _validate_group_name(surface_group)
    vol_name = _validate_group_name(volume_group)
    if surf_name == vol_name:
        raise MedPhysicalGroupError("MED_SURFACE_AND_VOLUME_GROUPS_MUST_DIFFER")

    path = Path(destination).resolve()
    if path.suffix.lower() != ".med":
        raise MedPhysicalGroupError("MED_DESTINATION_EXTENSION_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)

    import gmsh

    owned = not bool(gmsh.isInitialized())
    if owned:
        gmsh.initialize()
    try:
        gmsh.clear()
        gmsh.model.add("astermax_c7_7")
        surface_entity = gmsh.model.addDiscreteEntity(2, 1)
        volume_entity = gmsh.model.addDiscreteEntity(3, 1, [surface_entity])

        surface_nodes = sorted({int(i) for i in surface.reshape(-1)})
        surface_set = set(surface_nodes)
        interior_nodes = [i for i in range(nodes.shape[0]) if i not in surface_set]
        if not interior_nodes:
            # A tetra may have all nodes on its boundary; classify one node on
            # the volume entity only when necessary to keep node tags unique.
            interior_nodes = [int(volume.reshape(-1)[-1])]
            surface_nodes = [i for i in surface_nodes if i != interior_nodes[0]]

        if surface_nodes:
            tags = [i + 1 for i in surface_nodes]
            coords = nodes[surface_nodes].reshape(-1).tolist()
            gmsh.model.mesh.addNodes(2, surface_entity, tags, coords)
        if interior_nodes:
            tags = [i + 1 for i in interior_nodes]
            coords = nodes[interior_nodes].reshape(-1).tolist()
            gmsh.model.mesh.addNodes(3, volume_entity, tags, coords)

        tri_tags = list(range(1, surface.shape[0] + 1))
        tet_tags = list(range(1, volume.shape[0] + 1))
        gmsh.model.mesh.addElementsByType(surface_entity, 2, tri_tags, (surface + 1).reshape(-1).tolist())
        gmsh.model.mesh.addElementsByType(volume_entity, 4, tet_tags, (volume + 1).reshape(-1).tolist())

        surf_phys = gmsh.model.addPhysicalGroup(2, [surface_entity])
        gmsh.model.setPhysicalName(2, surf_phys, surf_name)
        vol_phys = gmsh.model.addPhysicalGroup(3, [volume_entity])
        gmsh.model.setPhysicalName(3, vol_phys, vol_name)
        gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.write(str(path))
    except Exception as exc:
        raise MedPhysicalGroupError("MED_WRITE_FAILED") from exc
    finally:
        gmsh.clear()
        if owned:
            gmsh.finalize()
    if not path.is_file() or path.stat().st_size <= 0:
        raise MedPhysicalGroupError("MED_WRITE_EMPTY")
    return path


def verify_med_surface_group(path: str | Path, *, expected_group: str, expected_element_count: int) -> MedPhysicalGroupEvidence:
    med = Path(path).resolve()
    group_name = _validate_group_name(expected_group)
    if not med.is_file() or med.suffix.lower() != ".med":
        raise MedPhysicalGroupError("MED_FILE_NOT_FOUND")
    expected = int(expected_element_count)
    if expected < 1:
        raise MedPhysicalGroupError("MED_EXPECTED_ELEMENT_COUNT_INVALID")

    import gmsh

    owned = not bool(gmsh.isInitialized())
    if owned:
        gmsh.initialize()
    try:
        gmsh.clear()
        gmsh.open(str(med))
        matches: list[tuple[int, int]] = []
        for dim, tag in gmsh.model.getPhysicalGroups(2):
            if gmsh.model.getPhysicalName(dim, tag) == group_name:
                matches.append((dim, tag))
        if len(matches) != 1:
            raise MedPhysicalGroupError("MED_SURFACE_GROUP_NOT_UNIQUE")
        dim, physical_tag = matches[0]
        entities = list(gmsh.model.getEntitiesForPhysicalGroup(dim, physical_tag))
        count = 0
        for entity in entities:
            _, element_tags, _ = gmsh.model.mesh.getElements(dim, int(entity))
            count += sum(len(tags) for tags in element_tags)
        if count != expected:
            raise MedPhysicalGroupError("MED_SURFACE_GROUP_ELEMENT_COUNT_MISMATCH")
        return MedPhysicalGroupEvidence(
            path=med,
            group_name=group_name,
            dimension=dim,
            entity_count=len(entities),
            element_count=count,
            med_sha256=_sha256_file(med),
        )
    finally:
        gmsh.clear()
        if owned:
            gmsh.finalize()
