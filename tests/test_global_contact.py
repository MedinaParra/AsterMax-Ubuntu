import unittest

from astermax.contact import rigid_stop_reference, solve_penalty_stop
from astermax.global_contact import (
    GlobalContactError,
    RigidStopContact,
    solve_active_set_from_stiffness,
    solve_tet4_with_rigid_stops,
)


class ActiveSetScalarContactTests(unittest.TestCase):
    def test_open_branch_matches_linear_spring(self):
        result = solve_active_set_from_stiffness(
            [[1000.0]],
            constraints={},
            loads={0: 399.0},
            contacts=[RigidStopContact(0, 0.4, 100000.0)],
        )
        self.assertTrue(result.converged)
        self.assertFalse(result.active_contacts[0])
        self.assertAlmostEqual(result.displacements[0], 0.399, places=12)
        self.assertAlmostEqual(result.contact_forces_n[0], 0.0, places=12)
        self.assertAlmostEqual(result.residual[0], 0.0, places=9)

    def test_closed_branch_matches_independent_penalty_oracle(self):
        ks = 1000.0
        kp = 50000.0
        gap = 0.4
        load = 1000.0
        oracle = solve_penalty_stop(ks, kp, gap, load)
        result = solve_active_set_from_stiffness(
            [[ks]],
            constraints={},
            loads={0: load},
            contacts=[RigidStopContact(0, gap, kp)],
        )
        self.assertTrue(result.converged)
        self.assertTrue(result.active_contacts[0])
        self.assertAlmostEqual(result.displacements[0], oracle.displacement_mm, places=12)
        self.assertAlmostEqual(result.contact_forces_n[0], oracle.contact_force_n, places=9)
        self.assertAlmostEqual(result.residual[0], 0.0, places=9)

    def test_penalty_converges_toward_rigid_stop_reference(self):
        reference = rigid_stop_reference(1000.0, 0.4, 1000.0)
        errors = []
        for kp in (10000.0, 100000.0, 1000000.0):
            result = solve_active_set_from_stiffness(
                [[1000.0]],
                constraints={},
                loads={0: 1000.0},
                contacts=[RigidStopContact(0, 0.4, kp)],
            )
            errors.append(abs(result.displacements[0] - reference.displacement_mm))
        self.assertGreater(errors[0], errors[1])
        self.assertGreater(errors[1], errors[2])

    def test_invalid_contact_definition_is_rejected(self):
        with self.assertRaises(GlobalContactError):
            solve_active_set_from_stiffness(
                [[1.0]], {}, {0: 1.0}, [RigidStopContact(2, 0.1, 1000.0)]
            )
        with self.assertRaises(GlobalContactError):
            solve_active_set_from_stiffness(
                [[1.0]], {0: 0.0}, {}, [RigidStopContact(0, 0.1, 1000.0)]
            )


class Tet4ContactIntegrationTests(unittest.TestCase):
    def test_tet4_model_closes_gap_and_balances_contact(self):
        # One tetrahedron. Node 0 is fully fixed. Nodes 1 and 2 are constrained
        # transversely enough to remove rigid modes; node 3 x-DOF is loaded toward
        # a scalar rigid stop. This is an integration smoke test, not a general
        # surface-contact benchmark.
        nodes = [
            (0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0),
            (0.0, 10.0, 0.0),
            (0.0, 0.0, 10.0),
        ]
        elements = [(0, 1, 2, 3)]
        constraints = {
            0: 0.0, 1: 0.0, 2: 0.0,
            4: 0.0, 5: 0.0,
            6: 0.0, 8: 0.0,
            10: 0.0, 11: 0.0,
        }
        contact_dof = 9  # node 3, x
        result = solve_tet4_with_rigid_stops(
            nodes,
            elements,
            young=210000.0,
            poisson=0.30,
            constraints=constraints,
            loads={contact_dof: 5000.0},
            contacts=[RigidStopContact(contact_dof, 0.001, 1.0e7)],
        )
        self.assertTrue(result.converged)
        self.assertTrue(result.active_contacts[0])
        self.assertGreater(result.contact_forces_n[0], 0.0)
        self.assertGreater(result.displacements[contact_dof], 0.001)
        self.assertLess(result.displacements[contact_dof] - 0.001, 0.001)
        free_residual = [
            abs(value)
            for dof, value in enumerate(result.residual)
            if dof not in constraints
        ]
        self.assertLess(max(free_residual), 1e-6)


if __name__ == "__main__":
    unittest.main()
