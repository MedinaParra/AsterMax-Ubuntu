#!/usr/bin/env python3
"""Independently inspect compiled bonded decks and add reaction observation only.

The command file is parsed as syntax, never executed by this validation script.
Each exported MPC is checked for affine invariance and independent rank together
with the prescribed supports. Loads, material, mesh and equations stay unchanged.
"""

import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_mail(text):
    mode, nodes, cells, groups = None, {}, {}, {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in ("FINSF", "FIN"):
            mode = None
        elif line in ("COOR_3D", "TETRA4", "TRIA3"):
            mode = line
        elif line.startswith("GROUP_MA NOM = ") or line.startswith("GROUP_NO NOM = "):
            kind = "GROUP_NO" if line.startswith("GROUP_NO") else "GROUP_MA"
            name = line.split("=", 1)[1].strip()
            require(name not in groups, "Repeated mesh group: " + name)
            groups[name] = {"kind": kind, "ids": []}
            mode = ("group", name)
        elif isinstance(mode, tuple):
            groups[mode[1]]["ids"].extend(line.split())
        elif mode == "COOR_3D":
            name, *values = line.split()
            require(name not in nodes and len(values) == 3, "Invalid mesh node record.")
            nodes[name] = tuple(float(value) for value in values)
        elif mode in ("TETRA4", "TRIA3"):
            name, *values = line.split()
            require(name not in cells, "Repeated mesh element: " + name)
            cells[name] = (mode, values)
    return nodes, cells, groups


def call_name(call):
    return call.func.id if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) else None


def keyword_nodes(call):
    return {item.arg: item.value for item in call.keywords}


def factor_items(expression):
    items = expression.elts if isinstance(expression, (ast.Tuple, ast.List)) else [expression]
    require(all(call_name(item) == "_F" for item in items), "Expected explicit _F factors in compiled command file.")
    return items


def literal_keywords(call):
    return {name: ast.literal_eval(value) for name, value in keyword_nodes(call).items()}


def sequence(value):
    return list(value) if isinstance(value, (list, tuple)) else [value]


def extract_deck(comm, groups):
    tree = ast.parse(comm)
    mechanical = [node for node in ast.walk(tree) if call_name(node) == "MECA_STATIQUE"]
    require(len(mechanical) == 1, "Bonded fixture must have one production MECA_STATIQUE solve.")
    require(not any(call_name(node) in ("DEFI_CONTACT", "LIAISON_MAIL", "STAT_NON_LINE") for node in ast.walk(tree)),
            "Bonded fixture must not substitute a contact solve or projection-only coupling.")
    solve_keywords = keyword_nodes(mechanical[0])
    require("LIST_INST" not in solve_keywords, "Synthetic linear admission expects one static result state.")
    result_time = float(ast.literal_eval(solve_keywords["INST"])) if "INST" in solve_keywords else 0.0
    # U4.51.01: MECA_STATIQUE defaults to the single static state INST=0.
    require(math.isfinite(result_time), "Invalid production result time.")
    excited = set()
    for factor in factor_items(solve_keywords["EXCIT"]):
        keywords = keyword_nodes(factor)
        require(set(keywords) == {"CHARGE"} and isinstance(keywords["CHARGE"], ast.Name),
                "Unexpected modified excitation in the synthetic fixture.")
        excited.add(keywords["CHARGE"].id)

    equations, prescribed, loads = [], {}, {}
    charge_names, bonded_names = set(), set()

    def group_nodes(value):
        found = []
        for name in sequence(value):
            require(name in groups and groups[name]["kind"] == "GROUP_NO", "Missing node group: " + str(name))
            found.extend(groups[name]["ids"])
        return found

    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or call_name(statement.value) != "AFFE_CHAR_MECA":
            continue
        require(len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name), "Unexpected charge assignment.")
        charge_name = statement.targets[0].id
        charge_names.add(charge_name)
        keywords = keyword_nodes(statement.value)
        require(set(keywords) <= {"MODELE", "LIAISON_DDL", "DDL_IMPO", "FORCE_NODALE"},
                "Unexpected mechanical load or constraint in fixture export.")
        if "LIAISON_DDL" in keywords:
            bonded_names.add(charge_name)
            for factor in factor_items(keywords["LIAISON_DDL"]):
                values = literal_keywords(factor)
                require(set(values) == {"GROUP_NO", "DDL", "COEF_MULT", "COEF_IMPO"}, "Unexpected bonded equation syntax.")
                names, axes, coefficients = (sequence(values[key]) for key in ("GROUP_NO", "DDL", "COEF_MULT"))
                require(len(names) == len(axes) == len(coefficients) and len(names) >= 2, "Invalid bonded term counts.")
                terms = []
                for name, axis, coefficient in zip(names, axes, coefficients):
                    ids = group_nodes(name)
                    require(len(ids) == 1 and axis in ("DX", "DY", "DZ"), "Bonded MPC requires singleton translational groups.")
                    require(isinstance(coefficient, (int, float)) and math.isfinite(coefficient), "Invalid MPC coefficient.")
                    terms.append({"node": ids[0], "axis": axis, "coefficient": float(coefficient)})
                require(values["COEF_IMPO"] == 0.0, "Bonded homogeneous coupling changed.")
                equations.append({"terms": terms, "rhs": 0.0})
        if "DDL_IMPO" in keywords:
            for factor in factor_items(keywords["DDL_IMPO"]):
                values = literal_keywords(factor)
                require(set(values) <= {"GROUP_NO", "DX", "DY", "DZ"}, "Unexpected prescribed DOF.")
                for node in group_nodes(values["GROUP_NO"]):
                    for axis in ("DX", "DY", "DZ"):
                        if axis not in values:
                            continue
                        value = float(values[axis])
                        require(math.isfinite(value), "Invalid prescribed value.")
                        key = (node, axis)
                        require(key not in prescribed or prescribed[key] == value, "Conflicting exported supports.")
                        prescribed[key] = value
        if "FORCE_NODALE" in keywords:
            for factor in factor_items(keywords["FORCE_NODALE"]):
                values = literal_keywords(factor)
                require(set(values) <= {"GROUP_NO", "FX", "FY", "FZ"}, "Unexpected nodal force syntax.")
                for node in group_nodes(values["GROUP_NO"]):
                    load = loads.setdefault(node, [0.0, 0.0, 0.0])
                    for axis, field in enumerate(("FX", "FY", "FZ")):
                        load[axis] += float(values.get(field, 0.0))
    require(equations and bonded_names <= excited and charge_names == excited,
            "All exported mechanical charges, including bonded MPCs, must be used by the solve.")
    return equations, prescribed, loads, result_time


def prepare_case(directory):
    contract = read_json(directory / "bonded-contract.json")
    metadata = read_json(directory / "bonded-fixture.input.json")
    output = directory / "exported"
    stem = metadata["stem"]
    comm_path, mail_path = output / f"{stem}.comm", output / f"{stem}.mail"
    manifest = read_json(output / f"{stem}.native-export.json")
    comm = comm_path.read_text(encoding="utf-8-sig")
    nodes, cells, groups = read_mail(mail_path.read_text(encoding="utf-8-sig"))
    expected_nodes = {node["id"]: tuple(float(node[axis]) for axis in ("x", "y", "z"))
                      for node in contract["mesh"]["nodes"]}
    expected_cells = {cell["id"]: (cell["type"], cell["nodes"]) for cell in contract["mesh"]["elements"]}
    require(nodes == expected_nodes, "Production export changed node coordinates or closed the gap.")
    require(cells == expected_cells, "Production export changed volume elements or added unexpected geometry.")
    require(manifest.get("exporter") == "C12.08-bonded-mpc-v1", "Wrong compiled exporter version.")
    require(contract["contacts"] == [] and len(contract["bonded_ties"]) == 2, "Fixture connection law changed.")
    material_calls = [node for node in ast.walk(ast.parse(comm)) if call_name(node) == "DEFI_MATERIAU"]
    require(len(material_calls) == 1 and set(keyword_nodes(material_calls[0])) == {"ELAS"},
            "The synthetic fixture must retain its single elastic material.")
    elastic = literal_keywords(keyword_nodes(material_calls[0])["ELAS"])
    material = contract["materials"][0]
    require(elastic == {"E": material["young_modulus_mpa"], "NU": material["poisson"]},
            "Production export changed the fixture's elastic constants.")
    equations, supports, forces, result_time = extract_deck(comm, groups)
    bindings = read_json(output / f"{stem}.bonded-mpc.json")["bindings"]
    ties = {tie["name"]: tie for tie in contract["bonded_ties"]}
    expected_bindings = {(tie["name"], node) for tie in contract["bonded_ties"]
                         for face in tie["slave"]["elements"] for node in face["nodes"]}
    require(len(bindings) == len(expected_bindings) and
            {(item["tie"], item["slave_node"]) for item in bindings} == expected_bindings,
            "The binding audit does not cover each original pair/slave-node candidate exactly once.")
    audit_rows = []
    for binding in bindings:
        tie = ties[binding["tie"]]
        adjacent = {face["source_element_id"] for face in tie["master"]["elements"]}
        require(binding["master_element"] in adjacent, "A binding used a volume outside its selected master surface.")
        cell_type, cell_nodes = expected_cells[binding["master_element"]]
        require(cell_type == "TETRA4" and binding["master_nodes"] == cell_nodes,
                "The binding audit does not identify the actual adjacent master tetrahedron.")
        weights = binding["weights"]
        require(len(weights) == 4 and all(math.isfinite(value) for value in weights), "Invalid audited interpolation weights.")
        require(abs(sum(weights) - 1.0) <= 1.0e-12 and all(abs(sum(
            weights[index] * nodes[node][axis] for index, node in enumerate(cell_nodes))
            - nodes[binding["slave_node"]][axis]) <= 1.0e-9 for axis in range(3)),
            "Audited weights do not reproduce the actual slave coordinates across the gap.")
        require(abs(binding["distance_mm"] - metadata["gap_mm"]) <= 1.0e-10,
                "The admitted synthetic interface gap changed.")
        for axis in binding["exported_axes"]:
            require(axis in ("DX", "DY", "DZ"), "Unexpected exported bonded component.")
            row = {(binding["slave_node"], axis): 1.0}
            for node, weight in zip(cell_nodes, weights):
                row[node, axis] = row.get((node, axis), 0.0) - weight
            audit_rows.append(row)
    require(len(audit_rows) == len(equations), "Binding audit and compiled deck disagree on retained equations.")
    for audited, equation in zip(audit_rows, equations):
        actual = {}
        for term in equation["terms"]:
            key = (term["node"], term["axis"])
            actual[key] = actual.get(key, 0.0) + term["coefficient"]
        require(all(abs(actual.get(key, 0.0) - audited.get(key, 0.0)) <= 1.0e-12
                    for key in set(actual) | set(audited)),
                "A compiled MPC differs from its independently checked geometric binding.")
    expected_supports = {}
    for support in contract["supports"]:
        for node in contract["mesh"]["node_groups"][support["group"]]:
            for axis, field in zip(("DX", "DY", "DZ"), ("dx", "dy", "dz")):
                if support.get(field) is not None:
                    expected_supports[node, axis] = float(support[field])
    require(set(supports) == set(expected_supports) and all(
        abs(supports[key] - expected_supports[key]) <= 1.0e-14 for key in supports),
        "Production export changed prescribed support DOFs or values.")
    nodal_force = [value / len(metadata["loaded_nodes"]) for value in metadata["applied_force_n"]]
    expected_forces = {node: nodal_force for node in metadata["loaded_nodes"]}
    require(forces == expected_forces, "Production export changed force values or distribution.")

    master_ids = set(metadata["master_nodes"])
    interface_ids = {node for tie in contract["bonded_ties"] for face in tie["slave"]["elements"]
                     for node in face["nodes"]}
    covered = set()
    for equation in equations:
        terms = equation["terms"]
        slave_terms = [term for term in terms if term["node"] in interface_ids]
        require(len(slave_terms) == 1 and slave_terms[0]["coefficient"] != 0.0,
                "Each retained MPC must bind one intended slave interface node.")
        require(len({term["axis"] for term in terms}) == 1 and all(
            term["node"] in master_ids or term is slave_terms[0] for term in terms),
            "An MPC references the wrong body or changes the scalar translation coupling.")
        covered.add((slave_terms[0]["node"], slave_terms[0]["axis"]))
    require(all((node, axis) in covered or (node, axis) in supports
                for node in interface_ids for axis in ("DX", "DY", "DZ")),
            "Some intended bonded slave DOFs were dropped without a prescribed support.")

    dofs = [(node, axis) for node in nodes for axis in ("DX", "DY", "DZ")]
    columns = {dof: index for index, dof in enumerate(dofs)}
    matrix = np.zeros((len(supports) + len(equations), len(dofs)))
    for row, dof in enumerate(supports):
        matrix[row, columns[dof]] = 1.0
    affine_max = 0.0
    for index, equation in enumerate(equations):
        for term in equation["terms"]:
            require(term["node"] in nodes, "MPC references an unknown mesh node.")
            matrix[len(supports) + index, columns[term["node"], term["axis"]]] += term["coefficient"]
        for axis in ("DX", "DY", "DZ"):
            terms = [term for term in equation["terms"] if term["axis"] == axis]
            residuals = [sum(term["coefficient"] for term in terms)]
            residuals.extend(sum(term["coefficient"] * nodes[term["node"]][coordinate] for term in terms)
                             for coordinate in range(3))
            affine_max = max(affine_max, *(abs(value) for value in residuals))
    acceptance = metadata["predeclared_acceptance"]
    require(affine_max <= acceptance["affine_equation_residual_absolute_max_mm"],
            "A bonded equation fails rigid translation/rotation and affine field invariance across the gap.")
    norms = np.linalg.norm(matrix, axis=1)
    require(np.all(norms > 0), "Exported empty MPC row.")
    singular_values = np.linalg.svd(matrix / norms[:, None], compute_uv=False)
    relative_min = float(singular_values[-1] / singular_values[0])
    require(relative_min > acceptance["rank_relative_singular_value_min"],
            "Exported MPC rows are rank-deficient against the actual prescribed supports.")

    # Observe reactions only after the untouched production MED output.
    (output / f"{stem}.production.comm").write_text(comm, encoding="utf-8")
    reaction_group = manifest["node_group_name_map"]["REACTION_NODES"]
    require(set(groups[reaction_group]["ids"]) == set(metadata["reaction_nodes"]), "Reaction scope changed.")
    observation = f"""# C12.08 observation only: no mesh, supports, loads, material or MPCs changed.
reaction = POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION', INTITULE='BOND_REACTIONS', RESULTAT=result, NOM_CHAM='REAC_NODA', GROUP_NO='{reaction_group}', NOM_CMP=('DX','DY','DZ'), TOUT_ORDRE='OUI'))
IMPR_TABLE(TABLE=reaction, UNITE=82)
FIN()
"""
    require(len(re.findall(r"(?m)^FIN\(\)\s*$", comm)) == 1, "Expected one final FIN() call.")
    require("REAC_NODA" in comm and "IMPR_RESU" in comm, "Production result output or reaction field missing.")
    comm_path.write_text(re.sub(r"(?m)^FIN\(\)\s*$", lambda _match: observation, comm), encoding="utf-8")
    (output / f"{stem}.export").write_text(f"""P actions make_etude
P version stable
P mode interactif
P time_limit 600
P memory_limit 4096
P ncpus 1
P mpi_nbcpu 1
F comm ./{stem}.comm D 1
F mail ./{stem}.mail D 20
F mess ./{stem}.mess R 6
F resu ./{stem}.resu R 80
F rmed ./{stem}.rmed R 81
F repe ./{stem}.reactions R 82
""", encoding="utf-8")
    report = {"release": "C12.08", "case": metadata["case"], "mesh_preserved": True,
              "bonded_law_preserved": True, "supports_and_loads_preserved": True,
              "material_preserved": True,
              "all_binding_candidates_checked": len(bindings), "adjacent_master_tetrahedra_verified": True,
              "gap_preserved_mm": 2.5, "expected_result_time": result_time,
              "independent_mpc_rows": len(equations), "support_dof_count": len(supports),
              "relative_smallest_singular_value": relative_min,
              "maximum_affine_residual_mm": affine_max, "equations": equations,
              "production_comm_sha256": digest(output / f"{stem}.production.comm"),
              "observation_only_instrumentation": "REAC_NODA table after production MED output",
              "input_sha256": {path.name: digest(path) for path in sorted(output.iterdir()) if path.is_file()}}
    (directory / "bonded-validation-deck.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {key: value for key, value in report.items() if key not in ("equations", "input_sha256")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    results = [prepare_case(root / name) for name in ("force", "rotation")]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
