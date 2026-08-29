from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .bounded_stress_concentration import StressConcentrationGrid, build_stress_concentration_grid
from .stress_concentration_source import StressConcentrationSource


class AuthorizedEmpiricalDatasetError(ValueError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_BASES = frozenset({
    "PUBLIC_DOMAIN",
    "LICENSED",
    "USER_SUPPLIED_WITH_RIGHTS_ATTESTATION",
    "SYNTHETIC_VERIFICATION",
})
_DATASET_SCHEMA = "AsterMaxStressConcentrationDatasetV1"
_DATASET_KEYS = frozenset({
    "schema",
    "dataset_id",
    "factor_name",
    "load_mode",
    "source_provenance_sha256",
    "diameter_ratios",
    "radius_ratios",
    "factors",
})


@dataclass(frozen=True)
class AuthorizedDatasetManifest:
    schema: str
    manifest_id: str
    dataset_filename: str
    expected_file_sha256: str
    source_provenance_sha256: str
    authorization_basis: str
    rights_reference: str
    attested_by: str
    authorized_for_calculation: bool
    manifest_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_sha256")
        return payload


@dataclass(frozen=True)
class AuthorizedStressConcentrationDataset:
    schema: str
    manifest_sha256: str
    source_provenance_sha256: str
    raw_file_sha256: str
    dataset_filename: str
    dataset_id: str
    factor_name: str
    load_mode: str
    grid_dataset_sha256: str
    authorization_basis: str
    synthetic_verification_only: bool
    intake_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("intake_sha256")
        return payload


def _text(name: str, value: str) -> str:
    clean = str(value).strip()
    if not clean:
        raise AuthorizedEmpiricalDatasetError(f"{name} must be non-empty")
    return clean


def _sha(name: str, value: str) -> str:
    clean = str(value).strip().lower()
    if not _SHA256_RE.fullmatch(clean):
        raise AuthorizedEmpiricalDatasetError(f"{name} must be a lowercase SHA-256 digest")
    return clean


def build_authorized_dataset_manifest(
    *,
    manifest_id: str,
    dataset_filename: str,
    expected_file_sha256: str,
    source_provenance_sha256: str,
    authorization_basis: str,
    rights_reference: str,
    attested_by: str,
    authorized_for_calculation: bool,
) -> AuthorizedDatasetManifest:
    clean_basis = _text("authorization_basis", authorization_basis).upper()
    if clean_basis not in _ALLOWED_BASES:
        raise AuthorizedEmpiricalDatasetError(f"unsupported authorization_basis: {clean_basis}")
    payload = {
        "schema": "AsterMaxAuthorizedDatasetManifestV1",
        "manifest_id": _text("manifest_id", manifest_id),
        "dataset_filename": _text("dataset_filename", dataset_filename),
        "expected_file_sha256": _sha("expected_file_sha256", expected_file_sha256),
        "source_provenance_sha256": _sha("source_provenance_sha256", source_provenance_sha256),
        "authorization_basis": clean_basis,
        "rights_reference": _text("rights_reference", rights_reference),
        "attested_by": _text("attested_by", attested_by),
        "authorized_for_calculation": bool(authorized_for_calculation),
    }
    return AuthorizedDatasetManifest(**payload, manifest_sha256=canonical_sha256(payload))


def _read_dataset(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AuthorizedEmpiricalDatasetError("DATASET_FILE_READ_FAILED") from exc
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthorizedEmpiricalDatasetError("DATASET_FILE_NOT_UTF8") from exc
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise AuthorizedEmpiricalDatasetError("DATASET_FILE_INVALID_JSON") from exc
    if not isinstance(data, dict):
        raise AuthorizedEmpiricalDatasetError("DATASET_ROOT_MUST_BE_OBJECT")
    return raw, data


def ingest_authorized_stress_concentration_dataset(
    dataset_path: str | Path,
    manifest: AuthorizedDatasetManifest,
    source: StressConcentrationSource,
) -> tuple[AuthorizedStressConcentrationDataset, StressConcentrationGrid]:
    path = Path(dataset_path)
    if path.name != manifest.dataset_filename:
        raise AuthorizedEmpiricalDatasetError("DATASET_FILENAME_MANIFEST_MISMATCH")
    if manifest.source_provenance_sha256 != source.provenance_sha256:
        raise AuthorizedEmpiricalDatasetError("DATASET_MANIFEST_SOURCE_PROVENANCE_MISMATCH")
    if not manifest.authorized_for_calculation:
        raise AuthorizedEmpiricalDatasetError("DATASET_NOT_AUTHORIZED_FOR_CALCULATION")

    raw, data = _read_dataset(path)
    raw_sha = hashlib.sha256(raw).hexdigest()
    if raw_sha != manifest.expected_file_sha256:
        raise AuthorizedEmpiricalDatasetError("DATASET_FILE_SHA256_MISMATCH")
    if frozenset(data.keys()) != _DATASET_KEYS:
        missing = sorted(_DATASET_KEYS - frozenset(data.keys()))
        extra = sorted(frozenset(data.keys()) - _DATASET_KEYS)
        raise AuthorizedEmpiricalDatasetError(f"DATASET_SCHEMA_KEYS_MISMATCH:missing={missing}:extra={extra}")
    if data.get("schema") != _DATASET_SCHEMA:
        raise AuthorizedEmpiricalDatasetError("DATASET_SCHEMA_VERSION_UNSUPPORTED")
    if str(data.get("source_provenance_sha256", "")).lower() != source.provenance_sha256:
        raise AuthorizedEmpiricalDatasetError("DATASET_PAYLOAD_SOURCE_PROVENANCE_MISMATCH")

    try:
        grid = build_stress_concentration_grid(
            dataset_id=_text("dataset_id", data["dataset_id"]),
            factor_name=_text("factor_name", data["factor_name"]),
            load_mode=_text("load_mode", data["load_mode"]),
            source_provenance_sha256=source.provenance_sha256,
            diameter_ratios=data["diameter_ratios"],
            radius_ratios=data["radius_ratios"],
            factors=data["factors"],
        )
    except (TypeError, ValueError) as exc:
        raise AuthorizedEmpiricalDatasetError(f"DATASET_SEMANTIC_VALIDATION_FAILED:{exc}") from exc

    payload = {
        "schema": "AsterMaxAuthorizedStressConcentrationDatasetV1",
        "manifest_sha256": manifest.manifest_sha256,
        "source_provenance_sha256": source.provenance_sha256,
        "raw_file_sha256": raw_sha,
        "dataset_filename": path.name,
        "dataset_id": grid.dataset_id,
        "factor_name": grid.factor_name,
        "load_mode": grid.load_mode,
        "grid_dataset_sha256": grid.dataset_sha256,
        "authorization_basis": manifest.authorization_basis,
        "synthetic_verification_only": manifest.authorization_basis == "SYNTHETIC_VERIFICATION",
    }
    return (
        AuthorizedStressConcentrationDataset(**payload, intake_sha256=canonical_sha256(payload)),
        grid,
    )


def authorization_declaration_evidence(manifest: AuthorizedDatasetManifest) -> EvidenceRecord:
    if manifest.authorization_basis == "SYNTHETIC_VERIFICATION":
        source = EvidenceSource.DETERMINISTIC_CHECK
    else:
        source = EvidenceSource.HUMAN_CONFIRMED
    return EvidenceRecord(
        evidence_id=f"DATASET_AUTH:{manifest.manifest_id}",
        kind="EMPIRICAL_DATASET_AUTHORIZATION_DECLARATION",
        status=EvidenceStatus.VERIFIED if manifest.authorized_for_calculation else EvidenceStatus.CONTRADICTED,
        source=source,
        description=(
            "Declared authorization basis for using this exact empirical dataset in calculations. "
            "For human/licensed inputs this records attestation provenance; it is not independent legal verification."
        ),
        payload_sha256=manifest.manifest_sha256,
        metadata=manifest.canonical_without_hash(),
    )


def authorized_dataset_intake_evidence(intake: AuthorizedStressConcentrationDataset) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"DATASET_INTAKE:{intake.dataset_id}:{intake.intake_sha256[:16]}",
        kind="AUTHORIZED_EMPIRICAL_DATASET_INTAKE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Exact dataset bytes, schema, source provenance and semantic stress-concentration grid passed deterministic intake checks."
        ),
        payload_sha256=intake.intake_sha256,
        metadata=intake.canonical_without_hash(),
    )


def empirical_dataset_intake_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_EMPIRICAL_DATASET_ACCEPTED_FOR_CALCULATION",
        context_id=context_id,
        statement=(
            "The exact stress-concentration dataset passed AsterMax byte-integrity, schema, source-binding and declared-authorization intake controls."
        ),
        requirements=(
            ClaimRequirement(
                "STRESS_CONCENTRATION_SOURCE_PROVENANCE",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "EMPIRICAL_DATASET_AUTHORIZATION_DECLARATION",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK, EvidenceSource.HUMAN_CONFIRMED),
            ),
            ClaimRequirement(
                "AUTHORIZED_EMPIRICAL_DATASET_INTAKE",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )
