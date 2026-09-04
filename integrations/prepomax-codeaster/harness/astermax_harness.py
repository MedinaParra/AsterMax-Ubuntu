#!/usr/bin/env python3
"""AsterMax solver harness.

This executable is intentionally independent from the WinForms GUI. It provides a
fail-closed contract around generated solver studies:

    study inputs -> preflight -> solver -> artifact checks -> result checks -> report

The harness never manufactures FEA results and never converts a missing/stale output
into success. A run passes only when the process exits successfully and every required
artifact/result contract is satisfied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

SCHEMA_VERSION = 1
CODE_ASTER_TABLES = (
    "PPM_DEPL",
    "PPM_STRESS_N",
    "PPM_STRESS_S",
    "PPM_STRAIN_N",
    "PPM_STRAIN_S",
)
CODE_ASTER_TABLE_COMPONENTS: Dict[str, Tuple[str, ...]] = {
    "PPM_DEPL": ("DX", "DY", "DZ"),
    "PPM_STRESS_N": ("SIXX", "SIYY", "SIZZ"),
    "PPM_STRESS_S": ("SIXY", "SIYZ", "SIXZ"),
    "PPM_STRAIN_N": ("EPXX", "EPYY", "EPZZ"),
    "PPM_STRAIN_S": ("EPXY", "EPYZ", "EPXZ"),
}


class HarnessError(RuntimeError):
    pass


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Artifact:
    path: str
    exists: bool
    size: int = 0
    sha256: Optional[str] = None
    modified_utc: Optional[str] = None


@dataclass
class ProcessResult:
    command: List[str]
    return_code: Optional[int]
    duration_seconds: float
    timed_out: bool
    stdout_log: str
    stderr_log: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> Artifact:
    if not path.exists() or not path.is_file():
        return Artifact(path=str(path), exists=False)
    stat = path.stat()
    return Artifact(
        path=str(path),
        exists=True,
        size=stat.st_size,
        sha256=sha256_file(path),
        modified_utc=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    )


def expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, list):
        return [expand(item) for item in value]
    if isinstance(value, dict):
        return {key: expand(item) for key, item in value.items()}
    return value


def read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HarnessError(f"Unable to read manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HarnessError("Harness manifest root must be a JSON object.")
    return expand(data)


def resolve_executable(executable: str, cwd: Path) -> Optional[str]:
    candidate = Path(executable)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    local = cwd / candidate
    if local.exists() and local.is_file():
        return str(local.resolve())
    return shutil.which(executable)


def case_path(cwd: Path, relative: str) -> Path:
    """Resolve a solver-owned artifact while forbidding paths outside the case root."""
    item = Path(relative)
    if item.is_absolute():
        raise HarnessError(f"Artifact paths must be relative to the working directory: {relative}")
    root = cwd.resolve()
    target = (root / item).resolve()
    if target != root and root not in target.parents:
        raise HarnessError(f"Artifact path escapes the working directory: {relative}")
    return target


def solver_defaults(solver: str, job_name: str) -> Tuple[List[str], List[str]]:
    if solver == "code_aster":
        return (
            [f"{job_name}.comm", f"{job_name}.mail", f"{job_name}.export"],
            [f"{job_name}.mess", f"{job_name}.rmed", f"{job_name}.resu"],
        )
    if solver == "calculix":
        return ([f"{job_name}.inp"], [f"{job_name}.frd"])
    raise HarnessError(f"Unsupported solver profile: {solver}")


def solver_command(solver: str, executable: str, job_name: str) -> List[str]:
    if solver == "code_aster":
        export_file = f"{job_name}.export"
        # Native Windows Code_Aster MSI distributions expose run_aster.bat.
        # subprocess(shell=False) cannot execute a batch file directly, so route
        # it explicitly through COMSPEC while keeping the harness fail-closed.
        if os.name == "nt" and Path(executable).suffix.lower() in (".bat", ".cmd"):
            comspec = os.environ.get("COMSPEC") or "cmd.exe"
            command_line = f'call "{executable}" "{export_file}"'
            return [comspec, "/d", "/s", "/c", command_line]
        return [executable, export_file]
    if solver == "calculix":
        return [executable, job_name]
    raise HarnessError(f"Unsupported solver profile: {solver}")


def normalize_file_list(value: Any, defaults: Sequence[str]) -> List[str]:
    if value is None:
        return list(defaults)
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        raise HarnessError("Artifact lists must contain non-empty strings.")
    return list(value)


def preflight(manifest: Dict[str, Any], manifest_path: Path) -> Tuple[Dict[str, Any], List[Check]]:
    checks: List[Check] = []
    schema = manifest.get("schema", SCHEMA_VERSION)
    if schema != SCHEMA_VERSION:
        raise HarnessError(f"Unsupported harness schema {schema}; expected {SCHEMA_VERSION}.")

    solver = str(manifest.get("solver", "")).strip().lower()
    if solver not in ("code_aster", "calculix"):
        raise HarnessError("solver must be 'code_aster' or 'calculix'.")

    job_name = str(manifest.get("job_name", "")).strip()
    if (not job_name or not re.fullmatch(r"[A-Za-z0-9_.-]+", job_name)
            or not re.search(r"[A-Za-z0-9]", job_name)):
        raise HarnessError("job_name must contain a letter/digit and use only letters, digits, dot, underscore or hyphen.")

    cwd_value = manifest.get("working_directory", ".")
    cwd = Path(str(cwd_value))
    if not cwd.is_absolute():
        cwd = (manifest_path.parent / cwd).resolve()
    checks.append(Check("working_directory", cwd.exists() and cwd.is_dir(), str(cwd)))

    default_inputs, default_outputs = solver_defaults(solver, job_name)
    required_inputs = normalize_file_list(manifest.get("required_inputs"), default_inputs)
    required_outputs = normalize_file_list(manifest.get("required_outputs"), default_outputs)

    min_input_bytes = int(manifest.get("min_input_bytes", 1))
    min_output_bytes = int(manifest.get("min_output_bytes", 1))
    if min_input_bytes < 1 or min_output_bytes < 1:
        raise HarnessError("Minimum artifact sizes must be at least one byte.")

    for relative in required_inputs:
        item = case_path(cwd, relative)
        ok = item.exists() and item.is_file() and item.stat().st_size >= min_input_bytes
        checks.append(Check(f"input:{relative}", ok, f"exists={item.exists()} size={item.stat().st_size if item.exists() else 0}"))
    for relative in required_outputs:
        case_path(cwd, relative)

    executable = str(manifest.get("solver_executable") or ("as_run" if solver == "code_aster" else "ccx"))
    resolved_executable = resolve_executable(executable, cwd)
    checks.append(Check("solver_executable", resolved_executable is not None, resolved_executable or executable))

    timeout_seconds = int(manifest.get("timeout_seconds", 3600))
    if timeout_seconds < 1:
        raise HarnessError("timeout_seconds must be positive.")

    normalized = dict(manifest)
    normalized.update(
        {
            "schema": SCHEMA_VERSION,
            "solver": solver,
            "job_name": job_name,
            "working_directory": str(cwd),
            "required_inputs": required_inputs,
            "required_outputs": required_outputs,
            "min_input_bytes": min_input_bytes,
            "min_output_bytes": min_output_bytes,
            "solver_executable_resolved": resolved_executable,
            "timeout_seconds": timeout_seconds,
        }
    )
    return normalized, checks


def remove_owned_outputs(cwd: Path, outputs: Iterable[str]) -> List[str]:
    removed: List[str] = []
    for relative in outputs:
        target = case_path(cwd, relative)
        if target.exists():
            if not target.is_file():
                raise HarnessError(f"Refusing to remove non-file solver output: {target}")
            target.unlink()
            removed.append(str(target))
    return removed


def run_process(command: Sequence[str], cwd: Path, environment: Dict[str, str], timeout: int,
                stdout_path: Path, stderr_path: Path) -> ProcessResult:
    start = time.monotonic()
    timed_out = False
    return_code: Optional[int] = None
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
        return_code = completed.returncode
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
    duration = time.monotonic() - start
    return ProcessResult(
        command=list(command),
        return_code=return_code,
        duration_seconds=round(duration, 6),
        timed_out=timed_out,
        stdout_log=str(stdout_path),
        stderr_log=str(stderr_path),
    )


def scan_text(path: Path, patterns: Sequence[str]) -> List[str]:
    if not path.exists() or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    hits: List[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            hits.append(pattern)
    return hits


def _normalize_table_line(value: str) -> str:
    return (value or "").lstrip("# ").strip()


def _split_table_line(value: str) -> List[str]:
    return [token.strip() for token in value.split(";")]


def _parse_node_id(token: str) -> Optional[int]:
    value = (token or "").strip()
    if value[:1].lower() == "n":
        value = value[1:]
    if not re.fullmatch(r"\d+", value):
        return None
    return int(value)


def _parse_finite_float(token: str) -> Optional[float]:
    value = (token or "").strip().replace("D", "E").replace("d", "e")
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def validate_code_aster_tables(path: Path, required_tables: Sequence[str], min_rows: int) -> List[Check]:
    """Validate the actual Code_Aster interoperability tables without inventing values."""
    checks: List[Check] = []
    if not path.exists() or path.stat().st_size == 0:
        return [Check("code_aster_result_tables", False, f"Missing or empty: {path}")]
    if min_rows < 1:
        raise HarnessError("min_rows_per_table must be at least one.")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    node_sets: Dict[str, Set[int]] = {}

    for raw_title in required_tables:
        title = str(raw_title).strip()
        title_index = next((i for i, line in enumerate(lines) if title.lower() in line.lower()), -1)
        if title_index < 0:
            checks.append(Check(f"table:{title}", False, "section title not found"))
            continue

        header_index = -1
        header: List[str] = []
        for i in range(title_index + 1, min(len(lines), title_index + 90)):
            normalized = _normalize_table_line(lines[i])
            if ";" not in normalized:
                continue
            tokens = _split_table_line(normalized)
            if any(token.upper() == "NOEUD" for token in tokens):
                header_index = i
                header = tokens
                break
        if header_index < 0:
            checks.append(Check(f"table:{title}", False, "semicolon NOEUD header not found"))
            continue

        upper_header = [token.upper() for token in header]
        node_column = upper_header.index("NOEUD")
        expected_components = CODE_ASTER_TABLE_COMPONENTS.get(title.upper(), ())
        missing_components = [component for component in expected_components if component not in upper_header]
        if missing_components:
            checks.append(Check(
                f"table:{title}:components",
                False,
                "missing=" + ",".join(missing_components),
            ))
            continue

        component_columns = [upper_header.index(component) for component in expected_components]
        nodes: Set[int] = set()
        duplicate_nodes: Set[int] = set()
        invalid_numeric_rows = 0
        rows = 0

        for i in range(header_index + 1, len(lines)):
            raw = lines[i].strip()
            if rows > 0 and (not raw or "PPM_" in raw):
                break
            normalized = _normalize_table_line(raw)
            if not normalized or ";" not in normalized:
                continue
            tokens = _split_table_line(normalized)
            if node_column >= len(tokens):
                continue
            node_id = _parse_node_id(tokens[node_column])
            if node_id is None:
                continue

            if node_id in nodes:
                duplicate_nodes.add(node_id)
            nodes.add(node_id)
            rows += 1

            for column in component_columns:
                if column >= len(tokens) or _parse_finite_float(tokens[column]) is None:
                    invalid_numeric_rows += 1
                    break

        node_sets[title] = nodes
        checks.append(Check(f"table:{title}", rows >= min_rows, f"rows={rows}, required>={min_rows}"))
        checks.append(Check(
            f"table:{title}:unique_nodes",
            not duplicate_nodes,
            "none" if not duplicate_nodes else "duplicates=" + ",".join(str(x) for x in sorted(duplicate_nodes)[:20]),
        ))
        if expected_components:
            checks.append(Check(
                f"table:{title}:finite_values",
                invalid_numeric_rows == 0,
                f"invalid_numeric_rows={invalid_numeric_rows}",
            ))

    complete_node_sets = [nodes for title, nodes in node_sets.items() if title in required_tables and nodes]
    if len(complete_node_sets) >= 2:
        reference = complete_node_sets[0]
        consistent = all(nodes == reference for nodes in complete_node_sets[1:])
        sizes = ", ".join(f"{title}={len(nodes)}" for title, nodes in node_sets.items())
        checks.append(Check("code_aster_node_sets_consistent", consistent, sizes))
    elif len(required_tables) > 1:
        checks.append(Check("code_aster_node_sets_consistent", False, "insufficient valid tables for comparison"))

    return checks


def validate_outputs(manifest: Dict[str, Any]) -> Tuple[List[Check], List[Artifact]]:
    cwd = Path(manifest["working_directory"])
    checks: List[Check] = []
    artifacts: List[Artifact] = []
    min_bytes = int(manifest["min_output_bytes"])

    for relative in manifest["required_outputs"]:
        item = case_path(cwd, relative)
        art = artifact(item)
        artifacts.append(art)
        ok = art.exists and art.size >= min_bytes
        checks.append(Check(f"output:{relative}", ok, f"exists={art.exists} size={art.size}"))

    if manifest["solver"] == "code_aster":
        mess = case_path(cwd, f"{manifest['job_name']}.mess")
        fatal_patterns = manifest.get(
            "fatal_message_patterns",
            [r"<F>", r"ERREUR\s+FATALE", r"FATAL(?:_|\s)+ERROR", r"ABNORMAL(?:_|\s)+ABORT"],
        )
        hits = scan_text(mess, fatal_patterns)
        checks.append(Check("code_aster_fatal_markers", not hits, "none" if not hits else ", ".join(hits)))

        result_contract = manifest.get("result_contract", {})
        if result_contract is not False:
            if not isinstance(result_contract, dict):
                raise HarnessError("result_contract must be an object or false.")
            required_tables = result_contract.get("required_tables", list(CODE_ASTER_TABLES))
            if not isinstance(required_tables, list) or not all(isinstance(x, str) and x.strip() for x in required_tables):
                raise HarnessError("result_contract.required_tables must contain non-empty strings.")
            min_rows = int(result_contract.get("min_rows_per_table", 1))
            checks.extend(validate_code_aster_tables(case_path(cwd, f"{manifest['job_name']}.resu"), required_tables, min_rows))

    return checks, artifacts


def write_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def execute(manifest_path: Path, preflight_only: bool = False, report_override: Optional[Path] = None) -> int:
    raw = read_json(manifest_path)
    manifest, preflight_checks = preflight(raw, manifest_path)
    cwd = Path(manifest["working_directory"])
    case_name = str(manifest.get("case_name") or manifest["job_name"])

    if report_override is not None:
        report_path = report_override
        if not report_path.is_absolute():
            report_path = (manifest_path.parent / report_path).resolve()
    elif cwd.exists() and cwd.is_dir():
        report_path = cwd / f"{manifest['job_name']}.harness.json"
    else:
        report_path = manifest_path.parent / f"{manifest['job_name']}.harness.json"

    report: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "case_name": case_name,
        "solver": manifest["solver"],
        "job_name": manifest["job_name"],
        "started_utc": utc_now(),
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "manifest": str(manifest_path.resolve()),
        "working_directory": str(cwd),
        "preflight_checks": [asdict(item) for item in preflight_checks],
        "status": "PRECHECK_ONLY" if preflight_only else "RUNNING",
    }

    if not all(item.passed for item in preflight_checks):
        report["status"] = "FAIL"
        report["failure_stage"] = "preflight"
        report["finished_utc"] = utc_now()
        write_report(report_path, report)
        print(json.dumps({"status": "FAIL", "report": str(report_path), "stage": "preflight"}))
        return 2

    report["input_artifacts"] = [asdict(artifact(case_path(cwd, item))) for item in manifest["required_inputs"]]
    if preflight_only:
        report["finished_utc"] = utc_now()
        write_report(report_path, report)
        print(json.dumps({"status": "PRECHECK_ONLY", "report": str(report_path)}))
        return 0

    removed = remove_owned_outputs(cwd, manifest["required_outputs"])
    report["removed_stale_outputs"] = removed

    environment = os.environ.copy()
    custom_environment = manifest.get("environment", {})
    if not isinstance(custom_environment, dict):
        raise HarnessError("environment must be a JSON object.")
    environment.update({str(k): str(v) for k, v in custom_environment.items()})

    executable = manifest["solver_executable_resolved"]
    assert executable is not None
    command = manifest.get("solver_command")
    if command is None:
        command = solver_command(manifest["solver"], executable, manifest["job_name"])
    elif not isinstance(command, list) or not command:
        raise HarnessError("solver_command must be a non-empty array when provided.")
    else:
        command = [str(x).replace("{solver}", executable).replace("{job}", manifest["job_name"]) for x in command]

    log_dir = cwd / ".astermax-harness"
    stdout_log = log_dir / f"{manifest['job_name']}.stdout.log"
    stderr_log = log_dir / f"{manifest['job_name']}.stderr.log"
    process = run_process(command, cwd, environment, manifest["timeout_seconds"], stdout_log, stderr_log)
    report["process"] = asdict(process)

    process_checks = [
        Check("solver_timeout", not process.timed_out, f"timed_out={process.timed_out}"),
        Check("solver_exit_code", process.return_code == 0, f"return_code={process.return_code}"),
    ]
    output_checks, output_artifacts = validate_outputs(manifest)
    all_checks = process_checks + output_checks
    report["checks"] = [asdict(item) for item in all_checks]
    report["output_artifacts"] = [asdict(item) for item in output_artifacts]
    report["status"] = "PASS" if all(item.passed for item in all_checks) else "FAIL"
    report["finished_utc"] = utc_now()
    write_report(report_path, report)

    print(json.dumps({"status": report["status"], "report": str(report_path)}))
    return 0 if report["status"] == "PASS" else 3


def self_test() -> int:
    """Small stdlib-only contract test. It never runs or fakes an FEA solver."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="astermax-harness-") as temp:
        root = Path(temp)
        for name in ("case.comm", "case.mail", "case.export"):
            (root / name).write_text("contract-test\n", encoding="utf-8")
        manifest = {
            "schema": 1,
            "case_name": "harness-self-test",
            "solver": "code_aster",
            "job_name": "case",
            "working_directory": str(root),
            "solver_executable": sys.executable,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        normalized, checks = preflight(read_json(manifest_path), manifest_path)
        if not normalized or not all(check.passed for check in checks):
            raise HarnessError("Self-test preflight failed.")
        if validate_code_aster_tables(root / "missing.resu", CODE_ASTER_TABLES, 1)[0].passed:
            raise HarnessError("Self-test failed closed-output check.")
        try:
            case_path(root, "../outside.rmed")
            raise HarnessError("Self-test failed workspace escape check.")
        except HarnessError:
            pass
    print("AsterMax harness self-test: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a generated AsterMax/PrePoMax solver study under a fail-closed contract.")
    parser.add_argument("--manifest", type=Path, help="JSON harness manifest")
    parser.add_argument("--preflight-only", action="store_true", help="validate inputs/executable without running the solver")
    parser.add_argument("--report", type=Path, help="override JSON report path")
    parser.add_argument("--self-test", action="store_true", help="run harness contract tests only; no FEA solver is invoked")
    args = parser.parse_args()

    try:
        if args.self_test:
            return self_test()
        if args.manifest is None:
            parser.error("--manifest is required unless --self-test is used")
        return execute(args.manifest.resolve(), args.preflight_only, args.report)
    except HarnessError as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"UNEXPECTED HARNESS ERROR: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
