#!/usr/bin/env python3
"""Create synthetic inputs for native bonded-interface admission, never results.

Two independently meshed TETRA4 bricks are separated by 2.5 mm. The slave
interface is finer than the master and is split into two tie pairs sharing an
edge. A force case checks tensile/shear load transfer and moment balance. A
rigid-rotation patch case checks the gap kinematics and redundant constraints
against nonzero prescribed displacements. Both use the production exporter.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path


FACE_INDICES = {"S1": (0, 2, 1), "S2": (0, 1, 3),
                "S3": (1, 2, 3), "S4": (2, 0, 3)}


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def signed_six_volume(points):
    a, b, c, d = points
    vectors = [[p[i] - a[i] for i in range(3)] for p in (b, c, d)]
    return sum(vectors[0][i] * cross(vectors[1], vectors[2])[i] for i in range(3))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def make_fixture():
    nodes, elements, blocks, points = [], [], {}, {}
    grids = {
        "master": ([0.0, 5.0, 10.0], [0.0, 5.0, 10.0], [0.0, 5.0, 10.0]),
        "slave": ([12.5, 17.5, 22.5], [0.0, 2.5, 5.0, 7.5, 10.0],
                  [0.0, 4.0, 7.0, 10.0]),
    }
    for body, (xs, ys, zs) in grids.items():
        body_nodes, body_elements = {}, []
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                for k, z in enumerate(zs):
                    node_id = f"N{len(nodes) + 1}"
                    body_nodes[i, j, k] = node_id
                    points[node_id] = [x, y, z]
                    nodes.append({"id": node_id, "x": x, "y": y, "z": z})
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                for k in range(len(zs) - 1):
                    brick = [body_nodes[i + di, j + dj, k + dk] for di, dj, dk in (
                        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))]
                    for indices in ((0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6),
                                    (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)):
                        connectivity = [brick[index] for index in indices]
                        six_volume = signed_six_volume([points[node] for node in connectivity])
                        if six_volume < 0:
                            connectivity[1], connectivity[2] = connectivity[2], connectivity[1]
                            six_volume = -six_volume
                        if six_volume <= 0:
                            raise RuntimeError("Degenerate synthetic tetrahedron.")
                        element = {"id": f"E{len(elements) + 1}", "type": "TETRA4", "nodes": connectivity}
                        elements.append(element)
                        body_elements.append(element)
        blocks[body] = {"nodes": list(body_nodes.values()), "elements": body_elements}

    def surface(body, lower, tie_index):
        skin = []
        plane = 10.0 if body == "master" else 12.5
        role = "M" if body == "master" else "S"
        for element in blocks[body]["elements"]:
            for face_name, indices in FACE_INDICES.items():
                face_nodes = [element["nodes"][index] for index in indices]
                xyz = [points[node] for node in face_nodes]
                if not all(point[0] == plane for point in xyz):
                    continue
                if lower and not all(point[1] <= 5.0 for point in xyz):
                    continue
                if not lower and not all(point[1] >= 5.0 for point in xyz):
                    continue
                skin.append({"id": f"{role}{tie_index}{len(skin) + 1:05d}", "type": "TRIA3",
                             "source_element_id": element["id"], "source_face": face_name,
                             "nodes": face_nodes})
        return {"source_surface": f"{body}_{'lower' if lower else 'upper'}",
                "group": f"AM_B{role}{tie_index}", "elements": skin}

    ties = [{"name": f"Bonded_{index}", "position_tolerance_mm": 3.0, "adjust": False,
             "master": surface("master", lower, index),
             "slave": surface("slave", lower, index)}
            for index, lower in ((1, True), (2, False))]
    fixed = [node for node in blocks["master"]["nodes"] if points[node][0] == 0.0]
    loaded = [node for node in blocks["slave"]["nodes"] if points[node][0] == 22.5]
    contract = {
        "schema": "astermax-model-contract/v0", "unit_system": "MM_N_S_MPA",
        "name": "C12.08 nonmatching bonded tetrahedra with a 2.5 mm gap",
        "analysis": {"type": "static_structural", "step_count": 1},
        "mesh": {"nodes": nodes, "elements": elements,
                 "node_groups": {"FIXED": fixed, "LOAD": loaded, "ALL_NODES": list(points)}},
        "materials": [{"name": "Steel", "young_modulus_mpa": 210000.0, "poisson": 0.30}],
        "supports": [{"name": "Master root fixed", "type": "fixed", "group": "FIXED",
                      "dx": 0.0, "dy": 0.0, "dz": 0.0}],
        "loads": [{"name": "Tension and transverse load", "type": "nodal_force_total", "group": "LOAD",
                   "fx_total_n": 1000.0, "fy_total_n": 400.0, "fz_total_n": 300.0}],
        "contacts": [], "bonded_ties": ties,
        "postprocess": {"displacement_probe_group": "ALL_NODES"},
    }
    slave_sets = [set(node for face in tie["slave"]["elements"] for node in face["nodes"]) for tie in ties]
    shared = sorted(slave_sets[0] & slave_sets[1], key=lambda node: int(node[1:]))
    if len(shared) != 4 or len(nodes) != 87 or len(elements) != 192:
        raise RuntimeError("The synthetic admission topology changed.")
    if set(blocks["master"]["nodes"]) & set(blocks["slave"]["nodes"]):
        raise RuntimeError("The bodies must not share mesh nodes.")
    return contract, blocks, points, shared


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    force_contract, blocks, points, shared = make_fixture()
    rotation_contract = copy.deepcopy(force_contract)
    rotation_contract["name"] += " - rigid rotation patch"
    omega = [1.0e-4, -2.0e-4, 3.0e-4]
    origin = next(node for node in blocks["master"]["nodes"] if points[node] == [0.0, 0.0, 0.0])
    rotation_contract["mesh"]["node_groups"]["FIXED"] = [origin]
    rotation_contract["supports"] = [{"name": "Rotation origin", "type": "fixed", "group": "FIXED",
                                      "dx": 0.0, "dy": 0.0, "dz": 0.0}]
    # A slave interface node is also prescribed consistently. Its tie rows must
    # be reduced against the support equations rather than create a null pivot.
    prescribed_slave = next(node for node in blocks["slave"]["nodes"] if points[node] == [12.5, 0.0, 0.0])
    prescribed = blocks["master"]["nodes"] + [prescribed_slave]
    for index, node in enumerate(prescribed):
        if node == origin:
            continue
        group = f"ROTATION_{index:03d}"
        rotation_contract["mesh"]["node_groups"][group] = [node]
        u = cross(omega, points[node])
        rotation_contract["supports"].append({"name": f"Rigid rotation at {node}", "type": "displacement",
                                              "group": group, "dx": u[0], "dy": u[1], "dz": u[2]})
    rotation_contract["mesh"]["node_groups"]["REACTION_NODES"] = prescribed
    force_contract["mesh"]["node_groups"]["REACTION_NODES"] = force_contract["mesh"]["node_groups"]["FIXED"][:]
    for key in ("fx_total_n", "fy_total_n", "fz_total_n"):
        rotation_contract["loads"][0][key] = 0.0
    rotation_contract["loads"][0]["name"] = "Zero external force for rigid rotation patch"

    tolerances = {
        "force_equilibrium_relative_error_max": 1.0e-5,
        "moment_equilibrium_relative_error_max": 1.0e-5,
        "table_med_displacement_relative_error_max": 1.0e-5,
        "table_med_displacement_absolute_error_max_mm": 1.0e-9,
        "fixed_displacement_absolute_max_mm": 1.0e-9,
        "rigid_rotation_displacement_absolute_error_max_mm": 1.0e-8,
        "rigid_rotation_stress_absolute_max_mpa": 1.0e-5,
        "rigid_rotation_reaction_absolute_max_n": 1.0e-5,
        "mpc_displacement_residual_absolute_max_mm": 1.0e-8,
        "affine_equation_residual_absolute_max_mm": 1.0e-9,
        "rank_relative_singular_value_min": 1.0e-10,
        "required_result_state_count": 1,
    }
    cases = []
    for name, contract in (("force", force_contract), ("rotation", rotation_contract)):
        directory = root / name
        directory.mkdir()
        contract_path = directory / "bonded-contract.json"
        write_json(contract_path, contract)
        applied = [contract["loads"][0][key] for key in ("fx_total_n", "fy_total_n", "fz_total_n")]
        load_nodes = contract["mesh"]["node_groups"]["LOAD"]
        nodal_force = [value / len(load_nodes) for value in applied]
        moment = [sum(cross(points[node], nodal_force)[axis] for node in load_nodes) for axis in range(3)]
        metadata = {
            "release": "C12.08", "case": name, "stem": "astermax-bonded",
            "fixture_source": "SYNTHETIC_INPUT_GEOMETRY_ONLY", "private_user_geometry_included": False,
            "nodes": len(points), "elements": len(contract["mesh"]["elements"]), "element_type": "TETRA4",
            "bodies": 2, "master_nodes": blocks["master"]["nodes"], "slave_nodes": blocks["slave"]["nodes"],
            "tie_count": 2, "gap_mm": 2.5, "position_tolerance_mm": 3.0,
            "shared_slave_nodes": shared, "shared_slave_node_count": len(shared),
            "master_interface_faces": sum(len(tie["master"]["elements"]) for tie in contract["bonded_ties"]),
            "slave_interface_faces": sum(len(tie["slave"]["elements"]) for tie in contract["bonded_ties"]),
            "fixed_nodes": contract["mesh"]["node_groups"]["FIXED"],
            "reaction_nodes": contract["mesh"]["node_groups"]["REACTION_NODES"],
            "loaded_nodes": load_nodes, "applied_force_n": applied, "applied_moment_n_mm": moment,
            "moment_reference_mm": [0.0, 0.0, 0.0],
            "rigid_rotation_vector_rad": omega if name == "rotation" else None,
            "prescribed_interface_slave": prescribed_slave if name == "rotation" else None,
            "expected_physics": ("Tension and transverse load cross the 2.5 mm gap with global force and moment equilibrium."
                                 if name == "force" else
                                 "An infinitesimal rigid rotation crosses the 2.5 mm gap without strain or stress."),
            "predeclared_acceptance": tolerances, "contract_sha256": digest(contract_path),
            "scientific_integrity": {"fea_values_invented": False, "results_source": "NATIVE_WINDOWS_CODE_ASTER_REQUIRED"},
        }
        write_json(directory / "bonded-fixture.input.json", metadata)
        cases.append({"name": name, "contract_sha256": metadata["contract_sha256"]})
    write_json(root / "bonded-suite.input.json", {"release": "C12.08", "cases": cases,
                                                "private_user_geometry_included": False,
                                                "predeclared_acceptance": tolerances})
    print(json.dumps({"cases": cases, "nodes_per_case": len(points), "elements_per_case": 192,
                      "shared_slave_nodes": shared, "gap_mm": 2.5}, indent=2))


if __name__ == "__main__":
    main()
