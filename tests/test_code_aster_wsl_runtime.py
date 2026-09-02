from pathlib import Path
import subprocess

import pytest

from astermax.code_aster_wsl_runtime import (
    CodeAsterWslError,
    CodeAsterWslRuntime,
    build_wsl_run_aster_command,
    probe_wsl_runtime,
    windows_path_to_wsl,
)


def runtime():
    return CodeAsterWslRuntime(
        distribution="smeca-2024",
        run_aster_linux="/opt/salome_meca/tools/Code_aster_stable/bin/run_aster",
    )


def test_command_contract_is_explicitly_windows_hosted_wsl2():
    rt = runtime()
    ev = rt.as_evidence()
    assert ev["engine_kind"] == "CODE_ASTER_WSL2_WINDOWS_HOST"
    assert ev["host_os"] == "Windows"
    assert ev["solver_os"] == "Linux/WSL2"
    assert ev["fea_solve_executed"] is False
    command = build_wsl_run_aster_command(rt, workdir_linux="/mnt/c/work/case", export_filename="astermax.export")
    assert command == [
        "wsl.exe", "--distribution", "smeca-2024", "--cd", "/mnt/c/work/case",
        "--", rt.run_aster_linux, "astermax.export",
    ]


def test_invalid_distribution_and_launcher_fail_closed():
    with pytest.raises(CodeAsterWslError, match="DISTRO_INVALID"):
        CodeAsterWslRuntime("bad distro;rm", "/opt/run_aster").validate()
    with pytest.raises(CodeAsterWslError, match="PATH_INVALID"):
        CodeAsterWslRuntime("smeca-2024", "run_aster;echo bad").validate()


def test_probe_requires_installed_distro_and_solver_identity(monkeypatch):
    calls = []

    def fake_run(command, *, timeout_s):
        calls.append(command)
        if command[:3] == ["wsl.exe", "--list", "--quiet"]:
            return subprocess.CompletedProcess(command, 0, stdout="smeca-2024\nUbuntu\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="usage: run_aster study.export\n", stderr="")

    monkeypatch.setattr("astermax.code_aster_wsl_runtime._run", fake_run)
    ev = probe_wsl_runtime(runtime())
    assert ev["wsl_distribution_verified"] is True
    assert ev["run_aster_identity_confirmed"] is True
    assert len(ev["probe_sha256"]) == 64
    assert ev["fea_solve_executed"] is False
    assert calls[1][0] == "wsl.exe"


def test_probe_rejects_unrelated_successful_binary(monkeypatch):
    def fake_run(command, *, timeout_s):
        if command[:3] == ["wsl.exe", "--list", "--quiet"]:
            return subprocess.CompletedProcess(command, 0, stdout="smeca-2024\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="generic program help\n", stderr="")

    monkeypatch.setattr("astermax.code_aster_wsl_runtime._run", fake_run)
    with pytest.raises(CodeAsterWslError, match="IDENTITY_UNCONFIRMED"):
        probe_wsl_runtime(runtime())


def test_windows_path_translation_must_return_absolute_linux_path(monkeypatch, tmp_path: Path):
    def fake_run(command, *, timeout_s):
        return subprocess.CompletedProcess(command, 0, stdout="/mnt/c/case\n", stderr="")

    monkeypatch.setattr("astermax.code_aster_wsl_runtime._run", fake_run)
    assert windows_path_to_wsl(runtime(), tmp_path) == "/mnt/c/case"


def test_study_command_rejects_non_export_or_relative_linux_workdir():
    with pytest.raises(CodeAsterWslError, match="STUDY_PATH_INVALID"):
        build_wsl_run_aster_command(runtime(), workdir_linux="relative", export_filename="astermax.export")
    with pytest.raises(CodeAsterWslError, match="STUDY_PATH_INVALID"):
        build_wsl_run_aster_command(runtime(), workdir_linux="/mnt/c/case", export_filename="astermax.comm")
