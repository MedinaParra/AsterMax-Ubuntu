#!/usr/bin/env python3
"""Admit only actual native Code_Aster/MED results for both bonded regressions."""

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from generate_bonded_fixture import cross

# Use the established real MED-step and named solver-table readers. They never
# substitute analytical values for results or execute the solver input.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "c1207-contact"))
from validate_contact_results import med_result_times, read_json, sha256, table_rows


def vector_sum(vectors):
    return [sum(vector[axis] for vector in vectors) for axis in range(3)]


def finite_matrix(values, count):
    return len(values) == count and all(isinstance(row, list) and len(row) == 3 and all(
        isinstance(value, (int, float)) and math.isfinite(value) for value in row) for row in values)


def validate_case(directory, executable_hash):
    metadata = read_json(directory / "bonded-fixture.input.json")
    contract = read_json(directory / "bonded-contract.json")
    deck = read_json(directory / "bonded-validation-deck.json")
    output = directory / "exported"
    stem = metadata["stem"]
    receipt = read_json(output / "compiled-export-receipt.json")
    manifest = read_json(output / f"{stem}.native-export.json")
    planner = manifest.get("bonded_mpc_report", {})
    execution = read_json(directory / "native-run.json")
    acceptance = metadata["predeclared_acceptance"]
    checks = []

    def gate(name, passed, evidence):
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    gate("compiled_packaged_exporter", receipt.get("export_source") == "COMPILED_ASTERMAX_EXECUTABLE"
         and receipt.get("executable_sha256") == executable_hash
         and receipt.get("dependency_resolution") == "PACKAGE_DIRECTORY_ONLY"
         and receipt.get("exporter_version") == "C12.08-bonded-mpc-v1", receipt)
    gate("source_contract_unchanged", receipt.get("source_contract_modified") is False
         and receipt.get("contract_sha256") == metadata["contract_sha256"]
         == sha256(directory / "bonded-contract.json"), metadata["contract_sha256"])
    gate("synthetic_nonmatching_shared_edge_fixture", metadata["nodes"] == 87 and metadata["elements"] == 192
         and metadata["bodies"] == 2 and metadata["tie_count"] == 2
         and metadata["shared_slave_node_count"] == 4
         and metadata["master_interface_faces"] != metadata["slave_interface_faces"]
         and metadata.get("private_user_geometry_included") is False,
         {key: metadata[key] for key in ("nodes", "elements", "tie_count", "shared_slave_nodes",
                                        "master_interface_faces", "slave_interface_faces")})
    gate("gap_mesh_law_supports_and_loads_preserved", deck.get("gap_preserved_mm") == metadata["gap_mm"] == 2.5
         and all(deck.get(key) is True for key in ("mesh_preserved", "bonded_law_preserved", "supports_and_loads_preserved", "material_preserved")),
         {key: deck.get(key) for key in ("gap_preserved_mm", "mesh_preserved", "bonded_law_preserved", "supports_and_loads_preserved", "material_preserved")})
    gate("every_binding_uses_its_selected_adjacent_tetrahedron", deck.get("all_binding_candidates_checked") == 24
         and deck.get("adjacent_master_tetrahedra_verified") is True,
         {key: deck.get(key) for key in ("all_binding_candidates_checked", "adjacent_master_tetrahedra_verified")})
    raw_expected = 3 * sum(len({node for face in tie["slave"]["elements"] for node in face["nodes"]})
                           for tie in contract["bonded_ties"])
    gate("production_planner_covers_every_candidate", planner.get("raw_rows") == raw_expected
         and planner.get("retained_rows") == deck["independent_mpc_rows"]
         and planner.get("retained_rows", 0) + planner.get("redundant_rows", 0) == raw_expected
         and planner.get("unmatched_slave_node_count") == 0,
         planner)
    gate("independent_rank_and_affine_invariance", deck.get("relative_smallest_singular_value", 0)
         > acceptance["rank_relative_singular_value_min"]
         and deck.get("maximum_affine_residual_mm", float("inf"))
         <= acceptance["affine_equation_residual_absolute_max_mm"],
         {key: deck.get(key) for key in ("independent_mpc_rows", "support_dof_count",
                                        "relative_smallest_singular_value", "maximum_affine_residual_mm")})
    input_integrity = {relative: (output / relative).is_file() and sha256(output / relative) == expected
                       for relative, expected in deck.get("input_sha256", {}).items()}
    gate("inputs_unchanged_during_native_execution", bool(input_integrity) and all(input_integrity.values()), input_integrity)
    gate("native_process_success", execution.get("exit_code") == 0 and execution.get("transport") == "WINDOWS_NATIVE"
         and execution.get("solver_execution") == "RUN" and execution.get("synthetic_results_allowed") is False, execution)

    paths = {suffix: output / f"{stem}.{suffix}" for suffix in (
        "mess", "resu", "reactions", "rmed", "astermax-results.json", "astermax-results.vtu")}
    for label, path in paths.items():
        gate(label + "_nonempty", path.is_file() and path.stat().st_size > 32,
             path.stat().st_size if path.is_file() else 0)
    mess = paths["mess"].read_text(encoding="utf-8", errors="replace") if paths["mess"].is_file() else ""
    gate("code_aster_identity_and_normal_termination", re.search(r"CODE[_ -]?ASTER", mess, re.IGNORECASE)
         and re.search(r"ARR(?:E|\u00ca|\u00db|\ufffd)T\s+NORMAL", mess, re.IGNORECASE) and "TOTAL_JOB" in mess,
         "Actual .mess must identify Code_Aster, normal termination, and TOTAL_JOB.")
    gate("no_fatal_solver_diagnostic", not re.search(
        r"<F(?:>|_)|<EXCEPTION>|_ABNORMAL_ABORT|ERREUR[ _]+FATALE|FATAL ERROR|Traceback \(most recent call last\)",
        mess, re.IGNORECASE), "No fatal diagnostic in actual solver output.")
    gate("real_bonded_linear_operators_executed", "LIAISON_DDL" in mess and "MECA_STATIQUE" in mess
         and "DEFI_CONTACT" not in mess, "MPC and static solve operators in actual solver output.")
    reactions = table_rows(paths["reactions"], "BOND_REACTIONS")
    displacements = table_rows(paths["resu"], "LOAD_FACE_DISPLA")
    reaction_ids, all_ids = set(metadata["reaction_nodes"]), {node["id"] for node in contract["mesh"]["nodes"]}
    gate("exact_prescribed_reaction_nodes", len(reactions) == len(reaction_ids)
         and {row[0] for row in reactions} == reaction_ids, {"observed": len(reactions), "expected": len(reaction_ids)})
    gate("exact_all_node_displacement_table", len(displacements) == len(all_ids)
         and {row[0] for row in displacements} == all_ids, {"observed": len(displacements), "expected": len(all_ids)})
    times = sorted({row[2] for row in reactions + displacements})
    gate("single_requested_static_table_state", times == [deck["expected_result_time"]], times)

    bundle = read_json(paths["astermax-results.json"])
    med_times = med_result_times(paths["rmed"]) if paths["rmed"].is_file() else {}
    gate("actual_med_fields_match_static_state", len(med_times) == 3
         and all(item["time"] == deck["expected_result_time"] for item in med_times.values())
         and {item["step"] for item in med_times.values()} == {bundle.get("source", {}).get("med_result_step")}, med_times)
    gate("actual_unmodified_production_med_source", bundle.get("source", {}).get("kind") == "REAL_CODE_ASTER_MED"
         and bundle.get("integrity", {}).get("fea_values_invented") is False
         and bundle.get("integrity", {}).get("solver_output_modified") is False
         and bundle.get("integrity", {}).get("bridge_validation_mode") == "production", bundle.get("integrity"))
    mesh = bundle.get("mesh", {})
    gate("med_mesh_counts_and_element_type", mesh.get("node_count") == metadata["nodes"]
         and mesh.get("element_count") == metadata["elements"] and mesh.get("element_types") == ["TETRA4"], mesh)
    arrays = bundle.get("arrays", {})
    coordinates, imported_u = arrays.get("coordinates", []), arrays.get("displacement", [])
    finite = finite_matrix(coordinates, metadata["nodes"]) and finite_matrix(imported_u, metadata["nodes"])
    gate("finite_med_coordinates_and_displacements", finite,
         {"coordinates": len(coordinates), "displacements": len(imported_u)})
    fixture_xyz = {node["id"]: [float(node[axis]) for axis in ("x", "y", "z")]
                   for node in contract["mesh"]["nodes"]}
    mapped_u = {}
    if finite:
        for node, target in fixture_xyz.items():
            indices = [i for i, point in enumerate(coordinates) if all(
                abs(point[axis] - target[axis]) < 1.0e-10 for axis in range(3))]
            if len(indices) == 1:
                mapped_u[node] = imported_u[indices[0]]
    gate("unique_original_node_coordinates_in_med", set(mapped_u) == all_ids,
         {"mapped": len(mapped_u), "expected": len(all_ids)})
    max_table_error = 0.0
    table_agreement = len(displacements) == len(all_ids) and set(mapped_u) == all_ids
    for node, values, _instant in displacements:
        if node not in mapped_u:
            table_agreement = False
            continue
        for axis in range(3):
            error = abs(mapped_u[node][axis] - values[axis])
            max_table_error = max(max_table_error, error)
            allowed = (acceptance["table_med_displacement_absolute_error_max_mm"]
                       + acceptance["table_med_displacement_relative_error_max"] * abs(values[axis]))
            table_agreement = table_agreement and error <= allowed
    gate("med_and_table_agree_at_every_node_component", table_agreement, {"max_absolute_error_mm": max_table_error})

    max_constraint_residual = 0.0
    constraint_complete = set(mapped_u) == all_ids
    if constraint_complete:
        for equation in deck["equations"]:
            residual = sum(term["coefficient"] * mapped_u[term["node"]][("DX", "DY", "DZ").index(term["axis"])]
                           for term in equation["terms"]) - equation["rhs"]
            max_constraint_residual = max(max_constraint_residual, abs(residual))
    gate("every_exported_mpc_satisfied_by_actual_med", constraint_complete
         and max_constraint_residual <= acceptance["mpc_displacement_residual_absolute_max_mm"], max_constraint_residual)
    fixed_u = [value for node in metadata["fixed_nodes"] for value in mapped_u.get(node, [float("inf")])]
    fixed_max = max((abs(value) for value in fixed_u), default=float("inf"))
    gate("fixed_support_zero_displacement", fixed_max <= acceptance["fixed_displacement_absolute_max_mm"], fixed_max)
    stress_components = arrays.get("stress", {})
    finite_stress = len(stress_components) == 6 and all(len(values) == metadata["nodes"]
        and all(isinstance(value, (int, float)) and math.isfinite(value) for value in values)
        for values in stress_components.values())
    max_stress = max((abs(value) for values in stress_components.values() for value in values), default=float("inf"))
    vm = bundle.get("fields", {}).get("von_mises", {}).get("nodal_max")
    gate("finite_six_component_stress_field", finite_stress, {"components": list(stress_components), "max_absolute_mpa": max_stress})

    total_reaction = vector_sum([values for _node, values, _instant in reactions])
    reaction_moment = vector_sum([cross(fixture_xyz[node], values) for node, values, _instant in reactions])
    applied_force, applied_moment = metadata["applied_force_n"], metadata["applied_moment_n_mm"]
    observed = {"reaction_n": total_reaction, "reaction_moment_n_mm": reaction_moment,
                "applied_force_n": applied_force, "applied_moment_n_mm": applied_moment,
                "max_mpc_displacement_residual_mm": max_constraint_residual,
                "max_table_med_absolute_error_mm": max_table_error,
                "max_stress_component_mpa": max_stress, "von_mises_nodal_max_mpa": vm,
                "med_field_times": med_times, "table_times": times}
    if metadata["case"] == "force":
        force_scale = max(abs(value) for value in applied_force)
        length_scale = max(abs(value) for point in fixture_xyz.values() for value in point)
        force_error = [abs(total_reaction[axis] + applied_force[axis]) / force_scale for axis in range(3)]
        moment_error = [abs(reaction_moment[axis] + applied_moment[axis]) / (force_scale * length_scale) for axis in range(3)]
        gate("global_force_equilibrium", max(force_error) <= acceptance["force_equilibrium_relative_error_max"], force_error)
        gate("global_moment_equilibrium_across_gap", max(moment_error) <= acceptance["moment_equilibrium_relative_error_max"], moment_error)
        gate("bonded_tension_transferred_to_support", total_reaction[0] < -0.99 * applied_force[0], total_reaction[0])
        loaded_u = [mapped_u[node] for node in metadata["loaded_nodes"] if node in mapped_u]
        work = sum(sum(value * applied_force[axis] / len(metadata["loaded_nodes"])
                       for axis, value in enumerate(row)) for row in loaded_u)
        gate("positive_external_load_work", len(loaded_u) == len(metadata["loaded_nodes"]) and work > 0, work)
        gate("nonzero_loaded_solid_stress", isinstance(vm, (int, float)) and math.isfinite(vm) and vm > 0, vm)
        observed.update({"force_equilibrium_relative_error": force_error,
                         "moment_equilibrium_relative_error": moment_error, "external_work_n_mm": work})
    else:
        rotation_error = max((abs(mapped_u[node][axis] - cross(metadata["rigid_rotation_vector_rad"], point)[axis])
                              for node, point in fixture_xyz.items() if node in mapped_u for axis in range(3)), default=float("inf"))
        max_reaction = max((abs(value) for _node, values, _instant in reactions for value in values), default=float("inf"))
        gate("rigid_rotation_crosses_gap_at_every_node", set(mapped_u) == all_ids
             and rotation_error <= acceptance["rigid_rotation_displacement_absolute_error_max_mm"], rotation_error)
        gate("rigid_rotation_has_no_spurious_stress", finite_stress
             and max_stress <= acceptance["rigid_rotation_stress_absolute_max_mpa"], max_stress)
        gate("rigid_rotation_has_no_spurious_reaction", max_reaction
             <= acceptance["rigid_rotation_reaction_absolute_max_n"], max_reaction)
        gate("consistent_shared_slave_and_support_rows_reduced", planner.get("redundant_rows", 0) >= 15
             and metadata.get("prescribed_interface_slave") in metadata["reaction_nodes"], planner)
        observed.update({"rigid_rotation_max_absolute_error_mm": rotation_error,
                         "rigid_rotation_max_absolute_reaction_n": max_reaction})
    vtk_types = []
    if paths["astermax-results.vtu"].is_file():
        tree = ET.parse(paths["astermax-results.vtu"])
        types = next((item for item in tree.iter("DataArray") if item.attrib.get("Name") == "types"), None)
        if types is not None:
            vtk_types = [int(value) for value in (types.text or "").split()]
    gate("vtu_preserves_all_tetrahedra", len(vtk_types) == metadata["elements"] and set(vtk_types) == {10},
         {"count": len(vtk_types), "types": sorted(set(vtk_types))})
    return {"case": metadata["case"], "checks": checks,
            "all_checks_pass": all(item["pass"] for item in checks), "observed": observed,
            "predeclared_acceptance": acceptance, "planner": planner,
            "output_sha256": {path.name: sha256(path) for path in paths.values() if path.is_file()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    probe = read_json(root / "native-probe.json")
    executable_hash = sha256(Path(args.executable))
    cases = [validate_case(root / name, executable_hash) for name in ("force", "rotation")]
    native_ready = bool(probe.get("ready") and probe.get("transport") == "WINDOWS_NATIVE" and probe.get("wsl_required") is False)
    checks = [{"name": "native_windows_probe", "pass": native_ready, "evidence": probe}]
    checks.extend({"name": case["case"] + "." + item["name"], "pass": item["pass"], "evidence": item["evidence"]}
                  for case in cases for item in case["checks"])
    report = {"release": "C12.08", "title": "Native Windows bonded MPC nonmatching gap and shared-edge regression",
              "transport": "WINDOWS_NATIVE", "solver_execution": "RUN", "synthetic_results_allowed": False,
              "fixture_source": "SYNTHETIC_INPUT_GEOMETRY_ONLY", "private_user_geometry_included": False,
              "actual_user_project_solver_execution": "NOT_RUN",
              "export_source": "COMPILED_ASTERMAX_EXECUTABLE", "executable_sha256": executable_hash,
              "gap_mm": 2.5, "shared_slave_node_count": 4, "cases": cases,
              "checks_total": len(checks), "checks_passed": sum(item["pass"] for item in checks),
              "all_checks_pass": all(item["pass"] for item in checks), "checks": checks,
              "scientific_integrity": {"fea_values_invented": False, "tolerances_relaxed_after_execution": False,
                                       "rigid_patch_reference": "Analytical infinitesimal rigid rotation; actual values from Code_Aster MED.",
                                       "observation_only_instrumentation": "REAC_NODA table after production MED output"}}
    (root / "C12.08_NATIVE_BONDED_VALIDATION.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_checks_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
