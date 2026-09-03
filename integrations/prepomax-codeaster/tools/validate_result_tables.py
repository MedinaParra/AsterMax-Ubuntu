#!/usr/bin/env python3
"""Fail-closed admission gate for Code_Aster -> AsterMax nodal result tables.

This tool validates interoperability-table completeness only. It does not execute a
solver and must not be used as evidence of a numerical FEA result.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

SECTIONS = {
    "PPM_DEPL": ("DX", "DY", "DZ"),
    "PPM_STRESS_N": ("SIXX", "SIYY", "SIZZ"),
    "PPM_STRESS_S": ("SIXY", "SIYZ", "SIXZ"),
    "PPM_STRAIN_N": ("EPXX", "EPYY", "EPZZ"),
    "PPM_STRAIN_S": ("EPXY", "EPYZ", "EPXZ"),
}


def _split(line: str) -> list[str]:
    line = line.strip()
    while line.startswith("#"):
        line = line[1:].lstrip()
    return [x.strip() for x in line.split(";")]


def mesh_nodes(mail: Path) -> set[int]:
    text = mail.read_text(encoding="utf-8", errors="replace").splitlines()
    nodes: set[int] = set()
    in_nodes = False
    for raw in text:
        s = raw.strip()
        upper = s.upper()
        if upper == "COOR_3D":
            in_nodes = True
            continue
        if in_nodes and upper == "FINSF":
            break
        if not in_nodes or not s:
            continue
        token = s.split()[0]
        m = re.fullmatch(r"[Nn](\d+)", token)
        if m:
            nodes.add(int(m.group(1)))
    if not nodes:
        raise ValueError("No nodes found in MAIL COOR_3D section")
    return nodes


def validate(resu: Path, expected_nodes: set[int]) -> dict:
    lines = resu.read_text(encoding="utf-8", errors="replace").splitlines()
    report = {"status": "PASS", "expected_node_count": len(expected_nodes), "sections": {}}
    failures: list[str] = []

    for title, components in SECTIONS.items():
        title_idx = next((i for i, line in enumerate(lines) if title.lower() in line.lower()), -1)
        if title_idx < 0:
            failures.append(f"missing section {title}")
            continue

        header_idx = -1
        header: list[str] = []
        for i in range(title_idx + 1, min(len(lines), title_idx + 81)):
            cand = _split(lines[i])
            upper = [x.upper() for x in cand]
            if "NOEUD" in upper and all(c in upper for c in components):
                header_idx, header = i, upper
                break
        if header_idx < 0:
            failures.append(f"missing header {title}")
            continue

        node_col = header.index("NOEUD")
        cols = {c: header.index(c) for c in components}
        seen: dict[int, tuple[float, ...]] = {}
        for raw in lines[header_idx + 1 :]:
            if any(other in raw for other in SECTIONS if other != title) and seen:
                break
            tokens = _split(raw)
            if len(tokens) <= node_col:
                continue
            m = re.fullmatch(r"[Nn]?(\d+)", tokens[node_col])
            if not m:
                continue
            node = int(m.group(1))
            vals: list[float] = []
            try:
                for c in components:
                    value = float(tokens[cols[c]].replace("D", "E").replace("d", "e"))
                    if not math.isfinite(value):
                        raise ValueError
                    vals.append(value)
            except (IndexError, ValueError):
                failures.append(f"non-finite or malformed row {title}: N{node}")
                continue
            if node in seen:
                failures.append(f"duplicate node {title}: N{node}")
            seen[node] = tuple(vals)

        missing = sorted(expected_nodes - set(seen))
        extra = sorted(set(seen) - expected_nodes)
        if missing:
            failures.append(f"incomplete {title}: missing " + ",".join(f"N{x}" for x in missing))
        if extra:
            failures.append(f"unexpected nodes {title}: " + ",".join(f"N{x}" for x in extra))
        report["sections"][title] = {"rows": len(seen), "missing": missing, "extra": extra}

    if failures:
        report["status"] = "FAIL"
        report["failures"] = failures
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mail", required=True, type=Path)
    ap.add_argument("--resu", required=True, type=Path)
    ap.add_argument("--report", type=Path)
    ns = ap.parse_args()
    report = validate(ns.resu, mesh_nodes(ns.mail))
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if ns.report:
        ns.report.write_text(payload + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
