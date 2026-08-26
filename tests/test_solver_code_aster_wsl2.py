from __future__ import annotations

import json
from pathlib import Path

from astermax.solver.code_aster_wsl2 import CodeAsterWSL2Adapter, ProcessOutcome
from astermax.solver.contracts import (
    ArtifactDigestV1,
    SolverCapabilityV1,
    SolverModelV1,
    SolverRequestV1,
    SolverTermination,
)


def placeholder(path: str) -> ArtifactDigestV1:
    return ArtifactDigestV1(relative_path=path, sha256="a" * 64, byte_size=1)


def request() -> SolverRequestV1:
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
            geometry=placeholder("input/geometry.med"),
            mesh=placeholder("input/mesh.med"),
            model_definition=placeholder("input/model.json"),
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


def test_execute_hashes_worker_outputs_and_logs(tmp_path: Path) -> None:
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
    ).execute(request(), tmp_path)
    assert manifest.termination == SolverTermination.SUCCEEDED
    assert manifest.backend_version == "16.test"
    assert manifest.stdout_artifact is not None
    assert manifest.stderr_artifact is not None
    assert {item.relative_path for item in manifest.output_artifacts} == {
        "output/worker_receipt.json",
        "output/displacement.vtu",
    }
    assert (tmp_path / "output" / "manifest.json").is_file()


def test_execute_fails_closed_when_success_exit_has_no_receipt(tmp_path: Path) -> None:
    adapter = CodeAsterWSL2Adapter(
        runner=lambda command, cwd, timeout: ProcessOutcome(0, "", ""),
        path_converter=lambda _: "/mnt/c/run",
    )
    manifest = adapter.execute(request(), tmp_path)
    assert manifest.termination == SolverTermination.INVALID_ARTIFACTS
    assert manifest.output_artifacts == []
