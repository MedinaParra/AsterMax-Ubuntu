import hashlib
import json

import pytest

from astermax.credibility import ClaimEngine, ClaimState, ConsequenceLevel, ContextOfUse, EvidenceGraph, EvidenceSource
from astermax.fea.authorized_empirical_dataset import (
    AuthorizedEmpiricalDatasetError,
    authorization_declaration_evidence,
    authorized_dataset_intake_evidence,
    build_authorized_dataset_manifest,
    empirical_dataset_intake_claim,
    ingest_authorized_stress_concentration_dataset,
)
from astermax.fea.stress_concentration_source import build_stress_concentration_source, source_provenance_evidence


def _source():
    return build_stress_concentration_source(
        source_id="SYNTHETIC_C15_SOURCE",
        title="Synthetic C15 verification dataset",
        edition_or_release="1",
        publisher="AsterMax verification suite",
        locator="tests/test_authorized_empirical_dataset.py",
        source_url="https://example.invalid/astermax-c15-synthetic",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA_NOT_PHYSICAL",
        calculation_data_embedded=False,
    )


def _payload(source):
    return {
        "schema": "AsterMaxStressConcentrationDatasetV1",
        "dataset_id": "SYNTHETIC_C15_GRID",
        "factor_name": "Kt_SYNTHETIC_NOT_PHYSICAL",
        "load_mode": "AXIAL_TENSION",
        "source_provenance_sha256": source.provenance_sha256,
        "diameter_ratios": [1.5, 2.0],
        "radius_ratios": [0.05, 0.10],
        "factors": [[101.0, 102.0], [201.0, 202.0]],
    }


def _write(tmp_path, source, payload=None):
    path = tmp_path / "synthetic_c15.json"
    data = _payload(source) if payload is None else payload
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _manifest(source, file_sha, **overrides):
    values = dict(
        manifest_id="C15_SYNTHETIC_MANIFEST",
        dataset_filename="synthetic_c15.json",
        expected_file_sha256=file_sha,
        source_provenance_sha256=source.provenance_sha256,
        authorization_basis="SYNTHETIC_VERIFICATION",
        rights_reference="AsterMax synthetic CI fixture; no physical values",
        attested_by="ASTERMAX_TEST_SUITE",
        authorized_for_calculation=True,
    )
    values.update(overrides)
    return build_authorized_dataset_manifest(**values)


def test_valid_synthetic_dataset_is_hash_bound_and_claim_permitted(tmp_path):
    source = _source()
    path, file_sha = _write(tmp_path, source)
    manifest = _manifest(source, file_sha)
    intake, grid = ingest_authorized_stress_concentration_dataset(path, manifest, source)
    assert intake.raw_file_sha256 == file_sha
    assert intake.grid_dataset_sha256 == grid.dataset_sha256
    assert intake.synthetic_verification_only is True
    assert grid.factors[0][1] == 102.0

    context = ContextOfUse(
        context_id="COU_C15_TEST",
        engineering_question="Did the exact synthetic dataset pass the authorized intake protocol?",
        intended_decision="Permit software verification only; never treat synthetic factors as physical Kt data.",
        quantities_of_interest=("dataset integrity", "authorization provenance"),
        acceptance_criteria=("exact byte hash", "strict schema", "source binding"),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("synthetic test fixture",),
    )
    graph = EvidenceGraph(context)
    for record in (
        source_provenance_evidence(source),
        authorization_declaration_evidence(manifest),
        authorized_dataset_intake_evidence(intake),
    ):
        graph.add(record)
    decision = ClaimEngine.evaluate(empirical_dataset_intake_claim(context.context_id), graph)
    assert decision.state is ClaimState.PERMITTED


def test_mutated_file_is_rejected_before_semantic_use(tmp_path):
    source = _source()
    path, file_sha = _write(tmp_path, source)
    manifest = _manifest(source, file_sha)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(AuthorizedEmpiricalDatasetError, match="SHA256_MISMATCH"):
        ingest_authorized_stress_concentration_dataset(path, manifest, source)


def test_unauthorized_manifest_is_rejected(tmp_path):
    source = _source()
    path, file_sha = _write(tmp_path, source)
    manifest = _manifest(source, file_sha, authorized_for_calculation=False)
    with pytest.raises(AuthorizedEmpiricalDatasetError, match="NOT_AUTHORIZED"):
        ingest_authorized_stress_concentration_dataset(path, manifest, source)
    evidence = authorization_declaration_evidence(manifest)
    assert evidence.claim_grade is False


def test_payload_source_mismatch_is_rejected(tmp_path):
    source = _source()
    data = _payload(source)
    data["source_provenance_sha256"] = "0" * 64
    path, file_sha = _write(tmp_path, source, data)
    manifest = _manifest(source, file_sha)
    with pytest.raises(AuthorizedEmpiricalDatasetError, match="PAYLOAD_SOURCE_PROVENANCE_MISMATCH"):
        ingest_authorized_stress_concentration_dataset(path, manifest, source)


def test_extra_schema_key_is_rejected(tmp_path):
    source = _source()
    data = _payload(source)
    data["unreviewed_note"] = "must not be silently ignored"
    path, file_sha = _write(tmp_path, source, data)
    manifest = _manifest(source, file_sha)
    with pytest.raises(AuthorizedEmpiricalDatasetError, match="SCHEMA_KEYS_MISMATCH"):
        ingest_authorized_stress_concentration_dataset(path, manifest, source)


def test_user_rights_attestation_remains_human_sourced(tmp_path):
    source = _source()
    _, file_sha = _write(tmp_path, source)
    manifest = _manifest(
        source,
        file_sha,
        authorization_basis="USER_SUPPLIED_WITH_RIGHTS_ATTESTATION",
        rights_reference="User states they possess calculation rights for the exact file",
        attested_by="USER",
    )
    evidence = authorization_declaration_evidence(manifest)
    assert evidence.source is EvidenceSource.HUMAN_CONFIRMED
    assert evidence.claim_grade is True


def test_manifest_source_binding_mismatch_hard_fails(tmp_path):
    source = _source()
    path, file_sha = _write(tmp_path, source)
    manifest = _manifest(source, file_sha, source_provenance_sha256="1" * 64)
    with pytest.raises(AuthorizedEmpiricalDatasetError, match="MANIFEST_SOURCE_PROVENANCE_MISMATCH"):
        ingest_authorized_stress_concentration_dataset(path, manifest, source)
