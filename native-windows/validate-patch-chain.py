#!/usr/bin/env python3
"""Validate AsterMax patch ordering and C# symbol dependencies in all workflows."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "native-windows" / "patch-chain.json"
WORKFLOWS = ROOT / ".github" / "workflows"
PATCH_RE = re.compile(r"(?<![A-Za-z0-9_.-])(?P<name>patch-[A-Za-z0-9_.-]+\\.ps1)")
QUOTED_PATCH_RE = re.compile(r"['\"](?P<name>patch-[A-Za-z0-9_.-]+\.ps1)['\"]")


def load_manifest():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    patches = data.get("patches")
    if not isinstance(patches, list):
        raise ValueError("patch-chain.json: 'patches' must be a list")
    by_file = {}
    by_id = {}
    for item in patches:
        for field in ("id", "file", "depends", "declares", "consumes"):
            if field not in item:
                raise ValueError(f"patch-chain.json: entry missing {field}: {item!r}")
        if item["file"] in by_file:
            raise ValueError(f"patch-chain.json: duplicate file {item['file']}")
        if item["id"] in by_id:
            raise ValueError(f"patch-chain.json: duplicate id {item['id']}")
        by_file[item["file"]] = item
        by_id[item["id"]] = item
    return by_file, by_id


def workflow_patch_list(path: Path):
    """Extract patch execution order, ignoring trigger path filters and comments."""
    result = []
    in_array = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]
        stripped = line.strip()
        if "$patches" in line and "@(" in line:
            in_array = True
        if in_array:
            result.extend(m.group("name") for m in QUOTED_PATCH_RE.finditer(line))
            if stripped == ")":
                in_array = False
            continue
        # Direct patch invocations always pass -Root. This excludes YAML path filters.
        if "-Root" in line and "native-windows" in line.lower():
            match = PATCH_RE.search(line)
            if match:
                result.append(match.group("name"))
    return result


def validate_manifest_coverage(by_file):
    errors = []
    actual = {p.name for p in (ROOT / "native-windows").glob("patch-*.ps1")}
    declared = set(by_file)
    for name in sorted(actual - declared):
        errors.append(f"manifest: patch file is not declared: native-windows/{name}")
    for name in sorted(declared - actual):
        errors.append(f"manifest: declared patch file does not exist: native-windows/{name}")
    return errors


def validate_workflow(path: Path, sequence, by_file, by_id):
    errors = []
    seen_ids = []
    declared_symbols = {}
    seen_files = set()
    for index, filename in enumerate(sequence, start=1):
        if filename in seen_files:
            errors.append(f"{path}: patch #{index} {filename}: duplicate execution in workflow")
            continue
        seen_files.add(filename)
        item = by_file.get(filename)
        if item is None:
            errors.append(f"{path}: patch #{index} {filename}: missing from patch-chain.json")
            continue
        for dep_id in item["depends"]:
            if dep_id not in by_id:
                errors.append(f"{path}: patch #{index} {filename}: manifest dependency id is unknown: {dep_id}")
            elif dep_id not in seen_ids:
                dep_file = by_id[dep_id]["file"]
                errors.append(
                    f"{path}: patch #{index} {filename}: dependency {dep_file} must be present earlier in this workflow"
                )
        for symbol in item["consumes"]:
            if symbol not in declared_symbols:
                errors.append(
                    f"{path}: patch #{index} {filename}: consumes C# symbol '{symbol}', "
                    "but no earlier patch in this workflow declares it"
                )
        for symbol in item["declares"]:
            declared_symbols.setdefault(symbol, filename)
        seen_ids.append(item["id"])
    return errors


def main():
    try:
        by_file, by_id = load_manifest()
    except Exception as exc:
        print(f"PATCH_CHAIN_INVALID: {exc}", file=sys.stderr)
        return 2

    errors = validate_manifest_coverage(by_file)
    validated = []
    for path in sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml"))):
        sequence = workflow_patch_list(path)
        if not sequence:
            continue
        validated.append((path, len(sequence)))
        errors.extend(validate_workflow(path, sequence, by_file, by_id))

    if errors:
        print("PATCH_CHAIN_VALIDATION=FAIL", file=sys.stderr)
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("PATCH_CHAIN_VALIDATION=PASS")
    print(f"PATCH_CHAIN_WORKFLOWS={len(validated)}")
    for path, count in validated:
        print(f"  {path.relative_to(ROOT)}: {count} patches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
