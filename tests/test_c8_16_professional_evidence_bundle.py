from hashlib import sha256
import json
from pathlib import Path

import pytest

from astermax.code_aster_reference_run import GenuineReferenceSolveEvidence
from astermax.credibility import canonical_sha256
from astermax.professional_evidence_bundle import (
    ProfessionalEvidenceBundleError,
    create_professional_evidence_bundle,
    verify_professional_evidence_bundle,
)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def make_case(root: Path):
    files = {
        "astermax.export": b"F comm astermax.comm D 1\nF mess astermax.mess R 6\n",
        "astermax.comm": b"DEBUT()\nFIN()\n",
        "astermax.med": b"MED-input-witness",
        "astermax_result.med": b"MED-result-process-double",
        "astermax.mess": b"EXECUTION_CODE_ASTER_EXIT_12345=0\n<INFO> diagnostic : OK\n",
        "reference_displacement.table": b"MOYENNE;\n2.5E-02;\n",
        "reference_reaction.table": b"RESULT_X;\n-1.0E+04;\n",
        "reference_stress.table": b"MOYENNE;\n5.0E+01;\n",
        "reference.step": b"ISO-10303-21;\n/* structure-only witness, not a production CAD model */\nEND-ISO-10303-21;\n",
    }
    for name, data in files.items():
        (root / name).write_bytes(data)

    quality_core = {
        "solver_gate_passed": True,
        "all_sampled_jacobians_positive": True,
        "length_unit": "mm",
        "ansys_metric_equivalence": False,
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
    }
    quality = dict(quality_core, report_sha256=canonical_sha256(quality_core))
    quality_path = root / "reference_mesh_quality.json"
    quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")

    case = {
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "mesh_quality_gate_passed": True,
        "med_sha256": _sha(root / "astermax.med"),
        "mesh_quality_artifact_sha256": _sha(quality_path),
        "mesh_quality_report_sha256": quality["report_sha256"],
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
    }
    (root / "reference_case_evidence.json").write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")


def evidence(root: Path, **overrides):
    quality = json.loads((root / "reference_mesh_quality.json").read_text(encoding="utf-8"))
    values = dict(
        engine_kind="CODE_ASTER_WSL2_WINDOWS_HOST",
        distribution="smeca-2024",
        export_sha256=_sha(root / "astermax.export"),
        command_sha256=_sha(root / "astermax.comm"),
        input_med_sha256=_sha(root / "astermax.med"),
        mesh_quality_report_sha256=quality["report_sha256"],
        mesh_quality_artifact_sha256=_sha(root / "reference_mesh_quality.json"),
        reference_case_evidence_sha256=_sha(root / "reference_case_evidence.json"),
        result_med_sha256=_sha(root / "astermax_result.med"),
        message_sha256=_sha(root / "astermax.mess"),
        displacement_table_sha256=_sha(root / "reference_displacement.table"),
        reaction_table_sha256=_sha(root / "reference_reaction.table"),
        stress_table_sha256=_sha(root / "reference_stress.table"),
        solver_stdout_sha256="d" * 64,
        returncode=0,
        message_diagnostic_ok=True,
        message_execution_exit_code=0,
        runtime_qualified=True,
        runtime_attested_immediately_before_solve=True,
        mesh_attested_immediately_before_solve=True,
        run_aster_sha256="a" * 64,
        config_sha256="b" * 64,
        detected_version="17.2.1",
        fea_solve_executed=True,
        numerical_verification=True,
        results_verified=True,
        ux_relative_error=0.0,
        reaction_relative_error=0.0,
        stress_relative_error=0.0,
    )
    values.update(overrides)
    return GenuineReferenceSolveEvidence(**values)


def test_create_and_replay_verify_bundle(tmp_path: Path):
    """Uses file witnesses only; this test is not Code_Aster simulation evidence."""
    make_case(tmp_path)
    manifest = tmp_path / "professional_evidence.json"
    bundle = create_professional_evidence_bundle(tmp_path, evidence(tmp_path), manifest, source_step=tmp_path / "reference.step")
    assert bundle.schema_version == "astermax.professional-evidence-bundle.v2"
    assert bundle.cad_length_unit == "mm"
    assert bundle.solver_unit_system == "mm-N-MPa"
    assert bundle.runtime_attested_immediately_before_solve is True
    assert bundle.mesh_attested_immediately_before_solve is True
    assert bundle.fea_solve_executed is True
    assert bundle.numerical_verification is True
    assert bundle.results_verified is True
    assert bundle.industrial_validation is False
    assert bundle.ansys_equivalence is False
    assert {item.role for item in bundle.artifacts} >= {
        "source_step", "input_med", "mesh_quality", "reference_case_evidence", "result_med", "solver_message"
    }
    replayed = verify_professional_evidence_bundle(manifest, tmp_path)
    assert replayed.manifest_sha256 == bundle.manifest_sha256
    assert replayed.artifacts == bundle.artifacts


def test_unverified_solve_cannot_be_packaged(tmp_path: Path):
    make_case(tmp_path)
    with pytest.raises(ProfessionalEvidenceBundleError, match="SOLVE_NOT_EXECUTED"):
        create_professional_evidence_bundle(tmp_path, evidence(tmp_path, fea_solve_executed=False, numerical_verification=False, results_verified=False), tmp_path / "bundle.json")


def test_unattested_mesh_cannot_be_packaged(tmp_path: Path):
    make_case(tmp_path)
    with pytest.raises(ProfessionalEvidenceBundleError, match="MESH_NOT_ATTESTED"):
        create_professional_evidence_bundle(tmp_path, evidence(tmp_path, mesh_attested_immediately_before_solve=False), tmp_path / "bundle.json")


def test_mesh_quality_hash_mismatch_fails_closed(tmp_path: Path):
    make_case(tmp_path)
    ev = evidence(tmp_path)
    (tmp_path / "reference_mesh_quality.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ProfessionalEvidenceBundleError, match="HASH_MISMATCH:mesh_quality"):
        create_professional_evidence_bundle(tmp_path, ev, tmp_path / "bundle.json")


def test_reference_case_hash_mismatch_fails_closed(tmp_path: Path):
    make_case(tmp_path)
    ev = evidence(tmp_path)
    (tmp_path / "reference_case_evidence.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ProfessionalEvidenceBundleError, match="HASH_MISMATCH:reference_case_evidence"):
        create_professional_evidence_bundle(tmp_path, ev, tmp_path / "bundle.json")


def test_artifact_hash_mismatch_fails_closed(tmp_path: Path):
    make_case(tmp_path)
    ev = evidence(tmp_path)
    (tmp_path / "astermax_result.med").write_bytes(b"tampered-after-evidence")
    with pytest.raises(ProfessionalEvidenceBundleError, match="HASH_MISMATCH:result_med"):
        create_professional_evidence_bundle(tmp_path, ev, tmp_path / "bundle.json")


def test_replay_detects_post_bundle_mesh_tampering(tmp_path: Path):
    make_case(tmp_path)
    manifest = tmp_path / "bundle.json"
    create_professional_evidence_bundle(tmp_path, evidence(tmp_path), manifest)
    (tmp_path / "reference_mesh_quality.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ProfessionalEvidenceBundleError, match="ARTIFACT_TAMPERED:mesh_quality"):
        verify_professional_evidence_bundle(manifest, tmp_path)


def test_replay_detects_post_bundle_tampering(tmp_path: Path):
    make_case(tmp_path)
    manifest = tmp_path / "bundle.json"
    create_professional_evidence_bundle(tmp_path, evidence(tmp_path), manifest)
    (tmp_path / "reference_stress.table").write_bytes(b"changed")
    with pytest.raises(ProfessionalEvidenceBundleError, match="ARTIFACT_TAMPERED:stress_table"):
        verify_professional_evidence_bundle(manifest, tmp_path)


def test_manifest_claim_promotion_is_detected(tmp_path: Path):
    make_case(tmp_path)
    manifest = tmp_path / "bundle.json"
    create_professional_evidence_bundle(tmp_path, evidence(tmp_path), manifest)
    text = manifest.read_text(encoding="utf-8").replace('"ansys_equivalence": false', '"ansys_equivalence": true')
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(ProfessionalEvidenceBundleError, match="MANIFEST_TAMPERED"):
        verify_professional_evidence_bundle(manifest, tmp_path)


def test_unit_contract_is_fail_closed(tmp_path: Path):
    make_case(tmp_path)
    with pytest.raises(ProfessionalEvidenceBundleError, match="CAD_UNIT_MUST_BE_MM"):
        create_professional_evidence_bundle(tmp_path, evidence(tmp_path), tmp_path / "bundle.json", cad_length_unit="m")


def test_missing_source_step_is_rejected_when_requested(tmp_path: Path):
    make_case(tmp_path)
    with pytest.raises(ProfessionalEvidenceBundleError, match="SOURCE_STEP_MISSING"):
        create_professional_evidence_bundle(tmp_path, evidence(tmp_path), tmp_path / "bundle.json", source_step=tmp_path / "missing.step")
