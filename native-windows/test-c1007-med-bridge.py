#!/usr/bin/env python3
"""Synthetic-format harness for C10.07 MED parsing mechanics.

The fixture contains deterministic arrays only to test the bridge parser, family mapping and VTU
serialization. It is NOT solver evidence and must never be presented as an FEA validation result.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import h5py
import numpy as np

ROOT = "ENS_MAA/00000001/-0000000000000000001-0000000000000000001"
STEP = "0000000000000000000100000000000000000001"
FAMILIES = {
    "TE4": {"npe": 4, "semantic": "TETRA4", "vtk": 10},
    "T10": {"npe": 10, "semantic": "TETRA10", "vtk": 24},
    "HE8": {"npe": 8, "semantic": "HEXA8", "vtk": 12},
}


def nom(*names):
    return "".join(n.ljust(16) for n in names).encode("ascii")


def add_flat_dataset(h, path, values):
    parent, name = path.rsplit("/", 1)
    g = h.require_group(parent)
    return g.create_dataset(name, data=np.asarray(values).reshape(-1))


def build_fixture(path, case_families):
    max_node = max(max(max(row) for row in conns) for conns in case_families.values())
    coords = np.array([[float(i), float((i * 3) % 7), float((i * 5) % 11)] for i in range(1, max_node + 1)])
    displacement = np.column_stack((np.linspace(0.0, 0.01, max_node), np.zeros(max_node), np.zeros(max_node)))
    s_names = ["SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ"]

    with h5py.File(path, "w") as h:
        coo = add_flat_dataset(h, f"{ROOT}/NOE/COO", coords.T.reshape(-1))
        coo.attrs["NBR"] = max_node

        for code, conns in case_families.items():
            info = FAMILIES[code]
            conn = np.asarray(conns, dtype=int)
            assert conn.shape[1] == info["npe"]
            add_flat_dataset(h, f"{ROOT}/MAI/{code}/NOD", conn.T.reshape(-1))
            h.require_group(f"{ROOT}/MAI/{code}").create_dataset("NUM", data=np.arange(1, len(conn) + 1))

        droot = h.require_group("CHA/0000000eDEPL")
        droot.attrs["NOM"] = nom("DX", "DY", "DZ")
        add_flat_dataset(h, f"CHA/0000000eDEPL/{STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO", displacement.T.reshape(-1))

        sroot = h.require_group("CHA/0000000eSIGM_ELNO")
        sroot.attrs["NOM"] = nom(*s_names)
        qroot = h.require_group("CHA/0000000eSIEQ_ELNO")
        qroot.attrs["NOM"] = nom("VMIS")

        for family_index, (code, conns) in enumerate(sorted(case_families.items())):
            conn = np.asarray(conns, dtype=int)
            count = conn.size
            base = np.linspace(1.0 + family_index, 2.0 + family_index, count)
            stress = np.vstack([base * (i + 1) for i in range(len(s_names))])
            vm = np.sqrt(np.sum(stress[:3] ** 2, axis=0))[None, :]
            add_flat_dataset(
                h,
                f"CHA/0000000eSIGM_ELNO/{STEP}/NOE.{code}/MED_NO_PROFILE_INTERNAL/CO",
                stress.reshape(-1),
            )
            add_flat_dataset(
                h,
                f"CHA/0000000eSIEQ_ELNO/{STEP}/NOE.{code}/MED_NO_PROFILE_INTERNAL/CO",
                vm.reshape(-1),
            )


def run_case(bridge, name, case_families, expected_semantics, expected_vtk):
    with tempfile.TemporaryDirectory(prefix=f"astermax-c1007-{name}-") as td:
        td = pathlib.Path(td)
        med = td / "case.rmed"
        bundle = td / "bundle.json"
        vtu = td / "results.vtu"
        build_fixture(med, case_families)
        env = dict(os.environ)
        env["ASTERMAX_MED_BRIDGE_MODE"] = "production"
        p = subprocess.run(
            [sys.executable, str(bridge), str(med), str(bundle), str(vtu)],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if p.returncode != 0:
            raise RuntimeError(f"{name}: bridge failed\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
        summary = json.loads(p.stdout)
        data = json.loads(bundle.read_text(encoding="utf-8"))
        if not summary.get("pass"):
            raise AssertionError(f"{name}: summary did not pass")
        if data["mesh"]["element_types"] != expected_semantics:
            raise AssertionError(f"{name}: semantics {data['mesh']['element_types']} != {expected_semantics}")
        if data["integrity"]["fea_values_invented"] is not False:
            raise AssertionError(f"{name}: integrity flag changed")
        tree = ET.parse(vtu)
        types_node = next(x for x in tree.iter("DataArray") if x.attrib.get("Name") == "types")
        vtk_types = [int(x) for x in (types_node.text or "").split()]
        if vtk_types != expected_vtk:
            raise AssertionError(f"{name}: VTK types {vtk_types} != {expected_vtk}")
        print(json.dumps({
            "case": name,
            "status": "PASS",
            "element_types": data["mesh"]["element_types"],
            "vtk_types": vtk_types,
            "synthetic_fixture_only": True,
            "solver_evidence": False,
        }))


def main():
    bridge = pathlib.Path(__file__).with_name("bridge-c964-med-results.py")
    run_case(bridge, "tet4", {"TE4": [[1, 2, 3, 4]]}, ["TETRA4"], [10])
    run_case(bridge, "tet10", {"T10": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]}, ["TETRA10"], [24])
    run_case(
        bridge,
        "mixed-tet",
        {
            "TE4": [[1, 2, 3, 4]],
            "T10": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
        },
        ["TETRA10", "TETRA4"],
        [24, 10],
    )
    run_case(bridge, "hexa8", {"HE8": [[1, 2, 3, 4, 5, 6, 7, 8]]}, ["HEXA8"], [12])
    print("C1007_MED_BRIDGE_FAMILY_HARNESS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
