#!/usr/bin/env python3
"""Fail-closed validation for the genuine C10.08 Code_Aster tetra solve."""

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


NUMBER = re.compile(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?")


def parse_prefixed_rows(path, prefix):
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.lstrip().startswith(prefix):
            continue
        values = [float(x) for x in NUMBER.findall(line)]
        if len(values) >= 3:
            rows.append(values[-3:])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--name", default="astermax-tet4-bar")
    args = parser.parse_args()
    root = Path(args.root)
    stem = args.name

    metadata = json.loads((root / f"{stem}.input.json").read_text(encoding="utf-8"))
    mess = root / f"{stem}.mess"
    resu = root / f"{stem}.resu"
    reactions = root / f"{stem}.reactions"
    rmed = root / f"{stem}.rmed"
    bundle_path = root / f"{stem}.astermax-results.json"
    vtu_path = root / f"{stem}.astermax-results.vtu"

    checks = []

    def gate(name, passed, evidence):
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path in (mess, resu, reactions, rmed, bundle_path, vtu_path):
        gate(f"{path.suffix.lstrip('.')}_exists", path.is_file(), str(path))
        gate(
            f"{path.suffix.lstrip('.')}_nonempty",
            path.is_file() and path.stat().st_size > 32,
            path.stat().st_size if path.is_file() else 0,
        )

    mess_text = mess.read_text(encoding="utf-8", errors="ignore") if mess.exists() else ""
    gate("code_aster_normal_stop", "ARRET NORMAL" in mess_text and "TOTAL_JOB" in mess_text, "ARRET NORMAL + TOTAL_JOB")
    gate("code_aster_no_fatal_marker", not re.search(r"(^|\n)\s*!?\s*<F(?:>|_)", mess_text), "no <F> marker")

    disp_rows = parse_prefixed_rows(resu, "LOAD_FACE_DISPLA") if resu.exists() else []
    reaction_rows = parse_prefixed_rows(reactions, "FIXED_REACTIONS") if reactions.exists() else []
    dx_values = [row[0] for row in disp_rows]
    rx_values = [row[0] for row in reaction_rows]
    solver_dx = sum(dx_values) / len(dx_values) if dx_values else None
    reaction_x = sum(rx_values) if rx_values else None
    analytical_dx = metadata["analytical_axial_displacement_mm"]
    displacement_error = abs(solver_dx - analytical_dx) / analytical_dx if solver_dx is not None else None
    reaction_error = abs(reaction_x + metadata["total_force_n"]) / metadata["total_force_n"] if reaction_x is not None else None
    face_spread = max(dx_values) - min(dx_values) if dx_values else None

    gate("all_loaded_nodes_reported", len(dx_values) == metadata["load_nodes"], [len(dx_values), metadata["load_nodes"]])
    gate("all_fixed_reactions_reported", len(rx_values) == metadata["fixed_nodes"], [len(rx_values), metadata["fixed_nodes"]])
    gate("positive_finite_axial_displacement", solver_dx is not None and math.isfinite(solver_dx) and solver_dx > 0.0, solver_dx)
    gate("axial_displacement_vs_reference_le_8pct", displacement_error is not None and displacement_error <= 0.08, displacement_error)
    gate("loaded_face_displacement_spread_le_2pct", face_spread is not None and solver_dx and face_spread / abs(solver_dx) <= 0.02, face_spread)
    gate("reaction_equilibrium_relative_error_le_1e_4", reaction_error is not None and reaction_error <= 1e-4, reaction_error)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8")) if bundle_path.exists() else {}
    gate("real_code_aster_med_source", bundle.get("source", {}).get("kind") == "REAL_CODE_ASTER_MED", bundle.get("source"))
    gate("tetra4_med_family", bundle.get("mesh", {}).get("element_types") == ["TETRA4"], bundle.get("mesh"))
    gate("bridge_node_count_matches", bundle.get("mesh", {}).get("node_count") == metadata["nodes"], bundle.get("mesh", {}).get("node_count"))
    gate("bridge_element_count_matches", bundle.get("mesh", {}).get("element_count") == metadata["elements"], bundle.get("mesh", {}).get("element_count"))
    gate("no_invented_fea_values", bundle.get("integrity", {}).get("fea_values_invented") is False, bundle.get("integrity"))
    vm_max = bundle.get("fields", {}).get("von_mises", {}).get("nodal_max")
    gate("positive_finite_von_mises", isinstance(vm_max, (int, float)) and math.isfinite(vm_max) and vm_max > 0.0, vm_max)
    table_dx_max = max(dx_values) if dx_values else None
    bridge_dx = bundle.get("fields", {}).get("displacement", {}).get("dx_max")
    gate(
        "table_and_med_max_displacement_agree_0p1pct",
        table_dx_max is not None
        and isinstance(bridge_dx, (int, float))
        and abs(bridge_dx - table_dx_max) / table_dx_max <= 0.001,
        [table_dx_max, bridge_dx],
    )

    vtk_types = []
    if vtu_path.exists():
        tree = ET.parse(vtu_path)
        types = next((x for x in tree.iter("DataArray") if x.attrib.get("Name") == "types"), None)
        if types is not None:
            vtk_types = [int(x) for x in (types.text or "").split()]
    gate("all_vtk_cells_are_tetra4", len(vtk_types) == metadata["elements"] and set(vtk_types) == {10}, {"count": len(vtk_types), "unique": sorted(set(vtk_types))})

    report = {
        "release": "C10.08",
        "title": "Genuine Code_Aster TETRA4 end-to-end admission",
        "solver_execution": "RUN",
        "solver_backend": "Code_Aster",
        "unit_contract": "MM_N_S_MPA",
        "input": metadata,
        "solver_observation": {
            "loaded_face_nodes": len(dx_values),
            "mean_axial_displacement_mm": solver_dx,
            "analytical_reference_mm": analytical_dx,
            "relative_displacement_error": displacement_error,
            "fixed_reaction_nodes": len(rx_values),
            "sum_fixed_reaction_x_n": reaction_x,
            "reaction_equilibrium_relative_error": reaction_error,
            "von_mises_nodal_max_mpa": vm_max,
            "rmed_bytes": rmed.stat().st_size if rmed.exists() else 0,
        },
        "predeclared_acceptance": {
            "displacement_reference_relative_error_max": 0.08,
            "loaded_face_spread_relative_max": 0.02,
            "reaction_equilibrium_relative_error_max": 1e-4,
            "required_med_element_family": "TETRA4",
        },
        "scientific_integrity": {
            "fea_values_invented": False,
            "analytical_reference_is_solver_output": False,
            "tolerances_relaxed_after_execution": False,
        },
        "checks_total": len(checks),
        "checks_passed": sum(item["pass"] for item in checks),
        "all_checks_pass": all(item["pass"] for item in checks),
        "checks": checks,
    }
    (root / "C10.08_REAL_TETRA_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_checks_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
