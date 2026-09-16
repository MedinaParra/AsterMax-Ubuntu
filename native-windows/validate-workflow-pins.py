#!/usr/bin/env python3
"""Fail if a GitHub workflow checks out PrePoMax without the approved immutable commit."""
from pathlib import Path
import re
import sys

PIN = "3669e65581650e5d9d868aa761db9efd856f8571"
WORKFLOWS = Path(".github/workflows")
REPOSITORY = re.compile(r"^\s*repository\s*:\s*tsvilans/PrePoMax\s*(?:#.*)?$", re.IGNORECASE)
REF = re.compile(r"^\s*ref\s*:\s*([^\s#]+)")


def inspect(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    errors = []
    checkouts = 0
    for i, line in enumerate(lines):
        if not REPOSITORY.match(line):
            continue
        checkouts += 1
        value = None
        # repository/ref/path live in the same small `with:` mapping. Stop at the next step.
        for candidate in lines[i + 1:i + 9]:
            stripped = candidate.lstrip()
            if stripped.startswith("- name:") or stripped.startswith("- uses:"):
                break
            match = REF.match(candidate)
            if match:
                value = match.group(1).strip("'\"")
                break
        if value is None:
            errors.append(f"{path}:{i+1}: PrePoMax checkout has no explicit ref")
        elif value != PIN:
            errors.append(
                f"{path}:{i+1}: PrePoMax ref {value!r} is not approved pin {PIN}"
            )
    return checkouts, errors


def main():
    files = sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))
    total = 0
    errors = []
    for path in files:
        count, found = inspect(path)
        total += count
        errors.extend(found)
    if total == 0:
        print("WORKFLOW_PIN_AUDIT=FAIL: no tsvilans/PrePoMax checkout found", file=sys.stderr)
        return 2
    if errors:
        print("WORKFLOW_PIN_AUDIT=FAIL", file=sys.stderr)
        for error in errors:
            print(" - " + error, file=sys.stderr)
        return 1
    print(f"WORKFLOW_PIN_AUDIT=PASS checkouts={total} pin={PIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
