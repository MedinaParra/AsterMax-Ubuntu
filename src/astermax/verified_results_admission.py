from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

from .cae_scene_contract import CaeSceneContract, validate_cae_scene_contract
from .code_aster_reference_run import GenuineReferenceSolveEvidence
from .professional_evidence_bundle import ProfessionalEvidenceBundle


class VerifiedResultsAdmissionError(RuntimeError):
    pass


def genuine_solve_evidence_sha256(evidence: GenuineReferenceSolveEvidence) -> str:
    """Return the exact solve-evidence digest used by the Code_Aster CAE scene bridge.

    This intentionally mirrors the existing scene contract until that serialization
    can be versioned without breaking prior evidence. Centralizing the check here
    prevents a visually valid scene from being admitted with unrelated solve data.
    """
    return sha256(str(sorted(evidence.as_dict().items())).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerifiedResultsProvenancePanel:
    admission_status: str
    engine_kind: str
    distribution: str
    detected_version: str | None
    cad_length_unit: str
    solver_unit_system: str
    displacement_field: str
    stress_field: str
    stress_field_location: str
    stress_display_note: str
    result_med_sha256: str
    solve_evidence_sha256: str
    evidence_bundle_manifest_sha256: str
    run_aster_sha256: str
    config_sha256: str
    runtime_qualified: bool
    runtime_attested_immediately_before_solve: bool
    mesh_attested_immediately_before_solve: bool
    fea_solve_executed: bool
    numerical_verification: bool
    results_verified: bool
    ux_relative_error: float
    reaction_relative_error: float
    stress_relative_error: float
    industrial_validation: bool
    ansys_equivalence: bool

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _require_sha256(value: str, code: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise VerifiedResultsAdmissionError(code)
    return text


def _result_med_sha(bundle: ProfessionalEvidenceBundle) -> str:
    matches = [item for item in bundle.artifacts if item.role == "result_med"]
    if len(matches) != 1:
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_RESULT_MED_ROLE_INVALID")
    return _require_sha256(matches[0].sha256, "VERIFIED_RESULTS_RESULT_MED_HASH_INVALID")


def _validate_verified_solve(evidence: GenuineReferenceSolveEvidence) -> None:
    if evidence.returncode != 0:
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_SOLVER_EXIT_NOT_ZERO")
    if not evidence.message_diagnostic_ok or evidence.message_execution_exit_code not in (None, 0):
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_MESSAGE_DIAGNOSTIC_NOT_OK")
    for value, code in (
        (evidence.runtime_qualified, "VERIFIED_RESULTS_RUNTIME_NOT_QUALIFIED"),
        (evidence.runtime_attested_immediately_before_solve, "VERIFIED_RESULTS_RUNTIME_NOT_ATTESTED"),
        (evidence.mesh_attested_immediately_before_solve, "VERIFIED_RESULTS_MESH_NOT_ATTESTED"),
        (evidence.fea_solve_executed, "VERIFIED_RESULTS_SOLVE_NOT_EXECUTED"),
        (evidence.numerical_verification, "VERIFIED_RESULTS_NUMERICAL_VERIFICATION_MISSING"),
        (evidence.results_verified, "VERIFIED_RESULTS_RESULT_VERIFICATION_MISSING"),
    ):
        if value is not True:
            raise VerifiedResultsAdmissionError(code)
    for value, code in (
        (evidence.result_med_sha256, "VERIFIED_RESULTS_EVIDENCE_MED_HASH_INVALID"),
        (evidence.run_aster_sha256, "VERIFIED_RESULTS_RUN_ASTER_HASH_INVALID"),
        (evidence.config_sha256, "VERIFIED_RESULTS_CONFIG_HASH_INVALID"),
    ):
        _require_sha256(value, code)
    for value, code in (
        (evidence.ux_relative_error, "VERIFIED_RESULTS_UX_ERROR_INVALID"),
        (evidence.reaction_relative_error, "VERIFIED_RESULTS_REACTION_ERROR_INVALID"),
        (evidence.stress_relative_error, "VERIFIED_RESULTS_STRESS_ERROR_INVALID"),
    ):
        if not math.isfinite(float(value)) or float(value) < 0.0:
            raise VerifiedResultsAdmissionError(code)


def _validate_bundle_alignment(bundle: ProfessionalEvidenceBundle, evidence: GenuineReferenceSolveEvidence) -> None:
    if bundle.schema_version != "astermax.professional-evidence-bundle.v2":
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_BUNDLE_SCHEMA_UNSUPPORTED")
    if bundle.cad_length_unit != "mm" or bundle.solver_unit_system != "mm-N-MPa":
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_UNIT_CONTRACT_INVALID")
    for value, code in (
        (bundle.runtime_qualified, "VERIFIED_RESULTS_BUNDLE_RUNTIME_NOT_QUALIFIED"),
        (bundle.runtime_attested_immediately_before_solve, "VERIFIED_RESULTS_BUNDLE_RUNTIME_NOT_ATTESTED"),
        (bundle.mesh_attested_immediately_before_solve, "VERIFIED_RESULTS_BUNDLE_MESH_NOT_ATTESTED"),
        (bundle.fea_solve_executed, "VERIFIED_RESULTS_BUNDLE_SOLVE_NOT_EXECUTED"),
        (bundle.numerical_verification, "VERIFIED_RESULTS_BUNDLE_NUMERICAL_VERIFICATION_MISSING"),
        (bundle.results_verified, "VERIFIED_RESULTS_BUNDLE_RESULTS_NOT_VERIFIED"),
    ):
        if value is not True:
            raise VerifiedResultsAdmissionError(code)
    if bundle.industrial_validation is not False or bundle.ansys_equivalence is not False:
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_UNSUPPORTED_PROMOTION")

    pairs = (
        (bundle.engine_kind, evidence.engine_kind, "ENGINE"),
        (bundle.distribution, evidence.distribution, "DISTRIBUTION"),
        (bundle.detected_version, evidence.detected_version, "VERSION"),
        (bundle.run_aster_sha256.lower(), evidence.run_aster_sha256.lower(), "RUN_ASTER_HASH"),
        (bundle.config_sha256.lower(), evidence.config_sha256.lower(), "CONFIG_HASH"),
        (bundle.mesh_quality_report_sha256.lower(), evidence.mesh_quality_report_sha256.lower(), "MESH_REPORT_HASH"),
        (bundle.mesh_quality_artifact_sha256.lower(), evidence.mesh_quality_artifact_sha256.lower(), "MESH_ARTIFACT_HASH"),
        (bundle.reference_case_evidence_sha256.lower(), evidence.reference_case_evidence_sha256.lower(), "REFERENCE_CASE_HASH"),
    )
    for observed, expected, label in pairs:
        if observed != expected:
            raise VerifiedResultsAdmissionError(f"VERIFIED_RESULTS_BUNDLE_{label}_MISMATCH")

    if _result_med_sha(bundle) != evidence.result_med_sha256.lower():
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_BUNDLE_RESULT_MED_MISMATCH")
    for observed, expected, label in (
        (bundle.ux_relative_error, evidence.ux_relative_error, "UX_ERROR"),
        (bundle.reaction_relative_error, evidence.reaction_relative_error, "REACTION_ERROR"),
        (bundle.stress_relative_error, evidence.stress_relative_error, "STRESS_ERROR"),
    ):
        if not math.isclose(float(observed), float(expected), rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise VerifiedResultsAdmissionError(f"VERIFIED_RESULTS_BUNDLE_{label}_MISMATCH")


def build_verified_results_provenance_panel(
    scene: CaeSceneContract,
    evidence: GenuineReferenceSolveEvidence,
    bundle: ProfessionalEvidenceBundle,
) -> VerifiedResultsProvenancePanel:
    """Admit a Code_Aster scene to the professional results UI only with full provenance.

    This is a visualization admission gate, not a solver. It cannot manufacture or
    promote FEA evidence; all solver and numerical claims must already be true in
    genuine solve evidence and the replayable evidence bundle.
    """
    validate_cae_scene_contract(scene)
    _validate_verified_solve(evidence)
    _validate_bundle_alignment(bundle, evidence)

    expected_scene_solve_sha = genuine_solve_evidence_sha256(evidence)
    if scene.solve_evidence_sha256.lower() != expected_scene_solve_sha:
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_SCENE_SOLVE_EVIDENCE_MISMATCH")
    if scene.workspace_sha256.lower() != evidence.result_med_sha256.lower():
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_SCENE_RESULT_MED_MISMATCH")
    if scene.length_unit != "mm" or scene.stress_unit != "MPa":
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_SCENE_UNITS_INVALID")
    if scene.displacement_vector_mm is None:
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_NATIVE_DEPL_VECTOR_REQUIRED")
    if not scene.stress_representation.startswith("CODE_ASTER_SIEQ_NOEU:"):
        raise VerifiedResultsAdmissionError("VERIFIED_RESULTS_NATIVE_SIEQ_NOEU_REQUIRED")

    return VerifiedResultsProvenancePanel(
        admission_status="VERIFIED_CODE_ASTER_RESULTS_ADMITTED",
        engine_kind=evidence.engine_kind,
        distribution=evidence.distribution,
        detected_version=evidence.detected_version,
        cad_length_unit="mm",
        solver_unit_system="mm-N-MPa",
        displacement_field="DEPL_NOEU",
        stress_field="SIEQ_NOEU",
        stress_field_location="NOEU",
        stress_display_note="SIEQ_NOEU is solver output; rendered surface triangles use node-average display interpolation only.",
        result_med_sha256=evidence.result_med_sha256,
        solve_evidence_sha256=expected_scene_solve_sha,
        evidence_bundle_manifest_sha256=_require_sha256(bundle.manifest_sha256, "VERIFIED_RESULTS_BUNDLE_MANIFEST_HASH_INVALID"),
        run_aster_sha256=evidence.run_aster_sha256,
        config_sha256=evidence.config_sha256,
        runtime_qualified=True,
        runtime_attested_immediately_before_solve=True,
        mesh_attested_immediately_before_solve=True,
        fea_solve_executed=True,
        numerical_verification=True,
        results_verified=True,
        ux_relative_error=float(evidence.ux_relative_error),
        reaction_relative_error=float(evidence.reaction_relative_error),
        stress_relative_error=float(evidence.stress_relative_error),
        industrial_validation=False,
        ansys_equivalence=False,
    )
