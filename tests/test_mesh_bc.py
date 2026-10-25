import unittest

from astermax.gmsh_ascii import parse_gmsh_v2_ascii
from astermax.mesh_bc import (
    BoundaryPreparationError,
    fixed_surface_constraints,
    resultant_from_nodal_loads,
    surface_total_force_loads,
)


MESH = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
2
2 11 "FIXED"
2 12 "LOAD"
$EndPhysicalNames
$Nodes
4
1 0 0 0
2 10 0 0
3 0 10 0
4 0 0 10
$EndNodes
$Elements
3
1 2 2 11 1 1 2 3
2 2 2 12 2 2 3 4
3 4 2 20 3 1 2 3 4
$EndElements
"""


class TestMeshBoundaryConditions(unittest.TestCase):
    def setUp(self):
        self.mesh = parse_gmsh_v2_ascii(MESH, declared_unit="mm")

    def test_fixed_surface_maps_named_nodes_to_xyz_dofs(self):
        constraints = fixed_surface_constraints(self.mesh, "FIXED")
        self.assertEqual(set(constraints), set(range(9)))
        self.assertTrue(all(value == 0.0 for value in constraints.values()))

    def test_partial_constraint_components_are_supported(self):
        constraints = fixed_surface_constraints(self.mesh, "FIXED", components=(0, 2))
        self.assertEqual(set(constraints), {0, 2, 3, 5, 6, 8})

    def test_surface_force_preserves_requested_resultant(self):
        requested = (1200.0, -500.0, 250.0)
        loads = surface_total_force_loads(self.mesh, "LOAD", requested)
        recovered = resultant_from_nodal_loads(loads)
        for actual, expected in zip(recovered, requested):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_single_triangle_uniform_traction_gives_equal_vertex_weights(self):
        loads = surface_total_force_loads(self.mesh, "LOAD", (0.0, 0.0, 900.0))
        z_loads = {dof: value for dof, value in loads.items() if dof % 3 == 2}
        self.assertEqual(len(z_loads), 3)
        for value in z_loads.values():
            self.assertAlmostEqual(value, 300.0, places=12)

    def test_invalid_component_selection_is_rejected(self):
        with self.assertRaisesRegex(BoundaryPreparationError, "subset"):
            fixed_surface_constraints(self.mesh, "FIXED", components=(3,))

    def test_force_vector_must_be_xyz(self):
        with self.assertRaisesRegex(BoundaryPreparationError, "Fx, Fy, Fz"):
            surface_total_force_loads(self.mesh, "LOAD", (100.0, 0.0))


if __name__ == "__main__":
    unittest.main()
