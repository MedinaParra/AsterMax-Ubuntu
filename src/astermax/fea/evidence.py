from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(_canonical_bytes(value))


def mesh_fingerprint(nodes_mm: np.ndarray, elements: np.ndarray) -> str:
    nodes = np.asarray(nodes_mm, dtype="<f8")
    elems = np.asarray(elements, dtype="<i8")
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 4:
        raise ValueError("elements must have shape (m, 4)")
    if not np.all(np.isfinite(nodes)):
        raise ValueError("mesh coordinates must be finite")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")
    header = _canonical_bytes(
        {
            "schema": "AsterMaxMeshFingerprintV1",
            "nodes_shape": list(nodes.shape),
            "elements_shape": list(elems.shape),
            "coordinate_dtype": "float64-little-endian",
            "connectivity_dtype": "int64-little-endian",
            "units": "mm",
            "element": "TET4",
        }
    )
    return sha256_bytes(header + b"\0" + nodes.tobytes(order="C") + b"\0" + elems.tobytes(order="C"))


def stage_source_file(
    package_dir: str | Path,
    source_path: str | Path,
    *,
    target_name: str | None = None,
) -> Path:
    """Copy an immutable input snapshot into the evidence package.

    The staged file is the source that the evidence manifest subsequently hashes
    and verifies.  This prevents a manifest from pointing at an external CAD file
    whose bytes can change independently of the published package.
    """
    root = Path(package_dir)
    root.mkdir(parents=True, exist_ok=True)
    source = Path(source_path)
    if not source.is_file():
        raise ValueError("source_path must reference an existing file")
    name = target_name or source.name
    if Path(name).name != name or not name:
        raise ValueError("target_name must be a plain file name")
    target = root / name
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target


@dataclass(frozen=True)
class EvidenceArtifact:
    role: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class AnalysisEvidenceManifest:
    schema_version: str
    classification: str
    analysis_type: str
    units: dict[str, str]
    source: dict[str, Any]
    mesh: dict[str, Any]
    analysis_definition: dict[str, Any]
    solver: dict[str, Any]
    claims: dict[str, bool]
    artifacts: list[EvidenceArtifact]
    chain_sha256: str


def _artifact(package_dir: Path, path: Path, role: str) -> EvidenceArtifact:
    resolved_package = package_dir.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_package)
    except ValueError as exc:
        raise ValueError("evidence artifact must be inside package_dir") from exc
    if not resolved_path.is_file():
        raise ValueError(f"missing evidence artifact: {relative}")
    return EvidenceArtifact(
        role=str(role),
        relative_path=relative.as_posix(),
        sha256=sha256_file(resolved_path),
        size_bytes=int(resolved_path.stat().st_size),
    )


def _source_record(root: Path, source_path: str | Path | None, source_kind: str) -> dict[str, Any]:
    if source_path is None:
        return {"kind": str(source_kind), "path": None, "sha256": None, "size_bytes": None}
    source_file = Path(source_path).resolve()
    try:
        relative = source_file.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("source_path must be staged inside package_dir before manifest generation") from exc
    if not source_file.is_file():
        raise ValueError("source_path must reference an existing file")
    return {
        "kind": str(source_kind),
        "path": relative.as_posix(),
        "sha256": sha256_file(source_file),
        "size_bytes": int(source_file.stat().st_size),
    }


def write_analysis_evidence_manifest(
    package_dir: str | Path,
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    analysis_definition: dict[str, Any],
    solver_identity: dict[str, Any],
    artifacts: list[tuple[str | Path, str]],
    source_path: str | Path | None = None,
    source_kind: str = "SYNTHETIC_VERIFICATION_FIXTURE",
    classification: str = "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
    converged_claim: bool = False,
    industrial_validation_claim: bool = False,
) -> AnalysisEvidenceManifest:
    """Write a deterministic, tamper-evident analysis manifest.

    Source CAD must be staged inside ``package_dir``.  The source bytes, mesh,
    analysis definition, solver identity and result artifacts are all covered by
    the root chain hash.  This is integrity evidence, not a digital signature.
    """
    root = Path(package_dir)
    root.mkdir(parents=True, exist_ok=True)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    mesh_hash = mesh_fingerprint(nodes, elems)
    source = _source_record(root, source_path, source_kind)

    artifact_records = [_artifact(root, root / Path(path), role) for path, role in artifacts]
    if len({a.relative_path for a in artifact_records}) != len(artifact_records):
        raise ValueError("artifact paths must be unique")
    if len({a.role for a in artifact_records}) != len(artifact_records):
        raise ValueError("artifact roles must be unique")

    analysis_hash = canonical_sha256(analysis_definition)
    solver_hash = canonical_sha256(solver_identity)
    claims = {
        "converged": bool(converged_claim),
        "industrial_validation": bool(industrial_validation_claim),
    }
    chain_payload = {
        "schema_version": "AsterMaxAnalysisEvidenceV2",
        "classification": str(classification),
        "analysis_type": "LINEAR_STATIC_3D_TET4",
        "units": {"length": "mm", "force": "N", "stress": "MPa", "moment": "N*mm"},
        "source": source,
        "mesh": {
            "fingerprint_sha256": mesh_hash,
            "nodes": int(nodes.shape[0]),
            "tet4": int(elems.shape[0]),
        },
        "analysis_definition": {
            "sha256": analysis_hash,
            "canonical": analysis_definition,
        },
        "solver": {
            "sha256": solver_hash,
            "identity": solver_identity,
        },
        "claims": claims,
        "artifacts": [asdict(a) for a in artifact_records],
    }
    chain_hash = canonical_sha256(chain_payload)
    manifest = AnalysisEvidenceManifest(
        schema_version=chain_payload["schema_version"],
        classification=chain_payload["classification"],
        analysis_type=chain_payload["analysis_type"],
        units=chain_payload["units"],
        source=source,
        mesh=chain_payload["mesh"],
        analysis_definition=chain_payload["analysis_definition"],
        solver=chain_payload["solver"],
        claims=claims,
        artifacts=artifact_records,
        chain_sha256=chain_hash,
    )
    (root / "analysis_evidence.json").write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_analysis_evidence_manifest(package_dir: str | Path) -> dict[str, Any]:
    root = Path(package_dir)
    manifest_path = root / "analysis_evidence.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    artifact_errors: list[str] = []
    for item in payload.get("artifacts", []):
        path = root / item["relative_path"]
        if not path.is_file():
            artifact_errors.append(f"missing:{item['relative_path']}")
            continue
        actual = sha256_file(path)
        if actual != item["sha256"]:
            artifact_errors.append(f"sha256:{item['relative_path']}")
        if int(path.stat().st_size) != int(item["size_bytes"]):
            artifact_errors.append(f"size:{item['relative_path']}")

    source_errors: list[str] = []
    source = payload.get("source", {})
    source_path = source.get("path")
    if source_path is not None:
        path = root / source_path
        if not path.is_file():
            source_errors.append(f"missing:{source_path}")
        else:
            if sha256_file(path) != source.get("sha256"):
                source_errors.append(f"sha256:{source_path}")
            expected_size = source.get("size_bytes")
            if expected_size is not None and int(path.stat().st_size) != int(expected_size):
                source_errors.append(f"size:{source_path}")

    chain_payload = {key: value for key, value in payload.items() if key != "chain_sha256"}
    chain_ok = canonical_sha256(chain_payload) == payload.get("chain_sha256")
    valid = bool(chain_ok and not artifact_errors and not source_errors)
    return {
        "schema_version": payload.get("schema_version"),
        "chain_ok": bool(chain_ok),
        "artifacts_ok": not artifact_errors,
        "source_ok": not source_errors,
        "artifact_errors": artifact_errors,
        "source_errors": source_errors,
        "valid": valid,
        "chain_sha256": payload.get("chain_sha256"),
    }
