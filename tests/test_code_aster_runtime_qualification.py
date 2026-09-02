import subprocess

import pytest

from astermax.code_aster_runtime_qualification import (
    CodeAsterRuntimeQualificationError,
    _detect_version,
    qualify_wsl_code_aster_runtime,
)
from astermax.code_aster_wsl_runtime import CodeAsterWslRuntime


RUNTIME = CodeAsterWslRuntime("smeca-2024", "/opt/smeca/bin/run_aster")
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def test_version_detection_is_conservative():
    assert _detect_version("Code_Aster version 17.2.1") == "17.2.1"
    assert _detect_version("unrelated launcher text") is None


def test_invalid_config_path_fails_before_subprocess(monkeypatch):
    monkeypatch.setattr(
        "astermax.code_aster_runtime_qualification.probe_wsl_runtime",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not probe")),
    )
    with pytest.raises(CodeAsterRuntimeQualificationError, match="CONFIG_PATH_INVALID"):
        qualify_wsl_code_aster_runtime(RUNTIME, config_linux="relative/config.yaml")


def test_qualified_runtime_fingerprints_launcher_config_and_platform(monkeypatch):
    monkeypatch.setattr(
        "astermax.code_aster_runtime_qualification.probe_wsl_runtime",
        lambda *a, **k: {"probe_sha256": HEX_C},
    )

    def fake_wsl(runtime, *args, timeout_s=30.0):
        command = list(args)
        if command[:2] == ["test", "-f"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["sha256sum", "--"]:
            digest = HEX_A if command[-1].endswith("run_aster") else HEX_B
            return subprocess.CompletedProcess(command, 0, stdout=f"{digest}  {command[-1]}\n", stderr="")
        if command == ["uname", "-srmo"]:
            return subprocess.CompletedProcess(command, 0, stdout="Linux 6.6.87.2-microsoft-standard-WSL2 x86_64 GNU/Linux\n", stderr="")
        if command == ["uname", "-m"]:
            return subprocess.CompletedProcess(command, 0, stdout="x86_64\n", stderr="")
        if command[-1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="Code_Aster version 17.2.1\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("astermax.code_aster_runtime_qualification._wsl", fake_wsl)
    ev = qualify_wsl_code_aster_runtime(
        RUNTIME,
        config_linux="/opt/smeca/share/aster/config.yaml",
    )
    assert ev.runtime_qualified is True
    assert ev.run_aster_sha256 == HEX_A
    assert ev.config_sha256 == HEX_B
    assert ev.identity_probe_sha256 == HEX_C
    assert ev.detected_version == "17.2.1"
    assert "microsoft-standard-WSL2" in ev.kernel_release
    assert ev.machine == "x86_64"
    assert ev.fea_solve_executed is False
    assert ev.results_verified is False


def test_missing_config_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "astermax.code_aster_runtime_qualification.probe_wsl_runtime",
        lambda *a, **k: {"probe_sha256": HEX_C},
    )

    def fake_wsl(runtime, *args, timeout_s=30.0):
        command = list(args)
        if command == ["test", "-f", "/opt/smeca/bin/run_aster"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["test", "-f", "/opt/smeca/share/aster/config.yaml"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("astermax.code_aster_runtime_qualification._wsl", fake_wsl)
    with pytest.raises(CodeAsterRuntimeQualificationError, match="CONFIG_NOT_FOUND"):
        qualify_wsl_code_aster_runtime(RUNTIME, config_linux="/opt/smeca/share/aster/config.yaml")


def test_malformed_sha256_output_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "astermax.code_aster_runtime_qualification.probe_wsl_runtime",
        lambda *a, **k: {"probe_sha256": HEX_C},
    )

    def fake_wsl(runtime, *args, timeout_s=30.0):
        command = list(args)
        if command[:2] == ["test", "-f"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["sha256sum", "--"]:
            return subprocess.CompletedProcess(command, 0, stdout="not-a-hash file\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("astermax.code_aster_runtime_qualification._wsl", fake_wsl)
    with pytest.raises(CodeAsterRuntimeQualificationError, match="HASH_INVALID"):
        qualify_wsl_code_aster_runtime(RUNTIME, config_linux="/opt/smeca/share/aster/config.yaml")
