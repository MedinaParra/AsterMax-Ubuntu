from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Iterable


class CodeAsterPayloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PayloadFile:
    relative_path: str
    sha256: str
    required: bool = True

    def validate(self) -> None:
        if not self.relative_path or Path(self.relative_path).is_absolute():
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_PATH_INVALID")
        normalized = Path(self.relative_path)
        if ".." in normalized.parts:
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_PATH_TRAVERSAL")
        digest = self.sha256.lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_SHA256_INVALID")


@dataclass(frozen=True)
class CodeAsterPayloadManifest:
    schema_version: int
    engine: str
    platform: str
    architecture: str
    code_aster_version: str
    distribution_id: str
    files: tuple[PayloadFile, ...]

    def validate(self) -> None:
        if self.schema_version != 1:
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_SCHEMA_UNSUPPORTED")
        if self.engine != "CODE_ASTER_NATIVE_WINDOWS":
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_ENGINE_INVALID")
        if self.platform != "windows-native":
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_PLATFORM_INVALID")
        if self.architecture.lower() not in {"x86_64", "amd64"}:
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_ARCH_INVALID")
        if not self.code_aster_version.strip() or not self.distribution_id.strip():
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_IDENTITY_MISSING")
        if not self.files:
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_FILES_EMPTY")
        seen: set[str] = set()
        for item in self.files:
            item.validate()
            key = os.path.normcase(item.relative_path.replace("\\", "/"))
            if key in seen:
                raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_DUPLICATE_PATH")
            seen.add(key)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine": self.engine,
            "platform": self.platform,
            "architecture": self.architecture,
            "code_aster_version": self.code_aster_version,
            "distribution_id": self.distribution_id,
            "files": [
                {
                    "relative_path": item.relative_path,
                    "sha256": item.sha256,
                    "required": item.required,
                }
                for item in self.files
            ],
        }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_payload_manifest(path: str | os.PathLike[str]) -> CodeAsterPayloadManifest:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_MANIFEST_UNREADABLE") from exc

    try:
        files = tuple(
            PayloadFile(
                relative_path=str(item["relative_path"]),
                sha256=str(item["sha256"]).lower(),
                required=bool(item.get("required", True)),
            )
            for item in raw["files"]
        )
        manifest = CodeAsterPayloadManifest(
            schema_version=int(raw["schema_version"]),
            engine=str(raw["engine"]),
            platform=str(raw["platform"]),
            architecture=str(raw["architecture"]),
            code_aster_version=str(raw["code_aster_version"]),
            distribution_id=str(raw["distribution_id"]),
            files=files,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_MANIFEST_INVALID") from exc

    manifest.validate()
    return manifest


def verify_payload_tree(
    root: str | os.PathLike[str],
    manifest: CodeAsterPayloadManifest,
) -> dict[str, object]:
    manifest.validate()
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_ROOT_NOT_FOUND")

    verified: list[dict[str, str]] = []
    missing_optional: list[str] = []
    for item in manifest.files:
        candidate = (root_path / item.relative_path).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError as exc:
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_PATH_ESCAPE") from exc

        if not candidate.is_file():
            if item.required:
                raise CodeAsterPayloadError(f"CODE_ASTER_PAYLOAD_REQUIRED_FILE_MISSING:{item.relative_path}")
            missing_optional.append(item.relative_path)
            continue

        actual = _sha256_file(candidate)
        if actual.lower() != item.sha256.lower():
            raise CodeAsterPayloadError(f"CODE_ASTER_PAYLOAD_HASH_MISMATCH:{item.relative_path}")
        verified.append({"relative_path": item.relative_path, "sha256": actual})

    manifest_bytes = json.dumps(
        manifest.to_json_dict(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_sha = sha256(manifest_bytes).hexdigest()
    return {
        "engine": manifest.engine,
        "platform": manifest.platform,
        "architecture": manifest.architecture,
        "code_aster_version": manifest.code_aster_version,
        "distribution_id": manifest.distribution_id,
        "manifest_sha256": manifest_sha,
        "verified_file_count": len(verified),
        "missing_optional": missing_optional,
        "payload_integrity_verified": True,
        "fea_solve_executed": False,
    }


def build_manifest_for_tree(
    root: str | os.PathLike[str],
    relative_paths: Iterable[str],
    *,
    code_aster_version: str,
    distribution_id: str,
    architecture: str = "x86_64",
) -> CodeAsterPayloadManifest:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_ROOT_NOT_FOUND")
    files: list[PayloadFile] = []
    for relative in relative_paths:
        candidate = (root_path / relative).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError as exc:
            raise CodeAsterPayloadError("CODE_ASTER_PAYLOAD_PATH_ESCAPE") from exc
        if not candidate.is_file():
            raise CodeAsterPayloadError(f"CODE_ASTER_PAYLOAD_REQUIRED_FILE_MISSING:{relative}")
        files.append(PayloadFile(relative_path=relative, sha256=_sha256_file(candidate)))
    manifest = CodeAsterPayloadManifest(
        schema_version=1,
        engine="CODE_ASTER_NATIVE_WINDOWS",
        platform="windows-native",
        architecture=architecture,
        code_aster_version=code_aster_version,
        distribution_id=distribution_id,
        files=tuple(files),
    )
    manifest.validate()
    return manifest
