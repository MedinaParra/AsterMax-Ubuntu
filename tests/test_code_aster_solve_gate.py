from pathlib import Path
import subprocess

import pytest

from astermax.code_aster_engine import CodeAsterRuntime
from astermax.code_aster_solve_gate import (
    CodeAsterSolveError,
    execute_code_aster_export,
)


def _runtime(tmp_path: Path) -> CodeAsterRuntime:
    launcher = tmp_path / "run_aster.cmd"
    launcher.write_text("@echo off\n", encoding="utf-8")
    config = tmp_path / "share" / "aster" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("version: test\n", encoding="utf-8")
    return CodeAsterRuntime(
        root=tmp_path,
        run_aster=launcher,
        config=config,
        launcher_sha256="launcher-sha",
    )


def _study(tmp_path: Path):
    export = tmp_path / "study.export"
    med = tmp_path / "mesh.med"
    comm = tmp_path / "study.comm"
    result = tmp_path / "result.med"
    export.write_text("P actions make_etude\n", encoding="utf-8")
    med.write_bytes(b"MEDINPUT")
    comm.write_text("DEBUT();\nFIN();\n", encoding="utf-8")
    return export, med, comm, result


def test_nonzero_exit_never_claims_solve(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    export, med, comm, result = _study(tmp_path)

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 4, "", "failure"),
    )

    with pytest.raises(CodeAsterSolveError, match="CODE_ASTER_SOLVE_NONZERO_EXIT:4"):
        execute_code_aster_export(runtime, export_file=export, input_med=med, command_file=comm, result_med=result)


def test_zero_exit_without_result_never_claims_solve(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    export, med, comm, result = _study(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    with pytest.raises(CodeAsterSolveError, match="CODE_ASTER_RESULT_MED_NOT_FOUND"):
        execute_code_aster_export(runtime, export_file=export, input_med=med, command_file=comm, result_med=result)


def test_success_requires_fresh_nonempty_result_and_keeps_results_unverified(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    export, med, comm, result = _study(tmp_path)

    def fake_run(*args, **kwargs):
        result.write_bytes(b"REAL-SOLVER-RESULT-BYTES-FOR-GATE-TEST")
        return subprocess.CompletedProcess(args[0], 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence = execute_code_aster_export(
        runtime,
        export_file=export,
        input_med=med,
        command_file=comm,
        result_med=result,
    )
    assert evidence.fea_solve_executed is True
    assert evidence.results_verified is False
    assert evidence.returncode == 0
    assert evidence.result_size_bytes == result.stat().st_size
    assert len(evidence.result_med_sha256) == 64
    assert len(evidence.export_sha256) == 64
    assert len(evidence.input_med_sha256) == 64
    assert len(evidence.command_file_sha256) == 64


def test_preexisting_result_is_rejected_as_stale(tmp_path):
    runtime = _runtime(tmp_path)
    export, med, comm, result = _study(tmp_path)
    result.write_bytes(b"stale")
    with pytest.raises(CodeAsterSolveError, match="CODE_ASTER_RESULT_PREEXISTS"):
        execute_code_aster_export(runtime, export_file=export, input_med=med, command_file=comm, result_med=result)


def test_empty_or_missing_solver_inputs_fail_closed(tmp_path):
    runtime = _runtime(tmp_path)
    export, med, comm, result = _study(tmp_path)
    comm.write_text("", encoding="utf-8")
    with pytest.raises(CodeAsterSolveError, match="CODE_ASTER_COMMAND_EMPTY"):
        execute_code_aster_export(runtime, export_file=export, input_med=med, command_file=comm, result_med=result)
