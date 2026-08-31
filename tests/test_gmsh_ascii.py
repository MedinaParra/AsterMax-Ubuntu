import unittest

from astermax.gmsh_ascii import GmshImportError, parse_gmsh_v2_ascii


MESH = """$MeshFormat
2.2 0 8
$EndMeshFormat
$Nodes
5
10 0 0 0
20 10 0 0
30 0 10 0
40 0 0 10
99 99 99 99
$EndNodes
$Elements
3
1 2 2 1 1 10 20 30
2 4 2 1 1 10 20 30 40
3 1 2 1 1 10 20
$EndElements
"""

PHYSICAL_MESH = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
2
2 11 "FIXED"
2 12 "LOAD"
$EndPhysicalNames
$Nodes
4
10 0 0 0
20 10 0 0
30 0 10 0
40 0 0 10
$EndNodes
$Elements
3
1 2 2 11 1 10 20 30
2 2 2 12 2 20 30 40
3 4 2 20 3 10 20 30 40
$EndElements
"""


class TestGmshAscii(unittest.TestCase):
    def test_imports_first_order_tetrahedra_and_compacts_unused_nodes(self):
        mesh = parse_gmsh_v2_ascii(MESH, declared_unit="mm")
        self.assertEqual(mesh.source_unit, "mm")
        self.assertEqual(mesh.nodes, ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, 0.0, 10.0)))
        self.assertEqual(mesh.elements, ((0, 1, 2, 3),))

    def test_preserves_named_physical_surface_groups(self):
        mesh = parse_gmsh_v2_ascii(PHYSICAL_MESH, declared_unit="mm")
        self.assertEqual([group.name for group in mesh.surface_groups], ["FIXED", "LOAD"])
        self.assertEqual(mesh.surface_group("FIXED").triangles, ((0, 1, 2),))
        self.assertEqual(mesh.surface_group("FIXED").node_indices, (0, 1, 2))
        self.assertEqual(mesh.surface_group("LOAD").triangles, ((1, 2, 3),))

    def test_unknown_surface_group_is_rejected(self):
        mesh = parse_gmsh_v2_ascii(PHYSICAL_MESH, declared_unit="mm")
        with self.assertRaisesRegex(GmshImportError, "unknown physical surface"):
            mesh.surface_group("MISSING")

    def test_rejects_unresolved_non_mm_unit(self):
        with self.assertRaisesRegex(GmshImportError, "resolved to mm"):
            parse_gmsh_v2_ascii(MESH, declared_unit="m")

    def test_rejects_binary_mesh(self):
        binary_header = MESH.replace("2.2 0 8", "2.2 1 8")
        with self.assertRaisesRegex(GmshImportError, "v2 ASCII"):
            parse_gmsh_v2_ascii(binary_header, declared_unit="mm")

    def test_rejects_mesh_without_tet4(self):
        without_tet = MESH.replace("3\n1 2 2 1 1 10 20 30\n2 4 2 1 1 10 20 30 40\n3 1 2 1 1 10 20", "2\n1 2 2 1 1 10 20 30\n3 1 2 1 1 10 20")
        with self.assertRaisesRegex(GmshImportError, "no first-order tetrahedra"):
            parse_gmsh_v2_ascii(without_tet, declared_unit="mm")

    def test_rejects_unknown_node_reference(self):
        bad = MESH.replace("10 20 30 40", "10 20 30 777")
        with self.assertRaisesRegex(GmshImportError, "unknown node ids"):
            parse_gmsh_v2_ascii(bad, declared_unit="mm")


if __name__ == "__main__":
    unittest.main()
