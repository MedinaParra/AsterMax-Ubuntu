from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .evidence import canonical_sha256, sha256_bytes, sha256_file


def tet10_mesh_fingerprint(nodes_mm: np.ndarray, elements: np.ndarray) -> str:
    nodes = np.asarray(nodes_mm, dtype="<f8")
    elems = np.asarray(elements, dtype="<i8")
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")
    if not np.all(np.isfinite(nodes)):
        raise ValueError("mesh coordinates must be finite")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("TET10 connectivity contains an out-of-range node index")
    header = {
        "schema": "AsterMaxTet10MeshFingerprintV1",
        "nodes_shape": list(nodes.shape),
        "elements_shape": list(elems.shape),
        "coordinate_dtype": "float64-little-endian",
        "connectivity_dtype": "int64-little-endian",
        "units": "mm",
        "element": "TET10_GMSH_TYPE_11",
        "node_order": "GMSH_TETRAHEDRON10",
    }
    canonical = __import__("json").dumps(
        header,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(canonical + b"\0" + nodes.tobytes(order="C") + b"\0" + elems.tobytes(order="C"))


@dataclass(frozen=True)
class Tet10EvidenceArtifact:
    role: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Tet10AnalysisEvidenceManifest:
    schema_version: str
    classification: str
    analysis_type: str
    units: dict[str, str]
    source: dict[str, Any]
    mesh: dict[str, Any]
    analysis_definition: dict[str, Any]
    solver: dict[str, Any]
    claims: dict[str, bool]
    artifacts: list[Tet10EvidenceArtifact]
    chain_sha256: str


def _artifact(root: Path, relative_path: str | Path, role: str) -> Tet10EvidenceArtifact:
    path = (root / Path(relative_path)).resolve()
    try:
        relative = path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("TET10 evidence artifact must be inside package_dir") from exc
    if not path.is_file():
        raise ValueError(f"missing TET10 evidence artifact: {relative}")
    return Tet10EvidenceArtifact(
        role=str(role),
        relative_path=relative.as_posix(),
        sha256=sha256_file(path),
        size_bytes=int(path.stat().st_size),
    )


def _source_record(root: Path, source_path: str | Path | None, source_kind: str) -> dict[str, Any]:
    if source_path is None:
        return {"kind": str(source_kind), "path": None, "sha256": None, "size_bytes": None}
    path = Path(source_path).resolve()
    try:
        relative = path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("source_path must be staged inside package_dir") from exc
    if not path.is_file():
        raise ValueError("source_path must reference an existing file")
    return {
        "kind": str(source_kind),
        "path": relative.as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": int(path.stat().st_size),
    }


def write_tet10_analysis_evidence_manifest(
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
) -> Tet10AnalysisEvidenceManifest:
    """Write a deterministic TET10 evidence chain without re-labelling TET4 data."""
    import json

    root = Path(package_dir)
    root.mkdir(parents=True, exist_ok=True)
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    mesh_hash = tet10_mesh_fingerprint(nodes, elems)
    source = _source_record(root, source_path, source_kind)
    artifact_records = [_artifact(root, path, role) for path, role in artifacts]
    if len({item.relative_path for item in artifact_records}) != len(artifact_records):
        raise ValueError("artifact paths must be unique")
    if len({item.role for item in artifact_records}) != len(artifact_records):
        raise ValueError("artifact roles must be unique")

    analysis_hash = canonical_sha256(analysis_definition)
    solver_hash = canonical_sha256(solver_identity)
    claims = {
        "converged": bool(converged_claim),
        "industrial_validation": bool(industrial_validation_claim),
    }
    chain_payload = {
        "schema_version": "AsterMaxTet10AnalysisEvidenceV1",
        "classification": str(classification),
        "analysis_type": "LINEAR_STATIC_3D_TET10",
        "units": {"length": "mm", "force": "N", "stress": "MPa", "moment": "N*mm"},
        "source": source,
        "mesh": {
            "fingerprint_sha256": mesh_hash,
            "nodes": int(nodes.shape[0]),
            "tet10": int(elems.shape[0]),
            "gmsh_element_type": 11,
            "vtk_cell_type": 24,
            "node_order": "GMSH_TETRAHEDRON10",
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
        "artifacts": [asdict(item) for item in artifact_records],
    }
    chain_hash = canonical_sha256(chain_payload)
    manifest = Tet10AnalysisEvidenceManifest(
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
