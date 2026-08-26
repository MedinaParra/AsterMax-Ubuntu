from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from astermax.solver.code_aster_wsl2 import CodeAsterWSL2Adapter, ProcessOutcome
from astermax.solver.contracts import (
    ArtifactDigestV1,
    SolverCapabilityV1,
    SolverModelV1,
    SolverRequestV1,
    SolverTermination,
)
from astermax.solver.errors import SolverEvidenceError


def artifact(root: Path, relative_path: str, data: bytes) -> ArtifactDigestV1:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return ArtifactDigestV1(
        relative_path=relative_path,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
    )


def request(root: Path) -> SolverRequestV1:
    return SolverRequestV1(
        request_id="req-1",
        run_id="run-1",
        project_id="p1",
        backend_id="code_aster_wsl2",
        model=SolverModelV1(
            model_id="m1",
            project_id="p1",
            analysis_type="linear_static",
            unit_system="SI",
            geometry=artifact(root, "input/geometry.med", b"geometry-contract-bytes"),
            mesh=artifact(root, "input/mesh.med", b"mesh-contract-bytes"),
            model_definition=artifact(root, "input/model.json", b"model-contract-bytes"),
            required_capabilities=["linear_static"],
        ),
        requested_fields=["displacement"],
    )


def test_capability_probe_is_schema_validated(tmp_path: Path) -> None:
    capability = SolverCapabilityV1(
        backend_id="code_aster_wsl2",
        backend_version="16.test",
        capabilities=["linear_static"],
        result_field_names=["displacement"],
    )

    def runner(command: list[str], cwd: Path, timeout: float) -> ProcessOutcome:
        assert command[-1] == "--capabilities-json"
        return ProcessOutcome(0, capability.model_dump_json(), "")

    adapter = CodeAsterWSL2Adapter(runner=runner, path_converter=lambda _: "/mnt/c/run")
    assert adapter.capability().backend_version == "16.test"


def test_execute_hashes_worker_outputs_logs_and_inputs(tmp_path: Path) -> None:
    req = request(tmp_path)

    def runner(command: list[str], cwd: Path, timeout: float) -> ProcessOutcome:
        output = cwd / "output"
        output.mkdir(exist_ok=True)
        (output / "displacement.vtu").write_bytes(b"solver-produced-bytes-for-process-contract-test")
        (output / "worker_receipt.json").write_text(
            json.dumps(
                {
                    "schema_version": "WorkerReceiptV1",
                    "backend_id": "code_aster_wsl2",
                    "backend_version": "16.test",
                    "worker_id": "code-aster-test-worker",
                    "produced_files": ["output/displacement.vtu"],
                    "metadata": {},
                }
            ),
            encoding="utf-8",
        )
        return ProcessOutcome(0, "worker stdout", "worker stderr")

    manifest = CodeAsterWSL2Adapter(
        runner=runner,
        path_converter=lambda _: "/mnt/c/run",
    ).execute(req, tmp_path)
    assert manifest.termination == SolverTermination.SUCCEEDED
    assert manifest.backend_version == "16.test"
    assert manifest.stdout_artifact is not None
    assert manifest.stderr_artifact is not None
    assert {item.relative_path for item in manifest.input_artifacts} == {
        "input/solver_request.json",
        "input/geometry.med",
        "input/mesh.med",
        "input/model.json",
    }
    assert {item.relative_path for item in manifest.output_artifacts} == {
        "output/worker_receipt.json",
        "output/displacement.vtu",
    }
    assert (tmp_path / "output" / "manifest.json").is_file()


def test_execute_fails_closed_when_declared_input_digest_is_tampered(tmp_path: Path) -> None:
    req = request(tmp_path)
    (tmp_path / "input" / "geometry.med").write_bytes(b"tampered-after-request")
    runner_called = False

    def runner(command: list[str], cwd: Path, timeout: float) -> ProcessOutcome:
        nonlocal runner_called
        runner_called = True
        return ProcessOutcome(0, "", "")

    adapter = CodeAsterWSL2Adapter(runner=runner, path_converter=lambda _: "/mnt/c/run")
    with pytest.raises(SolverEvidenceError, match="declared input artifact digest mismatch"):
        adapter.execute(req, tmp_path)
    assert runner_called is False


def test_execute_fails_closed_when_success_exit_has_no_receipt(tmp_path: Path) -> None:
    req = request(tmp_path)
    adapter = CodeAsterWSL2Adapter(
        runner=lambda command, cwd, timeout: ProcessOutcome(0, "", ""),
        path_converter=lambda _: "/mnt/c/run",
    )
    manifest = adapter.execute(req, tmp_path)
    assert manifest.termination == SolverTermination.INVALID_ARTIFACTS
    assert manifest.output_artifacts == []
