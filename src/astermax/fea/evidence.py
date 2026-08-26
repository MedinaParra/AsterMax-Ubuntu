from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
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
    """Write a deterministic, hash-chained evidence manifest.

    The chain is tamper-evident, not cryptographically signed. A future release may
    attach a digital signature to the manifest hash without changing solver output.
    """
    root = Path(package_dir)
    root.mkdir(parents=True, exist_ok=True)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    mesh_hash = mesh_fingerprint(nodes, elems)

    if source_path is None:
        source = {
            "kind": str(source_kind),
            "path": None,
            "sha256": None,
        }
    else:
        source_file = Path(source_path)
        if not source_file.is_file():
            raise ValueError("source_path must reference an existing file")
        source = {
            "kind": str(source_kind),
            "path": source_file.name,
            "sha256": sha256_file(source_file),
        }

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
        "schema_version": "AsterMaxAnalysisEvidenceV1",
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

    chain_payload = {key: value for key, value in payload.items() if key != "chain_sha256"}
    chain_ok = canonical_sha256(chain_payload) == payload.get("chain_sha256")
    return {
        "schema_version": payload.get("schema_version"),
        "chain_ok": bool(chain_ok),
        "artifacts_ok": not artifact_errors,
        "artifact_errors": artifact_errors,
        "valid": bool(chain_ok and not artifact_errors),
        "chain_sha256": payload.get("chain_sha256"),
    }
