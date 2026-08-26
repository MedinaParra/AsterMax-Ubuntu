from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from astermax.solver.contracts import (
    ArtifactDigestV1,
    SolverCapabilityV1,
    SolverRequestV1,
    SolverRunManifestV1,
    SolverTermination,
)
from astermax.solver.errors import SolverEvidenceError


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str


ProcessRunner = Callable[[list[str], Path, float], ProcessOutcome]
PathConverter = Callable[[Path], str]


class WorkerReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="WorkerReceiptV1", pattern=r"^WorkerReceiptV1$")
    backend_id: str = Field(pattern=r"^code_aster_wsl2$")
    backend_version: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    produced_files: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def _default_runner(command: list[str], cwd: Path, timeout_seconds: float) -> ProcessOutcome:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    return ProcessOutcome(completed.returncode, completed.stdout, completed.stderr)


def _default_wsl_path(path: Path, distro: str, wsl_executable: str) -> str:
    completed = subprocess.run(
        [wsl_executable, "--distribution", distro, "--exec", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SolverEvidenceError("could not translate Windows run directory into WSL path")
    return completed.stdout.strip()


def _artifact(path: Path, root: Path, media_type: str | None = None) -> ArtifactDigestV1:
    resolved = path.resolve()
    root = root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise SolverEvidenceError(f"worker artifact escapes run directory: {path}") from exc
    if not resolved.is_file():
        raise SolverEvidenceError(f"worker declared missing artifact: {relative}")
    data = resolved.read_bytes()
    return ArtifactDigestV1(
        relative_path=relative,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        media_type=media_type,
    )


def _verified_declared_artifact(declared: ArtifactDigestV1, root: Path) -> ArtifactDigestV1:
    actual = _artifact(root / declared.relative_path, root, declared.media_type)
    if actual.sha256 != declared.sha256 or actual.byte_size != declared.byte_size:
        raise SolverEvidenceError(f"declared input artifact digest mismatch: {declared.relative_path}")
    return actual


def _write_json(path: Path, payload: dict) -> bytes:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return encoded


class CodeAsterWSL2Adapter:
    """Windows process adapter for a fixed Code_Aster worker installed inside WSL2."""

    backend_id = "code_aster_wsl2"

    def __init__(
        self,
        *,
        distro: str = "Ubuntu",
        worker_executable: str = "/opt/astermax/bin/astermax-code-aster-worker",
        wsl_executable: str = "wsl.exe",
        timeout_seconds: float = 3600,
        runner: ProcessRunner = _default_runner,
        path_converter: PathConverter | None = None,
    ) -> None:
        self.distro = distro
        self.worker_executable = worker_executable
        self.wsl_executable = wsl_executable
        self.timeout_seconds = timeout_seconds
        self.runner = runner
        self.path_converter = path_converter or (
            lambda path: _default_wsl_path(path, self.distro, self.wsl_executable)
        )
        self._capability: SolverCapabilityV1 | None = None

    def _base_command(self) -> list[str]:
        return [
            self.wsl_executable,
            "--distribution",
            self.distro,
            "--exec",
            self.worker_executable,
        ]

    def capability(self) -> SolverCapabilityV1:
        if self._capability is not None:
            return self._capability
        outcome = self.runner([*self._base_command(), "--capabilities-json"], Path.cwd(), 30)
        if outcome.returncode != 0:
            raise SolverEvidenceError("Code_Aster worker capability probe failed")
        try:
            capability = SolverCapabilityV1.model_validate_json(outcome.stdout)
        except ValidationError as exc:
            raise SolverEvidenceError("Code_Aster worker returned malformed capability descriptor") from exc
        if capability.backend_id != self.backend_id:
            raise SolverEvidenceError("Code_Aster capability descriptor backend mismatch")
        self._capability = capability
        return capability

    def execute(self, request: SolverRequestV1, run_directory: Path) -> SolverRunManifestV1:
        run_directory = run_directory.resolve()
        input_dir = run_directory / "input"
        output_dir = run_directory / "output"
        logs_dir = run_directory / "logs"
        for directory in (input_dir, output_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

        verified_model_inputs = [
            _verified_declared_artifact(request.model.geometry, run_directory),
            _verified_declared_artifact(request.model.mesh, run_directory),
            _verified_declared_artifact(request.model.model_definition, run_directory),
        ]

        request_path = input_dir / "solver_request.json"
        _write_json(request_path, request.model_dump(mode="json"))
        request_artifact = _artifact(request_path, run_directory, "application/json")
        input_artifacts = [request_artifact, *verified_model_inputs]

        wsl_run_directory = self.path_converter(run_directory)
        started_at = datetime.now(timezone.utc)
        outcome = self.runner(
            [
                *self._base_command(),
                "--request",
                f"{wsl_run_directory}/input/solver_request.json",
                "--run-dir",
                wsl_run_directory,
            ],
            run_directory,
            self.timeout_seconds,
        )
        finished_at = datetime.now(timezone.utc)

        stdout_path = logs_dir / "stdout.txt"
        stderr_path = logs_dir / "stderr.txt"
        stdout_path.write_text(outcome.stdout, encoding="utf-8")
        stderr_path.write_text(outcome.stderr, encoding="utf-8")
        stdout_artifact = _artifact(stdout_path, run_directory, "text/plain")
        stderr_artifact = _artifact(stderr_path, run_directory, "text/plain")

        receipt_path = output_dir / "worker_receipt.json"
        termination = SolverTermination.FAILED
        backend_version = "unknown"
        worker_id = f"wsl2:{self.distro}:unknown"
        output_artifacts: list[ArtifactDigestV1] = []

        if outcome.returncode == 0:
            if not receipt_path.is_file():
                termination = SolverTermination.INVALID_ARTIFACTS
            else:
                try:
                    receipt = WorkerReceiptV1.model_validate_json(receipt_path.read_text(encoding="utf-8"))
                    backend_version = receipt.backend_version
                    worker_id = receipt.worker_id
                    output_artifacts.append(_artifact(receipt_path, run_directory, "application/json"))
                    for relative_path in receipt.produced_files:
                        output_artifacts.append(_artifact(run_directory / relative_path, run_directory))
                    if receipt.produced_files:
                        termination = SolverTermination.SUCCEEDED
                    else:
                        termination = SolverTermination.INVALID_ARTIFACTS
                except (ValidationError, SolverEvidenceError, OSError):
                    termination = SolverTermination.INVALID_ARTIFACTS

        manifest = SolverRunManifestV1(
            run_id=request.run_id,
            request_id=request.request_id,
            backend_id=self.backend_id,
            backend_version=backend_version,
            worker_id=worker_id,
            started_at=started_at,
            finished_at=finished_at,
            termination=termination,
            exit_code=outcome.returncode,
            input_artifacts=input_artifacts,
            output_artifacts=output_artifacts,
            stdout_artifact=stdout_artifact,
            stderr_artifact=stderr_artifact,
            environment={"transport": "WSL2", "distribution": self.distro},
        )
        _write_json(output_dir / "manifest.json", manifest.model_dump(mode="json"))
        return manifest
