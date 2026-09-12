from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from astermax.harness.evals import run_frozen_eval_suite
from astermax.harness.models import (
    GateResultV1,
    GateStatus,
    HarnessDecision,
    HarnessDecisionV1,
    WorkPackageV1,
)
from astermax.harness.policy import evaluate_scope, validate_workpackage


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_workpackage(path: str | Path) -> tuple[WorkPackageV1, str]:
    raw = Path(path).read_bytes()
    package = WorkPackageV1.model_validate(yaml.safe_load(raw.decode("utf-8")))
    return package, hashlib.sha256(raw).hexdigest()


def get_changed_files(repo_root: Path, base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _run_command_gate(repo_root: Path, gate_id: str, command: list[str]) -> GateResultV1:
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return GateResultV1(
            gate_id=gate_id,
            status=GateStatus.ERROR,
            evidence_type="command",
            summary=f"Could not execute gate: {exc}",
            command=command,
            evidence={"exception": type(exc).__name__},
        )

    status = GateStatus.PASS if result.returncode == 0 else GateStatus.FAIL
    return GateResultV1(
        gate_id=gate_id,
        status=status,
        evidence_type="benchmark" if gate_id == "numerical_validation" else "command",
        summary=f"Command exited with {result.returncode}.",
        command=command,
        exit_code=result.returncode,
        evidence={
            "stdout_tail": result.stdout[-6000:],
            "stderr_tail": result.stderr[-6000:],
        },
    )


def run_harness(
    package_path: str | Path,
    repo_root: str | Path,
    base_ref: str,
    changed_files: list[str] | None = None,
) -> HarnessDecisionV1:
    repo_root = Path(repo_root).resolve()
    package, package_hash = load_workpackage(package_path)
    config = load_yaml(repo_root / "harness" / "config" / "harness.v1.yaml")
    gates_config = config.get("gates", {})
    known_gates = set(gates_config)

    errors = validate_workpackage(package, known_gates)
    if errors:
        return HarnessDecisionV1(
            workpackage_id=package.workpackage_id,
            workpackage_sha256=package_hash,
            decision=HarnessDecision.REJECT,
            human_merge_required=package.human_merge_required,
            reasons=errors,
        )

    files = changed_files if changed_files is not None else get_changed_files(repo_root, base_ref)
    results: list[GateResultV1] = []

    for gate_id in package.required_gates:
        gate_cfg = gates_config[gate_id]
        kind = gate_cfg.get("kind")
        if kind == "builtin_scope":
            results.append(evaluate_scope(package, files))
        elif kind == "command":
            command = gate_cfg.get("command")
            if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
                results.append(
                    GateResultV1(
                        gate_id=gate_id,
                        status=GateStatus.ERROR,
                        evidence_type="command",
                        summary="Gate command is malformed.",
                    )
                )
            else:
                results.append(_run_command_gate(repo_root, gate_id, command))
        elif kind == "frozen_eval_suite":
            suite_path = gate_cfg.get("suite")
            if not isinstance(suite_path, str) or not suite_path:
                results.append(
                    GateResultV1(
                        gate_id=gate_id,
                        status=GateStatus.ERROR,
                        evidence_type="frozen_eval_suite",
                        summary="Frozen eval suite path is malformed.",
                    )
                )
            else:
                results.append(
                    run_frozen_eval_suite(repo_root, repo_root / suite_path, gate_id)
                )
        else:
            results.append(
                GateResultV1(
                    gate_id=gate_id,
                    status=GateStatus.ERROR,
                    evidence_type="review_artifact",
                    summary=f"Unsupported gate kind: {kind}",
                )
            )

    bad = [gate for gate in results if gate.status != GateStatus.PASS]
    decision = HarnessDecision.REWORK if bad else HarnessDecision.PASS
    reasons = [f"{gate.gate_id}: {gate.status.value} - {gate.summary}" for gate in bad]

    return HarnessDecisionV1(
        workpackage_id=package.workpackage_id,
        workpackage_sha256=package_hash,
        decision=decision,
        changed_files=files,
        gates=results,
        human_merge_required=package.human_merge_required,
        reasons=reasons,
    )


def decision_json(decision: HarnessDecisionV1) -> str:
    return json.dumps(decision.model_dump(mode="json"), indent=2, sort_keys=True)
