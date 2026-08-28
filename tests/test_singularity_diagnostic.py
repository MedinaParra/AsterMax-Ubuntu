import pytest

from astermax.fea.singularity_diagnostic import (
    RefinementFieldSample,
    SingularityDiagnosticError,
    diagnose_local_singularity,
)


def test_growing_peak_with_stable_neighborhood_is_likely_singularity():
    result = diagnose_local_singularity(
        diagnostic_id="SING",
        samples=(
            RefinementFieldSample(4.0, 200.0, 160.0),
            RefinementFieldSample(2.0, 260.0, 162.0),
            RefinementFieldSample(1.0, 350.0, 163.0),
            RefinementFieldSample(0.5, 480.0, 163.5),
        ),
    )
    assert result.classification == "LIKELY_SINGULARITY"
    assert result.peak_growth_factor > 2.0
    assert result.neighborhood_last_change < 0.03


def test_stable_peak_and_neighborhood_is_locally_converged_field():
    result = diagnose_local_singularity(
        diagnostic_id="CONV",
        samples=(
            RefinementFieldSample(4.0, 205.0, 160.0),
            RefinementFieldSample(2.0, 210.0, 162.0),
            RefinementFieldSample(1.0, 212.0, 163.0),
        ),
    )
    assert result.classification == "LOCALLY_CONVERGED_FIELD"


def test_refinement_order_must_be_coarse_to_fine():
    with pytest.raises(SingularityDiagnosticError, match="strictly decreasing"):
        diagnose_local_singularity(
            diagnostic_id="BAD",
            samples=(
                RefinementFieldSample(2.0, 200.0, 160.0),
                RefinementFieldSample(4.0, 220.0, 161.0),
                RefinementFieldSample(1.0, 240.0, 162.0),
            ),
        )
