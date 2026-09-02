from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Mapping

from .code_aster_engine import CodeAsterRuntime, CodeAsterEngineError, _windows_launcher_command


class CodeAsterSolveError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CodeAsterSolveEvidence:
    runtime_launcher_sha256: str
    export_sha256: str
    input_med_sha256: str
    command_file_sha256: str
    result_med_sha256: str
    returncode: int
    result_size_bytes: int
    fea_solve_executed: bool
    results_verified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "runtime_launcher_sha256": self.runtime_launcher_sha256,
            "export_sha256": self.export_sha256,
            "input_med_sha256": self.input_med_sha256,
            "command_file_sha256": self.command_file_sha256,
            "result_med_sha256": self.result_med_sha256,
            "returncode": self.returncode,
            "result_size_bytes": self.result_size_bytes,
            "fea_solve_executed": self.fea_solve_executed,
            "results_verified": self.results_verified,
        }


def _require_regular_nonempty(path: Path, code: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise CodeAsterSolveError(f"{code}_NOT_FOUND")
    if resolved.stat().st_size <= 0:
        raise CodeAsterSolveError(f"{code}_EMPTY")
    return resolved


def execute_code_aster_export(
    runtime: CodeAsterRuntime,
    *,
    export_file: str | Path,
    input_med: str | Path,
    command_file: str | Path,
    result_med: str | Path,
    timeout_s: float = 300.0,
    extra_env: Mapping[str, str] | None = None,
) -> CodeAsterSolveEvidence:
    """Execute a real Code_Aster ``.export`` study and gate evidence fail-closed.

    ``fea_solve_executed`` is only True after the real launcher returns zero and a
    non-empty result MED exists. ``results_verified`` intentionally remains False;
    numerical/physical result verification is a separate post-processing gate.
    """
    export_path = _require_regular_nonempty(Path(export_file), "CODE_ASTER_EXPORT")
    input_med_path = _require_regular_nonempty(Path(input_med), "CODE_ASTER_INPUT_MED")
    command_path = _require_regular_nonempty(Path(command_file), "CODE_ASTER_COMMAND")
    result_path = Path(result_med).expanduser().resolve()

    if result_path.exists():
        # Refuse stale output so a previous solve cannot be mistaken for this run.
        raise CodeAsterSolveError("CODE_ASTER_RESULT_PREEXISTS")

    command = _windows_launcher_command(runtime, [str(export_path)])
    env = None
    if extra_env:
        import os
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in extra_env.items()})

    try:
        completed = subprocess.run(
            command,
            cwd=export_path.parent,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeAsterSolveError("CODE_ASTER_SOLVE_TIMEOUT") from exc
    except OSError as exc:
        raise CodeAsterSolveError("CODE_ASTER_SOLVE_EXECUTION_FAILED") from exc

    if completed.returncode != 0:
        raise CodeAsterSolveError(f"CODE_ASTER_SOLVE_NONZERO_EXIT:{completed.returncode}")

    result_path = _require_regular_nonempty(result_path, "CODE_ASTER_RESULT_MED")

    return CodeAsterSolveEvidence(
        runtime_launcher_sha256=runtime.launcher_sha256,
        export_sha256=_sha256_file(export_path),
        input_med_sha256=_sha256_file(input_med_path),
        command_file_sha256=_sha256_file(command_path),
        result_med_sha256=_sha256_file(result_path),
        returncode=completed.returncode,
        result_size_bytes=result_path.stat().st_size,
        fea_solve_executed=True,
        results_verified=False,
    )


def write_solve_evidence(evidence: CodeAsterSolveEvidence, destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
