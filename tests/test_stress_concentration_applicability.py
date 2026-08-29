import pytest

from astermax.credibility import ClaimEngine, ClaimState, ConsequenceLevel, ContextOfUse, EvidenceGraph
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry, shaft_shoulder_geometry_evidence
from astermax.fea.stress_concentration_applicability import (
    StressConcentrationApplicabilityError,
    applicability_assessment_evidence,
    applicability_domain_evidence,
    assess_stress_concentration_applicability,
    build_stress_concentration_applicability_domain,
    empirical_kt_source_applicability_claim,
)
from astermax.fea.stress_concentration_source import (
    build_stress_concentration_source,
    naca_tn_2442_source_metadata,
    source_provenance_evidence,
)


def _domain(source):
    return build_stress_concentration_applicability_domain(
        domain_id="NACA_TN2442_TENSION_FILLET_SCOPE",
        source_provenance_sha256=source.provenance_sha256,
        load_mode="AXIAL_TENSION",
        allowed_diameter_ratios=(1.5, 2.0),
        radius_ratio_min=0.011,
        radius_ratio_max=0.08,
        source_locator="NACA TN-2442 published investigation scope",
    )


def test_naca_domain_accepts_in_scope_geometry():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="IN_SCOPE",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=1.0,
    )
    result = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert geometry.diameter_ratio == pytest.approx(1.5)
    assert geometry.radius_ratio == pytest.approx(0.05)
    assert result.applicable is True
    assert result.classification == "APPLICABLE"
    assert result.blockers == ()


def test_c14_fixture_radius_ratio_is_outside_naca_domain_and_claim_blocks():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="C14_R10_R15_R2",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=2.0,
    )
    result = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert geometry.diameter_ratio == pytest.approx(1.5)
    assert geometry.radius_ratio == pytest.approx(0.10)
    assert result.applicable is False
    assert result.classification == "OUTSIDE_EMPIRICAL_DOMAIN"
    assert result.blockers == ("RADIUS_RATIO_OUTSIDE_EMPIRICAL_DOMAIN",)

    context = ContextOfUse(
        context_id="COU_C14_TEST",
        engineering_question="Is NACA TN-2442 applicable to this exact shoulder geometry?",
        intended_decision="Permit only a source-applicability claim; no Kt calculation.",
        quantities_of_interest=("empirical source applicability",),
        acceptance_criteria=("geometry and load mode inside published source domain",),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("source scope represented exactly",),
    )
    graph = EvidenceGraph(context)
    for record in (
        source_provenance_evidence(source),
        shaft_shoulder_geometry_evidence(geometry),
        applicability_domain_evidence(domain),
        applicability_assessment_evidence(result),
    ):
        graph.add(record)
    decision = ClaimEngine.evaluate(empirical_kt_source_applicability_claim(context.context_id), graph)
    assert decision.state is ClaimState.BLOCKED


def test_wrong_load_mode_fails_closed():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="LOAD_MODE",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=1.0,
    )
    result = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="TORSION"
    )
    assert result.applicable is False
    assert "LOAD_MODE_OUTSIDE_EMPIRICAL_DOMAIN" in result.blockers


def test_undeclared_diameter_ratio_fails_closed_without_interpolation():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="D_RATIO",
        small_diameter_mm=20.0,
        large_diameter_mm=34.0,
        fillet_radius_mm=1.0,
    )
    result = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert geometry.diameter_ratio == pytest.approx(1.7)
    assert result.applicable is False
    assert "DIAMETER_RATIO_OUTSIDE_EMPIRICAL_DOMAIN" in result.blockers


def test_domain_source_binding_mismatch_rejected():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    other = build_stress_concentration_source(
        source_id="OTHER",
        title="Other",
        edition_or_release="1",
        publisher="Other",
        locator="Other",
        source_url="https://example.invalid/other",
        rights_note="TEST",
    )
    geometry = build_shaft_shoulder_geometry(
        geometry_id="BINDING",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=1.0,
    )
    with pytest.raises(StressConcentrationApplicabilityError, match="PROVENANCE_MISMATCH"):
        assess_stress_concentration_applicability(
            other, domain, geometry, requested_load_mode="AXIAL_TENSION"
        )
