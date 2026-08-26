from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import yaml

from astermax.harness.models import GateResultV1, GateStatus


# Eval commands are code-owned, not YAML-owned. A work package can select an eval
# ID but cannot inject a new command into the harness.
EVAL_REGISTRY: dict[str, list[str]] = {
    "harness_contract_integrity": ["python", "-m", "pytest", "-q", "tests/test_coding_harness.py"],
    "evidence_lineage": ["python", "-m", "pytest", "-q", "tests/test_frontier_methodology.py", "-k", "evidence"],
    "meta_regression_guard": ["python", "-m", "pytest", "-q", "tests/test_frontier_methodology.py", "-k", "meta"],
    "source_compile": ["python", "-m", "compileall", "-q", "src"],
}


def load_eval_suite(path: str | Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Eval suite must be a mapping")
    if data.get("frozen") is not True:
        raise ValueError("Frontier eval suite must be frozen")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Frontier eval suite must contain cases")
    return data, hashlib.sha256(raw).hexdigest()


def run_frozen_eval_suite(repo_root: Path, suite_path: Path, gate_id: str) -> GateResultV1:
    suite, suite_hash = load_eval_suite(suite_path)
    case_results: list[dict[str, Any]] = []
    mandatory_failures: list[str] = []

    for case in suite["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Eval case must be a mapping")
        case_id = str(case.get("id", ""))
        mandatory = bool(case.get("mandatory", True))
        command = EVAL_REGISTRY.get(case_id)
        if command is None:
            raise ValueError(f"Unknown frozen eval id: {case_id}")

        result = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, check=False)
        passed = result.returncode == 0
        if mandatory and not passed:
            mandatory_failures.append(case_id)
        case_results.append(
            {
                "id": case_id,
                "mandatory": mandatory,
                "claim": case.get("claim", ""),
                "protects_against": case.get("protects_against", []),
                "exit_code": result.returncode,
                "passed": passed,
                "stdout_tail": result.stdout[-3000:],
                "stderr_tail": result.stderr[-3000:],
            }
        )

    passed_count = sum(1 for case in case_results if case["passed"])
    total = len(case_results)
    status = GateStatus.PASS if not mandatory_failures else GateStatus.FAIL
    return GateResultV1(
        gate_id=gate_id,
        status=status,
        evidence_type="frozen_eval_suite",
        summary=(
            f"Frozen eval suite passed {passed_count}/{total} cases."
            if not mandatory_failures
            else f"Mandatory eval failures: {', '.join(mandatory_failures)}"
        ),
        evidence={
            "suite_id": suite.get("suite_id"),
            "suite_sha256": suite_hash,
            "frozen": True,
            "validity_risks": suite.get("validity_risks", []),
            "cases": case_results,
        },
    )
