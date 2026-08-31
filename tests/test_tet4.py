import math
import unittest

from astermax.tet4 import Tet4Error, evaluate, stiffness_matrix


class Tet4PatchTest(unittest.TestCase):
    def setUp(self):
        self.nodes = ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, 0.0, 10.0))
        self.young = 210000.0  # MPa = N/mm^2
        self.nu = 0.30

    def _affine_displacements(self, exx=1e-3, eyy=2e-3, ezz=-5e-4):
        u = []
        for x, y, z in self.nodes:
            u.extend((exx * x, eyy * y, ezz * z))
        return u

    def test_constant_strain_patch_is_recovered_exactly(self):
        result = evaluate(self.nodes, self._affine_displacements(), self.young, self.nu)
        expected = (1e-3, 2e-3, -5e-4, 0.0, 0.0, 0.0)
        for actual, target in zip(result.strain, expected):
            self.assertAlmostEqual(actual, target, places=12)
        self.assertAlmostEqual(result.volume, 1000.0 / 6.0, places=12)

    def test_stress_matches_3d_hooke_law(self):
        result = evaluate(self.nodes, self._affine_displacements(), self.young, self.nu)
        exx, eyy, ezz = result.strain[:3]
        lam = self.young * self.nu / ((1 + self.nu) * (1 - 2 * self.nu))
        mu = self.young / (2 * (1 + self.nu))
        trace = exx + eyy + ezz
        expected = (
            lam * trace + 2 * mu * exx,
            lam * trace + 2 * mu * eyy,
            lam * trace + 2 * mu * ezz,
        )
        for actual, target in zip(result.stress[:3], expected):
            self.assertAlmostEqual(actual, target, places=9)
        for shear in result.stress[3:]:
            self.assertAlmostEqual(shear, 0.0, places=12)

    def test_internal_forces_have_zero_net_force_and_moment(self):
        result = evaluate(self.nodes, self._affine_displacements(), self.young, self.nu)
        f = [result.internal_force[3*i:3*i+3] for i in range(4)]
        for axis in range(3):
            self.assertAlmostEqual(sum(node_force[axis] for node_force in f), 0.0, places=9)
        mx = my = mz = 0.0
        for (x, y, z), (fx, fy, fz) in zip(self.nodes, f):
            mx += y*fz - z*fy
            my += z*fx - x*fz
            mz += x*fy - y*fx
        self.assertAlmostEqual(mx, 0.0, places=9)
        self.assertAlmostEqual(my, 0.0, places=9)
        self.assertAlmostEqual(mz, 0.0, places=9)

    def test_energy_matches_continuum_energy_density(self):
        result = evaluate(self.nodes, self._affine_displacements(), self.young, self.nu)
        density = 0.5 * sum(e*s for e, s in zip(result.strain, result.stress))
        self.assertAlmostEqual(result.strain_energy, density * result.volume, places=9)

    def test_rigid_translation_produces_zero_strain_and_internal_force(self):
        u = [component for _ in self.nodes for component in (3.0, -2.0, 7.0)]
        result = evaluate(self.nodes, u, self.young, self.nu)
        for value in result.strain + result.internal_force:
            self.assertAlmostEqual(value, 0.0, places=9)

    def test_stiffness_is_symmetric(self):
        k = stiffness_matrix(self.nodes, self.young, self.nu)
        for i in range(12):
            for j in range(12):
                self.assertAlmostEqual(k[i][j], k[j][i], places=9)

    def test_degenerate_element_is_rejected(self):
        flat = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0))
        with self.assertRaises(Tet4Error):
            evaluate(flat, [0.0] * 12, self.young, self.nu)

    def test_invalid_material_is_rejected(self):
        with self.assertRaises(Tet4Error):
            evaluate(self.nodes, [0.0] * 12, -1.0, self.nu)
        with self.assertRaises(Tet4Error):
            evaluate(self.nodes, [0.0] * 12, self.young, 0.5)


if __name__ == "__main__":
    unittest.main()
