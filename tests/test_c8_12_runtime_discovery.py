from __future__ import annotations

import subprocess

import pytest

from astermax.code_aster_runtime_discovery import (
    CodeAsterRuntimeDiscoveryError,
    discover_wsl_code_aster_runtimes,
)


def cp(command: list[str], code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, code, out, err)


def test_discovers_identity_confirmed_run_aster_without_promoting_solver_claims() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        assert timeout_s > 0
        if command[:3] == ["wsl.exe", "--list", "--quiet"]:
            return cp(command, out="Ubuntu-24.04\n")
        if command[-2:] == ["/opt/aster/bin/run_aster", "--help"]:
            return cp(command, out="usage: run_aster export-file\nCode_Aster launcher")
        if "command -v run_aster" in command[-1]:
            return cp(command, out="/opt/aster/bin/run_aster\n")
        raise AssertionError(command)

    evidence = discover_wsl_code_aster_runtimes(runner=runner)
    assert evidence.discovery_complete is True
    assert evidence.distributions == ("Ubuntu-24.04",)
    assert len(evidence.candidates) == 1
    assert evidence.candidates[0].identity_confirmed is True
    assert evidence.candidates[0].run_aster_linux == "/opt/aster/bin/run_aster"
    assert evidence.blocker == "RUNTIME_REQUIRES_QUALIFICATION"
    assert evidence.qualified_runtime_available is False
    assert evidence.fea_solve_executed is False
    assert evidence.numerical_verification is False
    assert evidence.results_verified is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False


def test_no_distribution_is_explicit_blocker() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        return cp(command, out="")

    evidence = discover_wsl_code_aster_runtimes(runner=runner)
    assert evidence.distributions == ()
    assert evidence.candidates == ()
    assert evidence.blocker == "NO_WSL_DISTRIBUTION"


def test_distribution_without_run_aster_is_explicit_blocker() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["wsl.exe", "--list", "--quiet"]:
            return cp(command, out="Ubuntu\n")
        return cp(command, code=1, out="")

    evidence = discover_wsl_code_aster_runtimes(runner=runner)
    assert evidence.distributions == ("Ubuntu",)
    assert evidence.candidates == ()
    assert evidence.blocker == "RUN_ASTER_NOT_DISCOVERED"


def test_unconfirmed_identity_is_not_a_candidate() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["wsl.exe", "--list", "--quiet"]:
            return cp(command, out="Ubuntu\n")
        if "command -v run_aster" in command[-1]:
            return cp(command, out="/tmp/run_aster\n")
        return cp(command, out="generic helper")

    evidence = discover_wsl_code_aster_runtimes(runner=runner)
    assert evidence.candidates == ()
    assert evidence.blocker == "RUN_ASTER_NOT_DISCOVERED"


def test_invalid_distribution_fails_closed() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        return cp(command, out="bad distro name!\n")

    with pytest.raises(CodeAsterRuntimeDiscoveryError, match="DISTRO_INVALID"):
        discover_wsl_code_aster_runtimes(runner=runner)


def test_invalid_discovered_path_fails_closed() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["wsl.exe", "--list", "--quiet"]:
            return cp(command, out="Ubuntu\n")
        return cp(command, out="relative/run_aster\n")

    with pytest.raises(CodeAsterRuntimeDiscoveryError, match="PATH_INVALID"):
        discover_wsl_code_aster_runtimes(runner=runner)


def test_wsl_list_failure_fails_closed() -> None:
    def runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        return cp(command, code=1, err="WSL unavailable")

    with pytest.raises(CodeAsterRuntimeDiscoveryError, match="WSL_LIST_FAILED"):
        discover_wsl_code_aster_runtimes(runner=runner)
