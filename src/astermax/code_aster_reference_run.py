from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json

from .code_aster_diagnostic import verify_code_aster_message
from .code_aster_reference_harness import (
    ReferenceObservedMetrics,
    UniaxialPrismSpec,
    verify_uniaxial_reference_results,
)
from .code_aster_result_contract import ResultTableSpec, parse_reference_result_tables
from .code_aster_wsl_runtime import (
    CodeAsterWslRuntime,
    _run,
    build_wsl_run_aster_command,
    probe_wsl_runtime,
    windows_path_to_wsl,
)


class CodeAsterReferenceRunError(RuntimeError):
    pass


def _require(path: Path, code: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise CodeAsterReferenceRunError(code)
    return path


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class GenuineReferenceSolveEvidence:
    engine_kind: str
    distribution: str
    export_sha256: str
    command_sha256: str
    input_med_sha256: str
    result_med_sha256: str
    message_sha256: str
    displacement_table_sha256: str
    reaction_table_sha256: str
    stress_table_sha256: str
    solver_stdout_sha256: str
    returncode: int
    message_diagnostic_ok: bool
    message_execution_exit_code: int | None
    fea_solve_executed: bool
    numerical_verification: bool
    results_verified: bool
    ux_relative_error: float
    reaction_relative_error: float
    stress_relative_error: float

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def execute_and_verify_reference_wsl(
    runtime: CodeAsterWslRuntime,
    spec: UniaxialPrismSpec,
    directory: str | Path,
    *,
    tables: ResultTableSpec | None = None,
    message_filename: str = "astermax.mess",
    timeout_s: float = 300.0,
) -> GenuineReferenceSolveEvidence:
    """Run a WSL2 Code_Aster reference study and verify solver plus mechanics.

    A successful process exit is necessary but not sufficient. C8.6 additionally
    requires a fresh Code_Aster message file with an explicit successful solver
    diagnostic, a fresh result MED, three fresh scalar evidence tables, and the
    analytical displacement/reaction/stress checks. Only this combined gate may
    emit fea_solve_executed=True for the reference case.
    """
    spec.validate()
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise CodeAsterReferenceRunError("REFERENCE_RUN_DIRECTORY_NOT_FOUND")
    if Path(message_filename).name != message_filename or not message_filename.lower().endswith(".mess"):
        raise CodeAsterReferenceRunError("REFERENCE_RUN_MESSAGE_FILENAME_INVALID")

    export = _require(root / "astermax.export", "REFERENCE_RUN_EXPORT_MISSING")
    command = _require(root / "astermax.comm", "REFERENCE_RUN_COMMAND_MISSING")
    input_med = _require(root / "astermax.med", "REFERENCE_RUN_INPUT_MED_MISSING")
    result_med = root / "astermax_result.med"
    message = root / message_filename
    table_spec = tables or ResultTableSpec()
    table_spec.validate()
    displacement = root / table_spec.displacement_filename
    reaction = root / table_spec.reaction_filename
    stress = root / table_spec.stress_filename
    outputs = (result_med, message, displacement, reaction, stress)
    if any(path.exists() for path in outputs):
        raise CodeAsterReferenceRunError("REFERENCE_RUN_STALE_OUTPUT_PRESENT")

    # The explicit F mess binding prevents a launcher stdout-only success from
    # being treated as durable solver evidence.
    export_text = export.read_text(encoding="utf-8", errors="strict")
    expected_binding = f"F mess {message_filename} R 6"
    if expected_binding not in {line.strip() for line in export_text.splitlines()}:
        raise CodeAsterReferenceRunError("REFERENCE_RUN_MESSAGE_BINDING_MISSING")

    probe_wsl_runtime(runtime, timeout_s=min(timeout_s, 30.0))
    workdir_linux = windows_path_to_wsl(runtime, root, timeout_s=min(timeout_s, 30.0))
    launch = build_wsl_run_aster_command(runtime, workdir_linux=workdir_linux, export_filename=export.name)
    completed = _run(launch, timeout_s=timeout_s)
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise CodeAsterReferenceRunError(f"REFERENCE_RUN_NONZERO_EXIT:{completed.returncode}")

    for path, code in (
        (result_med, "REFERENCE_RUN_RESULT_MED_MISSING"),
        (message, "REFERENCE_RUN_MESSAGE_MISSING"),
        (displacement, "REFERENCE_RUN_DISPLACEMENT_TABLE_MISSING"),
        (reaction, "REFERENCE_RUN_REACTION_TABLE_MISSING"),
        (stress, "REFERENCE_RUN_STRESS_TABLE_MISSING"),
    ):
        _require(path, code)

    diagnostic = verify_code_aster_message(message)
    parsed = parse_reference_result_tables(displacement, reaction, stress)
    observed = ReferenceObservedMetrics(
        load_face_mean_ux_mm=parsed.load_face_mean_ux_mm,
        support_reaction_x_n=parsed.support_reaction_x_n,
        axial_stress_mpa=parsed.axial_stress_mpa,
    )
    verified = verify_uniaxial_reference_results(spec, observed, fea_solve_executed=True)

    # fea_solve_executed means both launcher success and a positive durable
    # Code_Aster diagnostic. results_verified remains the stricter mechanics gate.
    return GenuineReferenceSolveEvidence(
        engine_kind=runtime.engine_kind,
        distribution=runtime.distribution,
        export_sha256=_sha(export),
        command_sha256=_sha(command),
        input_med_sha256=_sha(input_med),
        result_med_sha256=_sha(result_med),
        message_sha256=diagnostic.sha256,
        displacement_table_sha256=_sha(displacement),
        reaction_table_sha256=_sha(reaction),
        stress_table_sha256=_sha(stress),
        solver_stdout_sha256=sha256(combined.encode("utf-8", errors="replace")).hexdigest(),
        returncode=completed.returncode,
        message_diagnostic_ok=diagnostic.diagnostic_ok,
        message_execution_exit_code=diagnostic.execution_exit_code,
        fea_solve_executed=True,
        numerical_verification=verified.numerical_verification,
        results_verified=verified.results_verified,
        ux_relative_error=verified.ux_relative_error,
        reaction_relative_error=verified.reaction_relative_error,
        stress_relative_error=verified.stress_relative_error,
    )


def write_genuine_reference_solve_evidence(evidence: GenuineReferenceSolveEvidence, destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
