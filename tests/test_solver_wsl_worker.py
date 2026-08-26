from __future__ import annotations

import hashlib
import json
from pathlib import Path

from astermax.solver.contracts import ArtifactDigestV1, SolverModelV1, SolverRequestV1
from astermax.solver.wsl_worker import main


def digest(path: Path, root: Path) -> ArtifactDigestV1:
    data = path.read_bytes()
    return ArtifactDigestV1(
        relative_path=path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
    )


def test_worker_rejects_tampered_input_before_solver(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    geometry = input_dir / "geometry.med"
    mesh = input_dir / "mesh.med"
    job = input_dir / "job.json"
    for path in (geometry, mesh):
        path.write_bytes(b"x")
    job.write_text(json.dumps({"schema_version": "CodeAsterJobV1", "export_file": "input/job.export", "produced_files": ["output/result.med"]}), encoding="utf-8")
    geometry_artifact = digest(geometry, tmp_path)
    request = SolverRequestV1(
        request_id="r",
        run_id="run",
        project_id="p",
        backend_id="code_aster_wsl2",
        model=SolverModelV1(
            model_id="m",
            project_id="p",
            analysis_type="linear_static",
            unit_system="SI",
            geometry=geometry_artifact,
            mesh=digest(mesh, tmp_path),
            model_definition=digest(job, tmp_path),
        ),
    )
    request_path = input_dir / "solver_request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    geometry.write_bytes(b"tampered")
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("solver must not run after input tampering")

    monkeypatch.setattr("astermax.solver.wsl_worker.subprocess.run", forbidden_run)
    assert main(["--request", str(request_path), "--run-dir", str(tmp_path)]) == 2
    assert called is False


def test_worker_uses_fixed_run_aster_command_and_writes_receipt(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    geometry = input_dir / "geometry.med"
    mesh = input_dir / "mesh.med"
    export = input_dir / "job.export"
    result = output_dir / "result.med"
    for path in (geometry, mesh, export):
        path.write_bytes(b"x")
    job = input_dir / "job.json"
    job.write_text(json.dumps({"schema_version": "CodeAsterJobV1", "export_file": "input/job.export", "produced_files": ["output/result.med"]}), encoding="utf-8")
    request = SolverRequestV1(
        request_id="r",
        run_id="run",
        project_id="p",
        backend_id="code_aster_wsl2",
        model=SolverModelV1(
            model_id="m",
            project_id="p",
            analysis_type="linear_static",
            unit_system="SI",
            geometry=digest(geometry, tmp_path),
            mesh=digest(mesh, tmp_path),
            model_definition=digest(job, tmp_path),
        ),
    )
    request_path = input_dir / "solver_request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    capability = tmp_path / "capabilities.json"
    capability.write_text(json.dumps({"schema_version": "SolverCapabilityV1", "backend_id": "code_aster_wsl2", "backend_version": "16.test", "capabilities": [], "result_field_names": [], "metadata": {}}), encoding="utf-8")
    monkeypatch.setenv("ASTERMAX_CODE_ASTER_CAPABILITY_FILE", str(capability))
    monkeypatch.setenv("ASTERMAX_RUN_ASTER", "/opt/code_aster/bin/run_aster")

    class Completed:
        returncode = 0
        stdout = "solver stdout"
        stderr = ""

    def fake_run(command, **kwargs):
        assert command == ["/opt/code_aster/bin/run_aster", str(export.resolve())]
        result.write_bytes(b"real-solver-output-placeholder-only-for-process-test")
        return Completed()

    monkeypatch.setattr("astermax.solver.wsl_worker.subprocess.run", fake_run)
    assert main(["--request", str(request_path), "--run-dir", str(tmp_path)]) == 0
    receipt = json.loads((output_dir / "worker_receipt.json").read_text(encoding="utf-8"))
    assert receipt["backend_version"] == "16.test"
    assert receipt["produced_files"] == ["output/result.med"]
