from astermax.fea.neighborhood_verification import NeighborhoodSample, compare_local_neighborhood
from astermax.fea.physics_guided_refinement import recommend_local_refinement
from astermax.fea.singularity_diagnostic import RefinementFieldSample, diagnose_local_singularity


def _passing_neighborhood():
    return compare_local_neighborhood(
        comparison_id="PASS",
        samples=(
            NeighborhoodSample(1.0, 101.0, 100.0),
            NeighborhoodSample(2.0, 150.0, 150.0),
            NeighborhoodSample(3.0, 199.0, 200.0),
        ),
        max_allowed_relative_error=0.02,
    )


def test_likely_singularity_stops_peak_chasing():
    singularity = diagnose_local_singularity(
        diagnostic_id="SING",
        samples=(
            RefinementFieldSample(4.0, 200.0, 160.0),
            RefinementFieldSample(2.0, 270.0, 162.0),
            RefinementFieldSample(1.0, 380.0, 163.0),
        ),
    )
    recommendation = recommend_local_refinement(
        recommendation_id="R1",
        neighborhood=_passing_neighborhood(),
        singularity=singularity,
    )
    assert recommendation.action == "REFINE_NEIGHBORHOOD_DO_NOT_CHASE_PEAK"
    assert recommendation.target_size_factor == 0.5


def test_converged_neighborhood_and_peak_need_no_refinement():
    singularity = diagnose_local_singularity(
        diagnostic_id="CONV",
        samples=(
            RefinementFieldSample(4.0, 205.0, 160.0),
            RefinementFieldSample(2.0, 210.0, 162.0),
            RefinementFieldSample(1.0, 212.0, 163.0),
        ),
    )
    recommendation = recommend_local_refinement(
        recommendation_id="R2",
        neighborhood=_passing_neighborhood(),
        singularity=singularity,
    )
    assert recommendation.action == "NO_REFINEMENT_REQUIRED"
    assert recommendation.target_size_factor is None


def test_failed_neighborhood_requests_local_refinement():
    neighborhood = compare_local_neighborhood(
        comparison_id="FAIL",
        samples=(
            NeighborhoodSample(1.0, 130.0, 100.0),
            NeighborhoodSample(2.0, 160.0, 150.0),
            NeighborhoodSample(3.0, 210.0, 200.0),
        ),
        max_allowed_relative_error=0.02,
    )
    diagnostic = diagnose_local_singularity(
        diagnostic_id="INC",
        samples=(
            RefinementFieldSample(4.0, 200.0, 160.0),
            RefinementFieldSample(2.0, 210.0, 170.0),
            RefinementFieldSample(1.0, 215.0, 180.0),
        ),
    )
    recommendation = recommend_local_refinement(
        recommendation_id="R3",
        neighborhood=neighborhood,
        singularity=diagnostic,
    )
    assert recommendation.action == "REFINE_LOCAL_NEIGHBORHOOD"
