import math
import tempfile
import unittest
from pathlib import Path

from astermax.gmsh_ascii import SurfaceGroup, TetraMesh
from astermax.global_surface_contact import GlobalSurfaceContactResult, SurfaceContactState
from astermax.surface_contact_post import (
    SurfaceContactPostError,
    slave_tributary_area_mm2,
    surface_contact_nodal_fields,
    write_surface_contact_legacy_vtk,
)


class SurfaceContactPostTests(unittest.TestCase):
    def _mesh(self):
        nodes = (
            (0.0, 0.0, 0.1),
            (2.0, 0.0, 0.1),
            (0.0, 2.0, 0.1),
            (0.0, 0.0, 1.0),
        )
        return TetraMesh(
            nodes=nodes,
            elements=((0, 1, 2, 3),),
            source_unit="mm",
            surface_groups=(SurfaceGroup("CONTACT_SLAVE", 10, ((0, 1, 2),)),),
        )

    def _state(self, node, force, active=True, gap=-0.01):
        return SurfaceContactState(
            slave_node=node,
            master_nodes=(0, 1, 2),
            reference_gap_mm=0.1,
            signed_gap_mm=gap,
            penetration_mm=max(0.0, -gap) if active else 0.0,
            normal_force_n=force,
            active=active,
            barycentric=(1.0, 0.0, 0.0),
            normal=(0.0, 0.0, 1.0),
            slave_force_n=(0.0, 0.0, force),
            master_nodal_forces_n=((0.0, 0.0, -force), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        )

    def _result(self):
        states = (
            self._state(0, 200.0),
            self._state(1, 100.0),
            self._state(2, 0.0, active=False, gap=0.02),
        )
        return GlobalSurfaceContactResult(
            displacements=(0.0,) * 12,
            reactions=(0.0,) * 12,
            residual=(0.0,) * 12,
            contact_states=states,
            iterations=2,
            converged=True,
        )

    def test_tributary_area_is_triangle_area_over_three(self):
        areas = slave_tributary_area_mm2(self._mesh())
        # Right triangle with legs 2 mm has area 2 mm^2.
        for node in (0, 1, 2):
            self.assertAlmostEqual(areas[node], 2.0 / 3.0, places=12)
        self.assertEqual(areas[3], 0.0)

    def test_pressure_is_force_over_tributary_area_in_mpa(self):
        fields = surface_contact_nodal_fields(self._mesh(), self._result())
        self.assertAlmostEqual(fields["contact_pressure_MPa"][0], 300.0, places=12)
        self.assertAlmostEqual(fields["contact_pressure_MPa"][1], 150.0, places=12)
        self.assertEqual(fields["contact_pressure_MPa"][2], 0.0)
        self.assertTrue(math.isnan(fields["contact_pressure_MPa"][3]))
        self.assertAlmostEqual(fields["contact_tributary_area_mm2"][0], 2.0 / 3.0, places=12)

    def test_missing_slave_state_is_fail_closed(self):
        result = self._result()
        incomplete = GlobalSurfaceContactResult(
            result.displacements,
            result.reactions,
            result.residual,
            result.contact_states[:2],
            result.iterations,
            result.converged,
        )
        with self.assertRaisesRegex(SurfaceContactPostError, "missing slave nodes"):
            surface_contact_nodal_fields(self._mesh(), incomplete)

    def test_duplicate_slave_state_is_rejected(self):
        result = self._result()
        duplicate = GlobalSurfaceContactResult(
            result.displacements,
            result.reactions,
            result.residual,
            result.contact_states + (result.contact_states[0],),
            result.iterations,
            result.converged,
        )
        with self.assertRaisesRegex(SurfaceContactPostError, "duplicate contact state"):
            surface_contact_nodal_fields(self._mesh(), duplicate)

    def test_degenerate_slave_triangle_is_rejected(self):
        mesh = self._mesh()
        bad_nodes = (mesh.nodes[0], mesh.nodes[0], mesh.nodes[2], mesh.nodes[3])
        bad = TetraMesh(bad_nodes, mesh.elements, "mm", mesh.surface_groups)
        with self.assertRaisesRegex(SurfaceContactPostError, "degenerate TRI3"):
            slave_tributary_area_mm2(bad)

    def test_vtk_contains_gap_pressure_force_and_displacement_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_surface_contact_legacy_vtk(
                Path(directory) / "surface-contact.vtk", self._mesh(), self._result()
            )
            text = path.read_text(encoding="utf-8")
        self.assertIn("VECTORS displacement_mm double", text)
        self.assertIn("VECTORS contact_force_N double", text)
        self.assertIn("SCALARS contact_gap_mm double 1", text)
        self.assertIn("SCALARS contact_pressure_MPa double 1", text)
        self.assertIn("SCALARS contact_tributary_area_mm2 double 1", text)
        self.assertIn("SCALARS contact_active double 1", text)


if __name__ == "__main__":
    unittest.main()
