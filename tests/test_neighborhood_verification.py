import pytest

from astermax.credibility import EvidenceStatus
from astermax.fea.neighborhood_verification import (
    NeighborhoodSample,
    compare_local_neighborhood,
    neighborhood_comparison_evidence,
)


def test_neighborhood_passes_when_all_spatial_samples_are_within_tolerance():
    samples = [
        NeighborhoodSample(0.5, 102.0, 100.0),
        NeighborhoodSample(1.0, 151.0, 150.0),
        NeighborhoodSample(2.0, 198.0, 200.0),
        NeighborhoodSample(4.0, 120.0, 118.0),
    ]
    comparison = compare_local_neighborhood(
        comparison_id="LOCAL",
        samples=samples,
        max_allowed_relative_error=0.03,
    )
    assert comparison.passed is True
    assert comparison.max_relative_error <= 0.03
    assert neighborhood_comparison_evidence(comparison).status is EvidenceStatus.VERIFIED


def test_neighborhood_failure_becomes_contradicted_evidence():
    samples = [
        NeighborhoodSample(1.0, 130.0, 100.0),
        NeighborhoodSample(2.0, 150.0, 150.0),
        NeighborhoodSample(3.0, 200.0, 200.0),
    ]
    comparison = compare_local_neighborhood(
        comparison_id="BAD",
        samples=samples,
        max_allowed_relative_error=0.05,
    )
    assert comparison.passed is False
    assert neighborhood_comparison_evidence(comparison).status is EvidenceStatus.CONTRADICTED


def test_core_exclusion_removes_declared_peak_region_before_comparison():
    samples = [
        NeighborhoodSample(0.1, 1000.0, 100.0),
        NeighborhoodSample(1.0, 101.0, 100.0),
        NeighborhoodSample(2.0, 151.0, 150.0),
        NeighborhoodSample(3.0, 199.0, 200.0),
    ]
    comparison = compare_local_neighborhood(
        comparison_id="EXCLUDED_CORE",
        samples=samples,
        core_exclusion_mm=0.5,
        max_allowed_relative_error=0.02,
        min_samples=3,
    )
    assert comparison.passed is True
    assert comparison.sample_count == 3
