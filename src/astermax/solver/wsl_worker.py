from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from astermax.solver.contracts import ArtifactDigestV1, SolverCapabilityV1, SolverRequestV1


class CodeAsterJobV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="CodeAsterJobV1", pattern=r"^CodeAsterJobV1$")
    export_file: str = Field(min_length=1)
    input_artifacts: list[ArtifactDigestV1] = Field(min_length=1)
    produced_files: list[str] = Field(min_length=1)


def _inside(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    root = root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes run directory: {relative_path}") from exc
    return candidate


def _verify(root: Path, artifact: ArtifactDigestV1) -> None:
    path = _inside(root, artifact.relative_path)
    if not path.is_file():
        raise ValueError(f"missing input artifact: {artifact.relative_path}")
    data = path.read_bytes()
    if len(data) != artifact.byte_size or hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise ValueError(f"input artifact digest mismatch: {artifact.relative_path}")


def _load_capability() -> SolverCapabilityV1:
    path = Path(os.environ.get("ASTERMAX_CODE_ASTER_CAPABILITY_FILE", "/etc/astermax/code_aster_capabilities.json"))
    capability = SolverCapabilityV1.model_validate_json(path.read_text(encoding="utf-8"))
    if capability.backend_id != "code_aster_wsl2":
        raise ValueError("capability backend must be code_aster_wsl2")
    return capability


def _run(request_path: Path, run_dir: Path) -> int:
    request = SolverRequestV1.model_validate_json(request_path.read_text(encoding="utf-8"))
    for artifact in (request.model.geometry, request.model.mesh, request.model.model_definition):
        _verify(run_dir, artifact)

    job_path = _inside(run_dir, request.model.model_definition.relative_path)
    job = CodeAsterJobV1.model_validate_json(job_path.read_text(encoding="utf-8"))
    for artifact in job.input_artifacts:
        _verify(run_dir, artifact)

    export_path = _inside(run_dir, job.export_file)
    if not export_path.is_file():
        raise ValueError(f"missing Code_Aster export file: {job.export_file}")
    if job.export_file not in {artifact.relative_path for artifact in job.input_artifacts}:
        raise ValueError("Code_Aster export file must be present in job input_artifacts")

    run_aster = os.environ.get("ASTERMAX_RUN_ASTER", "run_aster")
    completed = subprocess.run(
        [run_aster, str(export_path)],
        cwd=run_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        return completed.returncode

    produced: list[str] = []
    for relative_path in job.produced_files:
        path = _inside(run_dir, relative_path)
        if not path.is_file():
            raise ValueError(f"Code_Aster did not produce required file: {relative_path}")
        produced.append(path.relative_to(run_dir.resolve()).as_posix())

    capability = _load_capability()
    receipt = {
        "schema_version": "WorkerReceiptV1",
        "backend_id": "code_aster_wsl2",
        "backend_version": capability.backend_version or "unknown",
        "worker_id": f"code-aster:{socket.gethostname()}",
        "produced_files": produced,
        "metadata": {"launcher": "run_aster"},
    }
    receipt_path = run_dir / "output" / "worker_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="astermax-code-aster-worker")
    parser.add_argument("--capabilities-json", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--run-dir")
    args = parser.parse_args(argv)

    try:
        if args.capabilities_json:
            print(_load_capability().model_dump_json())
            return 0
        if not args.request or not args.run_dir:
            parser.error("--request and --run-dir are required for execution")
        return _run(Path(args.request).resolve(), Path(args.run_dir).resolve())
    except (OSError, ValueError, ValidationError) as exc:
        print(f"ASTERMAX_WORKER_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
