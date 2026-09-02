from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
import subprocess
from pathlib import Path
from typing import Callable

from .code_aster_wsl_runtime import ENGINE_KIND


class CodeAsterRuntimeDiscoveryError(RuntimeError):
    pass


_DISTRO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_LINUX_PATH_RE = re.compile(r"^/[A-Za-z0-9_./+\-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RuntimeCandidate:
    distribution: str
    run_aster_linux: str
    identity_confirmed: bool
    identity_sha256: str

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RuntimeDiscoveryEvidence:
    engine_kind: str
    host_os: str
    solver_os: str
    distributions: tuple[str, ...]
    candidates: tuple[RuntimeCandidate, ...]
    discovery_complete: bool
    qualified_runtime_available: bool = False
    fea_solve_executed: bool = False
    numerical_verification: bool = False
    results_verified: bool = False
    industrial_validation: bool = False
    ansys_equivalence: bool = False

    @property
    def blocker(self) -> str:
        if not self.distributions:
            return "NO_WSL_DISTRIBUTION"
        if not self.candidates:
            return "RUN_ASTER_NOT_DISCOVERED"
        return "RUNTIME_REQUIRES_QUALIFICATION"

    def as_dict(self) -> dict[str, object]:
        data = self.__dict__.copy()
        data["distributions"] = list(self.distributions)
        data["candidates"] = [candidate.as_dict() for candidate in self.candidates]
        data["blocker"] = self.blocker
        return data


Runner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


def _default_runner(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeAsterRuntimeDiscoveryError("CODE_ASTER_RUNTIME_DISCOVERY_EXECUTION_FAILED") from exc


def _clean_distributions(stdout: str) -> tuple[str, ...]:
    names: list[str] = []
    for raw in stdout.splitlines():
        name = raw.replace("\x00", "").strip()
        if not name:
            continue
        if not _DISTRO_RE.fullmatch(name):
            raise CodeAsterRuntimeDiscoveryError("CODE_ASTER_RUNTIME_DISCOVERY_DISTRO_INVALID")
        if name not in names:
            names.append(name)
    return tuple(names)


def _discover_path(distribution: str, runner: Runner, timeout_s: float) -> str | None:
    command = [
        "wsl.exe", "--distribution", distribution, "--", "sh", "-lc",
        "command -v run_aster 2>/dev/null || find /opt /usr/local -maxdepth 6 -type f -name run_aster -print -quit 2>/dev/null",
    ]
    completed = runner(command, timeout_s)
    if completed.returncode not in (0, 1):
        raise CodeAsterRuntimeDiscoveryError("CODE_ASTER_RUNTIME_DISCOVERY_SEARCH_FAILED")
    path = (completed.stdout or "").strip().splitlines()
    if not path:
        return None
    candidate = path[0].strip()
    if not _LINUX_PATH_RE.fullmatch(candidate):
        raise CodeAsterRuntimeDiscoveryError("CODE_ASTER_RUNTIME_DISCOVERY_PATH_INVALID")
    return candidate


def _probe_identity(distribution: str, run_aster_linux: str, runner: Runner, timeout_s: float) -> RuntimeCandidate:
    completed = runner(
        ["wsl.exe", "--distribution", distribution, "--", run_aster_linux, "--help"],
        timeout_s,
    )
    combined = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    identity = completed.returncode == 0 and ("run_aster" in combined.lower() or "code_aster" in combined.lower())
    digest = sha256(combined.encode("utf-8", errors="replace")).hexdigest()
    if not _SHA256_RE.fullmatch(digest):
        raise CodeAsterRuntimeDiscoveryError("CODE_ASTER_RUNTIME_DISCOVERY_IDENTITY_HASH_INVALID")
    return RuntimeCandidate(
        distribution=distribution,
        run_aster_linux=run_aster_linux,
        identity_confirmed=identity,
        identity_sha256=digest,
    )


def discover_wsl_code_aster_runtimes(*, timeout_s: float = 20.0, runner: Runner | None = None) -> RuntimeDiscoveryEvidence:
    """Discover concrete WSL2 ``run_aster`` candidates without claiming qualification or a solve.

    Discovery is deliberately weaker than runtime qualification. A candidate is useful
    only when ``--help`` identifies Code_Aster/run_aster. Even then the evidence keeps
    qualified_runtime_available and all numerical/result claims false until the C8.7+
    qualification and genuine-solve gates have passed.
    """
    run = runner or _default_runner
    listed = run(["wsl.exe", "--list", "--quiet"], timeout_s)
    if listed.returncode != 0:
        raise CodeAsterRuntimeDiscoveryError("CODE_ASTER_RUNTIME_DISCOVERY_WSL_LIST_FAILED")
    distributions = _clean_distributions(listed.stdout or "")

    candidates: list[RuntimeCandidate] = []
    for distribution in distributions:
        path = _discover_path(distribution, run, timeout_s)
        if path is None:
            continue
        candidate = _probe_identity(distribution, path, run, timeout_s)
        if candidate.identity_confirmed:
            candidates.append(candidate)

    return RuntimeDiscoveryEvidence(
        engine_kind=ENGINE_KIND,
        host_os="Windows",
        solver_os="Linux/WSL2",
        distributions=distributions,
        candidates=tuple(candidates),
        discovery_complete=True,
    )


def write_runtime_discovery_evidence(evidence: RuntimeDiscoveryEvidence, destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
