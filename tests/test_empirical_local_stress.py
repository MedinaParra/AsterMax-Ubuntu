import math

import pytest

from astermax.credibility import ClaimEngine, ClaimState, ConsequenceLevel, ContextOfUse, EvidenceGraph
from astermax.fea.analytical_witness import analytical_section_witness_evidence, build_linear_normal_stress_witness
from astermax.fea.authorized_empirical_dataset import AuthorizedStressConcentrationDataset, authorized_dataset_intake_evidence
from astermax.fea.bounded_stress_concentration import build_stress_concentration_grid, evaluate_stress_concentration
from astermax.fea.empirical_local_stress import (
    EmpiricalLocalStressError,
    build_empirical_local_stress_prediction,
    empirical_evaluation_evidence,
    empirical_local_prediction_evidence,
    empirical_local_stress_chain_evidence,
    empirical_local_stress_computation_claim,
)
from astermax.fea.section_evidence import PlanarSectionProperties
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry
from astermax.fea.stress_concentration_applicability import (
    applicability_assessment_evidence,
    assess_stress_concentration_applicability,
    build_stress_concentration_applicability_domain,
)
from astermax.fea.stress_concentration_source import build_stress_concentration_source


def _section(diameter=20.0):
    area = math.pi * diameter**2 / 4.0
    i = math.pi * diameter**4 / 64.0
    return PlanarSectionProperties(
        schema="AsterMaxPlanarSectionPropertiesV1",
        selection_id="TEST_SECTION",
        source_sha256="1" * 64,
        face_signature_sha256="2" * 64,
        area_mm2=area,
        centroid_mm=(0.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        axis_u=(0.0, 1.0, 0.0),
        axis_v=(0.0, 0.0, 1.0),
        i_u_mm4=i,
        i_v_mm4=i,
        i_uv_mm4=0.0,
        principal_i_min_mm4=i,
        principal_i_max_mm4=i,
        polar_i_n_mm4=2.0 * i,
        polar_identity_relative_residual=0.0,
        method="TEST_EXACT_CIRCLE",
        section_sha256="3" * 64,
    )


def _fixture(*, radius_ratio_max=0.15, witness_diameter=20.0, moments=(0.0, 0.0)):
    source = build_stress_concentration_source(
        source_id="C16_SYNTHETIC",
        title="Synthetic C16",
        edition_or_release="1",
        publisher="AsterMax tests",
        locator="test_empirical_local_stress.py",
        source_url="https://example.invalid/c16",
        rights_note="SYNTHETIC_NOT_PHYSICAL",
    )
    grid = build_stress_concentration_grid(
        dataset_id="C16_GRID",
        factor_name="Kt_SYNTHETIC_NOT_PHYSICAL",
        load_mode="AXIAL_TENSION",
        source_provenance_sha256=source.provenance_sha256,
        diameter_ratios=(1.5, 2.0),
        radius_ratios=(0.05, 0.10),
        factors=((101.0, 102.0), (201.0, 202.0)),
    )
    intake_payload = {
        "schema": "AsterMaxAuthorizedStressConcentrationDatasetV1",
        "manifest_sha256": "4" * 64,
        "source_provenance_sha256": source.provenance_sha256,
        "raw_file_sha256": "5" * 64,
        "dataset_filename": "synthetic.json",
        "dataset_id": grid.dataset_id,
        "factor_name": grid.factor_name,
        "load_mode": grid.load_mode,
        "grid_dataset_sha256": grid.dataset_sha256,
        "authorization_basis": "SYNTHETIC_VERIFICATION",
        "synthetic_verification_only": True,
    }
    from astermax.credibility import canonical_sha256
    intake = AuthorizedStressConcentrationDataset(
        **intake_payload, intake_sha256=canonical_sha256(intake_payload)
    )
    geometry = build_shaft_shoulder_geometry(
        geometry_id="C16_GEOMETRY",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=2.0,
    )
    domain = build_stress_concentration_applicability_domain(
        domain_id="C16_DOMAIN",
        source_provenance_sha256=source.provenance_sha256,
        load_mode="AXIAL_TENSION",
        allowed_diameter_ratios=(1.5, 2.0),
        radius_ratio_min=0.01,
        radius_ratio_max=radius_ratio_max,
        source_locator="synthetic C16 domain",
    )
    applicability = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    evaluation = evaluate_stress_concentration(grid, geometry)
    section = _section(witness_diameter)
    witness = build_linear_normal_stress_witness(
        section,
        axial_force_n=1000.0,
        moment_u_nmm=moments[0],
        moment_v_nmm=moments[1],
    )
    return intake, grid, applicability, geometry, witness, evaluation


def test_synthetic_empirical_chain_computes_but_is_not_physical():
    intake, grid, applicability, geometry, witness, evaluation = _fixture()
    prediction = build_empirical_local_stress_prediction(
        intake, grid, applicability, geometry, witness, evaluation
    )
    assert prediction.kt_factor == 102.0
    assert prediction.predicted_local_axial_stress_mpa == pytest.approx(102.0 * witness.sigma0_mpa)
    assert prediction.nominal_area_relative_mismatch < 1e-12
    assert prediction.uses_non_synthetic_authorized_data is False

    context = ContextOfUse(
        context_id="COU_C16_TEST",
        engineering_question="Can the exact synthetic empirical chain be computed?",
        intended_decision="Permit software-chain verification only.",
        quantities_of_interest=("nominal stress", "synthetic Kt", "synthetic local stress"),
        acceptance_criteria=("all hashes and geometry bindings match",),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("synthetic nonphysical dataset",),
    )
    graph = EvidenceGraph(context)
    records = (
        authorized_dataset_intake_evidence(intake),
        applicability_assessment_evidence(applicability),
        analytical_section_witness_evidence(witness),
        empirical_evaluation_evidence(intake, evaluation),
        empirical_local_prediction_evidence(prediction),
        empirical_local_stress_chain_evidence(intake, applicability, witness, evaluation, prediction),
    )
    for record in records:
        graph.add(record)
    decision = ClaimEngine.evaluate(empirical_local_stress_computation_claim(context.context_id), graph)
    assert decision.state is ClaimState.PERMITTED


def test_outside_domain_blocks_prediction():
    args = _fixture(radius_ratio_max=0.08)
    assert args[2].applicable is False
    with pytest.raises(EmpiricalLocalStressError, match="OUTSIDE_GEOMETRY_DOMAIN"):
        build_empirical_local_stress_prediction(*args)


def test_nominal_section_for_other_diameter_blocks_prediction():
    args = _fixture(witness_diameter=18.0)
    with pytest.raises(EmpiricalLocalStressError, match="NOMINAL_SECTION_GEOMETRY_MISMATCH"):
        build_empirical_local_stress_prediction(*args)


def test_bending_moment_blocks_axial_kt_chain():
    args = _fixture(moments=(100.0, 0.0))
    with pytest.raises(EmpiricalLocalStressError, match="ZERO_BENDING_MOMENT"):
        build_empirical_local_stress_prediction(*args)


def test_geometry_hash_mismatch_blocks_prediction():
    intake, grid, applicability, geometry, witness, evaluation = _fixture()
    other_geometry = build_shaft_shoulder_geometry(
        geometry_id="OTHER_GEOMETRY",
        small_diameter_mm=20.0,
        large_diameter_mm=32.0,
        fillet_radius_mm=2.0,
    )
    with pytest.raises(EmpiricalLocalStressError, match="EVALUATION_GEOMETRY_SHA_MISMATCH"):
        build_empirical_local_stress_prediction(
            intake, grid, applicability, other_geometry, witness, evaluation
        )


def test_grid_hash_mismatch_blocks_prediction():
    intake, grid, applicability, geometry, witness, evaluation = _fixture()
    other_grid = build_stress_concentration_grid(
        dataset_id="OTHER_GRID",
        factor_name="Kt_SYNTHETIC_NOT_PHYSICAL",
        load_mode="AXIAL_TENSION",
        source_provenance_sha256=intake.source_provenance_sha256,
        diameter_ratios=(1.5, 2.0),
        radius_ratios=(0.05, 0.10),
        factors=((11.0, 12.0), (21.0, 22.0)),
    )
    with pytest.raises(EmpiricalLocalStressError, match="GRID_INTAKE_SHA_MISMATCH"):
        build_empirical_local_stress_prediction(
            intake, other_grid, applicability, geometry, witness, evaluation
        )
