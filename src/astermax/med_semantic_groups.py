from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

import numpy as np


MANIFEST_SUFFIX = ".groups.json"


class MedSemanticGroupError(RuntimeError):
    pass


def _canonical_geometry_payload(nodes_mm: np.ndarray, connectivity: np.ndarray) -> list[list[list[float]]]:
    nodes = np.asarray(nodes_mm, dtype=float)
    conn = np.asarray(connectivity, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.isfinite(nodes).all():
        raise MedSemanticGroupError("MED_SEMANTIC_NODES_INVALID")
    if conn.ndim != 2 or conn.shape[0] < 1 or conn.min() < 0 or conn.max() >= nodes.shape[0]:
        raise MedSemanticGroupError("MED_SEMANTIC_CONNECTIVITY_INVALID")
    elements: list[list[list[float]]] = []
    for row in conn:
        coords = [[round(float(v), 12) for v in nodes[int(i)]] for i in row]
        coords.sort()
        elements.append(coords)
    elements.sort()
    return elements


def geometry_fingerprint(nodes_mm: np.ndarray, connectivity: np.ndarray) -> str:
    payload = _canonical_geometry_payload(nodes_mm, connectivity)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def manifest_path(med_path: str | Path) -> Path:
    med = Path(med_path)
    return med.with_name(med.name + MANIFEST_SUFFIX)


def write_semantic_manifest(med_path: str | Path, groups: dict[str, dict[str, object]]) -> Path:
    med = Path(med_path).resolve()
    if not med.is_file() or med.stat().st_size <= 0:
        raise MedSemanticGroupError("MED_SEMANTIC_MED_MISSING")
    normalized: dict[str, dict[str, object]] = {}
    for semantic_name, item in groups.items():
        name = str(semantic_name).strip()
        if not name:
            raise MedSemanticGroupError("MED_SEMANTIC_NAME_EMPTY")
        normalized[name] = {
            "dimension": int(item["dimension"]),
            "element_type": int(item["element_type"]),
            "element_count": int(item["element_count"]),
            "geometry_fingerprint": str(item["geometry_fingerprint"]),
        }
    payload = {
        "schema": "ASTERMAX_MED_SEMANTIC_GROUPS_V1",
        "med_sha256": sha256(med.read_bytes()).hexdigest(),
        "groups": normalized,
    }
    out = manifest_path(med)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out


def load_semantic_manifest(med_path: str | Path) -> dict[str, object]:
    med = Path(med_path).resolve()
    path = manifest_path(med)
    if not path.is_file():
        raise MedSemanticGroupError("MED_SEMANTIC_MANIFEST_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "ASTERMAX_MED_SEMANTIC_GROUPS_V1":
        raise MedSemanticGroupError("MED_SEMANTIC_MANIFEST_SCHEMA_INVALID")
    actual = sha256(med.read_bytes()).hexdigest()
    if payload.get("med_sha256") != actual:
        raise MedSemanticGroupError("MED_SEMANTIC_MED_HASH_MISMATCH")
    return payload


def _group_geometry_from_gmsh(gmsh, dim: int, physical_tag: int, element_type: int) -> tuple[np.ndarray, np.ndarray]:
    node_coordinates: dict[int, tuple[float, float, float]] = {}
    rows: list[list[int]] = []
    for entity in gmsh.model.getEntitiesForPhysicalGroup(dim, physical_tag):
        types, _tags, node_tags = gmsh.model.mesh.getElements(dim, int(entity))
        for typ, flattened in zip(types, node_tags):
            if int(typ) != int(element_type):
                continue
            _, _, _, nodes_per_element, _, _ = gmsh.model.mesh.getElementProperties(int(typ))
            n = int(nodes_per_element)
            values = [int(v) for v in flattened]
            for offset in range(0, len(values), n):
                row = values[offset:offset+n]
                if len(row) == n:
                    rows.append(row)
                    for tag in row:
                        if tag not in node_coordinates:
                            coord, _, _, _ = gmsh.model.mesh.getNode(tag)
                            node_coordinates[tag] = (float(coord[0]), float(coord[1]), float(coord[2]))
    if not rows:
        return np.empty((0, 3), dtype=float), np.empty((0, 0), dtype=int)
    unique_tags = sorted(node_coordinates)
    index = {tag: i for i, tag in enumerate(unique_tags)}
    nodes = np.asarray([node_coordinates[tag] for tag in unique_tags], dtype=float)
    conn = np.asarray([[index[tag] for tag in row] for row in rows], dtype=int)
    return nodes, conn


def resolve_semantic_group(gmsh, med_path: str | Path, semantic_name: str) -> dict[str, object]:
    payload = load_semantic_manifest(med_path)
    groups = payload.get("groups")
    if not isinstance(groups, dict) or semantic_name not in groups:
        raise MedSemanticGroupError("MED_SEMANTIC_GROUP_NOT_DECLARED")
    expected = groups[semantic_name]
    dim = int(expected["dimension"])
    element_type = int(expected["element_type"])
    expected_count = int(expected["element_count"])
    expected_fp = str(expected["geometry_fingerprint"])

    matches: list[dict[str, object]] = []
    for d, tag in gmsh.model.getPhysicalGroups(dim):
        nodes, conn = _group_geometry_from_gmsh(gmsh, int(d), int(tag), element_type)
        if conn.shape[0] != expected_count:
            continue
        if geometry_fingerprint(nodes, conn) != expected_fp:
            continue
        matches.append({
            "dimension": int(d),
            "physical_tag": int(tag),
            "serialized_group_name": str(gmsh.model.getPhysicalName(int(d), int(tag))),
            "element_count": int(conn.shape[0]),
            "geometry_fingerprint": expected_fp,
        })
    if len(matches) != 1:
        raise MedSemanticGroupError("MED_SEMANTIC_GROUP_GEOMETRY_NOT_UNIQUE")
    return matches[0]
