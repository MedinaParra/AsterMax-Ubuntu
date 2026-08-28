from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class AnalyticalComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class ScalarQoiComparison:
    schema: str
    qoi_id: str
    units: str
    analytical_evidence_sha256: str
    fea_evidence_sha256: str
    analytical_value: float
    fea_value: float
    absolute_error: float
    relative_error: float
    relative_scale_floor: float
    max_absolute_error: float
    max_relative_error: float
    absolute_check_passed: bool
    relative_check_passed: bool
    passed: bool
    comparison_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("comparison_sha256")
        return payload


def compare_scalar_qoi(
    *,
    qoi_id: str,
    units: str,
    analytical_evidence_sha256: str,
    fea_evidence_sha256: str,
    analytical_value: float,
    fea_value: float,
    max_absolute_error: float,
    max_relative_error: float,
    relative_scale_floor: float = 1.0e-12,
) -> ScalarQoiComparison:
    clean_qoi = str(qoi_id).strip(); clean_units = str(units).strip()
    a_sha = str(analytical_evidence_sha256).strip().lower()
    f_sha = str(fea_evidence_sha256).strip().lower()
    if not clean_qoi or not clean_units:
        raise AnalyticalComparisonError("QOI_ID_AND_UNITS_MUST_BE_NONEMPTY")
    if not _SHA_RE.fullmatch(a_sha) or not _SHA_RE.fullmatch(f_sha):
        raise AnalyticalComparisonError("QOI_COMPARISON_EVIDENCE_SHA_INVALID")

    ref = float(analytical_value); fea = float(fea_value)
    abs_limit = float(max_absolute_error); rel_limit = float(max_relative_error); floor = float(relative_scale_floor)
    if not all(math.isfinite(x) for x in (ref, fea, abs_limit, rel_limit, floor)):
        raise AnalyticalComparisonError("QOI_COMPARISON_VALUES_MUST_BE_FINITE")
    if abs_limit < 0.0 or rel_limit < 0.0 or floor <= 0.0:
        raise AnalyticalComparisonError("QOI_COMPARISON_THRESHOLDS_INVALID")

    absolute = abs(fea - ref)
    relative = absolute / max(abs(ref), floor)
    abs_pass = absolute <= abs_limit
    rel_pass = relative <= rel_limit
    passed = abs_pass and rel_pass

    payload = {
        "schema": "AsterMaxScalarQoiComparisonV1",
        "qoi_id": clean_qoi,
        "units": clean_units,
        "analytical_evidence_sha256": a_sha,
        "fea_evidence_sha256": f_sha,
        "analytical_value": ref,
        "fea_value": fea,
        "absolute_error": absolute,
        "relative_error": relative,
        "relative_scale_floor": floor,
        "max_absolute_error": abs_limit,
        "max_relative_error": rel_limit,
        "absolute_check_passed": abs_pass,
        "relative_check_passed": rel_pass,
        "passed": passed,
    }
    return ScalarQoiComparison(**payload, comparison_sha256=canonical_sha256(payload))


def scalar_qoi_comparison_evidence(comparison: ScalarQoiComparison) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"QOI_COMPARE:{comparison.qoi_id}:{comparison.comparison_sha256[:16]}",
        kind="ANALYTICAL_FEA_QOI_COMPARISON",
        status=EvidenceStatus.VERIFIED if comparison.passed else EvidenceStatus.CONTRADICTED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Explicit absolute and relative comparison between one FEA quantity of interest "
            "and its independently hashed analytical reference."
        ),
        payload_sha256=comparison.comparison_sha256,
        metadata=comparison.canonical_without_hash(),
    )
