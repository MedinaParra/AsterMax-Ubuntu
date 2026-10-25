import unittest

from astermax.windows_cae_workspace import PreviewError, _parse_msh2_surface


MESH = """$MeshFormat
2.2 0 8
$EndMeshFormat
$Nodes
4
10 0 0 0
20 1 0 0
30 0 1 0
40 0 0 1
$EndNodes
$Elements
3
1 2 2 7 11 10 20 30
2 2 0 10 30 40
3 1 0 10 20
$EndElements
"""


class WindowsCaeWorkspacePreviewTests(unittest.TestCase):
    def test_surface_preview_compacts_nonconsecutive_ids_and_keeps_tri3(self):
        mesh = _parse_msh2_surface(MESH)
        self.assertEqual(mesh.nodes, ((0.0,0.0,0.0),(1.0,0.0,0.0),(0.0,1.0,0.0),(0.0,0.0,1.0)))
        self.assertEqual(mesh.triangles, ((0,1,2),(0,2,3)))

    def test_missing_triangles_fails_closed(self):
        text = MESH.replace("1 2 2 7 11 10 20 30", "1 1 0 10 20").replace("2 2 0 10 30 40", "2 1 0 20 30")
        with self.assertRaises(PreviewError):
            _parse_msh2_surface(text)

    def test_missing_node_reference_fails_closed(self):
        text = MESH.replace("10 20 30", "10 20 99")
        with self.assertRaises(PreviewError):
            _parse_msh2_surface(text)

    def test_invalid_msh_fails_closed(self):
        with self.assertRaises(PreviewError):
            _parse_msh2_surface("not a gmsh mesh")


if __name__ == "__main__":
    unittest.main()
