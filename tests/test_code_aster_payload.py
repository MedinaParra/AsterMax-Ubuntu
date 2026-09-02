from hashlib import sha256
import json
from pathlib import Path

import pytest

from astermax.code_aster_payload import (
    CodeAsterPayloadError,
    build_manifest_for_tree,
    load_payload_manifest,
    verify_payload_tree,
)


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def test_build_and_verify_payload_tree(tmp_path: Path) -> None:
    root = tmp_path / "code_aster"
    (root / "bin").mkdir(parents=True)
    (root / "share" / "aster").mkdir(parents=True)
    launcher = root / "bin" / "run_aster.exe"
    config = root / "share" / "aster" / "config.yaml"
    launcher.write_bytes(b"native-windows-launcher")
    config.write_bytes(b"version: 17.3.14\n")

    manifest = build_manifest_for_tree(
        root,
        ["bin/run_aster.exe", "share/aster/config.yaml"],
        code_aster_version="17.3.14",
        distribution_id="astermax-test-ucrt64",
    )
    evidence = verify_payload_tree(root, manifest)

    assert evidence["payload_integrity_verified"] is True
    assert evidence["verified_file_count"] == 2
    assert evidence["fea_solve_executed"] is False
    assert evidence["code_aster_version"] == "17.3.14"


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "code_aster"
    root.mkdir()
    target = root / "run_aster.exe"
    target.write_bytes(b"actual")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "engine": "CODE_ASTER_NATIVE_WINDOWS",
        "platform": "windows-native",
        "architecture": "x86_64",
        "code_aster_version": "17.3.14",
        "distribution_id": "test",
        "files": [{"relative_path": "run_aster.exe", "sha256": _digest(b"different")}],
    }), encoding="utf-8")
    manifest = load_payload_manifest(manifest_path)
    with pytest.raises(CodeAsterPayloadError, match="CODE_ASTER_PAYLOAD_HASH_MISMATCH"):
        verify_payload_tree(root, manifest)


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "engine": "CODE_ASTER_NATIVE_WINDOWS",
        "platform": "windows-native",
        "architecture": "x86_64",
        "code_aster_version": "17.3.14",
        "distribution_id": "test",
        "files": [{"relative_path": "../escape.dll", "sha256": "0" * 64}],
    }), encoding="utf-8")
    with pytest.raises(CodeAsterPayloadError, match="CODE_ASTER_PAYLOAD_PATH_TRAVERSAL"):
        load_payload_manifest(manifest_path)


def test_missing_required_file_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "code_aster"
    root.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "engine": "CODE_ASTER_NATIVE_WINDOWS",
        "platform": "windows-native",
        "architecture": "x86_64",
        "code_aster_version": "17.3.14",
        "distribution_id": "test",
        "files": [{"relative_path": "bin/run_aster.exe", "sha256": "0" * 64}],
    }), encoding="utf-8")
    manifest = load_payload_manifest(manifest_path)
    with pytest.raises(CodeAsterPayloadError, match="CODE_ASTER_PAYLOAD_REQUIRED_FILE_MISSING"):
        verify_payload_tree(root, manifest)
