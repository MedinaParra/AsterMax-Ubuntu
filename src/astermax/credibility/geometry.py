from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .core import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


def _finite_tuple(name: str, values: Iterable[float], size: int) -> tuple[float, ...]:
    result = tuple(float(v) for v in values)
    if len(result) != size or not all(math.isfinite(v) for v in result):
        raise ValueError(f"{name} must contain exactly {size} finite values")
    return result


@dataclass(frozen=True)
class CadArtifact:
    """Identity of the exact CAD payload used by an analysis.

    C1 deliberately permits only millimetres. Unit conversion must happen before
    evidence is admitted so downstream section/load calculations have one unit
    contract instead of an implicit scale factor.
    """

    file_sha256: str
    length_unit: str = "mm"
    format: str = "STEP"

    def __post_init__(self) -> None:
        digest = str(self.file_sha256).lower().strip()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("file_sha256 must be a lowercase SHA-256 digest")
        object.__setattr__(self, "file_sha256", digest)
        if self.length_unit != "mm":
            raise ValueError("C1 CAD evidence requires canonical millimetre units")
        if self.format.upper() not in {"STEP", "STP"}:
            raise ValueError("C1 CAD evidence currently accepts STEP/STP only")
        object.__setattr__(self, "format", "STEP")

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(
            {"schema": "AsterMaxCadArtifactV1", "sha256": self.file_sha256, "unit": "mm", "format": "STEP"}
        )


@dataclass(frozen=True)
class FaceSignature:
    """Persistent geometric signature independent of transient CAD face numbers."""

    surface_type: str
    area_mm2: float
    centroid_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    bbox_mm: tuple[float, float, float, float, float, float]
    edge_count: int

    def __post_init__(self) -> None:
        kind = str(self.surface_type).strip().upper()
        if not kind:
            raise ValueError("surface_type must be non-empty")
        object.__setattr__(self, "surface_type", kind)
        area = float(self.area_mm2)
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError("area_mm2 must be finite and positive")
        object.__setattr__(self, "area_mm2", area)
        object.__setattr__(self, "centroid_mm", _finite_tuple("centroid_mm", self.centroid_mm, 3))
        normal = _finite_tuple("normal", self.normal, 3)
        norm = math.sqrt(sum(v * v for v in normal))
        if norm <= 1.0e-12:
            raise ValueError("normal must have non-zero magnitude")
        object.__setattr__(self, "normal", tuple(v / norm for v in normal))
        bbox = _finite_tuple("bbox_mm", self.bbox_mm, 6)
        if any(bbox[i] > bbox[i + 3] for i in range(3)):
            raise ValueError("bbox_mm minima must not exceed maxima")
        object.__setattr__(self, "bbox_mm", bbox)
        if int(self.edge_count) < 1:
            raise ValueError("edge_count must be positive")
        object.__setattr__(self, "edge_count", int(self.edge_count))

    def canonical(self) -> dict:
        return {
            "surface_type": self.surface_type,
            "area_mm2": self.area_mm2,
            "centroid_mm": list(self.centroid_mm),
            "normal": list(self.normal),
            "bbox_mm": list(self.bbox_mm),
            "edge_count": self.edge_count,
        }

    @property
    def fingerprint_sha256(self) -> str:
        return canonical_sha256({"schema": "AsterMaxFaceSignatureV1", **self.canonical()})


@dataclass(frozen=True)
class FaceMatchPolicy:
    relative_area_tolerance: float = 1.0e-6
    centroid_tolerance_mm: float = 1.0e-5
    normal_cosine_min: float = 0.999999
    bbox_tolerance_mm: float = 1.0e-5

    def __post_init__(self) -> None:
        if not (0.0 <= self.relative_area_tolerance < 1.0):
            raise ValueError("relative_area_tolerance must be in [0, 1)")
        if self.centroid_tolerance_mm < 0.0 or self.bbox_tolerance_mm < 0.0:
            raise ValueError("geometric tolerances must be non-negative")
        if not (-1.0 <= self.normal_cosine_min <= 1.0):
            raise ValueError("normal_cosine_min must be in [-1, 1]")


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def face_signature_matches(reference: FaceSignature, candidate: FaceSignature, policy: FaceMatchPolicy = FaceMatchPolicy()) -> bool:
    if reference.surface_type != candidate.surface_type or reference.edge_count != candidate.edge_count:
        return False
    area_scale = max(reference.area_mm2, candidate.area_mm2)
    if abs(reference.area_mm2 - candidate.area_mm2) > policy.relative_area_tolerance * area_scale:
        return False
    if _distance(reference.centroid_mm, candidate.centroid_mm) > policy.centroid_tolerance_mm:
        return False
    if sum(a * b for a, b in zip(reference.normal, candidate.normal)) < policy.normal_cosine_min:
        return False
    if max(abs(a - b) for a, b in zip(reference.bbox_mm, candidate.bbox_mm)) > policy.bbox_tolerance_mm:
        return False
    return True


def resolve_persistent_face(reference: FaceSignature, candidates: Iterable[FaceSignature], policy: FaceMatchPolicy = FaceMatchPolicy()) -> FaceSignature:
    matches = [candidate for candidate in candidates if face_signature_matches(reference, candidate, policy)]
    if not matches:
        raise ValueError("persistent face signature could not be resolved")
    if len(matches) != 1:
        raise ValueError("persistent face signature is ambiguous")
    return matches[0]


@dataclass(frozen=True)
class SectionProperties:
    """Deterministic CAD-derived section properties in the canonical mm system."""

    area_mm2: float
    centroid_mm: tuple[float, float, float]
    ixx_mm4: float
    iyy_mm4: float
    ixy_mm4: float
    section_normal: tuple[float, float, float]

    def __post_init__(self) -> None:
        area = float(self.area_mm2)
        ixx = float(self.ixx_mm4)
        iyy = float(self.iyy_mm4)
        ixy = float(self.ixy_mm4)
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError("section area must be finite and positive")
        if not all(math.isfinite(v) for v in (ixx, iyy, ixy)) or ixx <= 0.0 or iyy <= 0.0:
            raise ValueError("section inertia terms must be finite and principal diagonal terms positive")
        if ixx * iyy - ixy * ixy <= 0.0:
            raise ValueError("section inertia tensor must be positive definite")
        object.__setattr__(self, "area_mm2", area)
        object.__setattr__(self, "ixx_mm4", ixx)
        object.__setattr__(self, "iyy_mm4", iyy)
        object.__setattr__(self, "ixy_mm4", ixy)
        object.__setattr__(self, "centroid_mm", _finite_tuple("centroid_mm", self.centroid_mm, 3))
        normal = _finite_tuple("section_normal", self.section_normal, 3)
        norm = math.sqrt(sum(v * v for v in normal))
        if norm <= 1.0e-12:
            raise ValueError("section_normal must have non-zero magnitude")
        object.__setattr__(self, "section_normal", tuple(v / norm for v in normal))

    def canonical(self) -> dict:
        return {
            "area_mm2": self.area_mm2,
            "centroid_mm": list(self.centroid_mm),
            "ixx_mm4": self.ixx_mm4,
            "iyy_mm4": self.iyy_mm4,
            "ixy_mm4": self.ixy_mm4,
            "section_normal": list(self.section_normal),
        }


def cad_artifact_evidence(evidence_id: str, artifact: CadArtifact) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind="CAD_ARTIFACT_IDENTITY",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Exact STEP payload identity and canonical millimetre unit contract",
        payload_sha256=artifact.file_sha256,
        metadata={"format": artifact.format, "length_unit": artifact.length_unit, "artifact_identity_sha256": artifact.identity_sha256},
    )


def persistent_face_evidence(evidence_id: str, cad: CadArtifact, signature: FaceSignature) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind="PERSISTENT_CAD_FACE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="CAD face identified by geometry signature rather than transient face index",
        payload_sha256=signature.fingerprint_sha256,
        metadata={"cad_sha256": cad.file_sha256, "length_unit": "mm", "signature": signature.canonical()},
    )


def section_properties_evidence(evidence_id: str, cad: CadArtifact, section: SectionProperties, derivation: str = "CAD_SECTION_INTEGRATION") -> EvidenceRecord:
    payload = {"schema": "AsterMaxCadSectionEvidenceV1", "cad_sha256": cad.file_sha256, "unit": "mm", "derivation": derivation, "section": section.canonical()}
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind="CAD_SECTION_PROPERTIES",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Section properties deterministically derived from the identified CAD geometry",
        payload_sha256=canonical_sha256(payload),
        metadata=payload,
    )
