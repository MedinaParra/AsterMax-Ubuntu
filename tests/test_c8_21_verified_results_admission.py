from dataclasses import replace

import numpy as np
import pytest

from astermax.cae_scene_contract import CaeSceneContract
from astermax.code_aster_reference_run import GenuineReferenceSolveEvidence
from astermax.professional_evidence_bundle import EvidenceArtifact, ProfessionalEvidenceBundle
from astermax.verified_results_admission import (
    VerifiedResultsAdmissionError,
    build_verified_results_provenance_panel,
    genuine_solve_evidence_sha256,
)


def _h(ch: str) -> str:
    return ch * 64


def _evidence() -> GenuineReferenceSolveEvidence:
    return GenuineReferenceSolveEvidence(
        engine_kind="code_aster_wsl2",
        distribution="Ubuntu-24.04",
        export_sha256=_h("1"),
        command_sha256=_h("2"),
        input_med_sha256=_h("3"),
        mesh_quality_report_sha256=_h("4"),
        mesh_quality_artifact_sha256=_h("5"),
        reference_case_evidence_sha256=_h("6"),
        result_med_sha256=_h("7"),
        message_sha256=_h("8"),
        displacement_table_sha256=_h("9"),
        reaction_table_sha256=_h("a"),
        stress_table_sha256=_h("b"),
        solver_stdout_sha256=_h("c"),
        returncode=0,
        message_diagnostic_ok=True,
        message_execution_exit_code=0,
        runtime_qualified=True,
        runtime_attested_immediately_before_solve=True,
        mesh_attested_immediately_before_solve=True,
        run_aster_sha256=_h("d"),
        config_sha256=_h("e"),
        detected_version="17.x-harness",
        fea_solve_executed=True,
        numerical_verification=True,
        results_verified=True,
        ux_relative_error=1.0e-4,
        reaction_relative_error=2.0e-4,
        stress_relative_error=3.0e-4,
    )


def _bundle(evidence: GenuineReferenceSolveEvidence) -> ProfessionalEvidenceBundle:
    return ProfessionalEvidenceBundle(
        schema_version="astermax.professional-evidence-bundle.v2",
        engine_kind=evidence.engine_kind,
        distribution=evidence.distribution,
        detected_version=evidence.detected_version,
        cad_length_unit="mm",
        solver_unit_system="mm-N-MPa",
        runtime_qualified=True,
        runtime_attested_immediately_before_solve=True,
        mesh_attested_immediately_before_solve=True,
        fea_solve_executed=True,
        numerical_verification=True,
        results_verified=True,
        industrial_validation=False,
        ansys_equivalence=False,
        run_aster_sha256=evidence.run_aster_sha256,
        config_sha256=evidence.config_sha256,
        mesh_quality_report_sha256=evidence.mesh_quality_report_sha256,
        mesh_quality_artifact_sha256=evidence.mesh_quality_artifact_sha256,
        reference_case_evidence_sha256=evidence.reference_case_evidence_sha256,
        ux_relative_error=evidence.ux_relative_error,
        reaction_relative_error=evidence.reaction_relative_error,
        stress_relative_error=evidence.stress_relative_error,
        artifacts=(EvidenceArtifact("result_med", "astermax_result.med", evidence.result_med_sha256, 123),),
        manifest_sha256=_h("f"),
    )


def _scene(evidence: GenuineReferenceSolveEvidence) -> CaeSceneContract:
    nodes = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    displacement = np.array([[0.01, 0.0, 0.0]] * 4, dtype=float)
    nodal_vm = np.array([10.0, 20.0, 30.0, 40.0], dtype=float)
    return CaeSceneContract(
        undeformed_nodes_mm=nodes,
        deformed_nodes_mm=nodes + displacement,
        surface_triangles=np.array([[0, 1, 2]], dtype=int),
        nodal_von_mises_mpa=nodal_vm,
        triangle_von_mises_mpa=np.array([20.0], dtype=float),
        triangle_scalar_normalized=np.array([0.5], dtype=float),
        displacement_magnitude_mm=np.array([0.01] * 4, dtype=float),
        scalar_min_mpa=10.0,
        scalar_max_mpa=40.0,
        deformation_scale=1.0,
        length_unit="mm",
        stress_unit="MPa",
        stress_representation="CODE_ASTER_SIEQ_NOEU:SIEQ_NOEU;DISPLAY_SURFACE=NODE_AVERAGE_ONLY",
        workspace_sha256=evidence.result_med_sha256,
        solve_evidence_sha256=genuine_solve_evidence_sha256(evidence),
        displacement_vector_mm=displacement,
    )


def test_verified_code_aster_scene_is_admitted_only_with_aligned_provenance():
    evidence = _evidence()
    panel = build_verified_results_provenance_panel(_scene(evidence), evidence, _bundle(evidence))
    assert panel.admission_status == "VERIFIED_CODE_ASTER_RESULTS_ADMITTED"
    assert panel.displacement_field == "DEPL_NOEU"
    assert panel.stress_field == "SIEQ_NOEU"
    assert panel.cad_length_unit == "mm"
    assert panel.solver_unit_system == "mm-N-MPa"
    assert panel.fea_solve_executed is True
    assert panel.numerical_verification is True
    assert panel.results_verified is True
    assert panel.industrial_validation is False
    assert panel.ansys_equivalence is False


def test_scene_from_unrelated_solve_is_rejected():
    evidence = _evidence()
    scene = replace(_scene(evidence), solve_evidence_sha256=_h("0"))
    with pytest.raises(VerifiedResultsAdmissionError, match="SCENE_SOLVE_EVIDENCE_MISMATCH"):
        build_verified_results_provenance_panel(scene, evidence, _bundle(evidence))


def test_result_med_hash_mismatch_between_scene_bundle_and_solve_is_rejected():
    evidence = _evidence()
    bundle = _bundle(evidence)
    bad_artifact = replace(bundle.artifacts[0], sha256=_h("0"))
    with pytest.raises(VerifiedResultsAdmissionError, match="BUNDLE_RESULT_MED_MISMATCH"):
        build_verified_results_provenance_panel(_scene(evidence), evidence, replace(bundle, artifacts=(bad_artifact,)))


def test_unverified_solve_cannot_unlock_professional_results():
    evidence = replace(_evidence(), results_verified=False)
    with pytest.raises(VerifiedResultsAdmissionError, match="RESULT_VERIFICATION_MISSING"):
        build_verified_results_provenance_panel(_scene(evidence), evidence, _bundle(evidence))


def test_native_code_aster_displacement_vector_is_required():
    evidence = _evidence()
    scene = replace(_scene(evidence), displacement_vector_mm=None)
    with pytest.raises(VerifiedResultsAdmissionError, match="NATIVE_DEPL_VECTOR_REQUIRED"):
        build_verified_results_provenance_panel(scene, evidence, _bundle(evidence))


def test_ansys_equivalence_cannot_be_promoted_by_results_bundle():
    evidence = _evidence()
    bundle = replace(_bundle(evidence), ansys_equivalence=True)
    with pytest.raises(VerifiedResultsAdmissionError, match="UNSUPPORTED_PROMOTION"):
        build_verified_results_provenance_panel(_scene(evidence), evidence, bundle)
