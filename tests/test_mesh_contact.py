import math
from pathlib import Path
import tempfile
import unittest

from astermax.geometric_contact import GeometricContactResult, NodePlaneState
from astermax.gmsh_ascii import SurfaceGroup, TetraMesh
from astermax.mesh_contact import (
    ContactPreparationError,
    contact_nodal_fields,
    surface_to_rigid_plane_contacts,
    write_contact_legacy_vtk,
)


class MeshContactPreparationTests(unittest.TestCase):
    def setUp(self):
        self.mesh = TetraMesh(
            nodes=(
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            elements=((0, 1, 2, 3),),
            source_unit="mm",
            surface_groups=(
                SurfaceGroup("CONTACT_SLAVE", 7, ((0, 1, 2),)),
            ),
        )

    def test_named_surface_maps_unique_nodes_to_geometric_contacts(self):
        contacts = surface_to_rigid_plane_contacts(
            self.mesh,
            "CONTACT_SLAVE",
            plane_point_mm=(0.0, 0.0, 0.1),
            normal=(0.0, 0.0, 2.0),
            penalty_stiffness_n_per_mm=50000.0,
        )
        self.assertEqual(tuple(contact.node for contact in contacts), (0, 1, 2))
        self.assertTrue(all(contact.plane_point_mm == (0.0, 0.0, 0.1) for contact in contacts))
        self.assertTrue(all(contact.penalty_stiffness_n_per_mm == 50000.0 for contact in contacts))

    def test_unknown_surface_and_invalid_contact_data_are_rejected(self):
        with self.assertRaises(ContactPreparationError):
            surface_to_rigid_plane_contacts(
                self.mesh, "MISSING", plane_point_mm=(0, 0, 0), normal=(0, 0, 1),
                penalty_stiffness_n_per_mm=1.0,
            )
        with self.assertRaises(ContactPreparationError):
            surface_to_rigid_plane_contacts(
                self.mesh, "CONTACT_SLAVE", plane_point_mm=(0, 0, 0), normal=(0, 0, 0),
                penalty_stiffness_n_per_mm=1.0,
            )
        with self.assertRaises(ContactPreparationError):
            surface_to_rigid_plane_contacts(
                self.mesh, "CONTACT_SLAVE", plane_point_mm=(0, 0, 0), normal=(0, 0, 1),
                penalty_stiffness_n_per_mm=0.0,
            )

    def test_contact_states_expand_to_dense_nodal_fields(self):
        result = GeometricContactResult(
            displacements=(0.0,) * 12,
            reactions=(0.0,) * 12,
            residual=(0.0,) * 12,
            contacts=(
                NodePlaneState(0, -0.02, 0.02, 1000.0, True, (0.0, 0.0, 1000.0)),
                NodePlaneState(2, 0.15, 0.0, 0.0, False, (0.0, 0.0, 0.0)),
            ),
            iterations=2,
            converged=True,
        )
        fields = contact_nodal_fields(4, result)
        self.assertAlmostEqual(fields["contact_gap_mm"][0], -0.02)
        self.assertAlmostEqual(fields["contact_penetration_mm"][0], 0.02)
        self.assertAlmostEqual(fields["contact_normal_force_N"][0], 1000.0)
        self.assertEqual(fields["contact_active"][0], 1.0)
        self.assertEqual(fields["contact_force_N"][0], (0.0, 0.0, 1000.0))
        self.assertTrue(math.isnan(fields["contact_gap_mm"][1]))
        self.assertEqual(fields["contact_active"][2], 0.0)

    def test_contact_vtk_contains_explicit_visualization_fields(self):
        result = GeometricContactResult(
            displacements=(0.0, 0.0, 0.01) + (0.0,) * 9,
            reactions=(0.0,) * 12,
            residual=(0.0,) * 12,
            contacts=(
                NodePlaneState(0, -0.01, 0.01, 500.0, True, (0.0, 0.0, 500.0)),
            ),
            iterations=1,
            converged=True,
        )
        with tempfile.TemporaryDirectory(prefix="astermax-contact-vtk-") as temporary:
            path = write_contact_legacy_vtk(Path(temporary) / "contact.vtk", self.mesh, result)
            vtk = path.read_text(encoding="utf-8")
        self.assertIn("DATASET UNSTRUCTURED_GRID", vtk)
        self.assertIn("VECTORS displacement_mm double", vtk)
        self.assertIn("VECTORS contact_force_N double", vtk)
        self.assertIn("SCALARS contact_gap_mm double 1", vtk)
        self.assertIn("SCALARS contact_penetration_mm double 1", vtk)
        self.assertIn("SCALARS contact_normal_force_N double 1", vtk)
        self.assertIn("SCALARS contact_active double 1", vtk)


if __name__ == "__main__":
    unittest.main()
