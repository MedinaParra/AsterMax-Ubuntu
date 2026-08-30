from dataclasses import replace

import pytest

from astermax.credibility import canonical_sha256
from astermax.fea.local_refinement_plan import (
    approve_refinement_plan,
    build_controlled_local_refinement_plan,
    target_size_at_point,
    verify_refinement_execution_boundary,
)
from astermax.fea.qoi_convergence import LocalRefinementReviewV1


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def make_review() -> LocalRefinementReviewV1:
    core = {
        "schema": "AsterMaxLocalRefinementReviewV1",
        "inspector_snapshot_sha256": "d" * 64,
        "candidate_element_indices": (4, 9),
        "candidate_centroids_mm": ((10.0, 20.0, 30.0), (40.0, 50.0, 60.0)),
        "rationale": ("SYNTHETIC_HARNESS_REVIEW_ONLY",),
        "requires_human_approval": True,
        "auto_execution_allowed": False,
        "changes_physics": False,
    }
    return LocalRefinementReviewV1(**core, review_sha256=canonical_sha256(core))


def make_plan():
    return build_controlled_local_refinement_plan(
        source_step_sha256=SHA_A,
        route_sha256=SHA_B,
        baseline_mesh_sha256=SHA_C,
        review=make_review(),
        baseline_size_mm=10.0,
        refined_size_factor=0.5,
        influence_radius_factor=2.0,
    )


def test_plan_is_deterministic_and_provenance_bound():
    one = make_plan()
    two = make_plan()
    assert one == two
    assert one.plan_sha256 == two.plan_sha256
    assert one.source_step_sha256 == SHA_A
    assert one.route_sha256 == SHA_B
    assert one.baseline_mesh_sha256 == SHA_C
    assert one.baseline_size_mm == 10.0
    assert one.refined_size_mm == 5.0
    assert one.radius_mm == 20.0
    assert one.preserves_source_geometry is True
    assert one.preserves_bc_load_route is True
    assert one.auto_execution_allowed is False
    assert one.changes_physics is False


def test_target_size_field_is_local_and_bounded():
    plan = make_plan()
    assert target_size_at_point(plan, (10.0, 20.0, 30.0)) == 5.0
    assert target_size_at_point(plan, (30.0, 20.0, 30.0)) == 5.0
    assert target_size_at_point(plan, (31.0, 20.0, 30.0)) == 10.0
    assert target_size_at_point(plan, (1000.0, 1000.0, 1000.0)) == 10.0


def test_human_approval_is_explicit_but_does_not_enable_auto_execution():
    plan = make_plan()
    approval = approve_refinement_plan(plan, approver="Engineering Reviewer", approved=True)
    assert approval.approved is True
    assert approval.plan_sha256 == plan.plan_sha256
    assert approval.scope == "MESH_DISCRETIZATION_ONLY_NO_PHYSICS_CHANGE"
    verify_refinement_execution_boundary(plan, approval)
    assert plan.auto_execution_allowed is False


def test_rejects_stale_approval():
    plan = make_plan()
    approval = approve_refinement_plan(plan, approver="Reviewer", approved=True)
    stale = replace(approval, plan_sha256="f" * 64)
    with pytest.raises(ValueError, match="REFINEMENT_APPROVAL_STALE"):
        verify_refinement_execution_boundary(plan, stale)


def test_rejects_auto_execution_or_physics_mutation_overclaim():
    plan = make_plan()
    with pytest.raises(ValueError, match="REFINEMENT_AUTO_EXECUTION_OVERCLAIM"):
        verify_refinement_execution_boundary(replace(plan, auto_execution_allowed=True))
    with pytest.raises(ValueError, match="REFINEMENT_PHYSICS_MUTATION_OVERCLAIM"):
        verify_refinement_execution_boundary(replace(plan, changes_physics=True))


def test_rejects_invalid_refinement_parameters():
    kwargs = dict(
        source_step_sha256=SHA_A,
        route_sha256=SHA_B,
        baseline_mesh_sha256=SHA_C,
        review=make_review(),
        baseline_size_mm=10.0,
    )
    with pytest.raises(ValueError, match="REFINEMENT_SIZE_FACTOR_RANGE"):
        build_controlled_local_refinement_plan(**kwargs, refined_size_factor=1.0)
    with pytest.raises(ValueError, match="REFINEMENT_RADIUS_FACTOR_RANGE"):
        build_controlled_local_refinement_plan(**kwargs, influence_radius_factor=0.0)


def test_rejects_nonfinite_centroid_and_bad_review_policy():
    review = make_review()
    bad_centroid = replace(review, candidate_centroids_mm=((float("nan"), 0.0, 0.0),))
    bad_centroid = replace(bad_centroid, candidate_element_indices=(4,))
    with pytest.raises(ValueError, match="REFINEMENT_CANDIDATE_CENTROID_NONFINITE"):
        build_controlled_local_refinement_plan(
            source_step_sha256=SHA_A,
            route_sha256=SHA_B,
            baseline_mesh_sha256=SHA_C,
            review=bad_centroid,
            baseline_size_mm=10.0,
        )

    with pytest.raises(ValueError, match="REFINEMENT_REVIEW_AUTO_EXECUTION_FORBIDDEN"):
        build_controlled_local_refinement_plan(
            source_step_sha256=SHA_A,
            route_sha256=SHA_B,
            baseline_mesh_sha256=SHA_C,
            review=replace(review, auto_execution_allowed=True),
            baseline_size_mm=10.0,
        )
