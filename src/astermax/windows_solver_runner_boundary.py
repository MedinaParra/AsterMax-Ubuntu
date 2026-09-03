from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from .code_aster_runtime_discovery import RuntimeDiscoveryEvidence


@dataclass(frozen=True)
class WindowsSolverRunnerBoundary:
    runner_environment: str
    github_actions: bool
    wsl_distributions_present: bool
    code_aster_candidates_present: bool
    hosted_runner_supported_for_genuine_solve: bool
    self_hosted_runner_required: bool
    next_gate: str
    blocker: str | None
    fea_solve_executed: bool = False
    numerical_verification: bool = False
    results_verified: bool = False
    industrial_validation: bool = False
    ansys_equivalence: bool = False

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def classify_windows_solver_runner(
    discovery: RuntimeDiscoveryEvidence,
    *,
    environ: Mapping[str, str] | None = None,
) -> WindowsSolverRunnerBoundary:
    """Separate CI-runner capability from Code_Aster runtime qualification.

    A GitHub-hosted Windows runner with no WSL distribution is an infrastructure
    blocker, not a solver failure. A self-hosted runner is still not trusted merely
    because it exists: it must expose an identity-confirmed run_aster candidate and
    then pass the existing immutable runtime qualification gate.
    """
    env = environ if environ is not None else os.environ
    runner_environment = (env.get("RUNNER_ENVIRONMENT") or "unknown").strip().lower()
    github_actions = (env.get("GITHUB_ACTIONS") or "").strip().lower() == "true"
    is_github_hosted = runner_environment == "github-hosted"
    is_self_hosted = runner_environment == "self-hosted"
    has_wsl = bool(discovery.distributions)
    has_candidate = bool(discovery.candidates)

    if is_github_hosted and not has_wsl:
        return WindowsSolverRunnerBoundary(
            runner_environment=runner_environment,
            github_actions=github_actions,
            wsl_distributions_present=False,
            code_aster_candidates_present=False,
            hosted_runner_supported_for_genuine_solve=False,
            self_hosted_runner_required=True,
            next_gate="PROVISION_SELF_HOSTED_WINDOWS_WSL2_CODE_ASTER",
            blocker="GITHUB_HOSTED_WINDOWS_NO_WSL_DISTRIBUTION",
        )

    if not has_wsl:
        return WindowsSolverRunnerBoundary(
            runner_environment=runner_environment,
            github_actions=github_actions,
            wsl_distributions_present=False,
            code_aster_candidates_present=False,
            hosted_runner_supported_for_genuine_solve=not is_github_hosted,
            self_hosted_runner_required=not is_self_hosted,
            next_gate="PROVISION_WSL2_DISTRIBUTION",
            blocker="NO_WSL_DISTRIBUTION",
        )

    if not has_candidate:
        return WindowsSolverRunnerBoundary(
            runner_environment=runner_environment,
            github_actions=github_actions,
            wsl_distributions_present=True,
            code_aster_candidates_present=False,
            hosted_runner_supported_for_genuine_solve=not is_github_hosted,
            self_hosted_runner_required=is_github_hosted,
            next_gate="INSTALL_OR_LOCATE_CODE_ASTER_RUN_ASTER",
            blocker="RUN_ASTER_NOT_DISCOVERED",
        )

    return WindowsSolverRunnerBoundary(
        runner_environment=runner_environment,
        github_actions=github_actions,
        wsl_distributions_present=True,
        code_aster_candidates_present=True,
        hosted_runner_supported_for_genuine_solve=not is_github_hosted,
        self_hosted_runner_required=is_github_hosted,
        next_gate="QUALIFY_DISCOVERED_CODE_ASTER_RUNTIME",
        blocker=None,
    )
