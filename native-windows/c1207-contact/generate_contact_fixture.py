#!/usr/bin/env python3
"""Define a real three-body contact case with 12 shared slave nodes.

This writes model inputs only. Results must come from native Windows Code_Aster.
The middle prism is compressed into two perpendicular support prisms. Separate
node IDs at each interface ensure forces can cross bodies only through contact.
"""

import argparse
import hashlib
import json
from pathlib import Path


def base36(value, width):
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = ""
    while value:
        value, digit = divmod(value, 36)
        result = digits[digit] + result
    return result.rjust(width, "0")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    layers = 11
    nodes, elements, blocks = [], [], {}
    for name, origin in (("central", (0, 0)), ("left", (-1, 0)), ("bottom", (0, -1))):
        block_nodes, block_elements = {}, []
        for z in range(layers + 1):
            for y in range(2):
                for x in range(2):
                    node_id = f"N{len(nodes) + 1}"
                    block_nodes[x, y, z] = node_id
                    nodes.append({"id": node_id, "x": origin[0] + x, "y": origin[1] + y, "z": z})
        for z in range(layers):
            connectivity = [block_nodes[x, y, z + dz] for x, y, dz in (
                (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
            )]
            element = {"id": f"E{len(elements) + 1}", "type": "HEXA8", "nodes": connectivity}
            elements.append(element)
            block_elements.append(element)
        blocks[name] = {"nodes": block_nodes, "elements": block_elements}

    # The exact same face order as LinearHexaElement.GetVtkCellFromFaceName.
    face_indices = {"S3": (0, 1, 5, 4), "S4": (1, 2, 6, 5),
                    "S5": (2, 3, 7, 6), "S6": (3, 0, 4, 7)}

    def surface(block_name, face_name, role, contact_index):
        skin = []
        for index, volume in enumerate(blocks[block_name]["elements"], start=1):
            skin.append({
                "id": role + base36(contact_index, 2) + base36(index, 5),
                "type": "QUAD4", "source_element_id": volume["id"], "source_face": face_name,
                "nodes": [volume["nodes"][i] for i in face_indices[face_name]],
            })
        return {"source_surface": f"{block_name}_{face_name}",
                "group": f"AM_{role}{contact_index:03d}", "elements": skin}

    contacts = []
    for index, master_block, master_face, slave_face in (
        (13, "left", "S4", "S6"), (28, "bottom", "S5", "S3")
    ):
        contacts.append({
            "name": f"Contact_{index}", "surface_interaction": "Frictionless",
            "method": "SurfaceToSurface", "small_sliding": False, "adjust": False,
            "formulation": "CONTINUE", "friction": "SANS", "friction_coefficient": 0.0,
            "friction_stick_slope": None, "contact_init": "OUI",
            "master": surface(master_block, master_face, "M", index),
            "slave": surface("central", slave_face, "S", index),
        })

    fixed_left = [node for (x, _y, _z), node in blocks["left"]["nodes"].items() if x == 0]
    fixed_bottom = [node for (_x, y, _z), node in blocks["bottom"]["nodes"].items() if y == 0]
    loaded = [node for (x, y, _z), node in blocks["central"]["nodes"].items() if x == 1 and y == 1]
    fixed = fixed_left + fixed_bottom
    force = 1100.0
    contract = {
        "schema": "astermax-model-contract/v0", "unit_system": "MM_N_S_MPA",
        "name": "C12.07 orthogonal contact interfaces sharing twelve slave nodes",
        "analysis": {"type": "static_structural", "step_count": 1},
        "mesh": {"nodes": nodes, "elements": elements, "node_groups": {
            "FIXED": fixed, "GUIDE_Z": list(blocks["central"]["nodes"].values()), "LOAD": loaded,
        }},
        "materials": [{"name": "Steel", "young_modulus_mpa": 210000.0, "poisson": 0.30}],
        "supports": [
            {"name": "Outer supports", "type": "fixed", "group": "FIXED", "dx": 0.0, "dy": 0.0, "dz": 0.0},
            {"name": "Frictionless out-of-plane guide", "type": "displacement", "group": "GUIDE_Z", "dx": None, "dy": None, "dz": 0.0},
        ],
        "loads": [{"name": "Compress into both supports", "type": "nodal_force_total", "group": "LOAD",
                   "fx_total_n": -force, "fy_total_n": -force, "fz_total_n": 0.0}],
        "contacts": contacts, "postprocess": {"displacement_probe_group": "LOAD"},
    }
    slave_nodes = [set(node for face in item["slave"]["elements"] for node in face["nodes"]) for item in contacts]
    shared = sorted(slave_nodes[0] & slave_nodes[1])
    if len(shared) != 12:
        raise RuntimeError("The regression must have exactly twelve shared slave nodes.")
    body_node_sets = [set(block["nodes"].values()) for block in blocks.values()]
    if any(a & b for i, a in enumerate(body_node_sets) for b in body_node_sets[i + 1:]):
        raise RuntimeError("Bodies must have independent interface node IDs.")

    contract_path = root / "contact-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "release": "C12.07", "case": "astermax-contact", "nodes": len(nodes), "elements": len(elements),
        "element_type": "HEXA8", "bodies": 3, "original_contact_zones": 2,
        "original_contact_names": [item["name"] for item in contacts],
        "original_shared_slave_nodes": shared, "original_shared_slave_node_count": len(shared),
        "fixed_nodes": fixed, "fixed_left_nodes": fixed_left, "fixed_bottom_nodes": fixed_bottom,
        "loaded_nodes": loaded, "applied_force_n": [-force, -force, 0.0],
        "contact_formulation": "CONTINUE", "friction": "SANS", "contact_init": "OUI",
        "expected_physics": "Compression transferred from the central body to each independent support only by contact.",
        "predeclared_acceptance": {"reaction_equilibrium_relative_error_max": 1e-4,
                                   "table_med_displacement_relative_error_max": 1e-3,
                                   "fixed_displacement_absolute_max_mm": 1e-9,
                                   "required_final_time": 1.0},
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "scientific_integrity": {"fea_values_invented": False, "results_source": "NATIVE_WINDOWS_CODE_ASTER_REQUIRED"},
    }
    (root / "contact-fixture.input.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixture": str(contract_path), "nodes": len(nodes), "elements": len(elements),
                      "shared_slave_nodes": len(shared)}))


if __name__ == "__main__":
    main()
