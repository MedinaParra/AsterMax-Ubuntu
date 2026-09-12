from __future__ import annotations

from pathlib import PurePosixPath

from astermax.harness.models import GateResultV1, GateStatus, WorkPackageV1


def _matches(path: str, pattern: str) -> bool:
    normalized = path.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/")
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized == prefix or normalized.startswith(prefix + "/")
    return PurePosixPath(normalized).match(normalized_pattern)


def validate_workpackage(package: WorkPackageV1, known_gates: set[str]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(set(package.required_gates) - known_gates)
    if unknown:
        errors.append(f"Unknown gates: {', '.join(unknown)}")
    if package.numerical_impact and "numerical_validation" not in package.required_gates:
        errors.append("numerical_impact requires numerical_validation gate")
    if package.validity_risks and "frontier_validity" not in package.required_gates:
        errors.append("validity_risks require frontier_validity gate")
    if not package.human_merge_required:
        errors.append("PMV policy requires human_merge_required=true")
    return errors


def evaluate_scope(package: WorkPackageV1, changed_files: list[str]) -> GateResultV1:
    issues: list[str] = []
    normalized = [path.replace("\\", "/") for path in changed_files]

    if len(normalized) > package.max_files_changed:
        issues.append(f"Changed {len(normalized)} files; limit is {package.max_files_changed}.")

    for path in normalized:
        if any(_matches(path, pattern) for pattern in package.forbidden_paths):
            issues.append(f"Forbidden path changed: {path}")
            continue
        if not any(_matches(path, pattern) for pattern in package.allowed_files):
            issues.append(f"Out-of-scope path changed: {path}")

    status = GateStatus.FAIL if issues else GateStatus.PASS
    summary = "Scope respected." if not issues else f"{len(issues)} scope issue(s)."
    return GateResultV1(
        gate_id="scope_policy",
        status=status,
        evidence_type="scope_check",
        summary=summary,
        evidence={
            "changed_files": normalized,
            "issues": issues,
            "validity_risks": package.validity_risks,
            "evaluation_budget": package.evaluation_budget.model_dump(mode="json"),
        },
    )
