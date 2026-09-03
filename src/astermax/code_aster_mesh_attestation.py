from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .credibility import canonical_sha256


class CodeAsterMeshAttestationError(RuntimeError):
    pass


def _require_file(path: Path, code: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise CodeAsterMeshAttestationError(code)
    return path


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, code: str) -> dict[str, object]:
    _require_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CodeAsterMeshAttestationError(f"{code}_INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise CodeAsterMeshAttestationError(f"{code}_NOT_OBJECT")
    return value


def _require_hex64(value: object, code: str) -> str:
    text = str(value or "").lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise CodeAsterMeshAttestationError(code)
    return text


@dataclass(frozen=True)
class MeshChainOfCustodyEvidence:
    med_sha256: str
    quality_report_sha256: str
    quality_artifact_sha256: str
    reference_case_evidence_sha256: str
    mesh_quality_gate_passed: bool
    all_sampled_jacobians_positive: bool
    length_unit: str
    solver_unit_system: str
    mesh_attested_immediately_before_solve: bool
    fea_solve_executed: bool
    numerical_verification: bool
    results_verified: bool
    industrial_validation: bool
    ansys_equivalence: bool

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def attest_reference_mesh_before_solve(
    directory: str | Path,
    *,
    med_filename: str = "astermax.med",
    quality_filename: str = "reference_mesh_quality.json",
    case_evidence_filename: str = "reference_case_evidence.json",
) -> MeshChainOfCustodyEvidence:
    """Re-attest the exact quality-gated MED immediately before solver launch.

    The quality report is independently re-hashed canonically, its serialized
    artifact hash must match the case evidence, and the current MED bytes must
    match the MED hash recorded by the quality-gated preparation stage. This
    gate cannot create solver, numerical-verification or ANSYS claims.
    """
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_DIRECTORY_NOT_FOUND")
    for name, code in (
        (med_filename, "MESH_ATTESTATION_MED_FILENAME_INVALID"),
        (quality_filename, "MESH_ATTESTATION_QUALITY_FILENAME_INVALID"),
        (case_evidence_filename, "MESH_ATTESTATION_CASE_FILENAME_INVALID"),
    ):
        if Path(name).name != name:
            raise CodeAsterMeshAttestationError(code)

    med = _require_file(root / med_filename, "MESH_ATTESTATION_MED_MISSING")
    quality_path = root / quality_filename
    case_path = root / case_evidence_filename
    quality = _load_json(quality_path, "MESH_ATTESTATION_QUALITY_MISSING")
    case = _load_json(case_path, "MESH_ATTESTATION_CASE_EVIDENCE_MISSING")

    if case.get("units") != {"length": "mm", "force": "N", "stress": "MPa"}:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_UNIT_CONTRACT_MISMATCH")
    if case.get("mesh_quality_gate_passed") is not True:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_QUALITY_GATE_NOT_PASSED")
    if quality.get("solver_gate_passed") is not True:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_QUALITY_ARTIFACT_NOT_PASSED")
    if quality.get("all_sampled_jacobians_positive") is not True:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_JACOBIAN_NOT_POSITIVE")
    if quality.get("length_unit") != "mm":
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_LENGTH_UNIT_NOT_MM")
    if quality.get("ansys_metric_equivalence") is not False:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_ANSYS_EQUIVALENCE_CLAIM_FORBIDDEN")

    for key in ("fea_solve_executed", "numerical_verification", "results_verified"):
        if quality.get(key) is not False:
            raise CodeAsterMeshAttestationError(f"MESH_ATTESTATION_QUALITY_{key.upper()}_CLAIM_FORBIDDEN")
        if case.get(key) is not False:
            raise CodeAsterMeshAttestationError(f"MESH_ATTESTATION_CASE_{key.upper()}_CLAIM_FORBIDDEN")

    quality_report_sha = _require_hex64(
        quality.get("report_sha256"),
        "MESH_ATTESTATION_QUALITY_REPORT_HASH_INVALID",
    )
    quality_core = dict(quality)
    quality_core.pop("report_sha256", None)
    if canonical_sha256(quality_core) != quality_report_sha:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_QUALITY_REPORT_CANONICAL_HASH_MISMATCH")

    actual_med_sha = _sha256(med)
    expected_med_sha = _require_hex64(case.get("med_sha256"), "MESH_ATTESTATION_CASE_MED_HASH_INVALID")
    if actual_med_sha != expected_med_sha:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_MED_HASH_MISMATCH")

    actual_quality_artifact_sha = _sha256(quality_path)
    expected_quality_artifact_sha = _require_hex64(
        case.get("mesh_quality_artifact_sha256"),
        "MESH_ATTESTATION_QUALITY_ARTIFACT_HASH_INVALID",
    )
    if actual_quality_artifact_sha != expected_quality_artifact_sha:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_QUALITY_ARTIFACT_HASH_MISMATCH")

    case_quality_report_sha = _require_hex64(
        case.get("mesh_quality_report_sha256"),
        "MESH_ATTESTATION_CASE_QUALITY_REPORT_HASH_INVALID",
    )
    if quality_report_sha != case_quality_report_sha:
        raise CodeAsterMeshAttestationError("MESH_ATTESTATION_QUALITY_REPORT_HASH_MISMATCH")

    return MeshChainOfCustodyEvidence(
        med_sha256=actual_med_sha,
        quality_report_sha256=quality_report_sha,
        quality_artifact_sha256=actual_quality_artifact_sha,
        reference_case_evidence_sha256=_sha256(case_path),
        mesh_quality_gate_passed=True,
        all_sampled_jacobians_positive=True,
        length_unit="mm",
        solver_unit_system="mm-N-MPa",
        mesh_attested_immediately_before_solve=True,
        fea_solve_executed=False,
        numerical_verification=False,
        results_verified=False,
        industrial_validation=False,
        ansys_equivalence=False,
    )
