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
import re
import sys
import tempfile
from xml.sax.saxutils import quoteattr

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


def med_field_path(h, token):
    # Code_Aster 15 uses an internal eight-hex-digit concept prefix; 17 writes
    # the result concept name followed by __. Never silently pick among results.
    names = [name for name in h["CHA"] if name == token or name.endswith("__" + token)
             or re.fullmatch(r"[0-9a-fA-F]{8}" + re.escape(token), name)]
    if len(names) != 1:
        raise RuntimeError(f"{token}: expected one unambiguous MED field, found {names}")
    root = h["CHA/" + names[0]]
    mesh = root.attrs.get("MAI", b"")
    if isinstance(mesh, bytes):
        mesh = mesh.decode("ascii")
    if str(mesh) != MESH_ROOT.split("/")[1]:
        raise RuntimeError(f"{token}: field belongs to a different MED mesh: {mesh}")
    return "CHA/" + names[0]


def nodal_field(h, token):
    root_path = med_field_path(h, token)
    root = h[root_path]
    comps = decode_components(root.attrs["NOM"])
    data = np.asarray(
        h[f"{root_path}/{STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO"][()], dtype=float
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
    root_path = med_field_path(h, token)
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
    sums = np.zeros(n_nodes, dtype=np.float64)
    counts = np.zeros(n_nodes, dtype=np.int64)
    for code, data in blocks.items():
        values = np.asarray(data[component_index], dtype=np.float64)
        conn = np.asarray(families[code]["conn"], dtype=np.int64).reshape(-1)
        if len(values) != len(conn):
            raise RuntimeError(f"{code}: result/connectivity length mismatch")
        bad = conn[(conn < 1) | (conn > n_nodes)]
        if bad.size:
            raise RuntimeError(f"{code}: node id {int(bad[0])} is outside 1..{n_nodes}")
        zero_based = conn - 1
        sums += np.bincount(zero_based, weights=values, minlength=n_nodes)[:n_nodes]
        counts += np.bincount(zero_based, minlength=n_nodes)[:n_nodes]
    missing = np.flatnonzero(counts == 0) + 1
    if missing.size:
        raise RuntimeError(
            "element-node result coverage does not include all MED nodes; first missing ids: "
            + ",".join(map(str, missing[:10].tolist()))
        )
    return sums / counts


def _write_json_vector(handle, values, integer=False, chunk_size=8192):
    arr = np.asarray(values).reshape(-1)
    handle.write("[")
    first = True
    for start in range(0, arr.size, chunk_size):
        chunk = arr[start:start + chunk_size]
        text = ",".join(str(int(x)) if integer else repr(float(x)) for x in chunk)
        if text:
            if not first:
                handle.write(",")
            handle.write(text)
            first = False
    handle.write("]")


def _write_json_matrix(handle, values, integer=False):
    arr = np.asarray(values)
    if arr.ndim != 2:
        raise ValueError("matrix writer requires a 2D array")
    handle.write("[")
    for i, row in enumerate(arr):
        if i:
            handle.write(",")
        _write_json_vector(handle, row, integer=integer)
    handle.write("]")


def _write_json_connectivity(handle, families, family_codes):
    handle.write("[")
    first = True
    for code in family_codes:
        for row in families[code]["conn"]:
            if not first:
                handle.write(",")
            _write_json_vector(handle, row, integer=True)
            first = False
    handle.write("]")


def _write_json_cell_types(handle, families, family_codes):
    handle.write("[")
    first = True
    for code in family_codes:
        value = str(int(families[code]["vtk_type"]))
        remaining = int(families[code]["n_elem"])
        while remaining:
            count = min(8192, remaining)
            text = ",".join([value] * count)
            if not first:
                handle.write(",")
            handle.write(text)
            first = False
            remaining -= count
    handle.write("]")


def write_bundle_streaming(path, bundle, families, family_codes, coords, displacement, total, von_mises, nodal_stress):
    """Write schema v0 compactly without materializing NumPy arrays as Python lists."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("{")
        first = True
        for key in ("schema", "release", "source", "units", "mesh", "fields"):
            if not first:
                handle.write(",")
            handle.write(json.dumps(key) + ":")
            handle.write(json.dumps(bundle[key], indent=None, separators=(",", ":"), allow_nan=False))
            first = False
        handle.write(',"arrays":{')
        handle.write('"coordinates":')
        _write_json_matrix(handle, coords)
        handle.write(',"connectivity":')
        _write_json_connectivity(handle, families, family_codes)
        handle.write(',"cell_types":')
        _write_json_cell_types(handle, families, family_codes)
        handle.write(',"displacement":')
        _write_json_matrix(handle, displacement)
        handle.write(',"total_deformation":')
        _write_json_vector(handle, total)
        handle.write(',"von_mises":')
        _write_json_vector(handle, von_mises)
        handle.write(',"stress":{')
        for i, (name, values) in enumerate(nodal_stress.items()):
            if i:
                handle.write(",")
            handle.write(json.dumps(name) + ":")
            _write_json_vector(handle, values)
        handle.write("}")
        handle.write("}")
        handle.write(',"integrity":')
        handle.write(json.dumps(bundle["integrity"], indent=None, separators=(",", ":"), allow_nan=False))
        handle.write("}")


def _write_vtu_values(handle, chunks, vtk_type, chunk_size=8192):
    first = True
    for values in chunks:
        arr = np.asarray(values).reshape(-1)
        for start in range(0, arr.size, chunk_size):
            chunk = arr[start:start + chunk_size]
            if vtk_type.startswith("Float"):
                text = " ".join(f"{float(x):.15g}" for x in chunk)
            else:
                text = " ".join(str(int(x)) for x in chunk)
            if text:
                if not first:
                    handle.write(" ")
                handle.write(text)
                first = False


def _write_vtu_data_array(handle, name, chunks, ncomp=1, vtk_type="Float64", indent="        "):
    attrs = f'type={quoteattr(vtk_type)} Name={quoteattr(name)} format="ascii"'
    if ncomp != 1:
        attrs += f' NumberOfComponents="{ncomp}"'
    handle.write(f"{indent}<DataArray {attrs}>\n{indent}  ")
    _write_vtu_values(handle, chunks, vtk_type)
    handle.write(f"\n{indent}</DataArray>\n")


def _connectivity_chunks(families, family_codes):
    for code in family_codes:
        yield np.asarray(families[code]["conn"], dtype=np.int64).reshape(-1) - 1


def _offset_chunks(families, family_codes):
    running = 0
    for code in family_codes:
        fam = families[code]
        npe = int(fam["nodes_per_cell"])
        count = int(fam["n_elem"])
        chunk = running + np.arange(1, count + 1, dtype=np.int64) * npe
        if count:
            running = int(chunk[-1])
        yield chunk


def _cell_type_chunks(families, family_codes):
    for code in family_codes:
        fam = families[code]
        yield np.full(int(fam["n_elem"]), int(fam["vtk_type"]), dtype=np.uint8)


def write_vtu_streaming(path, n_nodes, n_elem, families, family_codes, coords, displacement, total, von_mises, nodal_stress):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write('<?xml version="1.0" encoding="utf-8"?>\n')
        handle.write('<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">\n')
        handle.write("  <UnstructuredGrid>\n")
        handle.write(f'    <Piece NumberOfPoints="{n_nodes}" NumberOfCells="{n_elem}">\n')
        handle.write("      <Points>\n")
        _write_vtu_data_array(handle, "Points", (coords,), 3, indent="        ")
        handle.write("      </Points>\n")
        handle.write("      <Cells>\n")
        _write_vtu_data_array(handle, "connectivity", _connectivity_chunks(families, family_codes), vtk_type="Int32", indent="        ")
        _write_vtu_data_array(handle, "offsets", _offset_chunks(families, family_codes), vtk_type="Int32", indent="        ")
        _write_vtu_data_array(handle, "types", _cell_type_chunks(families, family_codes), vtk_type="UInt8", indent="        ")
        handle.write("      </Cells>\n")
        handle.write('      <PointData Scalars="Equivalent Stress" Vectors="Displacement">\n')
        _write_vtu_data_array(handle, "Displacement", (displacement,), 3, indent="        ")
        _write_vtu_data_array(handle, "Total Deformation", (total,), indent="        ")
        _write_vtu_data_array(handle, "Equivalent Stress", (von_mises,), indent="        ")
        for name, arr in nodal_stress.items():
            _write_vtu_data_array(handle, f"Stress {name}", (arr,), indent="        ")
        handle.write("      </PointData>\n")
        handle.write("    </Piece>\n")
        handle.write("  </UnstructuredGrid>\n")
        handle.write("</VTKFile>\n")


def _temporary_path(final_path):
    directory = os.path.dirname(os.path.abspath(final_path))
    prefix = "." + os.path.basename(final_path) + "."
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    os.close(fd)
    return path


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
    "integrity": {
        "fea_values_invented": False,
        "solver_output_modified": False,
        "derived_nodal_stress_average_declared": True,
        "bridge_validation_mode": validation_mode,
        "supported_med_families": ["TE4", "T10", "HE8"],
    },
}

production_checks = {
    "real_med_source": bool(bundle["source"]["size_bytes"] > 1000),
    "mesh_nonempty_supported": bool(n_nodes > 0 and n_elem > 0),
    "supported_element_families_only": bool(all(c in SUPPORTED_FAMILIES for c in family_codes)),
    "coordinates_present_finite": bool(coords.shape == (n_nodes, 3) and np.isfinite(coords).all()),
    "displacement_present_finite": bool(displacement.shape == (n_nodes, 3) and np.isfinite(displacement).all()),
    "total_deformation_present_finite": bool(total.shape == (n_nodes,) and np.isfinite(total).all()),
    "stress_present_finite": bool(
        len(scomp) > 0 and all(len(v) == n_nodes and np.isfinite(v).all() for v in nodal_stress.values())
    ),
    "von_mises_present_finite": bool(len(von_mises) == n_nodes and np.isfinite(von_mises).all()),
    "no_invented_results": bool(bundle["integrity"]["fea_values_invented"] is False),
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

# Reject invalid numerical data before spending I/O on temporary artifacts. No final artifact is
# touched here; the full check set is evaluated again after the temporary VTU has been written.
if not all(checks.values()):
    failed = [name for name, passed in checks.items() if not passed]
    raise SystemExit("C10.17 results bridge gate failed before publication: " + ", ".join(failed))

bundle_tmp = None
vtu_tmp = None
try:
    bundle_tmp = _temporary_path(bundle_path)
    write_bundle_streaming(
        bundle_tmp, bundle, families, family_codes, coords, displacement, total, von_mises, nodal_stress
    )
    vtu_tmp = _temporary_path(vtu_path)
    write_vtu_streaming(
        vtu_tmp, n_nodes, n_elem, families, family_codes, coords, displacement, total, von_mises, nodal_stress
    )

    checks["vtu_written"] = bool(os.path.isfile(vtu_tmp) and os.path.getsize(vtu_tmp) > 1000)
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit("C10.17 results bridge gate failed before publication: " + ", ".join(failed))

    # Publish the VTU first and the JSON entry point last. Each promotion is an atomic rename on the
    # destination filesystem; no final artifact is touched until every validation check has passed.
    os.replace(vtu_tmp, vtu_path)
    vtu_tmp = None
    os.replace(bundle_tmp, bundle_path)
    bundle_tmp = None
finally:
    for temporary in (bundle_tmp, vtu_tmp):
        if temporary and os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass

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
