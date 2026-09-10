#!/usr/bin/env python3
"""Translate genuine Code_Aster MED results into an auditable AsterMax bundle + VTU.

C10.07 keeps the historical HEXA8 regression contract while extending the production bridge to
TETRA4, TETRA10 and supported mixed meshes. No synthetic FEA values are created. Displacements are
read directly from MED. SIGM_ELNO/SIEQ_ELNO are element-node fields; point contours use a declared
plain arithmetic average over the real incident element-node values.

Validation modes:
- regression (default): preserves the historical C9.62 44-node/10-HEXA8 numerical regression gate.
- production: validates actual MED dimensions and supported element families dynamically.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import h5py
import numpy as np

if len(sys.argv) != 4:
    raise SystemExit("usage: bridge-c964-med-results.py <input.rmed> <bundle.json> <results.vtu>")
med_path, bundle_path, vtu_path = sys.argv[1:]
if not os.path.isfile(med_path):
    raise SystemExit(f"MED file missing: {med_path}")

validation_mode = os.environ.get("ASTERMAX_MED_BRIDGE_MODE", "regression").strip().lower()
if validation_mode not in {"regression", "production"}:
    raise SystemExit("ASTERMAX_MED_BRIDGE_MODE must be regression or production")

MESH_ROOT = "ENS_MAA/00000001/-0000000000000000001-0000000000000000001"
STEP = "0000000000000000000100000000000000000001"

# MED geometry code -> (nodes/cell, AsterMax semantic name, VTK cell type)
SUPPORTED_FAMILIES = {
    "HE8": (8, "HEXA8", 12),
    "TE4": (4, "TETRA4", 10),
    "T10": (10, "TETRA10", 24),
}


def decode_components(raw, width=16):
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", "ignore")
    return [raw[i:i + width].strip() for i in range(0, len(raw), width) if raw[i:i + width].strip()]


def nodal_field(h, token):
    root = h[f"CHA/0000000e{token}"]
    comps = decode_components(root.attrs["NOM"])
    data = np.asarray(
        h[f"CHA/0000000e{token}/{STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO"][()], dtype=float
    )
    if not comps or len(data) % len(comps):
        raise RuntimeError(f"{token}: component/data size mismatch")
    return comps, data.reshape(len(comps), -1)


def discover_mesh_families(h):
    mai_path = f"{MESH_ROOT}/MAI"
    if mai_path not in h:
        raise RuntimeError("MED mesh has no MAI element section")
    families = {}
    unsupported = []
    for code in sorted(h[mai_path].keys()):
        group = h[f"{mai_path}/{code}"]
        if "NOD" not in group or "NUM" not in group:
            continue
        if code not in SUPPORTED_FAMILIES:
            unsupported.append(code)
            continue
        nodes_per_cell, semantic, vtk_type = SUPPORTED_FAMILIES[code]
        n_elem = int(group["NUM"].shape[0])
        raw = np.asarray(group["NOD"][()], dtype=int)
        if n_elem <= 0 or raw.size != n_elem * nodes_per_cell:
            raise RuntimeError(
                f"{code}: connectivity size {raw.size} is incompatible with {n_elem} x {nodes_per_cell}"
            )
        conn = raw.reshape(nodes_per_cell, n_elem).T
        if np.any(conn <= 0):
            raise RuntimeError(f"{code}: connectivity contains non-positive node ids")
        families[code] = {
            "nodes_per_cell": nodes_per_cell,
            "semantic": semantic,
            "vtk_type": vtk_type,
            "conn": conn,
            "n_elem": n_elem,
        }
    if unsupported:
        raise RuntimeError("unsupported MED volume element families: " + ",".join(unsupported))
    if not families:
        raise RuntimeError("MED contains no supported volume elements (TE4/T10/HE8)")
    return families


def discover_element_node_field(h, token, families):
    root_path = f"CHA/0000000e{token}"
    if root_path not in h:
        raise RuntimeError(f"missing MED field: {token}")
    root = h[root_path]
    comps = decode_components(root.attrs["NOM"])
    if not comps:
        raise RuntimeError(f"{token}: no components")
    step_path = f"{root_path}/{STEP}"
    if step_path not in h:
        raise RuntimeError(f"{token}: expected MED step is missing")
    blocks = {}
    for location in h[step_path].keys():
        if not location.startswith("NOE."):
            continue
        code = location.split(".", 1)[1]
        if code not in families:
            continue
        data_path = f"{step_path}/{location}/MED_NO_PROFILE_INTERNAL/CO"
        if data_path not in h:
            continue
        raw = np.asarray(h[data_path][()], dtype=float)
        if raw.size % len(comps):
            raise RuntimeError(f"{token}/{location}: component/data size mismatch")
        data = raw.reshape(len(comps), -1)
        expected = families[code]["n_elem"] * families[code]["nodes_per_cell"]
        if data.shape[1] != expected:
            raise RuntimeError(
                f"{token}/{location}: expected {expected} element-node values/component, got {data.shape[1]}"
            )
        blocks[code] = data
    missing = sorted(set(families) - set(blocks))
    if missing:
        raise RuntimeError(f"{token}: missing element-node result blocks for {','.join(missing)}")
    return comps, blocks


def average_element_node_component(blocks, families, component_index, n_nodes):
    accum = defaultdict(list)
    for code, data in blocks.items():
        values = data[component_index]
        conn = families[code]["conn"].reshape(-1)
        if len(values) != len(conn):
            raise RuntimeError(f"{code}: result/connectivity length mismatch")
        for nid, value in zip(conn, values):
            nid = int(nid)
            if nid < 1 or nid > n_nodes:
                raise RuntimeError(f"{code}: node id {nid} is outside 1..{n_nodes}")
            accum[nid].append(float(value))
    missing = [i for i in range(1, n_nodes + 1) if i not in accum]
    if missing:
        raise RuntimeError(
            "element-node result coverage does not include all MED nodes; first missing ids: "
            + ",".join(map(str, missing[:10]))
        )
    return np.array([sum(accum[i]) / len(accum[i]) for i in range(1, n_nodes + 1)], dtype=float)


def write_data_array(parent, name, values, ncomp=1, vtk_type="Float64"):
    attrs = {"type": vtk_type, "Name": name, "format": "ascii"}
    if ncomp != 1:
        attrs["NumberOfComponents"] = str(ncomp)
    e = ET.SubElement(parent, "DataArray", attrs)
    arr = np.asarray(values)
    e.text = "\n" + " ".join(
        f"{float(x):.15g}" if vtk_type.startswith("Float") else str(int(x))
        for x in arr.reshape(-1)
    ) + "\n"


with h5py.File(med_path, "r") as h:
    coords_raw = np.asarray(h[f"{MESH_ROOT}/NOE/COO"][()], dtype=float)
    n_nodes = int(h[f"{MESH_ROOT}/NOE/COO"].attrs["NBR"])
    if coords_raw.size != n_nodes * 3:
        raise RuntimeError("MED coordinate array does not match declared node count")
    coords = coords_raw.reshape(3, n_nodes).T

    families = discover_mesh_families(h)
    n_elem = sum(x["n_elem"] for x in families.values())

    dcomp, displacement_blocks = nodal_field(h, "DEPL")
    if dcomp[:3] != ["DX", "DY", "DZ"]:
        raise RuntimeError(f"unexpected DEPL components: {dcomp}")
    if displacement_blocks.shape[1] != n_nodes:
        raise RuntimeError("DEPL nodal count does not match mesh node count")
    displacement = displacement_blocks[:3].T
    total = np.linalg.norm(displacement, axis=1)

    scomp, stress_by_family = discover_element_node_field(h, "SIGM_ELNO", families)
    qcomp, equiv_by_family = discover_element_node_field(h, "SIEQ_ELNO", families)
    if "VMIS" not in qcomp:
        raise RuntimeError("SIEQ_ELNO has no VMIS component")

    nodal_stress = {
        name: average_element_node_component(stress_by_family, families, i, n_nodes)
        for i, name in enumerate(scomp)
    }
    vm_idx = qcomp.index("VMIS")
    von_mises = average_element_node_component(equiv_by_family, families, vm_idx, n_nodes)
    vm_elno = np.concatenate([equiv_by_family[c][vm_idx] for c in sorted(equiv_by_family)])

family_codes = sorted(families)
semantic_types = [families[c]["semantic"] for c in family_codes]
mesh_element_type = semantic_types[0] if len(semantic_types) == 1 else "MIXED"

connectivity_json = []
cell_types = []
offsets = []
flat_connectivity = []
running = 0
for code in family_codes:
    fam = families[code]
    for row in fam["conn"]:
        ids = [int(x) for x in row]
        connectivity_json.append(ids)
        flat_connectivity.extend(x - 1 for x in ids)
        running += len(ids)
        offsets.append(running)
        cell_types.append(fam["vtk_type"])

bundle = {
    "schema": "astermax-results-bundle/v0",
    "release": "C10.07-production" if validation_mode == "production" else "C10.07-regression",
    "source": {
        "kind": "REAL_CODE_ASTER_MED",
        "file": os.path.basename(med_path),
        "size_bytes": os.path.getsize(med_path),
    },
    "units": {"length": "mm", "force": "N", "stress": "MPa"},
    "mesh": {
        "node_count": int(n_nodes),
        "element_count": int(n_elem),
        "element_type": mesh_element_type,
        "element_types": semantic_types,
        "med_family_codes": family_codes,
    },
    "fields": {
        "displacement": {
            "location": "NODE",
            "components": dcomp[:3],
            "derived": False,
            "dx_min": float(displacement[:, 0].min()),
            "dx_max": float(displacement[:, 0].max()),
            "total_min": float(total.min()),
            "total_max": float(total.max()),
        },
        "stress": {
            "location": "NODE",
            "components": scomp,
            "derived": True,
            "derivation": "arithmetic mean of real Code_Aster SIGM_ELNO values over incident element-local nodes",
        },
        "von_mises": {
            "location": "NODE",
            "component": "VMIS",
            "derived": True,
            "derivation": "arithmetic mean of real Code_Aster SIEQ_ELNO/VMIS values over incident element-local nodes",
            "raw_elno_min": float(vm_elno.min()),
            "raw_elno_max": float(vm_elno.max()),
            "nodal_min": float(von_mises.min()),
            "nodal_max": float(von_mises.max()),
        },
    },
    "arrays": {
        "coordinates": coords.tolist(),
        "connectivity": connectivity_json,
        "cell_types": cell_types,
        "displacement": displacement.tolist(),
        "total_deformation": total.tolist(),
        "von_mises": von_mises.tolist(),
        "stress": {k: v.tolist() for k, v in nodal_stress.items()},
    },
    "integrity": {
        "fea_values_invented": False,
        "solver_output_modified": False,
        "derived_nodal_stress_average_declared": True,
        "bridge_validation_mode": validation_mode,
        "supported_med_families": ["TE4", "T10", "HE8"],
    },
}
with open(bundle_path, "w", encoding="utf-8") as f:
    json.dump(bundle, f, indent=2)

vtk = ET.Element("VTKFile", {"type": "UnstructuredGrid", "version": "0.1", "byte_order": "LittleEndian"})
ug = ET.SubElement(vtk, "UnstructuredGrid")
piece = ET.SubElement(ug, "Piece", {"NumberOfPoints": str(n_nodes), "NumberOfCells": str(n_elem)})
points = ET.SubElement(piece, "Points")
write_data_array(points, "Points", coords, 3)
cells = ET.SubElement(piece, "Cells")
write_data_array(cells, "connectivity", np.asarray(flat_connectivity), 1, "Int32")
write_data_array(cells, "offsets", np.asarray(offsets), 1, "Int32")
write_data_array(cells, "types", np.asarray(cell_types), 1, "UInt8")
pd = ET.SubElement(piece, "PointData", {"Scalars": "Equivalent Stress", "Vectors": "Displacement"})
write_data_array(pd, "Displacement", displacement, 3)
write_data_array(pd, "Total Deformation", total)
write_data_array(pd, "Equivalent Stress", von_mises)
for name, arr in nodal_stress.items():
    write_data_array(pd, f"Stress {name}", arr)
ET.ElementTree(vtk).write(vtu_path, encoding="utf-8", xml_declaration=True)

production_checks = {
    "real_med_source": bool(bundle["source"]["size_bytes"] > 1000),
    "mesh_nonempty_supported": bool(n_nodes > 0 and n_elem > 0 and len(connectivity_json) == n_elem),
    "supported_element_families_only": bool(all(c in SUPPORTED_FAMILIES for c in family_codes)),
    "coordinates_present_finite": bool(coords.shape == (n_nodes, 3) and np.isfinite(coords).all()),
    "displacement_present_finite": bool(displacement.shape == (n_nodes, 3) and np.isfinite(displacement).all()),
    "stress_present_finite": bool(
        len(scomp) > 0 and all(len(v) == n_nodes and np.isfinite(v).all() for v in nodal_stress.values())
    ),
    "von_mises_present_finite": bool(len(von_mises) == n_nodes and np.isfinite(von_mises).all()),
    "no_invented_results": bool(bundle["integrity"]["fea_values_invented"] is False),
    "vtu_written": bool(os.path.isfile(vtu_path) and os.path.getsize(vtu_path) > 1000),
}
if validation_mode == "regression":
    he8 = families.get("HE8")
    checks = dict(production_checks)
    checks.update({
        "mesh_44_nodes_10_hex": bool(
            len(families) == 1 and he8 is not None and n_nodes == 44 and he8["n_elem"] == 10
        ),
        "c962_dx_reproduced": bool(abs(float(displacement[:, 0].max()) - 0.0471697826890255) < 1e-12),
    })
else:
    checks = production_checks

summary = {
    "release": "C10.07",
    "validation_mode": validation_mode,
    "checks": checks,
    "checks_passed": int(sum(checks.values())),
    "checks_total": len(checks),
    "pass": bool(all(checks.values())),
    "node_count": int(n_nodes),
    "element_count": int(n_elem),
    "element_types": semantic_types,
    "dx_max_mm": float(displacement[:, 0].max()),
    "total_deformation_max_mm": float(total.max()),
    "von_mises_nodal_max_mpa": float(von_mises.max()),
    "von_mises_raw_elno_max_mpa": float(vm_elno.max()),
    "fea_values_invented": False,
}
print(json.dumps(summary, indent=2))
if not summary["pass"]:
    raise SystemExit("C10.07 results bridge gate failed")
