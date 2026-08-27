from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .tet10 import TET10_GAUSS_POINTS, tet10_shape_functions


class NeighborhoodVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class NeighborhoodVerificationPolicy:
    axis: int = 0
    lower_fraction: float = 0.2
    upper_fraction: float = 0.8
    relative_error_limit: float = 0.05
    absolute_floor_mpa: float = 1.0e-12
    schema: str = "ASTERMAX_FEA_NEIGHBORHOOD_POLICY_V1"

    def validate(self) -> None:
        if self.axis not in (0, 1, 2):
            raise NeighborhoodVerificationError("axis must be 0, 1 or 2")
        if not (0.0 <= self.lower_fraction < self.upper_fraction <= 1.0):
            raise NeighborhoodVerificationError("neighborhood fractions must satisfy 0 <= lower < upper <= 1")
        if not np.isfinite(self.relative_error_limit) or self.relative_error_limit <= 0.0:
            raise NeighborhoodVerificationError("relative_error_limit must be finite and positive")
        if not np.isfinite(self.absolute_floor_mpa) or self.absolute_floor_mpa <= 0.0:
            raise NeighborhoodVerificationError("absolute_floor_mpa must be finite and positive")
        if self.schema != "ASTERMAX_FEA_NEIGHBORHOOD_POLICY_V1":
            raise NeighborhoodVerificationError("unsupported neighborhood policy schema")


DEFAULT_NEIGHBORHOOD_POLICY = NeighborhoodVerificationPolicy()


@dataclass(frozen=True)
class NeighborhoodVerificationReport:
    schema: str
    status: str
    sample_count_total: int
    sample_count_in_neighborhood: int
    coordinate_min_mm: float
    coordinate_max_mm: float
    neighborhood_min_mm: float
    neighborhood_max_mm: float
    mean_fea_mpa: float
    mean_reference_mpa: float
    mean_signed_error_mpa: float
    rms_error_mpa: float
    maximum_absolute_error_mpa: float
    maximum_relative_error: float
    policy: dict
    comparison_quantity: str
    stress_representation: str
    evidence_boundary: str
    report_sha256: str


def tet10_integration_point_positions(nodes_mm: np.ndarray, elements: np.ndarray) -> np.ndarray:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise NeighborhoodVerificationError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise NeighborhoodVerificationError("elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise NeighborhoodVerificationError("elements contains an out-of-range node index")
    positions = np.empty((elems.shape[0], 4, 3), dtype=float)
    for element_index, conn in enumerate(elems):
        coords = nodes[conn]
        for ip_index, natural in enumerate(TET10_GAUSS_POINTS):
            positions[element_index, ip_index] = tet10_shape_functions(natural) @ coords
    return positions


def verify_scalar_stress_neighborhood(
    positions_mm: np.ndarray,
    fea_values_mpa: np.ndarray,
    reference_mpa: float | Callable[[np.ndarray], float],
    *,
    policy: NeighborhoodVerificationPolicy = DEFAULT_NEIGHBORHOOD_POLICY,
    comparison_quantity: str = "SIGMA_XX_AT_TET10_INTEGRATION_POINTS",
) -> NeighborhoodVerificationReport:
    policy.validate()
    positions = np.asarray(positions_mm, dtype=float)
    values = np.asarray(fea_values_mpa, dtype=float)
    if positions.ndim != 3 or positions.shape[1:] != (4, 3):
        raise NeighborhoodVerificationError("positions_mm must have shape (m, 4, 3)")
    if values.shape != positions.shape[:2]:
        raise NeighborhoodVerificationError("fea_values_mpa must have shape (m, 4)")
    if not np.all(np.isfinite(positions)) or not np.all(np.isfinite(values)):
        raise NeighborhoodVerificationError("neighborhood verification refuses non-finite data")
    flat_positions = positions.reshape((-1, 3))
    flat_values = values.reshape(-1)
    if flat_values.size == 0:
        raise NeighborhoodVerificationError("at least one integration-point sample is required")

    coordinate = flat_positions[:, policy.axis]
    cmin = float(np.min(coordinate))
    cmax = float(np.max(coordinate))
    span = cmax - cmin
    if span <= 0.0:
        raise NeighborhoodVerificationError("comparison coordinate must have positive span")
    lower = cmin + policy.lower_fraction * span
    upper = cmin + policy.upper_fraction * span
    mask = (coordinate >= lower) & (coordinate <= upper)
    if not np.any(mask):
        raise NeighborhoodVerificationError("declared neighborhood contains no integration points")

    p = flat_positions[mask]
    fea = flat_values[mask]
    if callable(reference_mpa):
        ref = np.asarray([float(reference_mpa(point)) for point in p], dtype=float)
    else:
        ref = np.full(fea.shape, float(reference_mpa), dtype=float)
    if not np.all(np.isfinite(ref)):
        raise NeighborhoodVerificationError("reference stress must be finite")

    error = fea - ref
    denom = np.maximum(np.abs(ref), policy.absolute_floor_mpa)
    rel = np.abs(error) / denom
    maximum_relative_error = float(np.max(rel))
    status = "PASS" if maximum_relative_error <= policy.relative_error_limit else "FAIL"
    payload = {
        "schema": "AsterMaxNeighborhoodVerificationReportV1",
        "status": status,
        "sample_count_total": int(flat_values.size),
        "sample_count_in_neighborhood": int(fea.size),
        "coordinate_min_mm": cmin,
        "coordinate_max_mm": cmax,
        "neighborhood_min_mm": lower,
        "neighborhood_max_mm": upper,
        "mean_fea_mpa": float(np.mean(fea)),
        "mean_reference_mpa": float(np.mean(ref)),
        "mean_signed_error_mpa": float(np.mean(error)),
        "rms_error_mpa": float(np.sqrt(np.mean(error * error))),
        "maximum_absolute_error_mpa": float(np.max(np.abs(error))),
        "maximum_relative_error": maximum_relative_error,
        "policy": asdict(policy),
        "comparison_quantity": str(comparison_quantity),
        "stress_representation": "TET10_INTEGRATION_POINT_STRESS_NO_NODAL_SMOOTHING",
        "evidence_boundary": "INTERIOR_NEIGHBORHOOD_COMPARISON_NOT_SINGULAR_PEAK_AND_NOT_INDUSTRIAL_VALIDATION",
    }
    return NeighborhoodVerificationReport(**payload, report_sha256=canonical_sha256(payload))


def neighborhood_verification_evidence(report: NeighborhoodVerificationReport) -> EvidenceRecord:
    status = EvidenceStatus.VERIFIED if report.status == "PASS" else EvidenceStatus.FAILED
    return EvidenceRecord(
        evidence_id=f"FEA_NEIGHBORHOOD:{report.report_sha256[:24]}",
        kind="FEA_ANALYTICAL_NEIGHBORHOOD_COMPARISON",
        status=status,
        source=EvidenceSource.NUMERICAL_VERIFICATION,
        description="TET10 integration-point stress compared with an analytical reference inside a declared interior neighborhood.",
        payload_sha256=report.report_sha256,
        metadata={
            "comparison_quantity": report.comparison_quantity,
            "maximum_relative_error": report.maximum_relative_error,
            "sample_count_in_neighborhood": report.sample_count_in_neighborhood,
            "stress_representation": report.stress_representation,
            "singular_peak_used": False,
            "ansys_equivalence": False,
            "industrial_validation": False,
        },
    )
