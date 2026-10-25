import math
import tempfile
import unittest
from pathlib import Path

from astermax.bolt_pretension import BoltPretensionConnector
from astermax.gapped_joint_vtk import (
    GappedJointVTKError,
    gapped_joint_nodal_fields,
    write_gapped_joint_legacy_vtk,
)
from astermax.gapped_preloaded_joint import solve_gapped_preloaded_joint_from_stiffness
from astermax.gmsh_ascii import SurfaceGroup, TetraMesh


class GappedJointVTKHarness(unittest.TestCase):
    def setUp(self):
        # Fixed master TRI3 plus a non-degenerate three-node slave patch.
        # Normal mechanics are identical to the independent multi-GAP oracle.
        self.nodes = (
            (0.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (0.0, 3.0, 0.0),
            (0.5, 0.5, 0.0),
            (1.0, 0.5, 0.0),
            (0.5, 1.0, 0.0),
        )
        self.mesh = TetraMesh(
            nodes=self.nodes,
            elements=((0, 1, 2, 3), (0, 1, 2, 4), (0, 1, 2, 5)),
            source_unit="mm",
            surface_groups=(SurfaceGroup("CONTACT_SLAVE", 10, ((3, 4, 5),)),),
        )
        ndof = 18
        self.k = [[0.0] * ndof for _ in range(ndof)]
        for i in range(ndof):
            self.k[i][i] = 1.0
        z = (11, 14, 17)
        block = (
            (1500.0, -500.0, 0.0),
            (-500.0, 2000.0, -500.0),
            (0.0, -500.0, 1500.0),
        )
        for a in range(3):
            for b in range(3):
                self.k[z[a]][z[b]] = block[a][b]
        self.constraints = {i: 0.0 for i in range(9)}
        for node in (3, 4, 5):
            self.constraints[3 * node] = 0.0
            self.constraints[3 * node + 1] = 0.0
        self.connectors = tuple(
            BoltPretensionConnector(
                node_a=0,
                node_b=node,
                direction=(0.0, 0.0, 1.0),
                axial_stiffness_n_per_mm=4000.0,
                preload_n=1000.0,
            )
            for node in (3, 4, 5)
        )
        self.result = solve_gapped_preloaded_joint_from_stiffness(
            self.nodes,
            self.k,
            self.constraints,
            {},
            self.connectors,
            gap_by_slave_mm={3: 0.1, 4: 0.2, 5: 0.4},
            slave_nodes=(3, 4, 5),
            master_triangles=((0, 1, 2),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=5000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
            search_distance_mm=1.0,
            max_iterations=100,
        )

    def test_fields_preserve_verified_partial_opening_and_bolt_redistribution(self):
        fields = gapped_joint_nodal_fields(self.mesh, self.connectors, self.result)
        expected_final_gap = (-0.052189781021898, 0.004014598540146, 0.200364963503650)
        expected_bolt = (391.240875912409, 216.058394160584, 201.459854014599)

        self.assertEqual(fields["initial_gap_mm"][3:6], (0.1, 0.2, 0.4))
        for actual, expected in zip(fields["final_gap_mm"][3:6], expected_final_gap):
            self.assertAlmostEqual(actual, expected, places=8)
        self.assertEqual(fields["support_state"][3:6], (1.0, 0.0, 0.0))
        for actual, expected in zip(fields["bolt_axial_force_N"][3:6], expected_bolt):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertAlmostEqual(sum(fields["bolt_load_share"][3:6]), 1.0, places=12)

        # Visualization pressure must be derived from the same verified contact force.
        # Slave patch area=0.125 mm^2 => tributary area=1/24 mm^2 at each node.
        self.assertAlmostEqual(fields["contact_tributary_area_mm2"][3], 1.0 / 24.0, places=12)
        self.assertAlmostEqual(
            fields["contact_pressure_MPa"][3],
            260.948905109489 / (1.0 / 24.0),
            places=5,
        )
        self.assertAlmostEqual(fields["contact_normal_force_N"][4], 0.0, places=12)
        self.assertAlmostEqual(fields["contact_normal_force_N"][5], 0.0, places=12)
        self.assertTrue(math.isnan(fields["initial_gap_mm"][0]))
        self.assertTrue(math.isnan(fields["bolt_axial_force_N"][1]))

    def test_vtk_contains_professional_traceable_field_names_and_source_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_gapped_joint_legacy_vtk(
                Path(folder) / "joint.vtk", self.mesh, self.connectors, self.result
            )
            text = path.read_text(encoding="utf-8")
        for token in (
            "SCALARS initial_gap_mm double 1",
            "SCALARS final_gap_mm double 1",
            "SCALARS support_state double 1",
            "SCALARS bolt_axial_force_N double 1",
            "SCALARS bolt_load_share double 1",
            "SCALARS contact_pressure_MPa double 1",
            "SCALARS friction_utilization double 1",
            "VECTORS displacement_mm double",
        ):
            self.assertIn(token, text)
        # VTK points are nominal/source CAD coordinates, not GAP-shifted analysis nodes.
        self.assertIn("0.5 0.5 0", text)
        self.assertNotIn("0.5 0.5 0.10000000000000001", text)

    def test_mismatched_visualization_mesh_fails_closed(self):
        wrong = TetraMesh(
            nodes=self.nodes[:-1] + ((0.5, 1.0, 0.01),),
            elements=self.mesh.elements,
            source_unit="mm",
            surface_groups=self.mesh.surface_groups,
        )
        with self.assertRaises(GappedJointVTKError):
            gapped_joint_nodal_fields(wrong, self.connectors, self.result)


if __name__ == "__main__":
    unittest.main()
