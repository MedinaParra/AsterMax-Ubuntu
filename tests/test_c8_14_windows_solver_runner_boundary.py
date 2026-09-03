from astermax.code_aster_runtime_discovery import RuntimeCandidate, RuntimeDiscoveryEvidence
from astermax.code_aster_wsl_runtime import ENGINE_KIND
from astermax.windows_solver_runner_boundary import classify_windows_solver_runner


def evidence(*, distros=(), candidates=()):
    return RuntimeDiscoveryEvidence(
        engine_kind=ENGINE_KIND,
        host_os="Windows",
        solver_os="Linux/WSL2",
        distributions=tuple(distros),
        candidates=tuple(candidates),
        discovery_complete=True,
    )


def candidate():
    return RuntimeCandidate(
        distribution="Ubuntu-24.04",
        run_aster_linux="/opt/aster/bin/run_aster",
        identity_confirmed=True,
        identity_sha256="a" * 64,
    )


def test_github_hosted_no_wsl_is_explicit_infrastructure_blocker():
    result = classify_windows_solver_runner(
        evidence(),
        environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"},
    )
    assert result.blocker == "GITHUB_HOSTED_WINDOWS_NO_WSL_DISTRIBUTION"
    assert result.self_hosted_runner_required is True
    assert result.next_gate == "PROVISION_SELF_HOSTED_WINDOWS_WSL2_CODE_ASTER"
    assert result.fea_solve_executed is False
    assert result.results_verified is False


def test_self_hosted_without_wsl_requests_wsl_provisioning_not_solver_claim():
    result = classify_windows_solver_runner(
        evidence(),
        environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
    )
    assert result.blocker == "NO_WSL_DISTRIBUTION"
    assert result.next_gate == "PROVISION_WSL2_DISTRIBUTION"
    assert result.self_hosted_runner_required is False


def test_wsl_without_run_aster_requests_solver_installation():
    result = classify_windows_solver_runner(
        evidence(distros=("Ubuntu-24.04",)),
        environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
    )
    assert result.blocker == "RUN_ASTER_NOT_DISCOVERED"
    assert result.next_gate == "INSTALL_OR_LOCATE_CODE_ASTER_RUN_ASTER"
    assert result.code_aster_candidates_present is False


def test_identity_confirmed_candidate_advances_only_to_runtime_qualification():
    result = classify_windows_solver_runner(
        evidence(distros=("Ubuntu-24.04",), candidates=(candidate(),)),
        environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
    )
    assert result.blocker is None
    assert result.next_gate == "QUALIFY_DISCOVERED_CODE_ASTER_RUNTIME"
    assert result.code_aster_candidates_present is True
    assert result.fea_solve_executed is False
    assert result.numerical_verification is False
    assert result.results_verified is False
    assert result.industrial_validation is False
    assert result.ansys_equivalence is False


def test_unknown_local_environment_stays_fail_closed():
    result = classify_windows_solver_runner(evidence(), environ={})
    assert result.runner_environment == "unknown"
    assert result.blocker == "NO_WSL_DISTRIBUTION"
    assert result.fea_solve_executed is False
