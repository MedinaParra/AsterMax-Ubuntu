from hashlib import sha256
import json
from pathlib import Path

import pytest

from astermax.code_aster_genuine_bundle import (
    GenuineReferenceBundleError,
    prepare_genuine_reference_bundle,
    validate_genuine_reference_bundle,
)
from astermax.code_aster_reference_harness import UniaxialPrismSpec


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _install_base_preparer(monkeypatch, root: Path):
    def fake_prepare(spec, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        (target / "astermax.med").write_bytes(b"MED-C8.20-STRUCTURE-WITNESS")
        quality = {
            "solver_gate_passed": True,
            "all_sampled_jacobians_positive": True,
            "length_unit": "mm",
            "ansys_metric_equivalence": False,
            "fea_solve_executed": False,
            "numerical_verification": False,
            "results_verified": False,
        }
        qpath = target / "reference_mesh_quality.json"
        qpath.write_text(json.dumps(quality, sort_keys=True), encoding="utf-8")
        base = {
            "case": "3D_UNIAXIAL_PRISM_TET10",
            "units": {"length": "mm", "force": "N", "stress": "MPa"},
            "mesh_quality_gate_passed": True,
            "mesh_quality_artifact_sha256": _sha(qpath),
            "mesh_quality_report_sha256": "a" * 64,
            "med_sha256": _sha(target / "astermax.med"),
            "comm_sha256": "b" * 64,
            "fea_solve_executed": False,
            "numerical_verification": False,
            "results_verified": False,
        }
        (target / "astermax.comm").write_text("legacy generic command", encoding="utf-8")
        (target / "reference_case_evidence.json").write_text(json.dumps(base, sort_keys=True), encoding="utf-8")
        return base

    monkeypatch.setattr("astermax.code_aster_genuine_bundle.prepare_reference_solver_bundle", fake_prepare)


def test_genuine_bundle_binds_every_artifact_required_by_reference_run(tmp_path: Path, monkeypatch):
    _install_base_preparer(monkeypatch, tmp_path)
    evidence = prepare_genuine_reference_bundle(UniaxialPrismSpec(), tmp_path)
    readiness = validate_genuine_reference_bundle(tmp_path)

    comm = (tmp_path / "astermax.comm").read_text(encoding="utf-8")
    export = (tmp_path / "astermax.export").read_text(encoding="utf-8")
    assert "FORCE=('REAC_NODA',)" in comm
    assert "POST_RELEVE_T" in comm
    assert "IMPR_TABLE" in comm
    assert "SIEQ_NOEU" in comm
    assert "F rmed astermax_result.med R 80" in export
    assert "F mess astermax.mess R 6" in export
    assert "F libr reference_displacement.table R 91" in export
    assert "F libr reference_reaction.table R 92" in export
    assert "F libr reference_stress.table R 93" in export
    assert evidence["verification_tables_bound"] is True
    assert evidence["solver_message_bound"] is True
    assert readiness["pre_solve_bundle_valid"] is True
    assert readiness["solver_message_bound"] is True
    assert readiness["fea_solve_executed"] is False
    assert readiness["numerical_verification"] is False
    assert readiness["results_verified"] is False
    assert readiness["ansys_equivalence"] is False


def test_comm_mutation_after_preparation_fails_closed(tmp_path: Path, monkeypatch):
    _install_base_preparer(monkeypatch, tmp_path)
    prepare_genuine_reference_bundle(UniaxialPrismSpec(), tmp_path)
    with (tmp_path / "astermax.comm").open("a", encoding="utf-8") as stream:
        stream.write("\n# mutation")
    with pytest.raises(GenuineReferenceBundleError, match="COMM_HASH_MISMATCH"):
        validate_genuine_reference_bundle(tmp_path)


def test_export_mutation_after_preparation_fails_closed(tmp_path: Path, monkeypatch):
    _install_base_preparer(monkeypatch, tmp_path)
    prepare_genuine_reference_bundle(UniaxialPrismSpec(), tmp_path)
    with (tmp_path / "astermax.export").open("a", encoding="utf-8") as stream:
        stream.write("\n# mutation")
    with pytest.raises(GenuineReferenceBundleError, match="EXPORT_HASH_MISMATCH"):
        validate_genuine_reference_bundle(tmp_path)


def test_med_mutation_after_preparation_fails_closed(tmp_path: Path, monkeypatch):
    _install_base_preparer(monkeypatch, tmp_path)
    prepare_genuine_reference_bundle(UniaxialPrismSpec(), tmp_path)
    (tmp_path / "astermax.med").write_bytes(b"changed")
    with pytest.raises(GenuineReferenceBundleError, match="MED_HASH_MISMATCH"):
        validate_genuine_reference_bundle(tmp_path)


def test_pre_solve_evidence_cannot_promote_solver_or_ansys_claims(tmp_path: Path, monkeypatch):
    _install_base_preparer(monkeypatch, tmp_path)
    prepare_genuine_reference_bundle(UniaxialPrismSpec(), tmp_path)
    case_path = tmp_path / "reference_case_evidence.json"
    raw = json.loads(case_path.read_text(encoding="utf-8"))
    raw["fea_solve_executed"] = True
    raw["ansys_equivalence"] = True
    case_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    with pytest.raises(GenuineReferenceBundleError, match="PRE_SOLVE_CLAIM_FORBIDDEN"):
        validate_genuine_reference_bundle(tmp_path)
