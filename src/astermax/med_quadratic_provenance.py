from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import re

import numpy as np

from .med_semantic_groups import (
    MedSemanticGroupError,
    geometry_fingerprint,
    resolve_semantic_group,
    write_semantic_manifest,
)


class QuadraticMedError(RuntimeError):
    pass


_GROUP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,23}$")


@dataclass(frozen=True)
class QuadraticMedEvidence:
    med_path: Path
    surface_group: str
    serialized_surface_group: str
    volume_group: str
    serialized_volume_group: str
    tri6_count: int
    tet10_count: int
    surface_geometry_fingerprint: str
    volume_geometry_fingerprint: str
    med_sha256: str
    comm_sha256: str
    verified: bool = True
    fea_solve_executed: bool = False
    results_verified: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "med_path": str(self.med_path),
            "surface_group": self.surface_group,
            "serialized_surface_group": self.serialized_surface_group,
            "volume_group": self.volume_group,
            "serialized_volume_group": self.serialized_volume_group,
            "tri6_count": self.tri6_count,
            "tet10_count": self.tet10_count,
            "surface_geometry_fingerprint": self.surface_geometry_fingerprint,
            "volume_geometry_fingerprint": self.volume_geometry_fingerprint,
            "med_sha256": self.med_sha256,
            "comm_sha256": self.comm_sha256,
            "verified": self.verified,
            "fea_solve_executed": self.fea_solve_executed,
            "results_verified": self.results_verified,
        }


def _hash_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _name(value: str) -> str:
    value = str(value).strip()
    if not _GROUP_RE.fullmatch(value):
        raise QuadraticMedError("MED_GROUP_NAME_INVALID")
    return value


def _validate(nodes_mm: np.ndarray, tet10: np.ndarray, tri6: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    vols = np.asarray(tet10, dtype=int)
    surfs = np.asarray(tri6, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or nodes.shape[0] < 10 or not np.isfinite(nodes).all():
        raise QuadraticMedError("MED_NODES_INVALID")
    if vols.ndim != 2 or vols.shape[1] != 10 or vols.shape[0] < 1:
        raise QuadraticMedError("MED_TET10_INVALID")
    if surfs.ndim != 2 or surfs.shape[1] != 6 or surfs.shape[0] < 1:
        raise QuadraticMedError("MED_TRI6_INVALID")
    for conn, label in ((vols, "TET10"), (surfs, "TRI6")):
        if conn.min() < 0 or conn.max() >= nodes.shape[0]:
            raise QuadraticMedError(f"MED_{label}_CONNECTIVITY_OUT_OF_RANGE")
        if any(len(set(map(int, row))) != row.size for row in conn):
            raise QuadraticMedError(f"MED_{label}_REPEATED_NODE")
    if np.unique(np.sort(surfs[:, :3], axis=1), axis=0).shape[0] != surfs.shape[0]:
        raise QuadraticMedError("MED_TRI6_DUPLICATE_CORNER_FACE")
    return nodes, vols, surfs


def _add_named_physical_group(gmsh, dim: int, entities: list[int], name: str) -> int:
    try:
        tag = int(gmsh.model.addPhysicalGroup(dim, entities, -1, name))
    except TypeError:
        tag = int(gmsh.model.addPhysicalGroup(dim, entities))
        gmsh.model.setPhysicalName(dim, tag, name)
    if gmsh.model.getPhysicalName(dim, tag) != name:
        raise QuadraticMedError("MED_PHYSICAL_NAME_BINDING_FAILED")
    memberships = [int(v) for v in gmsh.model.getPhysicalGroupsForEntity(dim, int(entities[0]))]
    if tag not in memberships:
        raise QuadraticMedError("MED_PHYSICAL_ENTITY_OWNERSHIP_FAILED")
    return tag


def write_quadratic_med(
    destination: str | Path,
    *,
    nodes_mm: np.ndarray,
    tet10: np.ndarray,
    surface_tri6: np.ndarray,
    surface_group: str,
    volume_group: str = "SOLID",
) -> Path:
    nodes, vols, surfs = _validate(nodes_mm, tet10, surface_tri6)
    surf_name, vol_name = _name(surface_group), _name(volume_group)
    if surf_name == vol_name:
        raise QuadraticMedError("MED_SURFACE_AND_VOLUME_GROUPS_MUST_DIFFER")
    path = Path(destination).resolve()
    if path.suffix.lower() != ".med":
        raise QuadraticMedError("MED_DESTINATION_EXTENSION_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)

    import gmsh
    owned = not bool(gmsh.isInitialized())
    if owned:
        gmsh.initialize()
    try:
        gmsh.clear()
        gmsh.model.add("astermax_c7_8")
        s = gmsh.model.addDiscreteEntity(2, 1)
        v = gmsh.model.addDiscreteEntity(3, 1, [s])
        tags = list(range(1, nodes.shape[0] + 1))
        gmsh.model.mesh.addNodes(3, v, tags, nodes.reshape(-1).tolist())
        gmsh.model.mesh.addElementsByType(s, 9, list(range(1, surfs.shape[0] + 1)), (surfs + 1).reshape(-1).tolist())
        gmsh.model.mesh.addElementsByType(v, 11, list(range(1001, 1001 + vols.shape[0])), (vols + 1).reshape(-1).tolist())
        _add_named_physical_group(gmsh, 2, [s], surf_name)
        _add_named_physical_group(gmsh, 3, [v], vol_name)
        gmsh.option.setNumber("Mesh.SaveAll", 0)
        gmsh.write(str(path))
    except QuadraticMedError:
        raise
    except Exception as exc:
        raise QuadraticMedError("MED_QUADRATIC_WRITE_FAILED") from exc
    finally:
        gmsh.clear()
        if owned:
            gmsh.finalize()
    if not path.is_file() or path.stat().st_size <= 0:
        raise QuadraticMedError("MED_WRITE_EMPTY")
    try:
        write_semantic_manifest(path, {
            surf_name: {
                "dimension": 2,
                "element_type": 9,
                "element_count": int(surfs.shape[0]),
                "geometry_fingerprint": geometry_fingerprint(nodes, surfs),
            },
            vol_name: {
                "dimension": 3,
                "element_type": 11,
                "element_count": int(vols.shape[0]),
                "geometry_fingerprint": geometry_fingerprint(nodes, vols),
            },
        })
    except MedSemanticGroupError as exc:
        raise QuadraticMedError(str(exc)) from exc
    return path


def verify_quadratic_med(path: str | Path, *, surface_group: str, volume_group: str, expected_tri6: int, expected_tet10: int, comm_text: str) -> QuadraticMedEvidence:
    med = Path(path).resolve()
    if not med.is_file():
        raise QuadraticMedError("MED_FILE_NOT_FOUND")
    surf_name, vol_name = _name(surface_group), _name(volume_group)
    if not comm_text.strip():
        raise QuadraticMedError("COMM_TEXT_EMPTY")
    import gmsh
    owned = not bool(gmsh.isInitialized())
    if owned:
        gmsh.initialize()
    try:
        gmsh.clear(); gmsh.open(str(med))
        try:
            surf = resolve_semantic_group(gmsh, med, surf_name)
            vol = resolve_semantic_group(gmsh, med, vol_name)
        except MedSemanticGroupError as exc:
            raise QuadraticMedError("MED_GROUP_NOT_UNIQUE") from exc
        ntri = int(surf["element_count"])
        ntet = int(vol["element_count"])
        if ntri != int(expected_tri6):
            raise QuadraticMedError("MED_TRI6_COUNT_MISMATCH")
        if ntet != int(expected_tet10):
            raise QuadraticMedError("MED_TET10_COUNT_MISMATCH")
        return QuadraticMedEvidence(
            med,
            surf_name,
            str(surf["serialized_group_name"]),
            vol_name,
            str(vol["serialized_group_name"]),
            ntri,
            ntet,
            str(surf["geometry_fingerprint"]),
            str(vol["geometry_fingerprint"]),
            _hash_file(med),
            _hash_bytes(comm_text.encode("utf-8")),
        )
    finally:
        gmsh.clear()
        if owned:
            gmsh.finalize()


def write_evidence(evidence: QuadraticMedEvidence, destination: str | Path) -> Path:
    out = Path(destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return out
