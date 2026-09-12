from __future__ import annotations

from astermax.harness.models import WorkPackageV1
from astermax.harness.policy import evaluate_scope, validate_workpackage


def package(**overrides) -> WorkPackageV1:
    data = {
        "workpackage_id": "TEST-001",
        "title": "Bounded change",
        "objective": "Exercise harness policy",
        "issue": 1,
        "allowed_files": ["src/astermax/solver/**", "tests/test_solver_*.py"],
        "forbidden_paths": ["harness/**"],
        "max_files_changed": 3,
        "prohibited_actions": ["fabricate results"],
        "acceptance_criteria": ["scope gate passes"],
        "required_gates": ["scope_policy", "unit_tests"],
        "numerical_impact": False,
        "human_merge_required": True,
    }
    data.update(overrides)
    return WorkPackageV1.model_validate(data)


def test_scope_passes_for_allowed_files() -> None:
    result = evaluate_scope(
        package(),
        ["src/astermax/solver/bridge.py", "tests/test_solver_bridge.py"],
    )
    assert result.status.value == "PASS"
    assert result.evidence["issues"] == []


def test_scope_fails_closed_for_forbidden_and_outside_paths() -> None:
    result = evaluate_scope(
        package(),
        ["harness/config/harness.v1.yaml", "README.md"],
    )
    assert result.status.value == "FAIL"
    assert len(result.evidence["issues"]) == 2


def test_scope_enforces_change_budget() -> None:
    result = evaluate_scope(
        package(max_files_changed=1),
        ["src/astermax/solver/a.py", "src/astermax/solver/b.py"],
    )
    assert result.status.value == "FAIL"
    assert "limit is 1" in result.evidence["issues"][0]


def test_numerical_work_requires_numerical_gate() -> None:
    item = package(numerical_impact=True)
    errors = validate_workpackage(
        item,
        {"scope_policy", "unit_tests", "numerical_validation", "frontier_validity"},
    )
    assert "numerical_impact requires numerical_validation gate" in errors


def test_validity_risks_require_frozen_frontier_gate() -> None:
    item = package(validity_risks=["reward_hacking"])
    errors = validate_workpackage(
        item,
        {"scope_policy", "unit_tests", "frontier_validity"},
    )
    assert "validity_risks require frontier_validity gate" in errors


def test_scope_evidence_records_budget_and_validity_risks() -> None:
    item = package(
        validity_risks=["scope_escape"],
        evaluation_budget={"max_tool_calls": 20, "max_retries": 2},
    )
    result = evaluate_scope(item, ["src/astermax/solver/bridge.py"])
    assert result.evidence["validity_risks"] == ["scope_escape"]
    assert result.evidence["evaluation_budget"]["max_tool_calls"] == 20


def test_unknown_gate_is_rejected() -> None:
    item = package(required_gates=["scope_policy", "invented_gate"])
    errors = validate_workpackage(item, {"scope_policy", "unit_tests"})
    assert errors == ["Unknown gates: invented_gate"]


def test_human_merge_is_required_for_pmv() -> None:
    item = package(human_merge_required=False)
    errors = validate_workpackage(item, {"scope_policy", "unit_tests"})
    assert "PMV policy requires human_merge_required=true" in errors
