import math
import unittest

from astermax.contact_diagnostics import (
    ContactAcceptanceCriteria,
    ContactDiagnosticsError,
    diagnose_updated_surface_contact,
)
from astermax.updated_surface_contact import (
    UpdatedSurfaceContactResult,
    UpdatedSurfaceContactState,
)


def _state(slave, penetration, force, active=True):
    return UpdatedSurfaceContactState(
        slave_node=slave,
        master_nodes=(3, 4, 5),
        signed_gap_mm=-penetration if active else 0.2,
        penetration_mm=penetration if active else 0.0,
        normal_force_n=force if active else 0.0,
        active=active,
        barycentric=(0.5, 0.25, 0.25),
        normal=(0.0, 0.0, 1.0),
        slave_force_n=(0.0, 0.0, force if active else 0.0),
        master_nodal_forces_n=(
            (0.0, 0.0, -0.5 * force),
            (0.0, 0.0, -0.25 * force),
            (0.0, 0.0, -0.25 * force),
        ),
    )


def _result(*, converged=True, unmatched=(), switches=1, residual=None, states=None):
    if residual is None:
        residual = (50.0, -20.0, 5e-7, 0.0, 0.0, -4e-7)
    if states is None:
        states = (
            _state(0, 0.01, 500.0),
            _state(1, 0.02, 1000.0),
            _state(2, 0.0, 0.0, False),
        )
    return UpdatedSurfaceContactResult(
        displacements=(0.0,) * len(residual),
        reactions=(0.0,) * len(residual),
        residual=tuple(residual),
        contact_states=tuple(states),
        unmatched_slave_nodes=tuple(unmatched),
        iterations=4,
        converged=converged,
        master_switch_count=switches,
    )


class ContactDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_accepts_result_with_explicit_limits(self):
        d = diagnose_updated_surface_contact(
            _result(),
            constraints={0: 0.0, 1: 0.0},
            criteria=ContactAcceptanceCriteria(
                max_penetration_mm=0.025,
                max_free_residual_n=1e-6,
                max_unmatched_fraction=0.0,
                max_master_switches=2,
            ),
        )
        self.assertTrue(d.accepted)
        self.assertEqual(d.reasons, ())
        self.assertEqual(d.slave_count, 3)
        self.assertEqual(d.active_contact_count, 2)
        self.assertAlmostEqual(d.max_penetration_mm, 0.02)
        self.assertAlmostEqual(d.mean_active_penetration_mm, 0.015)
        self.assertAlmostEqual(d.total_normal_force_n, 1500.0)
        self.assertAlmostEqual(d.max_normal_force_n, 1000.0)
        self.assertAlmostEqual(d.max_free_residual_n, 5e-7)
        self.assertAlmostEqual(d.residual_l2_n, math.sqrt((5e-7) ** 2 + (4e-7) ** 2))
        self.assertEqual(d.master_switch_count, 1)
        self.assertEqual(d.iterations, 4)

    def test_diagnostics_rejects_each_engineering_failure_mode(self):
        d = diagnose_updated_surface_contact(
            _result(
                converged=False,
                unmatched=(3,),
                switches=4,
                residual=(0.0, 0.0, 2e-3, 0.0, 0.0, 0.0),
            ),
            constraints={0: 0.0, 1: 0.0},
            criteria=ContactAcceptanceCriteria(
                max_penetration_mm=0.015,
                max_free_residual_n=1e-4,
                max_unmatched_fraction=0.0,
                max_master_switches=2,
            ),
        )
        self.assertFalse(d.accepted)
        self.assertEqual(
            set(d.reasons),
            {
                "solver_not_converged",
                "penetration_limit_exceeded",
                "free_residual_limit_exceeded",
                "unmatched_slave_limit_exceeded",
                "master_switch_limit_exceeded",
            },
        )
        self.assertEqual(d.slave_count, 4)
        self.assertAlmostEqual(d.unmatched_fraction, 0.25)

    def test_constraints_are_excluded_from_free_residual_gate(self):
        d = diagnose_updated_surface_contact(
            _result(residual=(9999.0, -9999.0, 1e-9, 0.0, 0.0, 0.0)),
            constraints=(0, 1),
            criteria=ContactAcceptanceCriteria(0.1, 1e-6),
        )
        self.assertTrue(d.accepted)
        self.assertAlmostEqual(d.max_free_residual_n, 1e-9)

    def test_unmatched_fraction_can_be_explicitly_allowed_for_diagnostics(self):
        d = diagnose_updated_surface_contact(
            _result(unmatched=(3,)),
            constraints={0: 0.0, 1: 0.0},
            criteria=ContactAcceptanceCriteria(0.1, 1e-6, max_unmatched_fraction=0.25),
        )
        self.assertTrue(d.accepted)
        self.assertEqual(d.unmatched_slave_count, 1)
        self.assertEqual(d.slave_count, 4)

    def test_invalid_acceptance_criteria_fail_closed(self):
        invalid = (
            ContactAcceptanceCriteria(-1.0, 1.0),
            ContactAcceptanceCriteria(1.0, -1.0),
            ContactAcceptanceCriteria(1.0, 1.0, max_unmatched_fraction=-0.1),
            ContactAcceptanceCriteria(1.0, 1.0, max_unmatched_fraction=1.1),
            ContactAcceptanceCriteria(1.0, 1.0, max_master_switches=-1),
        )
        for criteria in invalid:
            with self.subTest(criteria=criteria):
                with self.assertRaises(ContactDiagnosticsError):
                    diagnose_updated_surface_contact(_result(), {0: 0.0}, criteria)

    def test_nonfinite_residual_is_rejected(self):
        with self.assertRaises(ContactDiagnosticsError):
            diagnose_updated_surface_contact(
                _result(residual=(0.0, 0.0, float("nan"), 0.0, 0.0, 0.0)),
                {0: 0.0},
                ContactAcceptanceCriteria(0.1, 1e-6),
            )


if __name__ == "__main__":
    unittest.main()
