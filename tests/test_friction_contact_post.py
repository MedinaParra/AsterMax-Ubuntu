import math
import tempfile
import unittest
from pathlib import Path

from astermax.friction_contact_post import (
    FrictionContactPostError,
    friction_contact_nodal_fields,
    write_friction_contact_legacy_vtk,
)
from astermax.gmsh_ascii import SurfaceGroup, TetraMesh
from astermax.updated_surface_friction import (
    UpdatedSurfaceFrictionResult,
    UpdatedSurfaceFrictionState,
)


def _mesh():
    return TetraMesh(
        nodes=(
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.5, 0.5, 0.1),
        ),
        elements=((0, 1, 2, 3),),
        source_unit="mm",
        surface_groups=(SurfaceGroup("CONTACT_SLAVE", 1, ((0, 1, 2),)),),
    )


def _state(node, regime, *, fn, ft, limit, gap=-0.01, penetration=0.01, active=True):
    mag = math.sqrt(sum(v*v for v in ft))
    return UpdatedSurfaceFrictionState(
        slave_node=node,
        master_nodes=(0, 1, 2),
        signed_gap_mm=gap,
        penetration_mm=penetration,
        normal_force_n=fn,
        tangential_force_n=ft,
        tangential_force_magnitude_n=mag,
        friction_limit_n=limit,
        regime=regime,
        active=active,
        barycentric=(0.5, 0.25, 0.25),
        normal=(0.0, 0.0, 1.0),
        master_nodal_tangential_forces_n=((0.0, 0.0, 0.0),)*3,
    )


def _result(states):
    return UpdatedSurfaceFrictionResult(
        displacements=(0.0,)*12,
        reactions=(0.0,)*12,
        residual=(0.0,)*12,
        contact_states=tuple(states),
        unmatched_slave_nodes=(),
        iterations=3,
        converged=True,
        master_switch_count=0,
    )


class FrictionContactPostTests(unittest.TestCase):
    def test_pressure_traction_utilization_and_regime_oracle(self):
        # Slave TRI3 area = 2 mm^2, hence each nodal tributary area = 2/3 mm^2.
        # Node 0: Fn=200 N -> p=300 MPa. Ft=100 N -> tau=150 MPa.
        # Coulomb limit=200 N -> utilization=0.5 (STICK).
        # Node 1: Fn=100 N -> p=150 MPa. Ft=50 N -> tau=75 MPa.
        # Coulomb limit=50 N -> utilization=1.0 (SLIP).
        states = (
            _state(0, "STICK", fn=200.0, ft=(100.0, 0.0, 0.0), limit=200.0),
            _state(1, "SLIP", fn=100.0, ft=(50.0, 0.0, 0.0), limit=50.0),
            _state(2, "OPEN", fn=0.0, ft=(0.0, 0.0, 0.0), limit=0.0,
                   gap=0.2, penetration=0.0, active=False),
        )
        fields = friction_contact_nodal_fields(_mesh(), _result(states))
        self.assertAlmostEqual(fields["contact_tributary_area_mm2"][0], 2.0/3.0, places=12)
        self.assertAlmostEqual(fields["contact_pressure_MPa"][0], 300.0, places=12)
        self.assertAlmostEqual(fields["friction_traction_MPa"][0], 150.0, places=12)
        self.assertAlmostEqual(fields["friction_utilization"][0], 0.5, places=12)
        self.assertEqual(fields["friction_regime"][0], 1.0)
        self.assertAlmostEqual(fields["contact_pressure_MPa"][1], 150.0, places=12)
        self.assertAlmostEqual(fields["friction_traction_MPa"][1], 75.0, places=12)
        self.assertAlmostEqual(fields["friction_utilization"][1], 1.0, places=12)
        self.assertEqual(fields["friction_regime"][1], 2.0)
        self.assertEqual(fields["friction_regime"][2], 0.0)
        self.assertEqual(fields["friction_utilization"][2], 0.0)
        self.assertTrue(math.isnan(fields["contact_pressure_MPa"][3]))
        self.assertTrue(math.isnan(fields["friction_traction_MPa"][3]))

    def test_vtk_contains_professional_friction_fields(self):
        states = (
            _state(0, "STICK", fn=200.0, ft=(100.0, 0.0, 0.0), limit=200.0),
            _state(1, "SLIP", fn=100.0, ft=(50.0, 0.0, 0.0), limit=50.0),
            _state(2, "OPEN", fn=0.0, ft=(0.0, 0.0, 0.0), limit=0.0,
                   gap=0.2, penetration=0.0, active=False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_friction_contact_legacy_vtk(Path(tmp)/"contact.vtk", _mesh(), _result(states))
            text = path.read_text(encoding="utf-8")
        for token in (
            "VECTORS friction_force_N double",
            "SCALARS contact_pressure_MPa double 1",
            "SCALARS friction_traction_MPa double 1",
            "SCALARS friction_utilization double 1",
            "SCALARS friction_regime double 1",
        ):
            self.assertIn(token, text)

    def test_rejects_force_above_coulomb_limit(self):
        states = (
            _state(0, "STICK", fn=200.0, ft=(101.0, 0.0, 0.0), limit=100.0),
            _state(1, "OPEN", fn=0.0, ft=(0.0, 0.0, 0.0), limit=0.0, gap=0.2, penetration=0.0, active=False),
            _state(2, "OPEN", fn=0.0, ft=(0.0, 0.0, 0.0), limit=0.0, gap=0.2, penetration=0.0, active=False),
        )
        with self.assertRaises(FrictionContactPostError):
            friction_contact_nodal_fields(_mesh(), _result(states))

    def test_rejects_missing_slave_state(self):
        states = (
            _state(0, "STICK", fn=100.0, ft=(20.0, 0.0, 0.0), limit=50.0),
            _state(1, "OPEN", fn=0.0, ft=(0.0, 0.0, 0.0), limit=0.0, gap=0.2, penetration=0.0, active=False),
        )
        with self.assertRaises(FrictionContactPostError):
            friction_contact_nodal_fields(_mesh(), _result(states))


if __name__ == "__main__":
    unittest.main()
