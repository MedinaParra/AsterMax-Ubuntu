from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .code_aster_reference_harness import UniaxialPrismSpec, prepare_reference_solver_bundle
from .code_aster_result_contract import ResultTableSpec, render_reference_export, render_reference_linear_static_comm
from .code_aster_study import LinearStaticStudy


class GenuineReferenceBundleError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _require(path: Path, code: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise GenuineReferenceBundleError(code)
    return path


def prepare_genuine_reference_bundle(
    spec: UniaxialPrismSpec,
    directory: str | Path,
    *,
    tables: ResultTableSpec | None = None,
    time_limit_s: int = 300,
    memory_limit_mb: int = 2048,
) -> dict[str, object]:
    """Prepare the exact pre-solve bundle consumed by the genuine Code_Aster gate.

    The older reference preparer correctly creates the mm TET10/TRI6 MED and
    mesh-quality evidence, but its generic .comm does not emit the scalar tables
    required by ``execute_and_verify_reference_wsl`` and it does not create the
    .export profile.  This function deliberately reuses that trusted geometry /
    mesh path, then replaces only the solver command/profile layer with the
    auditable reference-result contract.

    This function never executes Code_Aster and cannot promote solver claims.
    """
    spec.validate()
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = prepare_reference_solver_bundle(spec, root)

    table_spec = tables or ResultTableSpec()
    table_spec.validate()
    study = LinearStaticStudy(
        mesh_filename="astermax.med",
        support_group="FIXED_FACE",
        load_group="LOAD_FACE",
        young_mpa=spec.young_mpa,
        poisson=spec.poisson,
        traction_mpa=(spec.traction_x_mpa, 0.0, 0.0),
    )

    comm = root / "astermax.comm"
    comm.write_text(
        render_reference_linear_static_comm(study, volume_group="SOLID", tables=table_spec),
        encoding="utf-8",
        newline="\n",
    )
    export = root / "astermax.export"
    export.write_text(
        render_reference_export(
            tables=table_spec,
            time_limit_s=time_limit_s,
            memory_limit_mb=memory_limit_mb,
        ),
        encoding="utf-8",
        newline="\n",
    )

    evidence = dict(base)
    evidence.update(
        {
            "schema": "astermax.genuine-reference-presolve-bundle.v1",
            "comm_sha256": _sha(comm),
            "export_sha256": _sha(export),
            "result_med_filename": "astermax_result.med",
            "displacement_table_filename": table_spec.displacement_filename,
            "reaction_table_filename": table_spec.reaction_filename,
            "stress_table_filename": table_spec.stress_filename,
            "verification_fields": ["DEPL", "REAC_NODA", "SIGM_NOEU", "SIEQ_NOEU"],
            "verification_tables_bound": True,
            "solver_message_bound": True,
            "fea_solve_executed": False,
            "numerical_verification": False,
            "results_verified": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        }
    )
    (root / "reference_case_evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    validate_genuine_reference_bundle(root, tables=table_spec)
    return evidence


def validate_genuine_reference_bundle(
    directory: str | Path,
    *,
    tables: ResultTableSpec | None = None,
) -> dict[str, object]:
    """Fail closed if preparation and genuine-run expectations drift apart."""
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_DIRECTORY_NOT_FOUND")
    table_spec = tables or ResultTableSpec()
    table_spec.validate()

    med = _require(root / "astermax.med", "GENUINE_BUNDLE_MED_MISSING")
    comm = _require(root / "astermax.comm", "GENUINE_BUNDLE_COMM_MISSING")
    export = _require(root / "astermax.export", "GENUINE_BUNDLE_EXPORT_MISSING")
    quality = _require(root / "reference_mesh_quality.json", "GENUINE_BUNDLE_QUALITY_MISSING")
    case_path = _require(root / "reference_case_evidence.json", "GENUINE_BUNDLE_CASE_EVIDENCE_MISSING")

    try:
        case = json.loads(case_path.read_text(encoding="utf-8", errors="strict"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_CASE_EVIDENCE_INVALID_JSON") from exc
    if not isinstance(case, dict):
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_CASE_EVIDENCE_NOT_OBJECT")
    if case.get("units") != {"length": "mm", "force": "N", "stress": "MPa"}:
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_UNIT_CONTRACT_MISMATCH")
    if case.get("mesh_quality_gate_passed") is not True:
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_MESH_QUALITY_NOT_PASSED")
    for flag in ("fea_solve_executed", "numerical_verification", "results_verified", "industrial_validation", "ansys_equivalence"):
        if case.get(flag) is not False:
            raise GenuineReferenceBundleError(f"GENUINE_BUNDLE_PRE_SOLVE_CLAIM_FORBIDDEN:{flag}")

    if case.get("med_sha256") != _sha(med):
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_MED_HASH_MISMATCH")
    if case.get("comm_sha256") != _sha(comm):
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_COMM_HASH_MISMATCH")
    if case.get("export_sha256") != _sha(export):
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_EXPORT_HASH_MISMATCH")
    if case.get("mesh_quality_artifact_sha256") != _sha(quality):
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_QUALITY_HASH_MISMATCH")

    comm_text = comm.read_text(encoding="utf-8", errors="strict")
    required_comm_tokens = (
        "FORCE=('REAC_NODA',)",
        "NOM_CHAM='DEPL'",
        "NOM_CHAM='REAC_NODA'",
        "NOM_CHAM='SIGM_NOEU'",
        "POST_RELEVE_T",
        "IMPR_TABLE",
        "SIEQ_NOEU",
    )
    for token in required_comm_tokens:
        if token not in comm_text:
            raise GenuineReferenceBundleError(f"GENUINE_BUNDLE_COMM_CONTRACT_MISSING:{token}")

    export_lines = {line.strip() for line in export.read_text(encoding="utf-8", errors="strict").splitlines() if line.strip()}
    required_export = {
        "F comm astermax.comm D 1",
        "F libr astermax.med D 20",
        "F rmed astermax_result.med R 80",
        f"F libr {table_spec.displacement_filename} R {table_spec.displacement_unit}",
        f"F libr {table_spec.reaction_filename} R {table_spec.reaction_unit}",
        f"F libr {table_spec.stress_filename} R {table_spec.stress_unit}",
    }
    missing = sorted(required_export - export_lines)
    if missing:
        raise GenuineReferenceBundleError("GENUINE_BUNDLE_EXPORT_BINDING_MISSING:" + "|".join(missing))

    return {
        "schema": "astermax.genuine-reference-launch-readiness.v1",
        "length_unit": "mm",
        "solver_unit_system": "mm-N-MPa",
        "mesh_quality_gate_passed": True,
        "verification_tables_bound": True,
        "result_med_bound": True,
        "pre_solve_bundle_valid": True,
        "med_sha256": _sha(med),
        "comm_sha256": _sha(comm),
        "export_sha256": _sha(export),
        "reference_case_evidence_sha256": _sha(case_path),
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
