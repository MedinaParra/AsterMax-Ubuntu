from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Iterable

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .shaft_shoulder import ShaftShoulderGeometry
from .stress_concentration_source import StressConcentrationSource


class StressConcentrationGridError(ValueError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StressConcentrationGrid:
    schema: str
    dataset_id: str
    factor_name: str
    load_mode: str
    source_provenance_sha256: str
    diameter_ratios: tuple[float, ...]
    radius_ratios: tuple[float, ...]
    factors: tuple[tuple[float, ...], ...]
    dataset_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("dataset_sha256")
        return payload


@dataclass(frozen=True)
class StressConcentrationEvaluation:
    schema: str
    dataset_sha256: str
    geometry_sha256: str
    diameter_ratio: float
    radius_ratio: float
    factor: float
    interpolation: str
    evaluation_sha256: str


def _axis(name: str, values: Iterable[float]) -> tuple[float, ...]:
    axis = tuple(float(value) for value in values)
    if len(axis) < 2 or any(not math.isfinite(v) or v <= 0.0 for v in axis):
        raise StressConcentrationGridError(f"{name} must contain at least two finite positive values")
    if any(b <= a for a, b in zip(axis, axis[1:])):
        raise StressConcentrationGridError(f"{name} must be strictly increasing")
    return axis


def build_stress_concentration_grid(
    *,
    dataset_id: str,
    factor_name: str,
    load_mode: str,
    source_provenance_sha256: str,
    diameter_ratios: Iterable[float],
    radius_ratios: Iterable[float],
    factors: Iterable[Iterable[float]],
) -> StressConcentrationGrid:
    dataset_id = str(dataset_id).strip()
    factor_name = str(factor_name).strip()
    load_mode = str(load_mode).strip()
    source_sha = str(source_provenance_sha256).lower().strip()
    if not dataset_id or not factor_name or not load_mode:
        raise StressConcentrationGridError("dataset_id, factor_name and load_mode must be non-empty")
    if not _SHA256_RE.fullmatch(source_sha):
        raise StressConcentrationGridError("source_provenance_sha256 must be a SHA-256 digest")
    d_axis = _axis("diameter_ratios", diameter_ratios)
    r_axis = _axis("radius_ratios", radius_ratios)
    rows = tuple(tuple(float(value) for value in row) for row in factors)
    if len(rows) != len(d_axis) or any(len(row) != len(r_axis) for row in rows):
        raise StressConcentrationGridError("factor matrix shape must match ratio axes")
    if any(not math.isfinite(value) or value <= 0.0 for row in rows for value in row):
        raise StressConcentrationGridError("all stress concentration factors must be finite and positive")

    payload = {
        "schema": "AsterMaxStressConcentrationGridV1",
        "dataset_id": dataset_id,
        "factor_name": factor_name,
        "load_mode": load_mode,
        "source_provenance_sha256": source_sha,
        "diameter_ratios": d_axis,
        "radius_ratios": r_axis,
        "factors": rows,
    }
    return StressConcentrationGrid(**payload, dataset_sha256=canonical_sha256(payload))


def assert_grid_source_binding(grid: StressConcentrationGrid, source: StressConcentrationSource) -> None:
    if grid.source_provenance_sha256 != source.provenance_sha256:
        raise StressConcentrationGridError("STRESS_CONCENTRATION_SOURCE_PROVENANCE_MISMATCH")
    if source.dataset_sha256 is not None and source.dataset_sha256 != grid.dataset_sha256:
        raise StressConcentrationGridError("STRESS_CONCENTRATION_DATASET_SHA_MISMATCH")


def _bracket(axis: tuple[float, ...], value: float) -> tuple[int, int, float]:
    if value < axis[0] or value > axis[-1]:
        raise StressConcentrationGridError("STRESS_CONCENTRATION_OUT_OF_DOMAIN")
    if value == axis[-1]:
        return len(axis) - 2, len(axis) - 1, 1.0
    for i in range(len(axis) - 1):
        if axis[i] <= value <= axis[i + 1]:
            span = axis[i + 1] - axis[i]
            return i, i + 1, (value - axis[i]) / span
    raise StressConcentrationGridError("STRESS_CONCENTRATION_OUT_OF_DOMAIN")


def evaluate_stress_concentration(
    grid: StressConcentrationGrid,
    geometry: ShaftShoulderGeometry,
) -> StressConcentrationEvaluation:
    i0, i1, tx = _bracket(grid.diameter_ratios, geometry.diameter_ratio)
    j0, j1, ty = _bracket(grid.radius_ratios, geometry.radius_ratio)
    q00 = grid.factors[i0][j0]
    q10 = grid.factors[i1][j0]
    q01 = grid.factors[i0][j1]
    q11 = grid.factors[i1][j1]
    factor = (
        (1.0 - tx) * (1.0 - ty) * q00
        + tx * (1.0 - ty) * q10
        + (1.0 - tx) * ty * q01
        + tx * ty * q11
    )
    payload = {
        "schema": "AsterMaxStressConcentrationEvaluationV1",
        "dataset_sha256": grid.dataset_sha256,
        "geometry_sha256": geometry.geometry_sha256,
        "diameter_ratio": geometry.diameter_ratio,
        "radius_ratio": geometry.radius_ratio,
        "factor": factor,
        "interpolation": "BOUNDED_BILINEAR_NO_EXTRAPOLATION",
    }
    return StressConcentrationEvaluation(**payload, evaluation_sha256=canonical_sha256(payload))


def stress_concentration_dataset_evidence(grid: StressConcentrationGrid) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SCF_DATASET:{grid.dataset_id}",
        kind="STRESS_CONCENTRATION_DATASET",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Hash-bound stress-concentration dataset with bounded interpolation axes. "
            "Dataset provenance must be validated separately."
        ),
        payload_sha256=grid.dataset_sha256,
        metadata=grid.canonical_without_hash(),
    )
