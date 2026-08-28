from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from astermax.credibility import canonical_sha256
from .persistent_geometry import (
    PersistentFaceSelection,
    capture_face_selection,
    resolve_face_selection,
)


class NamedSelectionError(ValueError):
    pass


_ALLOWED_ROLES = {"SUPPORT", "LOAD", "CONTACT", "REFERENCE"}


@dataclass(frozen=True)
class NamedSelectionFace:
    face_index: int
    selection_sha256: str
    signature_sha256: str
    area_mm2: float
    center_mm: tuple[float, float, float]


@dataclass(frozen=True)
class PersistentNamedSelection:
    schema: str
    name: str
    role: str
    source_sha256: str
    face_count: int
    faces: tuple[NamedSelectionFace, ...]
    named_selection_sha256: str


@dataclass(frozen=True)
class NamedSelectionResolution:
    schema: str
    name: str
    role: str
    source_sha256: str
    resolved_tags: tuple[int, ...]
    face_signature_sha256: tuple[str, ...]
    named_selection_sha256: str
    resolution_sha256: str


def _clean_name(value: str) -> str:
    name = str(value).strip()
    if not name or len(name) > 64:
        raise NamedSelectionError("name must contain 1..64 characters")
    if any(ord(ch) < 32 for ch in name):
        raise NamedSelectionError("name contains control characters")
    return name


def _clean_role(value: str) -> str:
    role = str(value).strip().upper()
    if role not in _ALLOWED_ROLES:
        raise NamedSelectionError("role must be SUPPORT, LOAD, CONTACT or REFERENCE")
    return role


def capture_named_selection(
    step_path: str | Path,
    face_tags: Iterable[int],
    name: str,
    role: str,
) -> PersistentNamedSelection:
    clean_name = _clean_name(name)
    clean_role = _clean_role(role)
    tags = tuple(int(v) for v in face_tags)
    if not tags:
        raise NamedSelectionError("named selection must contain at least one face")
    if len(set(tags)) != len(tags):
        raise NamedSelectionError("named selection contains duplicate face tags")

    captured: list[PersistentFaceSelection] = []
    for index, tag in enumerate(tags):
        captured.append(
            capture_face_selection(
                step_path,
                tag,
                f"NAMED_{clean_role}_{canonical_sha256({'name': clean_name})[:12]}_{index}",
            )
        )
    source_sha = captured[0].source_sha256
    if any(item.source_sha256 != source_sha for item in captured):
        raise NamedSelectionError("named selection faces do not share one STEP identity")

    faces = tuple(
        NamedSelectionFace(
            face_index=index,
            selection_sha256=item.selection_sha256,
            signature_sha256=item.signature.sha256,
            area_mm2=float(item.signature.area_mm2),
            center_mm=tuple(float(v) for v in item.signature.center_mm),
        )
        for index, item in enumerate(captured)
    )
    core = {
        "schema": "AsterMaxPersistentNamedSelectionV1",
        "name": clean_name,
        "role": clean_role,
        "source_sha256": source_sha,
        "face_count": len(faces),
        "faces": [asdict(face) for face in faces],
        "member_selection_sha256": [item.selection_sha256 for item in captured],
    }
    result = PersistentNamedSelection(
        schema=core["schema"],
        name=clean_name,
        role=clean_role,
        source_sha256=source_sha,
        face_count=len(faces),
        faces=faces,
        named_selection_sha256=canonical_sha256(core),
    )
    object.__setattr__(result, "_members", tuple(captured))
    return result


def resolve_named_selection(step_path: str | Path, selection: PersistentNamedSelection) -> NamedSelectionResolution:
    members = getattr(selection, "_members", None)
    if not members or len(members) != selection.face_count:
        raise NamedSelectionError("named selection member provenance is unavailable")
    resolutions = tuple(resolve_face_selection(step_path, member) for member in members)
    tags = tuple(item.resolved_tag for item in resolutions)
    signatures = tuple(item.signature_sha256 for item in resolutions)
    if len(set(tags)) != len(tags):
        raise NamedSelectionError("named selection resolved duplicate faces")
    if signatures != tuple(face.signature_sha256 for face in selection.faces):
        raise NamedSelectionError("named selection face signature mismatch")
    core = {
        "schema": "AsterMaxNamedSelectionResolutionV1",
        "name": selection.name,
        "role": selection.role,
        "source_sha256": selection.source_sha256,
        "resolved_tags": list(tags),
        "face_signature_sha256": list(signatures),
        "named_selection_sha256": selection.named_selection_sha256,
    }
    return NamedSelectionResolution(
        schema=core["schema"],
        name=selection.name,
        role=selection.role,
        source_sha256=selection.source_sha256,
        resolved_tags=tags,
        face_signature_sha256=signatures,
        named_selection_sha256=selection.named_selection_sha256,
        resolution_sha256=canonical_sha256(core),
    )
