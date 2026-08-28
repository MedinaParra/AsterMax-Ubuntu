from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .gmsh_bridge import GmshBridgeError, _gmsh, _node_table, _remap_connectivity
from .named_selections import PersistentNamedSelection, resolve_named_selection
from .persistent_geometry import _model_diagonal, _signature


class FaceOwnershipError(ValueError):
    pass


@dataclass(frozen=True)
class OwnedCadFaceTri6:
    face_tag: int
    signature_sha256: str
    surface_type: str
    area_mm2: float
    center_mm: tuple[float, float, float]
    bbox_mm: tuple[float, float, float, float, float, float]
    tri6_count: int
    triangles: np.ndarray


@dataclass(frozen=True)
class Tet10FaceOwnershipInventory:
    schema: str
    source_step_sha256: str
    source_size_bytes: int
    nodes_mm: np.ndarray
    elements: np.ndarray
    faces: tuple[OwnedCadFaceTri6, ...]
    bbox_mm: tuple[float, float, float, float, float, float]
    dimensions_mm: tuple[float, float, float]
    gmsh_version: str
    ownership_sha256: str


@dataclass(frozen=True)
class ArbitraryNamedSelectionBinding:
    schema: str
    name: str
    role: str
    named_selection_sha256: str
    resolution_sha256: str
    face_signature_sha256: tuple[str, ...]
    tri6_count: int
    ownership_sha256: str
    binding_sha256: str


def _validate_step(step_path: str | Path) -> Path:
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise GmshBridgeError("face ownership input must be an existing STEP/STP file")
    return path


def mesh_step_tet10_with_face_ownership(
    step_path: str | Path,
    mesh_size_mm: float,
) -> Tet10FaceOwnershipInventory:
    """Mesh one STEP solid and retain exact CAD-face -> TRI6 ownership.

    Unlike the legacy axis-surface map, every meshed OCC face is keyed by the
    same persistent geometric signature used by AsterMax named selections.
    Transient Gmsh tags remain provenance only and are never the binding key.
    """
    path = _validate_step(step_path)
    if not np.isfinite(mesh_size_mm) or mesh_size_mm <= 0.0:
        raise FaceOwnershipError("mesh_size_mm must be finite and positive")

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_arbitrary_face_ownership")
        imported = gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1 or not any(dim == 3 for dim, _ in imported):
            raise GmshBridgeError(f"PMV requires exactly one imported 3-D solid; found {len(volumes)}")

        bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, volumes[0][1]))
        dimensions = (bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2])
        if not all(np.isfinite(v) and v > 0.0 for v in dimensions):
            raise GmshBridgeError(f"invalid STEP dimensions: {dimensions}")
        _model_diagonal(gmsh)

        face_records = tuple((int(tag), _signature(gmsh, int(tag))) for _, tag in gmsh.model.getEntities(2))
        signature_hashes = tuple(sig.sha256 for _, sig in face_records)
        if len(set(signature_hashes)) != len(signature_hashes):
            raise FaceOwnershipError("CAD_FACE_SIGNATURE_NOT_UNIQUE")

        gmsh.option.setNumber("Mesh.MeshSizeMin", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.model.mesh.generate(3)

        nodes, tag_to_index = _node_table(gmsh)
        volume_types, _, volume_nodes = gmsh.model.mesh.getElements(3)
        tet_blocks: list[np.ndarray] = []
        unsupported: list[int] = []
        for element_type, connectivity in zip(volume_types, volume_nodes):
            raw = np.asarray(connectivity, dtype=np.int64)
            if int(element_type) == 11:
                tet_blocks.append(raw.reshape((-1, 10)))
            elif raw.size:
                unsupported.append(int(element_type))
        if unsupported:
            raise GmshBridgeError(f"non-TET10 volume element types: {sorted(set(unsupported))}")
        if not tet_blocks:
            raise GmshBridgeError("Gmsh produced no TET10 elements")
        elements = _remap_connectivity(np.vstack(tet_blocks), tag_to_index)

        owned_faces: list[OwnedCadFaceTri6] = []
        for face_tag, signature in face_records:
            surface_types, _, surface_nodes = gmsh.model.mesh.getElements(2, face_tag)
            blocks: list[np.ndarray] = []
            for element_type, connectivity in zip(surface_types, surface_nodes):
                raw = np.asarray(connectivity, dtype=np.int64)
                if int(element_type) == 9:
                    blocks.append(raw.reshape((-1, 6)))
                elif raw.size:
                    raise GmshBridgeError(
                        f"CAD face {face_tag} contains unsupported surface element type {int(element_type)}"
                    )
            if not blocks:
                raise GmshBridgeError(f"CAD face {face_tag} contains no TRI6 elements")
            triangles = _remap_connectivity(np.vstack(blocks), tag_to_index)
            owned_faces.append(
                OwnedCadFaceTri6(
                    face_tag=face_tag,
                    signature_sha256=signature.sha256,
                    surface_type=signature.surface_type,
                    area_mm2=float(signature.area_mm2),
                    center_mm=tuple(float(v) for v in signature.center_mm),
                    bbox_mm=tuple(float(v) for v in signature.bbox_mm),
                    tri6_count=int(triangles.shape[0]),
                    triangles=np.asarray(triangles, dtype=np.int64),
                )
            )

        hash_core = {
            "schema": "AsterMaxTet10FaceOwnershipInventoryV1",
            "source_step_sha256": sha256_file(path),
            "source_size_bytes": int(path.stat().st_size),
            "mesh_size_mm": float(mesh_size_mm),
            "node_count": int(nodes.shape[0]),
            "tet10_count": int(elements.shape[0]),
            "faces": [
                {
                    "face_tag": item.face_tag,
                    "signature_sha256": item.signature_sha256,
                    "surface_type": item.surface_type,
                    "area_mm2": item.area_mm2,
                    "center_mm": list(item.center_mm),
                    "bbox_mm": list(item.bbox_mm),
                    "tri6_count": item.tri6_count,
                }
                for item in owned_faces
            ],
        }
        return Tet10FaceOwnershipInventory(
            schema=hash_core["schema"],
            source_step_sha256=hash_core["source_step_sha256"],
            source_size_bytes=hash_core["source_size_bytes"],
            nodes_mm=np.asarray(nodes, dtype=float),
            elements=np.asarray(elements, dtype=np.int64),
            faces=tuple(owned_faces),
            bbox_mm=bbox,
            dimensions_mm=tuple(float(v) for v in dimensions),
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
            ownership_sha256=canonical_sha256(hash_core),
        )
    finally:
        gmsh.finalize()


def bind_named_selection_to_owned_faces(
    step_path: str | Path,
    selection: PersistentNamedSelection,
    inventory: Tet10FaceOwnershipInventory,
    *,
    expected_role: str,
) -> tuple[ArbitraryNamedSelectionBinding, np.ndarray]:
    path = _validate_step(step_path)
    role = str(expected_role).strip().upper()
    if role not in {"SUPPORT", "LOAD", "CONTACT", "REFERENCE"} or selection.role != role:
        raise FaceOwnershipError("named selection role does not match arbitrary face binding")
    current_sha = sha256_file(path)
    if current_sha != inventory.source_step_sha256 or current_sha != selection.source_sha256:
        raise FaceOwnershipError("SOURCE_IDENTITY_MISMATCH")
    if int(path.stat().st_size) != inventory.source_size_bytes:
        raise FaceOwnershipError("SOURCE_SIZE_MISMATCH")

    resolution = resolve_named_selection(path, selection)
    expected_signatures = tuple(face.signature_sha256 for face in selection.faces)
    if resolution.face_signature_sha256 != expected_signatures:
        raise FaceOwnershipError("NAMED_SELECTION_RESOLUTION_SIGNATURE_MISMATCH")

    by_signature = {face.signature_sha256: face for face in inventory.faces}
    if len(by_signature) != len(inventory.faces):
        raise FaceOwnershipError("CAD_FACE_SIGNATURE_NOT_UNIQUE")
    missing = [value for value in expected_signatures if value not in by_signature]
    if missing:
        raise FaceOwnershipError("NAMED_SELECTION_FACE_HAS_NO_OWNED_TRI6:" + ",".join(missing))

    owned = tuple(by_signature[value] for value in expected_signatures)
    triangles = np.vstack([face.triangles for face in owned])
    if triangles.ndim != 2 or triangles.shape[1] != 6 or triangles.shape[0] <= 0:
        raise FaceOwnershipError("owned named selection does not contain valid TRI6 data")

    hash_core = {
        "schema": "AsterMaxArbitraryNamedSelectionBindingV1",
        "name": selection.name,
        "role": selection.role,
        "named_selection_sha256": selection.named_selection_sha256,
        "resolution_sha256": resolution.resolution_sha256,
        "face_signature_sha256": list(expected_signatures),
        "tri6_count": int(triangles.shape[0]),
        "ownership_sha256": inventory.ownership_sha256,
    }
    binding = ArbitraryNamedSelectionBinding(
        schema=hash_core["schema"],
        name=selection.name,
        role=selection.role,
        named_selection_sha256=selection.named_selection_sha256,
        resolution_sha256=resolution.resolution_sha256,
        face_signature_sha256=expected_signatures,
        tri6_count=int(triangles.shape[0]),
        ownership_sha256=inventory.ownership_sha256,
        binding_sha256=canonical_sha256(hash_core),
    )
    return binding, np.asarray(triangles, dtype=np.int64)
