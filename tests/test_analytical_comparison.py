import pytest

from astermax.credibility import EvidenceStatus
from astermax.fea.analytical_comparison import (
    AnalyticalComparisonError,
    compare_scalar_qoi,
    scalar_qoi_comparison_evidence,
)


def test_qoi_comparison_passes_only_when_both_declared_limits_pass():
    result = compare_scalar_qoi(
        qoi_id="TIP_UY",
        units="mm",
        analytical_evidence_sha256="1" * 64,
        fea_evidence_sha256="2" * 64,
        analytical_value=-0.2578,
        fea_value=-0.25488,
        max_absolute_error=0.01,
        max_relative_error=0.02,
    )
    assert result.absolute_check_passed is True
    assert result.relative_check_passed is True
    assert result.passed is True
    assert scalar_qoi_comparison_evidence(result).status is EvidenceStatus.VERIFIED


def test_qoi_comparison_failure_becomes_contradicted_evidence():
    result = compare_scalar_qoi(
        qoi_id="TIP_UY",
        units="mm",
        analytical_evidence_sha256="1" * 64,
        fea_evidence_sha256="2" * 64,
        analytical_value=-0.2578,
        fea_value=-0.20,
        max_absolute_error=0.01,
        max_relative_error=0.02,
    )
    assert result.passed is False
    evidence = scalar_qoi_comparison_evidence(result)
    assert evidence.status is EvidenceStatus.CONTRADICTED


def test_qoi_comparison_rejects_invalid_hash():
    with pytest.raises(AnalyticalComparisonError, match="SHA_INVALID"):
        compare_scalar_qoi(
            qoi_id="Q", units="MPa",
            analytical_evidence_sha256="bad", fea_evidence_sha256="2" * 64,
            analytical_value=1.0, fea_value=1.0,
            max_absolute_error=0.1, max_relative_error=0.1,
        )


def test_qoi_comparison_hash_is_deterministic():
    kwargs = dict(
        qoi_id="ROOT_VM", units="MPa",
        analytical_evidence_sha256="a" * 64, fea_evidence_sha256="b" * 64,
        analytical_value=100.0, fea_value=101.0,
        max_absolute_error=2.0, max_relative_error=0.02,
    )
    assert compare_scalar_qoi(**kwargs) == compare_scalar_qoi(**kwargs)
