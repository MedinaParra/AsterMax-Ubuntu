from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json

from .code_aster_reference_run import GenuineReferenceSolveEvidence


class ProfessionalEvidenceBundleError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _require_file(path: Path, code: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ProfessionalEvidenceBundleError(code)
    return path


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class EvidenceArtifact:
    role: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ProfessionalEvidenceBundle:
    schema_version: str
    engine_kind: str
    distribution: str
    detected_version: str | None
    cad_length_unit: str
    solver_unit_system: str
    runtime_qualified: bool
    runtime_attested_immediately_before_solve: bool
    fea_solve_executed: bool
    numerical_verification: bool
    results_verified: bool
    industrial_validation: bool
    ansys_equivalence: bool
    run_aster_sha256: str
    config_sha256: str
    ux_relative_error: float
    reaction_relative_error: float
    stress_relative_error: float
    artifacts: tuple[EvidenceArtifact, ...]
    manifest_sha256: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["artifacts"] = [asdict(item) for item in self.artifacts]
        return payload


def _expected_artifacts(evidence: GenuineReferenceSolveEvidence) -> tuple[tuple[str, str, str], ...]:
    return (
        ("code_aster_export", "astermax.export", evidence.export_sha256),
        ("code_aster_command", "astermax.comm", evidence.command_sha256),
        ("input_med", "astermax.med", evidence.input_med_sha256),
        ("result_med", "astermax_result.med", evidence.result_med_sha256),
        ("solver_message", "astermax.mess", evidence.message_sha256),
        ("displacement_table", "reference_displacement.table", evidence.displacement_table_sha256),
        ("reaction_table", "reference_reaction.table", evidence.reaction_table_sha256),
        ("stress_table", "reference_stress.table", evidence.stress_table_sha256),
    )


def _validate_solve_evidence(evidence: GenuineReferenceSolveEvidence) -> None:
    if evidence.returncode != 0:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_SOLVER_EXIT_NOT_ZERO")
    if not evidence.message_diagnostic_ok or evidence.message_execution_exit_code not in (None, 0):
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_SOLVER_DIAGNOSTIC_NOT_VERIFIED")
    if not evidence.runtime_qualified:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_RUNTIME_NOT_QUALIFIED")
    if not evidence.runtime_attested_immediately_before_solve:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_RUNTIME_NOT_ATTESTED")
    if not evidence.fea_solve_executed:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_SOLVE_NOT_EXECUTED")
    if not evidence.numerical_verification:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_NUMERICAL_VERIFICATION_MISSING")
    if not evidence.results_verified:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_RESULTS_NOT_VERIFIED")


def create_professional_evidence_bundle(
    directory: str | Path,
    evidence: GenuineReferenceSolveEvidence,
    destination: str | Path,
    *,
    cad_length_unit: str = "mm",
    solver_unit_system: str = "mm-N-MPa",
    source_step: str | Path | None = None,
) -> ProfessionalEvidenceBundle:
    """Create an immutable, replay-verifiable manifest for a genuine verified solve.

    This function does not execute a solver and cannot promote unverified evidence.
    It only packages artifacts whose content hashes match GenuineReferenceSolveEvidence.
    """
    _validate_solve_evidence(evidence)
    if cad_length_unit != "mm":
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_CAD_UNIT_MUST_BE_MM")
    if solver_unit_system != "mm-N-MPa":
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_SOLVER_UNIT_SYSTEM_INVALID")

    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_DIRECTORY_NOT_FOUND")

    artifacts: list[EvidenceArtifact] = []
    for role, relative, expected_sha in _expected_artifacts(evidence):
        path = _require_file(root / relative, f"EVIDENCE_BUNDLE_ARTIFACT_MISSING:{role}")
        actual_sha = _sha(path)
        if actual_sha != expected_sha:
            raise ProfessionalEvidenceBundleError(f"EVIDENCE_BUNDLE_HASH_MISMATCH:{role}")
        artifacts.append(EvidenceArtifact(role, relative, actual_sha, path.stat().st_size))

    if source_step is not None:
        step_path = Path(source_step).expanduser().resolve()
        _require_file(step_path, "EVIDENCE_BUNDLE_SOURCE_STEP_MISSING")
        try:
            relative_step = step_path.relative_to(root).as_posix()
        except ValueError:
            relative_step = step_path.name
        artifacts.append(EvidenceArtifact("source_step", relative_step, _sha(step_path), step_path.stat().st_size))

    unsigned: dict[str, object] = {
        "schema_version": "astermax.professional-evidence-bundle.v1",
        "engine_kind": evidence.engine_kind,
        "distribution": evidence.distribution,
        "detected_version": evidence.detected_version,
        "cad_length_unit": cad_length_unit,
        "solver_unit_system": solver_unit_system,
        "runtime_qualified": evidence.runtime_qualified,
        "runtime_attested_immediately_before_solve": evidence.runtime_attested_immediately_before_solve,
        "fea_solve_executed": evidence.fea_solve_executed,
        "numerical_verification": evidence.numerical_verification,
        "results_verified": evidence.results_verified,
        "industrial_validation": False,
        "ansys_equivalence": False,
        "run_aster_sha256": evidence.run_aster_sha256,
        "config_sha256": evidence.config_sha256,
        "ux_relative_error": evidence.ux_relative_error,
        "reaction_relative_error": evidence.reaction_relative_error,
        "stress_relative_error": evidence.stress_relative_error,
        "artifacts": [asdict(item) for item in artifacts],
    }
    manifest_sha = sha256(_canonical_json(unsigned)).hexdigest()
    bundle = ProfessionalEvidenceBundle(
        artifacts=tuple(artifacts),
        manifest_sha256=manifest_sha,
        **{key: value for key, value in unsigned.items() if key != "artifacts"},
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return bundle


def verify_professional_evidence_bundle(
    manifest: str | Path,
    directory: str | Path,
) -> ProfessionalEvidenceBundle:
    manifest_path = _require_file(Path(manifest), "EVIDENCE_BUNDLE_MANIFEST_MISSING")
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_DIRECTORY_NOT_FOUND")

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "astermax.professional-evidence-bundle.v1":
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_SCHEMA_UNSUPPORTED")
    manifest_sha = raw.get("manifest_sha256")
    if not isinstance(manifest_sha, str) or len(manifest_sha) != 64:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_MANIFEST_HASH_INVALID")
    unsigned = dict(raw)
    unsigned.pop("manifest_sha256", None)
    if sha256(_canonical_json(unsigned)).hexdigest() != manifest_sha:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_MANIFEST_TAMPERED")

    for required_true in (
        "runtime_qualified",
        "runtime_attested_immediately_before_solve",
        "fea_solve_executed",
        "numerical_verification",
        "results_verified",
    ):
        if raw.get(required_true) is not True:
            raise ProfessionalEvidenceBundleError(f"EVIDENCE_BUNDLE_CLAIM_INVALID:{required_true}")
    if raw.get("industrial_validation") is not False or raw.get("ansys_equivalence") is not False:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_UNSUPPORTED_PROMOTION")
    if raw.get("cad_length_unit") != "mm" or raw.get("solver_unit_system") != "mm-N-MPa":
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_UNIT_CONTRACT_INVALID")

    artifacts_raw = raw.get("artifacts")
    if not isinstance(artifacts_raw, list) or not artifacts_raw:
        raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_ARTIFACTS_INVALID")
    artifacts: list[EvidenceArtifact] = []
    for item in artifacts_raw:
        if not isinstance(item, dict):
            raise ProfessionalEvidenceBundleError("EVIDENCE_BUNDLE_ARTIFACT_ENTRY_INVALID")
        artifact = EvidenceArtifact(
            role=str(item["role"]),
            relative_path=str(item["relative_path"]),
            sha256=str(item["sha256"]),
            size_bytes=int(item["size_bytes"]),
        )
        if Path(artifact.relative_path).is_absolute() or ".." in Path(artifact.relative_path).parts:
            raise ProfessionalEvidenceBundleError(f"EVIDENCE_BUNDLE_ARTIFACT_PATH_INVALID:{artifact.role}")
        path = _require_file(root / artifact.relative_path, f"EVIDENCE_BUNDLE_ARTIFACT_MISSING:{artifact.role}")
        if path.stat().st_size != artifact.size_bytes or _sha(path) != artifact.sha256:
            raise ProfessionalEvidenceBundleError(f"EVIDENCE_BUNDLE_ARTIFACT_TAMPERED:{artifact.role}")
        artifacts.append(artifact)

    return ProfessionalEvidenceBundle(
        schema_version=raw["schema_version"],
        engine_kind=raw["engine_kind"],
        distribution=raw["distribution"],
        detected_version=raw.get("detected_version"),
        cad_length_unit=raw["cad_length_unit"],
        solver_unit_system=raw["solver_unit_system"],
        runtime_qualified=raw["runtime_qualified"],
        runtime_attested_immediately_before_solve=raw["runtime_attested_immediately_before_solve"],
        fea_solve_executed=raw["fea_solve_executed"],
        numerical_verification=raw["numerical_verification"],
        results_verified=raw["results_verified"],
        industrial_validation=raw["industrial_validation"],
        ansys_equivalence=raw["ansys_equivalence"],
        run_aster_sha256=raw["run_aster_sha256"],
        config_sha256=raw["config_sha256"],
        ux_relative_error=float(raw["ux_relative_error"]),
        reaction_relative_error=float(raw["reaction_relative_error"]),
        stress_relative_error=float(raw["stress_relative_error"]),
        artifacts=tuple(artifacts),
        manifest_sha256=manifest_sha,
    )
