from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json

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
    displacement_table_sha256: str
    reaction_table_sha256: str
    stress_table_sha256: str
    solver_stdout_sha256: str
    returncode: int
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
    timeout_s: float = 300.0,
) -> GenuineReferenceSolveEvidence:
    """Run the reference study through real WSL2 Code_Aster and verify mechanics.

    This is the only C8.5 path allowed to emit fea_solve_executed=True. It first
    probes the real WSL distribution/run_aster identity, rejects stale outputs,
    executes the .export study, requires all result files, then compares scalar
    evidence against the closed-form uniaxial solution.
    """
    spec.validate()
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise CodeAsterReferenceRunError("REFERENCE_RUN_DIRECTORY_NOT_FOUND")

    export = _require(root / "astermax.export", "REFERENCE_RUN_EXPORT_MISSING")
    command = _require(root / "astermax.comm", "REFERENCE_RUN_COMMAND_MISSING")
    input_med = _require(root / "astermax.med", "REFERENCE_RUN_INPUT_MED_MISSING")
    result_med = root / "astermax_result.med"
    table_spec = tables or ResultTableSpec()
    table_spec.validate()
    displacement = root / table_spec.displacement_filename
    reaction = root / table_spec.reaction_filename
    stress = root / table_spec.stress_filename
    outputs = (result_med, displacement, reaction, stress)
    if any(path.exists() for path in outputs):
        raise CodeAsterReferenceRunError("REFERENCE_RUN_STALE_OUTPUT_PRESENT")

    probe_wsl_runtime(runtime, timeout_s=min(timeout_s, 30.0))
    workdir_linux = windows_path_to_wsl(runtime, root, timeout_s=min(timeout_s, 30.0))
    launch = build_wsl_run_aster_command(runtime, workdir_linux=workdir_linux, export_filename=export.name)
    completed = _run(launch, timeout_s=timeout_s)
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise CodeAsterReferenceRunError(f"REFERENCE_RUN_NONZERO_EXIT:{completed.returncode}")

    for path, code in (
        (result_med, "REFERENCE_RUN_RESULT_MED_MISSING"),
        (displacement, "REFERENCE_RUN_DISPLACEMENT_TABLE_MISSING"),
        (reaction, "REFERENCE_RUN_REACTION_TABLE_MISSING"),
        (stress, "REFERENCE_RUN_STRESS_TABLE_MISSING"),
    ):
        _require(path, code)

    parsed = parse_reference_result_tables(displacement, reaction, stress)
    observed = ReferenceObservedMetrics(
        load_face_mean_ux_mm=parsed.load_face_mean_ux_mm,
        support_reaction_x_n=parsed.support_reaction_x_n,
        axial_stress_mpa=parsed.axial_stress_mpa,
    )
    verified = verify_uniaxial_reference_results(spec, observed, fea_solve_executed=True)

    return GenuineReferenceSolveEvidence(
        engine_kind=runtime.engine_kind,
        distribution=runtime.distribution,
        export_sha256=_sha(export),
        command_sha256=_sha(command),
        input_med_sha256=_sha(input_med),
        result_med_sha256=_sha(result_med),
        displacement_table_sha256=_sha(displacement),
        reaction_table_sha256=_sha(reaction),
        stress_table_sha256=_sha(stress),
        solver_stdout_sha256=sha256(combined.encode("utf-8", errors="replace")).hexdigest(),
        returncode=completed.returncode,
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
