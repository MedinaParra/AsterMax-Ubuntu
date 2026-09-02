from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import re
import subprocess


ENGINE_KIND = "CODE_ASTER_WSL2_WINDOWS_HOST"
_DISTRO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_COMMAND_RE = re.compile(r"^/[A-Za-z0-9_./+-]+$")


class CodeAsterWslError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodeAsterWslRuntime:
    distribution: str
    run_aster_linux: str
    engine_kind: str = ENGINE_KIND

    def validate(self) -> None:
        if not _DISTRO_RE.fullmatch(self.distribution):
            raise CodeAsterWslError("CODE_ASTER_WSL_DISTRO_INVALID")
        if not _COMMAND_RE.fullmatch(self.run_aster_linux):
            raise CodeAsterWslError("CODE_ASTER_WSL_RUN_ASTER_PATH_INVALID")

    def as_evidence(self) -> dict[str, object]:
        self.validate()
        return {
            "engine_kind": self.engine_kind,
            "host_os": "Windows",
            "solver_os": "Linux/WSL2",
            "distribution": self.distribution,
            "run_aster_linux": self.run_aster_linux,
            "fea_solve_executed": False,
            "results_verified": False,
        }


def _run(command: list[str], *, timeout_s: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeAsterWslError("CODE_ASTER_WSL_EXECUTION_FAILED") from exc


def list_wsl_distributions(*, timeout_s: float = 15.0) -> tuple[str, ...]:
    completed = _run(["wsl.exe", "--list", "--quiet"], timeout_s=timeout_s)
    if completed.returncode != 0:
        raise CodeAsterWslError(f"CODE_ASTER_WSL_LIST_FAILED:{completed.returncode}")
    names = tuple(line.strip().replace("\x00", "") for line in completed.stdout.splitlines() if line.strip().replace("\x00", ""))
    return names


def probe_wsl_runtime(runtime: CodeAsterWslRuntime, *, timeout_s: float = 30.0) -> dict[str, object]:
    """Verify the Windows->WSL2->run_aster bridge without claiming an FEA solve."""
    runtime.validate()
    distributions = list_wsl_distributions(timeout_s=timeout_s)
    if runtime.distribution not in distributions:
        raise CodeAsterWslError("CODE_ASTER_WSL_DISTRO_NOT_INSTALLED")

    completed = _run(
        ["wsl.exe", "--distribution", runtime.distribution, "--", runtime.run_aster_linux, "--help"],
        timeout_s=timeout_s,
    )
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise CodeAsterWslError(f"CODE_ASTER_WSL_PROBE_NONZERO_EXIT:{completed.returncode}")
    if "run_aster" not in combined.lower() and "code_aster" not in combined.lower():
        raise CodeAsterWslError("CODE_ASTER_WSL_IDENTITY_UNCONFIRMED")

    evidence = runtime.as_evidence()
    evidence.update({
        "wsl_distribution_verified": True,
        "run_aster_identity_confirmed": True,
        "probe_returncode": completed.returncode,
        "probe_sha256": sha256(combined.encode("utf-8", errors="replace")).hexdigest(),
    })
    return evidence


def windows_path_to_wsl(runtime: CodeAsterWslRuntime, path: str | Path, *, timeout_s: float = 15.0) -> str:
    runtime.validate()
    absolute = str(Path(path).expanduser().resolve())
    completed = _run(
        ["wsl.exe", "--distribution", runtime.distribution, "--", "wslpath", "-a", absolute],
        timeout_s=timeout_s,
    )
    if completed.returncode != 0:
        raise CodeAsterWslError(f"CODE_ASTER_WSL_PATH_TRANSLATION_FAILED:{completed.returncode}")
    translated = completed.stdout.strip()
    if not translated.startswith("/"):
        raise CodeAsterWslError("CODE_ASTER_WSL_PATH_TRANSLATION_INVALID")
    return translated


def build_wsl_run_aster_command(runtime: CodeAsterWslRuntime, *, workdir_linux: str, export_filename: str) -> list[str]:
    runtime.validate()
    if not workdir_linux.startswith("/") or Path(export_filename).name != export_filename or not export_filename.lower().endswith(".export"):
        raise CodeAsterWslError("CODE_ASTER_WSL_STUDY_PATH_INVALID")
    return [
        "wsl.exe", "--distribution", runtime.distribution,
        "--cd", workdir_linux,
        "--", runtime.run_aster_linux, export_filename,
    ]


def write_wsl_runtime_evidence(evidence: dict[str, object], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return path
