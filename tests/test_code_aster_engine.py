from __future__ import annotations

from pathlib import Path

import pytest

from astermax.code_aster_engine import (
    CodeAsterEngineError,
    DEFAULT_ENV_VAR,
    default_runtime_roots,
    discover_runtime,
    validate_runtime_root,
    write_runtime_evidence,
)


def _make_runtime(root: Path) -> Path:
    (root / "bin").mkdir(parents=True)
    (root / "share" / "aster").mkdir(parents=True)
    launcher = root / "bin" / "run_aster.cmd"
    launcher.write_text("@echo run_aster code_aster\n", encoding="utf-8")
    (root / "share" / "aster" / "config.yaml").write_text("version_tag: test-only\n", encoding="utf-8")
    return launcher


def test_validate_runtime_requires_root_launcher_and_config(tmp_path: Path) -> None:
    with pytest.raises(CodeAsterEngineError, match="ROOT_NOT_FOUND"):
        validate_runtime_root(tmp_path / "missing")

    root = tmp_path / "aster"
    root.mkdir()
    with pytest.raises(CodeAsterEngineError, match="RUN_ASTER_NOT_FOUND"):
        validate_runtime_root(root)

    (root / "bin").mkdir()
    (root / "bin" / "run_aster.exe").write_bytes(b"launcher")
    with pytest.raises(CodeAsterEngineError, match="CONFIG_NOT_FOUND"):
        validate_runtime_root(root)


def test_runtime_evidence_hashes_actual_launcher_bytes(tmp_path: Path) -> None:
    root = tmp_path / "aster"
    launcher = _make_runtime(root)
    runtime = validate_runtime_root(root)

    assert runtime.root == root.resolve()
    assert runtime.run_aster == launcher.resolve()
    assert len(runtime.launcher_sha256) == 64
    assert runtime.engine_kind == "CODE_ASTER_NATIVE_WINDOWS"

    evidence_path = write_runtime_evidence(runtime, tmp_path / "evidence" / "runtime.json")
    payload = evidence_path.read_text(encoding="utf-8")
    assert runtime.launcher_sha256 in payload
    assert '"fea_solve_executed": false' in payload


def test_discovery_prefers_explicit_astermax_runtime(tmp_path: Path) -> None:
    explicit = tmp_path / "managed"
    _make_runtime(explicit)
    roots = default_runtime_roots(
        program_files=str(tmp_path / "Program Files"),
        local_app_data=str(tmp_path / "LocalAppData"),
        env={DEFAULT_ENV_VAR: str(explicit)},
    )
    assert roots[0] == explicit
    runtime = discover_runtime(roots)
    assert runtime.root == explicit.resolve()


def test_discovery_fails_closed_without_verified_runtime(tmp_path: Path) -> None:
    with pytest.raises(CodeAsterEngineError, match="CODE_ASTER_RUNTIME_NOT_FOUND"):
        discover_runtime([tmp_path / "not-installed"])
