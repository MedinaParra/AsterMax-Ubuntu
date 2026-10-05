#!/usr/bin/env python3
"""Regression tests for the C10.19 vectorized element-node averaging path.

The MED files are deterministic parser fixtures only. They are not solver executions or physical
validation evidence. The legacy implementation below is the exact pre-C10.19 averaging algorithm.
"""
import ast
from collections import defaultdict
import importlib.util
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent

fixture_spec = importlib.util.spec_from_file_location("c1007_fixture", HERE / "test-c1007-med-bridge.py")
fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixture)


def load_vectorized_function():
    source_path = HERE / "bridge-c964-med-results.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "average_element_node_component"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"np": np, "RuntimeError": RuntimeError}
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace["average_element_node_component"]


def legacy_average_element_node_component(blocks, families, component_index, n_nodes):
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


def read_fixture_fields(path):
    with h5py.File(path, "r") as h:
        n_nodes = int(h[f"{fixture.ROOT}/NOE/COO"].attrs["NBR"])
        families = {}
        stress = {}
        equivalent = {}
        for code, info in fixture.FAMILIES.items():
            group_path = f"{fixture.ROOT}/MAI/{code}"
            if group_path not in h:
                continue
            n_elem = int(h[f"{group_path}/NUM"].shape[0])
            raw_conn = np.asarray(h[f"{group_path}/NOD"][()], dtype=int)
            families[code] = {
                "conn": raw_conn.reshape(info["npe"], n_elem).T,
                "n_elem": n_elem,
                "nodes_per_cell": info["npe"],
            }
            stress_raw = np.asarray(
                h[f"CHA/0000000eSIGM_ELNO/{fixture.STEP}/NOE.{code}/MED_NO_PROFILE_INTERNAL/CO"][()],
                dtype=float,
            )
            equivalent_raw = np.asarray(
                h[f"CHA/0000000eSIEQ_ELNO/{fixture.STEP}/NOE.{code}/MED_NO_PROFILE_INTERNAL/CO"][()],
                dtype=float,
            )
            stress[code] = stress_raw.reshape(6, -1)
            equivalent[code] = equivalent_raw.reshape(1, -1)
        return n_nodes, families, stress, equivalent


class VectorizedAverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectorized = staticmethod(load_vectorized_function())

    def assert_fixture_equal(self, case_families):
        with tempfile.TemporaryDirectory(prefix="astermax-c1019-average-") as directory:
            med = Path(directory) / "fixture.rmed"
            fixture.build_fixture(med, case_families)
            n_nodes, families, stress, equivalent = read_fixture_fields(med)
            for component in range(6):
                expected = legacy_average_element_node_component(stress, families, component, n_nodes)
                actual = self.vectorized(stress, families, component, n_nodes)
                np.testing.assert_array_equal(actual, expected)
            expected_vm = legacy_average_element_node_component(equivalent, families, 0, n_nodes)
            actual_vm = self.vectorized(equivalent, families, 0, n_nodes)
            np.testing.assert_array_equal(actual_vm, expected_vm)

    def test_tetra4_fixture_matches_legacy_exactly(self):
        self.assert_fixture_equal({"TE4": [[1, 2, 3, 4]]})

    def test_tetra10_fixture_matches_legacy_exactly(self):
        self.assert_fixture_equal({"T10": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]})

    def test_mixed_tetra_fixture_matches_legacy_exactly(self):
        self.assert_fixture_equal({
            "TE4": [[1, 2, 3, 4]],
            "T10": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
        })

    def assert_same_error(self, blocks, families, component_index, n_nodes):
        with self.assertRaises(RuntimeError) as legacy:
            legacy_average_element_node_component(blocks, families, component_index, n_nodes)
        with self.assertRaises(RuntimeError) as vectorized:
            self.vectorized(blocks, families, component_index, n_nodes)
        self.assertEqual(str(vectorized.exception), str(legacy.exception))

    def test_out_of_range_error_matches_legacy(self):
        families = {"TE4": {"conn": np.asarray([[1, 2, 3, 5]], dtype=int)}}
        blocks = {"TE4": np.asarray([[1.0, 2.0, 3.0, 4.0]])}
        self.assert_same_error(blocks, families, 0, 4)

    def test_incomplete_coverage_error_matches_legacy(self):
        families = {"TE4": {"conn": np.asarray([[1, 2, 3, 4]], dtype=int)}}
        blocks = {"TE4": np.asarray([[1.0, 2.0, 3.0, 4.0]])}
        self.assert_same_error(blocks, families, 0, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
