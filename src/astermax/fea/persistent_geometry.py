from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .gmsh_bridge import GmshBridgeError, _gmsh


class PersistentGeometryError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaceSignature:
    surface_type: str
    area_mm2: float
    center_mm: tuple[float, float, float]
    bbox_mm: tuple[float, float, float, float, float, float]
    inertia_mm4: tuple[float, ...]
    edge_count: int
    adjacent_volume_count: int

    def canonical(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.canonical())


@dataclass(frozen=True)
class PersistentFaceSelection:
    selection_id: str
    source_name: str
    source_sha256: str
    source_size_bytes: int
    capture_tag: int
    gmsh_version: str
    model_diagonal_mm: float
    relative_tolerance: float
    signature: FaceSignature
    selection_sha256: str


@dataclass(frozen=True)
class FaceResolution:
    selection_id: str
    resolved_tag: int
    signature_sha256: str
    selection_sha256: str


@dataclass(frozen=True)
class RemeshSelectionSample:
    mesh_size_mm: float
    resolved_tag: int
    surface_node_count: int
    surface_element_count: int
    signature_sha256: str


def _step(path: str | Path) -> Path:
    p = Path(path)
    if p.suffix.lower() not in {".step", ".stp"} or not p.is_file():
        raise GmshBridgeError("persistent geometry input must be an existing STEP/STP file")
    return p


def _model_diagonal(gmsh) -> float:
    volumes = gmsh.model.getEntities(3)
    if not volumes:
        raise PersistentGeometryError("STEP contains no 3-D solid")
    boxes = [gmsh.model.getBoundingBox(3, tag) for _, tag in volumes]
    bbox = (
        min(v[0] for v in boxes), min(v[1] for v in boxes), min(v[2] for v in boxes),
        max(v[3] for v in boxes), max(v[4] for v in boxes), max(v[5] for v in boxes),
    )
    dims = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
    if np.any(dims <= 0.0) or not np.all(np.isfinite(dims)):
        raise PersistentGeometryError("STEP has invalid global dimensions")
    return float(np.linalg.norm(dims))


def _import(gmsh, source: Path, name: str) -> float:
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(name)
    gmsh.model.occ.importShapes(str(source))
    gmsh.model.occ.synchronize()
    return _model_diagonal(gmsh)


def _signature(gmsh, tag: int) -> FaceSignature:
    if (2, int(tag)) not in set(gmsh.model.getEntities(2)):
        raise PersistentGeometryError(f"surface tag does not exist: {tag}")
    area = float(gmsh.model.occ.getMass(2, int(tag)))
    center = tuple(float(v) for v in gmsh.model.occ.getCenterOfMass(2, int(tag)))
    bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(2, int(tag)))
    inertia = tuple(float(v) for v in gmsh.model.occ.getMatrixOfInertia(2, int(tag)))
    upward, downward = gmsh.model.getAdjacencies(2, int(tag))
    numeric = np.asarray((area, *center, *bbox, *inertia), dtype=float)
    if area <= 0.0 or len(inertia) != 9 or not np.all(np.isfinite(numeric)):
        raise PersistentGeometryError(f"surface {tag} has invalid geometric properties")
    return FaceSignature(
        surface_type=str(gmsh.model.getType(2, int(tag))),
        area_mm2=area,
        center_mm=center,
        bbox_mm=bbox,
        inertia_mm4=inertia,
        edge_count=int(len(downward)),
        adjacent_volume_count=int(len(upward)),
    )


def _close(a: float, b: float, scale: float, rel: float) -> bool:
    atol = max(abs(scale) * rel, np.finfo(float).eps * max(abs(scale), 1.0) * 64.0)
    return abs(float(a) - float(b)) <= max(atol, max(abs(float(a)), abs(float(b))) * rel)


def _matches(expected: FaceSignature, actual: FaceSignature, diagonal: float, rel: float) -> bool:
    if expected.surface_type != actual.surface_type:
        return False
    if expected.edge_count != actual.edge_count or expected.adjacent_volume_count != actual.adjacent_volume_count:
        return False
    if not _close(expected.area_mm2, actual.area_mm2, diagonal**2, rel):
        return False
    if any(not _close(a, b, diagonal, rel) for a, b in zip(expected.center_mm, actual.center_mm)):
        return False
    if any(not _close(a, b, diagonal, rel) for a, b in zip(expected.bbox_mm, actual.bbox_mm)):
        return False
    inertia_scale = max(diagonal**4, *(abs(v) for v in expected.inertia_mm4), 1.0)
    return all(_close(a, b, inertia_scale, rel) for a, b in zip(expected.inertia_mm4, actual.inertia_mm4))


def _resolve_current(gmsh, selection: PersistentFaceSelection, diagonal: float) -> FaceResolution:
    matches = []
    for _, tag in gmsh.model.getEntities(2):
        sig = _signature(gmsh, int(tag))
        if _matches(selection.signature, sig, diagonal, selection.relative_tolerance):
            matches.append((int(tag), sig))
    if not matches:
        raise PersistentGeometryError("PERSISTENT_FACE_NOT_FOUND")
    if len(matches) != 1:
        raise PersistentGeometryError("PERSISTENT_FACE_AMBIGUOUS:" + ",".join(str(tag) for tag, _ in matches))
    tag, sig = matches[0]
    return FaceResolution(selection.selection_id, tag, sig.sha256, selection.selection_sha256)


def list_face_signatures(step_path: str | Path) -> tuple[tuple[int, FaceSignature], ...]:
    source = _step(step_path)
    gmsh = _gmsh(); gmsh.initialize()
    try:
        _import(gmsh, source, "astermax_face_inventory")
        return tuple((int(tag), _signature(gmsh, int(tag))) for _, tag in gmsh.model.getEntities(2))
    finally:
        gmsh.finalize()


def capture_face_selection(step_path: str | Path, face_tag: int, selection_id: str,
                           *, relative_tolerance: float = 1.0e-9) -> PersistentFaceSelection:
    source = _step(step_path)
    sid = str(selection_id).strip()
    if not sid or any(ch.isspace() for ch in sid):
        raise ValueError("selection_id must be non-empty and contain no whitespace")
    if not np.isfinite(relative_tolerance) or not (0.0 < relative_tolerance <= 1.0e-3):
        raise ValueError("relative_tolerance must be finite and in (0, 1e-3]")
    gmsh = _gmsh(); gmsh.initialize()
    try:
        diagonal = _import(gmsh, source, "astermax_capture_face")
        sig = _signature(gmsh, int(face_tag))
        candidates = [int(tag) for _, tag in gmsh.model.getEntities(2)
                      if _matches(sig, _signature(gmsh, int(tag)), diagonal, float(relative_tolerance))]
        if len(candidates) != 1:
            raise PersistentGeometryError("PERSISTENT_FACE_CAPTURE_NOT_UNIQUE:" + ",".join(map(str, candidates)))
        payload = {
            "schema": "AsterMaxPersistentFaceSelectionV1",
            "selection_id": sid,
            "source_name": source.name,
            "source_sha256": sha256_file(source),
            "source_size_bytes": int(source.stat().st_size),
            "capture_tag": int(face_tag),
            "gmsh_version": str(getattr(gmsh, "__version__", "unknown")),
            "model_diagonal_mm": diagonal,
            "relative_tolerance": float(relative_tolerance),
            "signature": sig.canonical(),
        }
        return PersistentFaceSelection(
            selection_id=sid,
            source_name=source.name,
            source_sha256=payload["source_sha256"],
            source_size_bytes=payload["source_size_bytes"],
            capture_tag=int(face_tag),
            gmsh_version=payload["gmsh_version"],
            model_diagonal_mm=diagonal,
            relative_tolerance=float(relative_tolerance),
            signature=sig,
            selection_sha256=canonical_sha256(payload),
        )
    finally:
        gmsh.finalize()


def _assert_source(source: Path, selection: PersistentFaceSelection) -> None:
    if sha256_file(source) != selection.source_sha256 or int(source.stat().st_size) != selection.source_size_bytes:
        raise PersistentGeometryError("SOURCE_IDENTITY_MISMATCH")


def resolve_face_selection(step_path: str | Path, selection: PersistentFaceSelection) -> FaceResolution:
    source = _step(step_path); _assert_source(source, selection)
    gmsh = _gmsh(); gmsh.initialize()
    try:
        diagonal = _import(gmsh, source, "astermax_resolve_face")
        if not _close(diagonal, selection.model_diagonal_mm, selection.model_diagonal_mm, selection.relative_tolerance):
            raise PersistentGeometryError("SOURCE_DIMENSION_MISMATCH")
        return _resolve_current(gmsh, selection, diagonal)
    finally:
        gmsh.finalize()


def verify_face_selection_across_remesh(step_path: str | Path, selection: PersistentFaceSelection,
                                        mesh_sizes_mm: Iterable[float]) -> tuple[RemeshSelectionSample, ...]:
    source = _step(step_path); _assert_source(source, selection)
    sizes = tuple(float(v) for v in mesh_sizes_mm)
    if len(sizes) < 2 or any(not np.isfinite(v) or v <= 0.0 for v in sizes):
        raise ValueError("mesh_sizes_mm must contain at least two finite positive values")
    samples = []
    for index, size in enumerate(sizes):
        gmsh = _gmsh(); gmsh.initialize()
        try:
            diagonal = _import(gmsh, source, f"astermax_remesh_{index}")
            resolution = _resolve_current(gmsh, selection, diagonal)
            gmsh.option.setNumber("Mesh.MeshSizeMin", size)
            gmsh.option.setNumber("Mesh.MeshSizeMax", size)
            gmsh.model.mesh.generate(3)
            node_tags, _, _ = gmsh.model.mesh.getNodes(2, resolution.resolved_tag, includeBoundary=True)
            _, element_tags, _ = gmsh.model.mesh.getElements(2, resolution.resolved_tag)
            element_count = sum(len(tags) for tags in element_tags)
            if len(node_tags) == 0 or element_count == 0:
                raise PersistentGeometryError("RESOLVED_FACE_HAS_NO_SURFACE_MESH")
            samples.append(RemeshSelectionSample(size, resolution.resolved_tag, int(len(node_tags)),
                                                 int(element_count), resolution.signature_sha256))
        finally:
            gmsh.finalize()
    if len({sample.signature_sha256 for sample in samples}) != 1:
        raise PersistentGeometryError("FACE_SIGNATURE_CHANGED_ACROSS_REMESH")
    return tuple(samples)
