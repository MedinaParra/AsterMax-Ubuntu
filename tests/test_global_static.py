import unittest

from astermax.global_static import GlobalStaticError, assemble_stiffness, solve_linear_static


class MultiTet4PatchHarness(unittest.TestCase):
    def setUp(self):
        self.nodes = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 1.0),
        ]
        # Five tetrahedra filling the unit cube.
        self.elements = [
            (0, 1, 3, 4),
            (1, 2, 3, 6),
            (1, 3, 4, 6),
            (1, 4, 5, 6),
            (3, 4, 6, 7),
        ]
        self.young = 210000.0
        self.poisson = 0.30

    def affine_displacements(self):
        # Manufactured constant-strain field:
        # ex=0.001, ey=0.002, ez=-0.0005, gamma_xy=gamma_yz=gamma_xz=0.
        values = []
        for x, y, z in self.nodes:
            values.extend((0.001 * x, 0.002 * y, -0.0005 * z))
        return values

    def test_global_solver_recovers_manufactured_affine_solution(self):
        k = assemble_stiffness(self.nodes, self.elements, self.young, self.poisson)
        exact = self.affine_displacements()
        full_equivalent_load = [
            sum(k[i][j] * exact[j] for j in range(len(exact)))
            for i in range(len(exact))
        ]

        # Six independent rigid-body constraints. Their exact values are imposed;
        # equivalent loads are applied only on free DOFs, leaving support reactions
        # to recover the omitted constrained-DOF load contribution.
        constraints = {0: exact[0], 1: exact[1], 2: exact[2], 4: exact[4], 5: exact[5], 11: exact[11]}
        loads = {dof: value for dof, value in enumerate(full_equivalent_load) if dof not in constraints}

        result = solve_linear_static(
            self.nodes,
            self.elements,
            self.young,
            self.poisson,
            constraints,
            loads,
        )

        for actual, expected in zip(result.displacements, exact):
            self.assertAlmostEqual(actual, expected, places=12)

        expected_strain = (0.001, 0.002, -0.0005, 0.0, 0.0, 0.0)
        expected_stress = (
            464.4230769230769,
            625.9615384615385,
            222.1153846153846,
            0.0,
            0.0,
            0.0,
        )
        for element in result.element_results:
            for actual, expected in zip(element.strain, expected_strain):
                self.assertAlmostEqual(actual, expected, places=12)
            for actual, expected in zip(element.stress, expected_stress):
                self.assertAlmostEqual(actual, expected, places=9)

        # Global force balance: applied nodal force + recovered reactions ~= 0.
        applied = [0.0] * len(exact)
        for dof, value in loads.items():
            applied[dof] = value
        for component in range(3):
            balance = sum(
                applied[3 * node + component] + result.reactions[3 * node + component]
                for node in range(len(self.nodes))
            )
            self.assertAlmostEqual(balance, 0.0, places=9)

        # Free-DOF residual must vanish.
        for dof, residual in enumerate(result.residual):
            if dof not in constraints:
                self.assertAlmostEqual(residual, 0.0, places=9)

    def test_global_stiffness_is_symmetric(self):
        k = assemble_stiffness(self.nodes, self.elements, self.young, self.poisson)
        for i in range(len(k)):
            for j in range(len(k)):
                self.assertAlmostEqual(k[i][j], k[j][i], places=10)

    def test_underconstrained_model_is_rejected_as_singular(self):
        with self.assertRaises(GlobalStaticError):
            solve_linear_static(
                self.nodes,
                self.elements,
                self.young,
                self.poisson,
                {0: 0.0},
                {18: 1.0},
            )

    def test_bad_connectivity_is_rejected(self):
        with self.assertRaises(GlobalStaticError):
            assemble_stiffness(self.nodes, [(0, 1, 2, 99)], self.young, self.poisson)


if __name__ == "__main__":
    unittest.main()
