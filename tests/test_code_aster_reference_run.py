from pathlib import Path
import subprocess

import pytest

from astermax.code_aster_mesh_attestation import MeshChainOfCustodyEvidence
from astermax.code_aster_reference_harness import UniaxialPrismSpec
from astermax.code_aster_reference_run import (
    CodeAsterReferenceRunError,
    execute_and_verify_reference_wsl,
)
from astermax.code_aster_runtime_qualification import QualifiedCodeAsterRuntime, RuntimeAttestationEvidence
from astermax.code_aster_wsl_runtime import CodeAsterWslRuntime


HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64


def runtime():
    return CodeAsterWslRuntime("smeca-2024", "/opt/smeca/bin/run_aster")


def qualification(*, distro="smeca-2024"):
    return QualifiedCodeAsterRuntime(
        engine_kind="CODE_ASTER_WSL2_WINDOWS_HOST",
        distribution=distro,
        run_aster_linux="/opt/smeca/bin/run_aster",
        run_aster_sha256=HEX_A,
        config_linux="/opt/smeca/share/aster/config.yaml",
        config_sha256=HEX_B,
        kernel_release="6.6.87.2-microsoft-standard-WSL2",
        machine="x86_64",
        version_text_sha256=HEX_C,
        detected_version="17.2.1",
        identity_probe_sha256=HEX_C,
    )


def attestation():
    return RuntimeAttestationEvidence(
        engine_kind="CODE_ASTER_WSL2_WINDOWS_HOST",
        distribution="smeca-2024",
        run_aster_linux="/opt/smeca/bin/run_aster",
        run_aster_sha256=HEX_A,
        config_linux="/opt/smeca/share/aster/config.yaml",
        config_sha256=HEX_B,
        kernel_release="6.6.87.2-microsoft-standard-WSL2",
        machine="x86_64",
        identity_probe_sha256=HEX_C,
    )


def mesh_attestation(root: Path):
    from hashlib import sha256

    return MeshChainOfCustodyEvidence(
        med_sha256=sha256((root / "astermax.med").read_bytes()).hexdigest(),
        quality_report_sha256=HEX_D,
        quality_artifact_sha256=HEX_C,
        reference_case_evidence_sha256=HEX_B,
        mesh_quality_gate_passed=True,
        all_sampled_jacobians_positive=True,
        length_unit="mm",
        solver_unit_system="mm-N-MPa",
        mesh_attested_immediately_before_solve=True,
        fea_solve_executed=False,
        numerical_verification=False,
        results_verified=False,
        industrial_validation=False,
        ansys_equivalence=False,
    )


def make_inputs(root: Path):
    (root / "astermax.export").write_text("F comm astermax.comm D 1\nF mess astermax.mess R 6\n", encoding="utf-8")
    (root / "astermax.comm").write_text("DEBUT()\nFIN()\n", encoding="utf-8")
    (root / "astermax.med").write_bytes(b"MED-input-witness")


def install_attestation_double(monkeypatch):
    monkeypatch.setattr("astermax.code_aster_reference_run.attest_qualified_wsl_code_aster_runtime", lambda *a, **k: attestation())


def install_mesh_attestation_double(monkeypatch, root: Path):
    monkeypatch.setattr("astermax.code_aster_reference_run.attest_reference_mesh_before_solve", lambda *a, **k: mesh_attestation(root))


def test_runtime_qualification_mismatch_fails_before_io(tmp_path: Path):
    with pytest.raises(CodeAsterReferenceRunError, match="RUNTIME_DISTRO_MISMATCH"):
        execute_and_verify_reference_wsl(runtime(), UniaxialPrismSpec(), tmp_path, qualification=qualification(distro="wrong-distro"))


def test_stale_output_is_rejected_before_any_runtime_call(tmp_path: Path, monkeypatch):
    make_inputs(tmp_path)
    (tmp_path / "astermax_result.med").write_bytes(b"old")
    monkeypatch.setattr("astermax.code_aster_reference_run.attest_qualified_wsl_code_aster_runtime", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not attest")))
    with pytest.raises(CodeAsterReferenceRunError, match="STALE_OUTPUT"):
        execute_and_verify_reference_wsl(runtime(), UniaxialPrismSpec(), tmp_path, qualification=qualification())


def test_message_binding_is_required_before_runtime_call(tmp_path: Path, monkeypatch):
    make_inputs(tmp_path)
    (tmp_path / "astermax.export").write_text("F comm astermax.comm D 1\n", encoding="utf-8")
    monkeypatch.setattr("astermax.code_aster_reference_run.attest_qualified_wsl_code_aster_runtime", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not attest")))
    with pytest.raises(CodeAsterReferenceRunError, match="MESSAGE_BINDING_MISSING"):
        execute_and_verify_reference_wsl(runtime(), UniaxialPrismSpec(), tmp_path, qualification=qualification())


def test_nonzero_solver_exit_fails_closed(tmp_path: Path, monkeypatch):
    make_inputs(tmp_path)
    install_mesh_attestation_double(monkeypatch, tmp_path)
    install_attestation_double(monkeypatch)
    monkeypatch.setattr("astermax.code_aster_reference_run.windows_path_to_wsl", lambda *a, **k: "/mnt/c/case")
    monkeypatch.setattr("astermax.code_aster_reference_run._run", lambda *a, **k: subprocess.CompletedProcess(a[0], 7, stdout="", stderr="solver failed"))
    with pytest.raises(CodeAsterReferenceRunError, match="NONZERO_EXIT:7"):
        execute_and_verify_reference_wsl(runtime(), UniaxialPrismSpec(), tmp_path, qualification=qualification())


def test_process_double_only_exercises_gate_semantics(tmp_path: Path, monkeypatch):
    """Not Code_Aster evidence: verifies software wiring with synthetic test data only."""
    make_inputs(tmp_path)
    spec = UniaxialPrismSpec(young_mpa=200000.0, poisson=0.0, total_force_n=10000.0)
    install_mesh_attestation_double(monkeypatch, tmp_path)
    install_attestation_double(monkeypatch)
    monkeypatch.setattr("astermax.code_aster_reference_run.windows_path_to_wsl", lambda *a, **k: "/mnt/c/case")

    def fake_run(command, *, timeout_s):
        (tmp_path / "astermax_result.med").write_bytes(b"PROCESS-DOUBLE-NOT-SOLVER-EVIDENCE")
        (tmp_path / "astermax.mess").write_text("EXECUTION_CODE_ASTER_EXIT_12345=0\n<INFO> Code_Aster run ended, diagnostic : OK\n", encoding="utf-8")
        (tmp_path / "reference_displacement.table").write_text("MOYENNE;\n2.500000000000E-02;\n", encoding="utf-8")
        (tmp_path / "reference_reaction.table").write_text("RESULT_X;\n-1.000000000000E+04;\n", encoding="utf-8")
        (tmp_path / "reference_stress.table").write_text("MOYENNE;\n5.000000000000E+01;\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="process double", stderr="")

    monkeypatch.setattr("astermax.code_aster_reference_run._run", fake_run)
    ev = execute_and_verify_reference_wsl(runtime(), spec, tmp_path, qualification=qualification())
    assert ev.runtime_qualified is True
    assert ev.runtime_attested_immediately_before_solve is True
    assert ev.mesh_attested_immediately_before_solve is True
    assert ev.run_aster_sha256 == HEX_A
    assert ev.config_sha256 == HEX_B
    assert ev.message_diagnostic_ok is True
    assert ev.message_execution_exit_code == 0
    assert ev.fea_solve_executed is True
    assert ev.numerical_verification is True
    assert ev.results_verified is True
    assert ev.ux_relative_error == 0.0
    assert ev.reaction_relative_error == 0.0
    assert ev.stress_relative_error == 0.0
