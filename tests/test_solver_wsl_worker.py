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


def write_job(root: Path, export: Path, support_files: list[Path], result_rel: str = "output/result.med") -> Path:
    job = root / "input" / "job.json"
    job.write_text(
        json.dumps(
            {
                "schema_version": "CodeAsterJobV1",
                "export_file": export.relative_to(root).as_posix(),
                "input_artifacts": [digest(path, root).model_dump(mode="json") for path in support_files],
                "produced_files": [result_rel],
            }
        ),
        encoding="utf-8",
    )
    return job


def write_request(root: Path, geometry: Path, mesh: Path, job: Path) -> Path:
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
            geometry=digest(geometry, root),
            mesh=digest(mesh, root),
            model_definition=digest(job, root),
        ),
    )
    request_path = root / "input" / "solver_request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    return request_path


def test_worker_rejects_tampered_request_input_before_solver(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    geometry = input_dir / "geometry.med"
    mesh = input_dir / "mesh.med"
    export = input_dir / "job.export"
    comm = input_dir / "job.comm"
    for path in (geometry, mesh, export, comm):
        path.write_bytes(b"x")
    job = write_job(tmp_path, export, [export, comm, mesh])
    request_path = write_request(tmp_path, geometry, mesh, job)
    geometry.write_bytes(b"tampered")
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("solver must not run after input tampering")

    monkeypatch.setattr("astermax.solver.wsl_worker.subprocess.run", forbidden_run)
    assert main(["--request", str(request_path), "--run-dir", str(tmp_path)]) == 2
    assert called is False


def test_worker_rejects_tampered_job_support_input_before_solver(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    geometry = input_dir / "geometry.med"
    mesh = input_dir / "mesh.med"
    export = input_dir / "job.export"
    comm = input_dir / "job.comm"
    for path in (geometry, mesh, export, comm):
        path.write_bytes(b"original")
    job = write_job(tmp_path, export, [export, comm, mesh])
    request_path = write_request(tmp_path, geometry, mesh, job)
    comm.write_bytes(b"mutated-after-job-contract")
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("solver must not run after support input tampering")

    monkeypatch.setattr("astermax.solver.wsl_worker.subprocess.run", forbidden_run)
    assert main(["--request", str(request_path), "--run-dir", str(tmp_path)]) == 2
    assert called is False


def test_worker_rejects_unbound_export_file(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    geometry = input_dir / "geometry.med"
    mesh = input_dir / "mesh.med"
    export = input_dir / "job.export"
    comm = input_dir / "job.comm"
    for path in (geometry, mesh, export, comm):
        path.write_bytes(b"x")
    job = write_job(tmp_path, export, [comm, mesh])
    request_path = write_request(tmp_path, geometry, mesh, job)
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("solver must not run with an unbound export file")

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
    comm = input_dir / "job.comm"
    result = output_dir / "result.med"
    for path in (geometry, mesh, export, comm):
        path.write_bytes(b"x")
    job = write_job(tmp_path, export, [export, comm, mesh])
    request_path = write_request(tmp_path, geometry, mesh, job)
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
        result.write_bytes(b"solver-output-placeholder-used-only-for-process-contract-test")
        return Completed()

    monkeypatch.setattr("astermax.solver.wsl_worker.subprocess.run", fake_run)
    assert main(["--request", str(request_path), "--run-dir", str(tmp_path)]) == 0
    receipt = json.loads((output_dir / "worker_receipt.json").read_text(encoding="utf-8"))
    assert receipt["backend_version"] == "16.test"
    assert receipt["produced_files"] == ["output/result.med"]
