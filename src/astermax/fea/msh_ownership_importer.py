from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .face_ownership import OwnedCadFaceTri6, Tet10FaceOwnershipInventory
from .gmsh_bridge import _gmsh, _node_table, _remap_connectivity
from .persistent_geometry import list_face_signatures


class MshOwnershipImportError(ValueError):
    pass


@dataclass(frozen=True)
class MshOwnershipImportEvidenceV1:
    schema: str
    source_step_sha256: str
    source_mesh_sha256: str
    ownership_sha256: str
    tet10_count: int
    tri6_count: int
    face_count: int
    association_mode: str
    exact_mesh_artifact_consumed: bool
    transient_tags_are_identity: bool
    ready_for_rebinding: bool
    evidence_sha256: str


def _surface_bbox(nodes: np.ndarray, triangles: np.ndarray) -> tuple[float, float, float, float, float, float]:
    used = np.unique(np.asarray(triangles, dtype=np.int64).reshape(-1))
    xyz = np.asarray(nodes[used], dtype=float)
    lo = xyz.min(axis=0); hi = xyz.max(axis=0)
    return (float(lo[0]), float(lo[1]), float(lo[2]), float(hi[0]), float(hi[1]), float(hi[2]))


def _bbox_close(a: tuple[float, ...], b: tuple[float, ...], diagonal: float, rel: float) -> bool:
    atol = max(float(diagonal) * float(rel), 1.0e-10)
    return all(abs(float(x) - float(y)) <= atol for x, y in zip(a, b))


def import_tet10_ownership_from_msh(
    step_path: str | Path,
    msh_path: str | Path,
    *,
    expected_mesh_sha256: str,
    bbox_relative_tolerance: float = 1.0e-7,
) -> tuple[Tet10FaceOwnershipInventory, MshOwnershipImportEvidenceV1]:
    """Build face ownership by reading the exact approved Gmsh .msh artifact.

    CAD identity is recovered by strict, unique spatial association of mesh-surface
    bounding boxes to persistent STEP face signatures. Gmsh entity tags are used
    only to retrieve local mesh blocks and are never accepted as persistent identity.
    This V1 deliberately fails closed if the geometry is spatially ambiguous.
    """
    step = Path(step_path); msh = Path(msh_path)
    if step.suffix.lower() not in {".step", ".stp"} or not step.is_file():
        raise MshOwnershipImportError("MSH_IMPORT_STEP_REQUIRED")
    if msh.suffix.lower() != ".msh" or not msh.is_file() or msh.stat().st_size <= 0:
        raise MshOwnershipImportError("MSH_IMPORT_MESH_REQUIRED")
    mesh_sha = sha256_file(msh)
    if mesh_sha != str(expected_mesh_sha256):
        raise MshOwnershipImportError("MSH_IMPORT_ARTIFACT_SHA_MISMATCH")
    if not np.isfinite(bbox_relative_tolerance) or not 0.0 < bbox_relative_tolerance <= 1.0e-3:
        raise MshOwnershipImportError("MSH_IMPORT_TOLERANCE")

    cad_faces = list_face_signatures(step)
    if not cad_faces:
        raise MshOwnershipImportError("MSH_IMPORT_CAD_FACES_REQUIRED")
    cad_by_sha = {sig.sha256: sig for _, sig in cad_faces}
    if len(cad_by_sha) != len(cad_faces):
        raise MshOwnershipImportError("MSH_IMPORT_CAD_SIGNATURE_NOT_UNIQUE")

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(msh))
        nodes, tag_to_index = _node_table(gmsh)
        if nodes.shape[0] <= 0:
            raise MshOwnershipImportError("MSH_IMPORT_NODES_REQUIRED")

        vol_types, _, vol_nodes = gmsh.model.mesh.getElements(3)
        tet_blocks: list[np.ndarray] = []
        unsupported: list[int] = []
        for etype, conn in zip(vol_types, vol_nodes):
            raw = np.asarray(conn, dtype=np.int64)
            if int(etype) == 11:
                tet_blocks.append(raw.reshape((-1, 10)))
            elif raw.size:
                unsupported.append(int(etype))
        if unsupported:
            raise MshOwnershipImportError("MSH_IMPORT_NON_TET10:" + ",".join(map(str, sorted(set(unsupported)))))
        if not tet_blocks:
            raise MshOwnershipImportError("MSH_IMPORT_TET10_REQUIRED")
        elements = _remap_connectivity(np.vstack(tet_blocks), tag_to_index)

        lo = nodes.min(axis=0); hi = nodes.max(axis=0)
        bbox = (float(lo[0]), float(lo[1]), float(lo[2]), float(hi[0]), float(hi[1]), float(hi[2]))
        dimensions = (bbox[3]-bbox[0], bbox[4]-bbox[1], bbox[5]-bbox[2])
        diagonal = float(np.linalg.norm(np.asarray(dimensions, dtype=float)))
        if not np.isfinite(diagonal) or diagonal <= 0.0:
            raise MshOwnershipImportError("MSH_IMPORT_INVALID_DIMENSIONS")

        owned: list[OwnedCadFaceTri6] = []
        used_signatures: set[str] = set()
        total_tri6 = 0
        for _, surface_tag in gmsh.model.getEntities(2):
            types, _, conns = gmsh.model.mesh.getElements(2, int(surface_tag))
            blocks: list[np.ndarray] = []
            for etype, conn in zip(types, conns):
                raw = np.asarray(conn, dtype=np.int64)
                if int(etype) == 9:
                    blocks.append(raw.reshape((-1, 6)))
                elif raw.size:
                    raise MshOwnershipImportError(f"MSH_IMPORT_NON_TRI6_SURFACE:{int(surface_tag)}:{int(etype)}")
            if not blocks:
                continue
            triangles = _remap_connectivity(np.vstack(blocks), tag_to_index)
            mesh_bbox = _surface_bbox(nodes, triangles)
            matches = [(tag, sig) for tag, sig in cad_faces if _bbox_close(mesh_bbox, sig.bbox_mm, diagonal, bbox_relative_tolerance)]
            if not matches:
                raise MshOwnershipImportError(f"MSH_IMPORT_CAD_FACE_NOT_FOUND:{int(surface_tag)}")
            if len(matches) != 1:
                raise MshOwnershipImportError(f"MSH_IMPORT_CAD_FACE_AMBIGUOUS:{int(surface_tag)}")
            _, sig = matches[0]
            if sig.sha256 in used_signatures:
                raise MshOwnershipImportError("MSH_IMPORT_CAD_FACE_DUPLICATED")
            used_signatures.add(sig.sha256)
            total_tri6 += int(triangles.shape[0])
            owned.append(OwnedCadFaceTri6(
                face_tag=int(surface_tag),
                signature_sha256=sig.sha256,
                surface_type=sig.surface_type,
                area_mm2=float(sig.area_mm2),
                center_mm=tuple(float(v) for v in sig.center_mm),
                bbox_mm=tuple(float(v) for v in sig.bbox_mm),
                tri6_count=int(triangles.shape[0]),
                triangles=np.asarray(triangles, dtype=np.int64),
            ))
        if not owned or total_tri6 <= 0:
            raise MshOwnershipImportError("MSH_IMPORT_OWNED_TRI6_REQUIRED")
        if len(owned) != len(cad_faces):
            raise MshOwnershipImportError("MSH_IMPORT_INCOMPLETE_CAD_FACE_COVERAGE")

        core = {
            "schema": "AsterMaxTet10FaceOwnershipInventoryV1",
            "source_step_sha256": sha256_file(step),
            "source_size_bytes": int(step.stat().st_size),
            "source_mesh_sha256": mesh_sha,
            "node_count": int(nodes.shape[0]),
            "tet10_count": int(elements.shape[0]),
            "faces": [{
                "signature_sha256": f.signature_sha256,
                "surface_type": f.surface_type,
                "area_mm2": f.area_mm2,
                "center_mm": list(f.center_mm),
                "bbox_mm": list(f.bbox_mm),
                "tri6_count": f.tri6_count,
            } for f in sorted(owned, key=lambda item: item.signature_sha256)],
            "association_mode": "MESH_SURFACE_BBOX_TO_PERSISTENT_CAD_SIGNATURE_V1",
        }
        ownership_sha = canonical_sha256(core)
        inventory = Tet10FaceOwnershipInventory(
            schema="AsterMaxTet10FaceOwnershipInventoryV1",
            source_step_sha256=core["source_step_sha256"],
            source_size_bytes=core["source_size_bytes"],
            nodes_mm=np.asarray(nodes, dtype=float),
            elements=np.asarray(elements, dtype=np.int64),
            faces=tuple(owned),
            bbox_mm=bbox,
            dimensions_mm=tuple(float(v) for v in dimensions),
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
            ownership_sha256=ownership_sha,
        )
        evidence_core = {
            "schema": "AsterMaxMshOwnershipImportEvidenceV1",
            "source_step_sha256": core["source_step_sha256"],
            "source_mesh_sha256": mesh_sha,
            "ownership_sha256": ownership_sha,
            "tet10_count": int(elements.shape[0]),
            "tri6_count": int(total_tri6),
            "face_count": len(owned),
            "association_mode": core["association_mode"],
            "exact_mesh_artifact_consumed": True,
            "transient_tags_are_identity": False,
            "ready_for_rebinding": True,
        }
        evidence = MshOwnershipImportEvidenceV1(**evidence_core, evidence_sha256=canonical_sha256(evidence_core))
        return inventory, evidence
    finally:
        gmsh.finalize()
