from pathlib import Path

import pytest

from astermax.code_aster_export import (
    CodeAsterExportError,
    CodeAsterExportSpec,
    render_export,
    write_execution_bundle,
)


def _bundle_root(tmp_path: Path) -> Path:
    (tmp_path / "astermax.comm").write_text("DEBUT()\nFIN()\n", encoding="utf-8")
    (tmp_path / "astermax.med").write_bytes(b"MED-POC")
    return tmp_path


def test_render_export_is_deterministic_and_portable():
    spec = CodeAsterExportSpec(time_limit_s=420, memory_limit_mb=4096, ncpus=2, mpi_nbcpu=1)
    one = render_export(spec)
    two = render_export(spec)
    assert one == two
    assert "P time_limit 420" in one
    assert "P memory_limit 4096" in one
    assert "P ncpus 2" in one
    assert "F comm astermax.comm D 1" in one
    assert "F mmed astermax.med D 20" in one
    assert "F rmed astermax_result.med R 80" in one
    assert ":\\" not in one
    assert "../" not in one


def test_write_execution_bundle_hashes_real_inputs(tmp_path: Path):
    root = _bundle_root(tmp_path)
    evidence = write_execution_bundle(root)
    assert (root / "astermax.export").is_file()
    assert (root / "execution_bundle_evidence.json").is_file()
    assert len(evidence["export_sha256"]) == 64
    assert len(evidence["command_sha256"]) == 64
    assert len(evidence["input_med_sha256"]) == 64
    assert evidence["portable_relative_paths"] is True
    assert evidence["fea_solve_executed"] is False
    assert evidence["results_verified"] is False


def test_rejects_path_traversal_and_absolute_names():
    with pytest.raises(CodeAsterExportError):
        CodeAsterExportSpec(command_filename="../bad.comm").validate()
    with pytest.raises(CodeAsterExportError):
        CodeAsterExportSpec(input_med_filename="C:\\bad.med").validate()


def test_rejects_bad_resource_limits():
    with pytest.raises(CodeAsterExportError):
        CodeAsterExportSpec(time_limit_s=0).validate()
    with pytest.raises(CodeAsterExportError):
        CodeAsterExportSpec(memory_limit_mb=64).validate()
    with pytest.raises(CodeAsterExportError):
        CodeAsterExportSpec(ncpus=0).validate()


def test_rejects_missing_or_empty_inputs(tmp_path: Path):
    with pytest.raises(CodeAsterExportError, match="COMMAND_NOT_FOUND"):
        write_execution_bundle(tmp_path)
    (tmp_path / "astermax.comm").write_text("", encoding="utf-8")
    (tmp_path / "astermax.med").write_bytes(b"MED")
    with pytest.raises(CodeAsterExportError, match="COMMAND_EMPTY"):
        write_execution_bundle(tmp_path)


def test_rejects_stale_result(tmp_path: Path):
    root = _bundle_root(tmp_path)
    (root / "astermax_result.med").write_bytes(b"stale")
    with pytest.raises(CodeAsterExportError, match="RESULT_PREEXISTS"):
        write_execution_bundle(root)
