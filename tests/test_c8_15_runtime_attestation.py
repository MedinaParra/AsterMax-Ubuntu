import subprocess

import pytest

from astermax.code_aster_runtime_qualification import (
    CodeAsterRuntimeQualificationError,
    QualifiedCodeAsterRuntime,
    attest_qualified_wsl_code_aster_runtime,
)
from astermax.code_aster_wsl_runtime import CodeAsterWslRuntime


RUNTIME = CodeAsterWslRuntime("smeca-2024", "/opt/smeca/bin/run_aster")
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def qualification(**changes):
    values = dict(
        engine_kind=RUNTIME.engine_kind,
        distribution=RUNTIME.distribution,
        run_aster_linux=RUNTIME.run_aster_linux,
        run_aster_sha256=A,
        config_linux="/opt/smeca/share/aster/config.yaml",
        config_sha256=B,
        kernel_release="6.6.87.2-microsoft-standard-WSL2",
        machine="x86_64",
        version_text_sha256=D,
        detected_version="17.2.1",
        identity_probe_sha256=C,
    )
    values.update(changes)
    return QualifiedCodeAsterRuntime(**values)


def install_live_runtime(monkeypatch, *, launcher_sha=A, config_sha=B, identity_sha=C, kernel=None, machine="x86_64"):
    monkeypatch.setattr(
        "astermax.code_aster_runtime_qualification.probe_wsl_runtime",
        lambda *a, **k: {"probe_sha256": identity_sha},
    )

    def fake_wsl(runtime, *args, timeout_s=30.0):
        cmd = list(args)
        if cmd[:2] == ["test", "-f"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["sha256sum", "--"]:
            digest = launcher_sha if cmd[-1].endswith("run_aster") else config_sha
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{digest}  {cmd[-1]}\n", stderr="")
        if cmd == ["uname", "-srmo"]:
            release = kernel or "6.6.87.2-microsoft-standard-WSL2"
            return subprocess.CompletedProcess(cmd, 0, stdout=f"Linux {release} x86_64 GNU/Linux\n", stderr="")
        if cmd == ["uname", "-m"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{machine}\n", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr("astermax.code_aster_runtime_qualification._wsl", fake_wsl)


def test_attestation_rechecks_runtime_and_does_not_claim_fea(monkeypatch):
    install_live_runtime(monkeypatch)
    evidence = attest_qualified_wsl_code_aster_runtime(RUNTIME, qualification())
    assert evidence.attestation_valid is True
    assert evidence.run_aster_sha256 == A
    assert evidence.config_sha256 == B
    assert evidence.fea_solve_executed is False
    assert evidence.results_verified is False


def test_launcher_mutation_after_qualification_fails_closed(monkeypatch):
    install_live_runtime(monkeypatch, launcher_sha=D)
    with pytest.raises(CodeAsterRuntimeQualificationError, match="ATTESTATION_LAUNCHER_HASH_MISMATCH"):
        attest_qualified_wsl_code_aster_runtime(RUNTIME, qualification())


def test_config_mutation_after_qualification_fails_closed(monkeypatch):
    install_live_runtime(monkeypatch, config_sha=D)
    with pytest.raises(CodeAsterRuntimeQualificationError, match="ATTESTATION_CONFIG_HASH_MISMATCH"):
        attest_qualified_wsl_code_aster_runtime(RUNTIME, qualification())


def test_identity_change_after_qualification_fails_closed(monkeypatch):
    install_live_runtime(monkeypatch, identity_sha=D)
    with pytest.raises(CodeAsterRuntimeQualificationError, match="ATTESTATION_IDENTITY_MISMATCH"):
        attest_qualified_wsl_code_aster_runtime(RUNTIME, qualification())


def test_kernel_change_after_qualification_requires_requalification(monkeypatch):
    install_live_runtime(monkeypatch, kernel="6.7.0-microsoft-standard-WSL2")
    with pytest.raises(CodeAsterRuntimeQualificationError, match="ATTESTATION_KERNEL_MISMATCH"):
        attest_qualified_wsl_code_aster_runtime(RUNTIME, qualification())
