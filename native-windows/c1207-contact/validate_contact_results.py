#!/usr/bin/env python3
"""Validate native contact failure reproduction and the corrected physical solve."""

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import h5py


def solver_number(value):
    number = float(value.replace("D", "E").replace("d", "e"))
    if not math.isfinite(number):
        raise RuntimeError("Non-finite value in solver observation: " + value)
    return number


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_rows(path, prefix):
    rows = []
    header = None
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tokens = line.split()
        if all(name in tokens for name in ("INTITULE", "NOEUD", "INST", "DX", "DY", "DZ")):
            header = tokens
            continue
        if not line.lstrip().startswith(prefix):
            continue
        if header is None or len(tokens) != len(header):
            raise RuntimeError("Missing or mismatched named columns in solver table: " + line)
        record = dict(zip(header, tokens))
        node = record["NOEUD"].upper()
        if not re.fullmatch(r"N\d+", node):
            raise RuntimeError("Invalid node identity in solver table: " + line)
        values = [solver_number(record[component]) for component in ("DX", "DY", "DZ")]
        rows.append((node, values, solver_number(record["INST"])))
    return rows


def med_result_times(path):
    """Read real MED field-step times, not the requested .comm selection.

    MED stores the physical time in CHA/<field>/<step>.attrs['PDT']; the
    result-step name used by the bridge is an order/iteration key, not a time.
    """
    result = {}
    with h5py.File(path, "r") as med:
        for token in ("DEPL", "SIGM_ELNO", "SIEQ_ELNO"):
            names = [name for name in med["CHA"] if name == token or name.endswith("__" + token)
                     or re.fullmatch(r"[0-9a-fA-F]{8}" + re.escape(token), name)]
            if len(names) != 1:
                raise RuntimeError(f"Expected one actual MED field for {token}, found {names}")
            field = med["CHA/" + names[0]]
            steps = [(name, group) for name, group in field.items() if isinstance(group, h5py.Group)
                     and any(location == "NOE" or location.startswith("NOE.") for location in group)]
            if len(steps) != 1 or "PDT" not in steps[0][1].attrs:
                raise RuntimeError(f"Expected one actual MED result state with physical time for {token}")
            step, group = steps[0]
            value = float(group.attrs["PDT"])
            if not math.isfinite(value):
                raise RuntimeError("Non-finite physical time in MED field " + token)
            result[token] = {"step": step, "time": value}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    contract = read_json(root / "contact-contract.json")
    metadata = read_json(root / "contact-fixture.input.json")
    decks = read_json(root / "contact-validation-decks.json")
    stem = metadata["case"]
    corrected, original = root / "corrected", root / "original"
    receipt = read_json(corrected / "compiled-export-receipt.json")
    negative = read_json(root / "negative-control.json")
    positive = read_json(root / "corrected-run.json")
    probe = read_json(root / "native-probe.json")
    checks = []

    def gate(name, passed, evidence):
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    gate("native_windows_probe", probe.get("ready") and probe.get("transport") == "WINDOWS_NATIVE"
         and probe.get("wsl_required") is False, probe)
    gate("compiled_packaged_exporter", receipt.get("export_source") == "COMPILED_ASTERMAX_EXECUTABLE"
         and receipt.get("executable_sha256") == sha256(Path(args.executable))
         and receipt.get("dependency_resolution") == "PACKAGE_DIRECTORY_ONLY", receipt)
    gate("contract_identity", receipt.get("contract_sha256") == metadata["contract_sha256"]
         == sha256(root / "contact-contract.json"), metadata["contract_sha256"])
    gate("original_twelve_shared_slave_nodes", metadata["original_shared_slave_node_count"] == 12
         and decks.get("original_shared_slave_nodes") == 12, metadata["original_shared_slave_nodes"])
    gate("corrected_slave_membership_disjoint", decks.get("exported_shared_slave_nodes") == 0, decks.get("zones"))
    gate("same_faces_and_contact_law", decks.get("mesh_and_faces_preserved") is True
         and decks.get("contact_law_preserved") is True
         and decks.get("mechanical_difference") == "MASTER_SLAVE_ORIENTATION_ONLY", decks.get("mechanical_difference"))
    input_integrity = {relative: (root / relative).is_file() and sha256(root / relative) == expected
                       for relative, expected in decks.get("input_sha256", {}).items()}
    gate("inputs_unchanged_by_execution", bool(input_integrity) and all(input_integrity.values()), input_integrity)

    negative_mess = [path for path in original.rglob("*.mess")
                     if "CONTACT2_16" in path.read_text(encoding="utf-8", errors="replace")]
    gate("legacy_contact2_16_reproduced", negative.get("exit_code") == 31
         and negative.get("marker") == "CONTACT2_16" and negative.get("contact_zones") == [1, 2]
         and bool(negative_mess), negative)
    gate("legacy_failure_reports_twelve_nodes", negative.get("shared_slave_nodes") == 12,
         negative.get("shared_slave_nodes"))
    gate("legacy_failure_not_promoted", not (original / f"{stem}.rmed").exists()
         and not (original / f"{stem}.mess").exists(), "failed outputs retained in failed-* only")
    gate("corrected_native_process_success", positive.get("exit_code") == 0, positive)

    paths = {suffix: corrected / f"{stem}.{suffix}"
             for suffix in ("mess", "resu", "reactions", "rmed", "astermax-results.json", "astermax-results.vtu")}
    for label, path in paths.items():
        gate(label + "_nonempty", path.is_file() and path.stat().st_size > 32,
             path.stat().st_size if path.is_file() else 0)
    mess = paths["mess"].read_text(encoding="utf-8", errors="replace") if paths["mess"].is_file() else ""
    gate("code_aster_identity", re.search(r"CODE[_ -]?ASTER", mess, re.IGNORECASE), "Code_Aster identity in actual .mess")
    gate("code_aster_normal_termination", re.search(r"ARR(?:E|\u00ca|\u00db|\ufffd)T\s+NORMAL", mess, re.IGNORECASE)
         and "TOTAL_JOB" in mess, "normal stop and TOTAL_JOB")
    gate("corrected_no_fatal_diagnostic", not re.search(r"<F(?:>|_)|<EXCEPTION>|_ABNORMAL_ABORT|CONTACT2_16|ERREUR[ _]+FATALE|FATAL ERROR|Traceback \(most recent call last\)",
                                                       mess, re.IGNORECASE), "no fatal solver diagnostic")
    gate("contact_nonlinear_solve_executed", "DEFI_CONTACT" in mess and "STAT_NON_LINE" in mess,
         "both operators present in genuine solver output")

    reactions = table_rows(paths["reactions"], "FIXED_REACTIONS")
    displacements = table_rows(paths["resu"], "LOAD_FACE_DISPLA")
    final_time = metadata["predeclared_acceptance"]["required_final_time"]
    table_times = sorted({row[2] for row in reactions + displacements})
    gate("reaction_and_displacement_tables_at_final_time", bool(reactions) and bool(displacements)
         and table_times == [final_time], {"observed_times": table_times, "required": final_time})
    fixed_ids, load_ids = set(metadata["fixed_nodes"]), set(metadata["loaded_nodes"])
    gate("exact_fixed_reaction_nodes", len(reactions) == len(fixed_ids)
         and {row[0] for row in reactions} == fixed_ids, {"observed": len(reactions), "expected": len(fixed_ids)})
    gate("exact_loaded_displacement_nodes", len(displacements) == len(load_ids)
         and {row[0] for row in displacements} == load_ids, {"observed": len(displacements), "expected": len(load_ids)})
    total_reaction = [sum(row[1][axis] for row in reactions) for axis in range(3)]
    applied = metadata["applied_force_n"]
    force_scale = max(abs(value) for value in applied)
    equilibrium_error = [abs(total_reaction[axis] + applied[axis]) / force_scale for axis in range(3)]
    reaction_tolerance = metadata["predeclared_acceptance"]["reaction_equilibrium_relative_error_max"]
    gate("global_force_equilibrium", bool(reactions) and max(equilibrium_error) <= reaction_tolerance,
         {"reaction_n": total_reaction, "applied_n": applied, "relative_error": equilibrium_error})
    left_ids, bottom_ids = set(metadata["fixed_left_nodes"]), set(metadata["fixed_bottom_nodes"])
    left_reaction = sum(row[1][0] for row in reactions if row[0] in left_ids)
    bottom_reaction = sum(row[1][1] for row in reactions if row[0] in bottom_ids)
    gate("both_contacts_transfer_compression", left_reaction > 0.1 * force_scale and bottom_reaction > 0.1 * force_scale,
         {"left_support_rx_n": left_reaction, "bottom_support_ry_n": bottom_reaction})
    mean_u = [sum(row[1][axis] for row in displacements) / len(displacements) if displacements else None
              for axis in range(3)]
    gate("loaded_body_moves_into_both_supports", all(value is not None and math.isfinite(value) and value < 0 for value in mean_u[:2]), mean_u)

    bundle = read_json(paths["astermax-results.json"])
    actual_times = med_result_times(paths["rmed"])
    gate("actual_med_fields_at_final_time", all(item["time"] == final_time for item in actual_times.values())
         and {item["step"] for item in actual_times.values()} == {bundle.get("source", {}).get("med_result_step")},
         {"observed_fields": actual_times, "required": final_time})
    gate("actual_med_result_source", bundle.get("source", {}).get("kind") == "REAL_CODE_ASTER_MED", bundle.get("source"))
    gate("no_invented_results", bundle.get("integrity", {}).get("fea_values_invented") is False, bundle.get("integrity"))
    mesh = bundle.get("mesh", {})
    gate("med_matches_fixture_mesh", mesh.get("node_count") == metadata["nodes"]
         and mesh.get("element_count") == metadata["elements"] and mesh.get("element_types") == ["HEXA8"], mesh)
    arrays = bundle.get("arrays", {})
    coordinates, med_u = arrays.get("coordinates", []), arrays.get("displacement", [])
    finite_arrays = len(coordinates) == len(med_u) == metadata["nodes"] and all(
        len(row) == 3 and all(isinstance(value, (int, float)) and math.isfinite(value) for value in row)
        for row in coordinates + med_u)
    gate("finite_med_displacements", finite_arrays, {"coordinates": len(coordinates), "displacements": len(med_u)})
    med_loaded = [u for xyz, u in zip(coordinates, med_u) if len(xyz) == 3
                  and abs(xyz[0] - 1.0) < 1e-10 and abs(xyz[1] - 1.0) < 1e-10]
    med_mean = [sum(row[axis] for row in med_loaded) / len(med_loaded) if med_loaded else None for axis in range(3)]
    comparison_errors = [abs(med_mean[axis] - mean_u[axis]) / max(abs(mean_u[axis]), 1e-15)
                         if med_mean[axis] is not None and mean_u[axis] is not None else None for axis in range(2)]
    gate("med_and_solver_table_agree", len(med_loaded) == len(load_ids)
         and all(error is not None and error <= metadata["predeclared_acceptance"]["table_med_displacement_relative_error_max"]
                 for error in comparison_errors), {"table_mean_mm": mean_u, "med_mean_mm": med_mean, "relative_error_xy": comparison_errors})
    # Loaded-edge coordinates are unique across the three independent bodies.
    # Compare each actual node, so a displacement permutation cannot pass merely
    # because the two means happen to agree. Keep the predeclared XY tolerance.
    fixture_nodes = {node["id"]: [node[axis] for axis in ("x", "y", "z")]
                     for node in contract["mesh"]["nodes"]}
    nodal_errors = {}
    if finite_arrays:
        for node_id, observed_u, _instant in displacements:
            target = fixture_nodes[node_id]
            matches = [i for i, xyz in enumerate(coordinates)
                       if all(abs(xyz[axis] - target[axis]) < 1e-10 for axis in range(3))]
            if len(matches) != 1:
                nodal_errors[node_id] = {"coordinate_matches": len(matches)}
                continue
            imported_u = med_u[matches[0]]
            nodal_errors[node_id] = {"relative_error_xy": [
                abs(imported_u[axis] - observed_u[axis]) / max(abs(observed_u[axis]), 1e-15)
                for axis in range(2)]}
    gate("med_and_solver_table_agree_at_every_loaded_node", set(nodal_errors) == load_ids
         and all("relative_error_xy" in item and all(
             error <= metadata["predeclared_acceptance"]["table_med_displacement_relative_error_max"]
             for error in item["relative_error_xy"]) for item in nodal_errors.values()), nodal_errors)
    fixed_med = [u for xyz, u in zip(coordinates, med_u) if len(xyz) == 3
                 and (abs(xyz[0] + 1.0) < 1e-10 or abs(xyz[1] + 1.0) < 1e-10)]
    fixed_max = max((abs(value) for row in fixed_med for value in row), default=None)
    gate("fixed_boundary_displacement_zero", len(fixed_med) == len(fixed_ids) and fixed_max is not None
         and fixed_max <= metadata["predeclared_acceptance"]["fixed_displacement_absolute_max_mm"], fixed_max)
    vm = bundle.get("fields", {}).get("von_mises", {}).get("nodal_max")
    gate("positive_finite_stress", isinstance(vm, (int, float)) and math.isfinite(vm) and vm > 0, vm)
    vtk_types = []
    if paths["astermax-results.vtu"].is_file():
        tree = ET.parse(paths["astermax-results.vtu"])
        types = next((item for item in tree.iter("DataArray") if item.attrib.get("Name") == "types"), None)
        if types is not None:
            vtk_types = [int(value) for value in (types.text or "").split()]
    gate("vtu_preserves_volume_cells", len(vtk_types) == metadata["elements"] and set(vtk_types) == {12},
         {"count": len(vtk_types), "types": sorted(set(vtk_types))})

    report = {
        "release": "C12.07", "title": "Native Windows shared-slave contact regression",
        "transport": "WINDOWS_NATIVE", "solver_execution": "RUN", "synthetic_results_allowed": False,
        "export_source": receipt.get("export_source"), "executable_sha256": receipt.get("executable_sha256"),
        "negative_control": negative, "topology": decks.get("zones"),
        "original_shared_slave_nodes": metadata["original_shared_slave_node_count"],
        "exported_shared_slave_nodes": decks.get("exported_shared_slave_nodes"),
        "contact_law_preserved": decks.get("contact_law_preserved"),
        "observed": {"reaction_n": total_reaction, "force_equilibrium_relative_error": equilibrium_error,
                     "left_support_rx_n": left_reaction, "bottom_support_ry_n": bottom_reaction,
                     "table_loaded_mean_displacement_mm": mean_u, "med_loaded_mean_displacement_mm": med_mean,
                     "von_mises_nodal_max_mpa": vm, "rmed_bytes": paths["rmed"].stat().st_size if paths["rmed"].exists() else 0,
                     "med_field_times": actual_times, "table_times": table_times,
                     "loaded_node_table_med_errors": nodal_errors},
        "predeclared_acceptance": metadata["predeclared_acceptance"],
        "scientific_integrity": {"fea_values_invented": False, "tolerances_relaxed_after_execution": False,
                                 "negative_control_difference": "MASTER_SLAVE_ORIENTATION_ONLY",
                                 "observation_only_instrumentation": decks.get("observation_only_instrumentation")},
        "checks_total": len(checks), "checks_passed": sum(item["pass"] for item in checks),
        "all_checks_pass": all(item["pass"] for item in checks), "checks": checks,
        "output_sha256": {path.name: sha256(path) for path in paths.values() if path.is_file()},
    }
    (root / "C12.07_NATIVE_CONTACT_VALIDATION.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_checks_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
