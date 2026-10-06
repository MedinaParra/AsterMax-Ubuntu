"""Parser/derived-math fixtures only. This suite does not execute a solver."""
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fixture", HERE / "test-c1007-med-bridge.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class MedMechanicsTests(unittest.TestCase):
    def run_bridge(self, edit, succeeds=True):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            med, bundle, vtu = (root / n for n in ("case.rmed", "bundle.json", "result.vtu"))
            fixture.build_fixture(med, {"TE4": [[1,2,3,4], [1,2,3,4]]})
            with h5py.File(med, "r+") as h:
                edit(h)
            # Invalid data must leave previously published artifacts untouched.
            if not succeeds:
                bundle.write_text("previous-bundle")
                vtu.write_text("previous-vtu")
            p = subprocess.run([sys.executable, str(HERE / "bridge-c964-med-results.py"),
                                str(med), str(bundle), str(vtu)], capture_output=True, text=True,
                               env=dict(os.environ, ASTERMAX_MED_BRIDGE_MODE="production"))
            if succeeds:
                self.assertEqual(p.returncode, 0, p.stderr)
                return json.loads(bundle.read_text())
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(bundle.read_text(), "previous-bundle")
            self.assertEqual(vtu.read_text(), "previous-vtu")
            return p.stderr

    def stress(self, h, first, second, raw_vm=100):
        data = np.column_stack([first]*4 + [second]*4)
        h[f"CHA/0000000eSIGM_ELNO/{fixture.STEP}/NOE.TE4/MED_NO_PROFILE_INTERNAL/CO"][...] = data.reshape(-1)
        h[f"CHA/0000000eSIEQ_ELNO/{fixture.STEP}/NOE.TE4/MED_NO_PROFILE_INTERNAL/CO"][...] = np.full(8, raw_vm)

    def reaction(self, h, values):
        group = h.require_group("CHA/0000000eREAC_NODA")
        group.attrs["NOM"] = fixture.nom("DX", "DY", "DZ")
        group.attrs["MAI"] = b"00000001"
        fixture.add_flat_dataset(h, f"CHA/0000000eREAC_NODA/{fixture.STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO",
                                 np.asarray(values).T.reshape(-1))

    def test_opposite_tensors_cancel_before_invariant(self):
        data = self.run_bridge(lambda h: self.stress(h, [100,0,0,0,0,0], [-100,0,0,0,0,0]))
        self.assertEqual(data["arrays"]["von_mises"], [0]*4)
        self.assertEqual(data["fields"]["von_mises"]["raw_elno_max"], 100)
        self.assertTrue(data["integrity"]["von_mises_component_first_ansys_parity"])

    def test_hydrostatic_tensor_has_zero_von_mises(self):
        data = self.run_bridge(lambda h: self.stress(h, [100,100,100,0,0,0], [100,100,100,0,0,0]))
        self.assertEqual(data["arrays"]["von_mises"], [0]*4)

    def test_shear_invariant(self):
        data = self.run_bridge(lambda h: self.stress(h, [0,0,0,50,0,0], [0,0,0,50,0,0]))
        for value in data["arrays"]["von_mises"]:
            self.assertAlmostEqual(value, math.sqrt(3)*50)

    def test_reaction_is_read_from_independent_nodal_field(self):
        data = self.run_bridge(lambda h: self.reaction(h, [[10,0,0], [0,20,0], [0,0,-1000], [0,0,0]]))
        self.assertEqual(data["fields"]["reaction"]["resultant_n"], [10,20,-1000])
        self.assertTrue(data["integrity"]["reaction_resultant_from_real_reac_noda"])

    def test_absent_reactions_are_not_fabricated(self):
        data = self.run_bridge(lambda h: None)
        self.assertIsNone(data["fields"]["reaction"])
        self.assertFalse(data["integrity"]["reaction_resultant_from_real_reac_noda"])

    def test_invalid_reaction_preserves_previous_artifacts(self):
        self.run_bridge(lambda h: self.reaction(h, [[0,0,0]]*3 + [[float("nan"),0,0]]), False)

    def test_reaction_wrong_mesh_is_rejected(self):
        def edit(h):
            self.reaction(h, [[0,0,0]]*4)
            h["CHA/0000000eREAC_NODA"].attrs["MAI"] = b"OTHER"
        self.assertIn("different MED mesh", self.run_bridge(edit, False))

    def test_reaction_wrong_step_is_rejected(self):
        def edit(h):
            self.reaction(h, [[0,0,0]]*4)
            root = "CHA/0000000eREAC_NODA"
            h.move(f"{root}/{fixture.STEP}", f"{root}/different-step")
        self.assertIn("one common step", self.run_bridge(edit, False))

    def test_missing_tensor_component_is_rejected(self):
        def edit(h):
            h["CHA/0000000eSIGM_ELNO"].attrs["NOM"] = fixture.nom("SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "OTHER")
        self.assertIn("missing components", self.run_bridge(edit, False))

    def test_contact_skin_is_not_a_volume_result_family(self):
        def edit(h):
            fixture.add_flat_dataset(h, f"{fixture.ROOT}/MAI/TR3/NOD", [1,2,3])
            fixture.add_flat_dataset(h, f"{fixture.ROOT}/MAI/TR3/NUM", [3])
        data = self.run_bridge(edit)
        self.assertEqual(data["mesh"]["element_count"], 2)
        self.assertEqual(data["mesh"]["element_types"], ["TETRA4"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
