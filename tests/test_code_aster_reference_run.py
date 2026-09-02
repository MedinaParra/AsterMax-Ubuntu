from pathlib import Path
import subprocess

import pytest

from astermax.code_aster_reference_harness import UniaxialPrismSpec
from astermax.code_aster_reference_run import (
    CodeAsterReferenceRunError,
    execute_and_verify_reference_wsl,
)
from astermax.code_aster_wsl_runtime import CodeAsterWslRuntime


def runtime():
    return CodeAsterWslRuntime("smeca-2024", "/opt/smeca/bin/run_aster")


def make_inputs(root: Path):
    (root / "astermax.export").write_text("F comm astermax.comm D 1\n", encoding="utf-8")
    (root / "astermax.comm").write_text("DEBUT()\nFIN()\n", encoding="utf-8")
    (root / "astermax.med").write_bytes(b"MED-input-witness")


def test_stale_output_is_rejected_before_any_runtime_call(tmp_path: Path, monkeypatch):
    make_inputs(tmp_path)
    (tmp_path / "astermax_result.med").write_bytes(b"old")
    monkeypatch.setattr("astermax.code_aster_reference_run.probe_wsl_runtime", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not probe")))
    with pytest.raises(CodeAsterReferenceRunError, match="STALE_OUTPUT"):
        execute_and_verify_reference_wsl(runtime(), UniaxialPrismSpec(), tmp_path)


def test_nonzero_solver_exit_fails_closed(tmp_path: Path, monkeypatch):
    make_inputs(tmp_path)
    monkeypatch.setattr("astermax.code_aster_reference_run.probe_wsl_runtime", lambda *a, **k: {"identity": True})
    monkeypatch.setattr("astermax.code_aster_reference_run.windows_path_to_wsl", lambda *a, **k: "/mnt/c/case")
    monkeypatch.setattr(
        "astermax.code_aster_reference_run._run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 7, stdout="", stderr="solver failed"),
    )
    with pytest.raises(CodeAsterReferenceRunError, match="NONZERO_EXIT:7"):
        execute_and_verify_reference_wsl(runtime(), UniaxialPrismSpec(), tmp_path)


def test_process_double_only_exercises_gate_semantics(tmp_path: Path, monkeypatch):
    """This is not Code_Aster evidence; it only proves the software gate wiring."""
    make_inputs(tmp_path)
    spec = UniaxialPrismSpec(young_mpa=200000.0, poisson=0.0, total_force_n=10000.0)
    monkeypatch.setattr("astermax.code_aster_reference_run.probe_wsl_runtime", lambda *a, **k: {"identity": True})
    monkeypatch.setattr("astermax.code_aster_reference_run.windows_path_to_wsl", lambda *a, **k: "/mnt/c/case")

    def fake_run(command, *, timeout_s):
        (tmp_path / "astermax_result.med").write_bytes(b"PROCESS-DOUBLE-NOT-SOLVER-EVIDENCE")
        (tmp_path / "reference_displacement.table").write_text("MOYENNE;\n2.500000000000E-02;\n", encoding="utf-8")
        (tmp_path / "reference_reaction.table").write_text("RESULT_X;\n-1.000000000000E+04;\n", encoding="utf-8")
        (tmp_path / "reference_stress.table").write_text("MOYENNE;\n5.000000000000E+01;\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="process double", stderr="")

    monkeypatch.setattr("astermax.code_aster_reference_run._run", fake_run)
    ev = execute_and_verify_reference_wsl(runtime(), spec, tmp_path)
    assert ev.fea_solve_executed is True
    assert ev.numerical_verification is True
    assert ev.results_verified is True
    assert ev.ux_relative_error == 0.0
    assert ev.reaction_relative_error == 0.0
    assert ev.stress_relative_error == 0.0
