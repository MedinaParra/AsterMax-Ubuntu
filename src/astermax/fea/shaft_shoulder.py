from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


class ShaftShoulderError(ValueError):
    pass


@dataclass(frozen=True)
class ShaftShoulderGeometry:
    schema: str
    geometry_id: str
    small_diameter_mm: float
    large_diameter_mm: float
    fillet_radius_mm: float
    radial_step_mm: float
    diameter_ratio: float
    radius_ratio: float
    geometry_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("geometry_sha256")
        return payload


def _finite_positive(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ShaftShoulderError(f"{name} must be finite and positive")
    return result


def build_shaft_shoulder_geometry(
    *,
    geometry_id: str,
    small_diameter_mm: float,
    large_diameter_mm: float,
    fillet_radius_mm: float,
) -> ShaftShoulderGeometry:
    geometry_id = str(geometry_id).strip()
    if not geometry_id:
        raise ShaftShoulderError("geometry_id must be non-empty")
    d = _finite_positive("small_diameter_mm", small_diameter_mm)
    D = _finite_positive("large_diameter_mm", large_diameter_mm)
    r = _finite_positive("fillet_radius_mm", fillet_radius_mm)
    if D <= d:
        raise ShaftShoulderError("SHAFT_SHOULDER_REQUIRES_LARGE_DIAMETER_GT_SMALL_DIAMETER")
    radial_step = 0.5 * (D - d)
    if r > radial_step * (1.0 + 1.0e-12):
        raise ShaftShoulderError("FILLET_RADIUS_EXCEEDS_RADIAL_STEP")

    payload = {
        "schema": "AsterMaxShaftShoulderGeometryV1",
        "geometry_id": geometry_id,
        "small_diameter_mm": d,
        "large_diameter_mm": D,
        "fillet_radius_mm": r,
        "radial_step_mm": radial_step,
        "diameter_ratio": D / d,
        "radius_ratio": r / d,
    }
    return ShaftShoulderGeometry(**payload, geometry_sha256=canonical_sha256(payload))


def shaft_shoulder_geometry_evidence(geometry: ShaftShoulderGeometry) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SHAFT_SHOULDER:{geometry.geometry_id}",
        kind="SHAFT_SHOULDER_GEOMETRY",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Dimensionless shaft-shoulder geometry contract for bounded stress-concentration applicability."
        ),
        payload_sha256=geometry.geometry_sha256,
        metadata=geometry.canonical_without_hash(),
    )
