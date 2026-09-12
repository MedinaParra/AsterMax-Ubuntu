import math
import unittest

from astermax.viewport_selection import parse_force_command, pick_triangle, project_nodes


class ViewportSelectionTests(unittest.TestCase):
    def setUp(self):
        self.nodes = ((-1.0,-1.0,0.0),(1.0,-1.0,0.0),(1.0,1.0,0.0),(-1.0,1.0,0.0))
        self.triangles = ((0,1,2),(0,2,3))

    def test_center_pick_is_deterministic(self):
        screen = project_nodes(self.nodes, width=800, height=600, yaw=0.0, pitch=0.0, zoom=1.0)
        pick = pick_triangle(self.nodes, self.triangles, x=400, y=300, width=800, height=600, yaw=0.0, pitch=0.0, zoom=1.0)
        self.assertIsNotNone(pick)
        self.assertEqual(pick.triangle_index, 0)
        self.assertAlmostEqual(sum(v*v for v in pick.unit_normal), 1.0, places=12)
        self.assertEqual(len(screen), 4)

    def test_outside_pick_returns_none(self):
        pick = pick_triangle(self.nodes, self.triangles, x=5, y=5, width=800, height=600, yaw=0.0, pitch=0.0, zoom=1.0)
        self.assertIsNone(pick)

    def test_invalid_connectivity_fails_closed(self):
        with self.assertRaises(ValueError):
            pick_triangle(self.nodes, ((0,1,99),), x=400, y=300, width=800, height=600, yaw=0.0, pitch=0.0, zoom=1.0)

    def test_parse_kn_negative_z(self):
        cmd = parse_force_command('aplica 25 kN aqui en -Z')
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.vector_n, (0.0, 0.0, -25000.0))

    def test_parse_decimal_comma_n_positive_x(self):
        cmd = parse_force_command('poner 1250,5 N en +x')
        self.assertIsNotNone(cmd)
        self.assertAlmostEqual(cmd.vector_n[0], 1250.5)

    def test_force_command_requires_axis_and_unit(self):
        self.assertIsNone(parse_force_command('aplica fuerza aqui'))
        self.assertIsNone(parse_force_command('aplica 25 kN aqui'))
        self.assertIsNone(parse_force_command('aplica 0 N en z'))


if __name__ == '__main__':
    unittest.main()
