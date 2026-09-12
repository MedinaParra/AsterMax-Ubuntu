#!/usr/bin/env python3
"""Independent closed-form verification for the real Code_Aster tetra smoke case.

This verifier intentionally does not call Code_Aster and does not reuse solver output
formulas. It checks the known one-element mechanics problem in the AsterMax unit
system (mm, N, MPa) against the semicolon tables emitted in smoke.resu.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple

SCHEMA = "astermax.code-aster.linear-tetra-oracle.v1"
L_MM = 100.0
E_MPA = 210000.0
NU = 0.30
FX_N = 1000.0
REL_TOL = 1.0e-6
ABS_TOL = 1.0e-10


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(line: str) -> str:
    return line.lstrip("# ").strip()


def split_row(line: str) -> List[str]:
    return [token.strip() for token in line.split(";")]


def node_id(token: str) -> int:
    value = token.strip()
    if value[:1].lower() == "n":
        value = value[1:]
    if not re.fullmatch(r"\d+", value):
        raise ValueError(f"Invalid node identifier: {token!r}")
    return int(value)


def finite_float(token: str) -> float:
    value = float(token.strip().replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ValueError(f"Non-finite numeric value: {token!r}")
    return value


def parse_table(lines: List[str], title: str) -> Tuple[List[str], Dict[int, Dict[str, float]]]:
    title_index = next((i for i, line in enumerate(lines) if title.lower() in line.lower()), -1)
    if title_index < 0:
        raise ValueError(f"Missing table {title}")

    header_index = -1
    header: List[str] = []
    for i in range(title_index + 1, min(len(lines), title_index + 90)):
        current = normalize(lines[i])
        if ";" not in current:
            continue
        tokens = split_row(current)
        if any(token.upper() == "NOEUD" for token in tokens):
            header_index = i
            header = [token.upper() for token in tokens]
            break
    if header_index < 0:
        raise ValueError(f"Missing NOEUD header for {title}")

    node_col = header.index("NOEUD")
    rows: Dict[int, Dict[str, float]] = {}
    for i in range(header_index + 1, len(lines)):
        raw = lines[i].strip()
        if rows and (not raw or "PPM_" in raw):
            break
        current = normalize(raw)
        if not current or ";" not in current:
            continue
        tokens = split_row(current)
        if node_col >= len(tokens):
            continue
        try:
            nid = node_id(tokens[node_col])
        except ValueError:
            continue
        if nid in rows:
            raise ValueError(f"Duplicate node N{nid} in {title}")
        values: Dict[str, float] = {}
        for col, name in enumerate(header):
            if name == "NOEUD" or col >= len(tokens):
                continue
            try:
                values[name] = finite_float(tokens[col])
            except ValueError:
                continue
        rows[nid] = values
    if set(rows) != {1, 2, 3, 4}:
        raise ValueError(f"{title} node set mismatch: {sorted(rows)}")
    return header, rows


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def add_check(checks: List[dict], name: str, actual: float | str | bool, expected: float | str | bool, passed: bool) -> None:
    checks.append({"name": name, "actual": actual, "expected": expected, "passed": bool(passed)})


def validate_source_contract(mail: Path, comm: Path, checks: List[dict]) -> None:
    mail_text = mail.read_text(encoding="utf-8", errors="replace")
    comm_text = comm.read_text(encoding="utf-8", errors="replace")

    required_nodes = (
        "N1 0.0 0.0 0.0",
        "N2 100.0 0.0 0.0",
        "N3 0.0 100.0 0.0",
        "N4 0.0 0.0 100.0",
    )
    nodes_ok = all(token in mail_text for token in required_nodes)
    add_check(checks, "source:mm_geometry", nodes_ok, True, nodes_ok)

    material_ok = bool(re.search(r"E\s*=\s*2\.10E5\b", comm_text, flags=re.IGNORECASE))
    add_check(checks, "source:E_MPa", material_ok, True, material_ok)

    load_ok = bool(re.search(r"FX\s*=\s*1000\.0\b", comm_text, flags=re.IGNORECASE))
    add_check(checks, "source:load_N", load_ok, True, load_ok)


def verify(resu: Path, mail: Path, comm: Path) -> dict:
    checks: List[dict] = []
    validate_source_contract(mail, comm, checks)

    lines = resu.read_text(encoding="utf-8", errors="replace").splitlines()
    _, depl = parse_table(lines, "PPM_DEPL")
    _, stress_n = parse_table(lines, "PPM_STRESS_N")
    _, stress_s = parse_table(lines, "PPM_STRESS_S")

    # Closed-form oracle. With N1/N2/N3 fully fixed and only N4 free, the
    # horizontal stiffness is k_x = V * G / L^2 = G*L/6.
    shear_modulus_mpa = E_MPA / (2.0 * (1.0 + NU))
    kx_n_per_mm = shear_modulus_mpa * L_MM / 6.0
    expected_dx_mm = FX_N / kx_n_per_mm
    expected_sixz_mpa = shear_modulus_mpa * (expected_dx_mm / L_MM)

    for nid in (1, 2, 3):
        for component in ("DX", "DY", "DZ"):
            actual = depl[nid][component]
            add_check(checks, f"depl:N{nid}:{component}", actual, 0.0, close(actual, 0.0))

    for component, expected in (("DX", expected_dx_mm), ("DY", 0.0), ("DZ", 0.0)):
        actual = depl[4][component]
        add_check(checks, f"depl:N4:{component}", actual, expected, close(actual, expected))

    for nid in (1, 2, 3, 4):
        for component in ("SIXX", "SIYY", "SIZZ"):
            actual = stress_n[nid][component]
            add_check(checks, f"stress_n:N{nid}:{component}", actual, 0.0, close(actual, 0.0))
        for component, expected in (("SIXY", 0.0), ("SIYZ", 0.0), ("SIXZ", expected_sixz_mpa)):
            actual = stress_s[nid][component]
            add_check(checks, f"stress_s:N{nid}:{component}", actual, expected, close(actual, expected))

    passed = all(check["passed"] for check in checks)
    return {
        "schema": SCHEMA,
        "status": "PASS" if passed else "FAIL",
        "unit_system": {"length": "mm", "force": "N", "stress": "MPa"},
        "oracle": {
            "type": "closed_form_single_linear_tetra",
            "length_mm": L_MM,
            "young_modulus_mpa": E_MPA,
            "poisson_ratio": NU,
            "load_fx_n": FX_N,
            "shear_modulus_mpa": shear_modulus_mpa,
            "kx_n_per_mm": kx_n_per_mm,
            "expected_loaded_dx_mm": expected_dx_mm,
            "expected_sixz_mpa": expected_sixz_mpa,
            "relative_tolerance": REL_TOL,
            "absolute_tolerance": ABS_TOL,
        },
        "provenance": {
            "resu_sha256": sha256(resu),
            "mail_sha256": sha256(mail),
            "comm_sha256": sha256(comm),
        },
        "claims": {
            "fea_solve_executed": True,
            "numerical_verification": passed,
            "results_verified": passed,
            "industrial_validation": False,
            "ansys_equivalence": False,
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resu", type=Path, default=Path("smoke.resu"))
    parser.add_argument("--mail", type=Path, default=Path("smoke.mail"))
    parser.add_argument("--comm", type=Path, default=Path("smoke.comm"))
    parser.add_argument("--report", type=Path, default=Path("smoke.oracle.json"))
    args = parser.parse_args()

    try:
        report = verify(args.resu.resolve(), args.mail.resolve(), args.comm.resolve())
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
            "claims": {
                "fea_solve_executed": False,
                "numerical_verification": False,
                "results_verified": False,
                "industrial_validation": False,
                "ansys_equivalence": False,
            },
        }

    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.report)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
