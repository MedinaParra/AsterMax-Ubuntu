#!/usr/bin/env python3
"""Validate selected Code_Aster .resu values against explicit engineering references.

The validator is part of the AsterMax harness test infrastructure. It does not create
or alter FEA results. A contract identifies table, node, component, expected value and
absolute/relative tolerances. Any missing/non-finite/out-of-tolerance value fails closed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class ReferenceError(RuntimeError):
    pass


def normalize(line: str) -> str:
    return (line or "").lstrip("# ").strip()


def split(line: str) -> List[str]:
    return [token.strip() for token in line.split(";")]


def node_id(token: str):
    value = (token or "").strip()
    if value[:1].lower() == "n":
        value = value[1:]
    return int(value) if re.fullmatch(r"\d+", value) else None


def finite_float(token: str):
    try:
        value = float((token or "").strip().replace("D", "E").replace("d", "e"))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_tables(path: Path) -> Dict[str, Dict[int, Dict[str, float]]]:
    if not path.exists() or path.stat().st_size == 0:
        raise ReferenceError("Missing or empty Code_Aster .resu: " + str(path))
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    titles = ["PPM_DEPL", "PPM_STRESS_N", "PPM_STRESS_S", "PPM_STRAIN_N", "PPM_STRAIN_S"]
    result: Dict[str, Dict[int, Dict[str, float]]] = {}

    for title in titles:
        title_index = next((i for i, line in enumerate(lines) if title.lower() in line.lower()), -1)
        if title_index < 0:
            continue
        header_index = -1
        header: List[str] = []
        for i in range(title_index + 1, min(len(lines), title_index + 90)):
            text = normalize(lines[i])
            if ";" not in text:
                continue
            tokens = split(text)
            upper = [x.upper() for x in tokens]
            if "NOEUD" in upper:
                header_index = i
                header = upper
                break
        if header_index < 0:
            continue

        inode = header.index("NOEUD")
        table: Dict[int, Dict[str, float]] = {}
        rows = 0
        for i in range(header_index + 1, len(lines)):
            raw = lines[i].strip()
            if rows > 0 and (not raw or "PPM_" in raw):
                break
            text = normalize(raw)
            if not text or ";" not in text:
                continue
            tokens = split(text)
            if inode >= len(tokens):
                continue
            nid = node_id(tokens[inode])
            if nid is None:
                continue
            values: Dict[str, float] = {}
            for column, name in enumerate(header):
                if column == inode or column >= len(tokens):
                    continue
                value = finite_float(tokens[column])
                if value is not None:
                    values[name] = value
            table[nid] = values
            rows += 1
        result[title] = table
    return result


def validate(resu: Path, contract: Path) -> int:
    raw = json.loads(contract.read_text(encoding="utf-8"))
    expectations = raw.get("expectations")
    if not isinstance(expectations, list) or not expectations:
        raise ReferenceError("Contract must contain a non-empty expectations array.")

    tables = read_tables(resu)
    failures = 0
    print("AsterMax numerical reference contract")
    print("RESU:", resu)
    print("Contract:", contract)

    for index, item in enumerate(expectations, 1):
        if not isinstance(item, dict):
            raise ReferenceError("Expectation must be an object at index %d." % index)
        table = str(item.get("table", "")).strip().upper()
        component = str(item.get("component", "")).strip().upper()
        node = int(item.get("node"))
        expected = float(item.get("expected"))
        abs_tol = float(item.get("abs_tol", 0.0))
        rel_tol = float(item.get("rel_tol", 0.0))
        if abs_tol < 0 or rel_tol < 0:
            raise ReferenceError("Tolerances must be non-negative.")
        if not math.isfinite(expected):
            raise ReferenceError("Expected values must be finite.")

        actual = tables.get(table, {}).get(node, {}).get(component)
        allowed = max(abs_tol, rel_tol * abs(expected))
        passed = actual is not None and math.isfinite(actual) and abs(actual - expected) <= allowed
        delta = None if actual is None else actual - expected
        status = "PASS" if passed else "FAIL"
        print(
            f"{status} {table}[N{node}].{component}: actual={actual!r} expected={expected:.16g} "
            f"delta={delta!r} allowed={allowed:.6g}"
        )
        if not passed:
            failures += 1

    if failures:
        print("Numerical reference contract: FAIL (%d expectation(s))" % failures, file=sys.stderr)
        return 1
    print("Numerical reference contract: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resu", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    args = parser.parse_args()
    try:
        return validate(args.resu.resolve(), args.contract.resolve())
    except Exception as exc:
        print("Numerical reference contract: ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
