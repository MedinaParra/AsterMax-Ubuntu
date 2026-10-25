import math
import unittest

from astermax.feature_surface import (
    CylindricalSurfaceIntent,
    FeatureSurfaceError,
    apply_feature_surfaces,
    resolve_cylindrical_surface,
)
from astermax.gmsh_ascii import SurfaceGroup, TetraMesh


def make_cylindrical_boundary(segments: int, length: float, radius: float = 1.0) -> TetraMesh:
    """Create a closed triangulated cylinder boundary plus dummy TET4 connectivity.

    The side triangles are mixed with end-cap triangles inside ALL_BOUNDARY.  The
    feature selector must recover only the cylindrical side, independent of segment
    count and axial length.
    """
    nodes = []
    for x in (0.0, float(length)):
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            nodes.append((x, radius * math.cos(theta), radius * math.sin(theta)))
    nodes.extend(((0.0, 0.0, 0.0), (float(length), 0.0, 0.0)))
    c0 = 2 * segments
    c1 = 2 * segments + 1

    tris = []
    for i in range(segments):
        j = (i + 1) % segments
        a, b = i, j
        c, d = segments + i, segments + j
        tris.append((a, c, d))
        tris.append((a, d, b))
        tris.append((c0, b, a))
        tris.append((c1, c, d))

    # TetraMesh requires only data shape here; feature selection reads the boundary.
    # Use one nondegenerate placeholder TET4 from existing nodes.
    elements = ((0, 1, segments, c0),)
    return TetraMesh(
        nodes=tuple(nodes),
        elements=elements,
        source_unit="mm",
        surface_groups=(SurfaceGroup("ALL_BOUNDARY", 1, tuple(tris)),),
    )


class FeatureSurfaceHarness(unittest.TestCase):
    def test_cylindrical_feature_survives_remesh_and_length_change(self):
        coarse = make_cylindrical_boundary(segments=12, length=10.0)
        fine = make_cylindrical_boundary(segments=36, length=12.5)
        intent = CylindricalSurfaceIntent(
            name="BOLT_HOLE",
            axis="x",
            center_fraction=(0.5, 0.5),
            radius_mm=1.0,
            radial_tolerance_fraction=0.08,
            maximum_axis_normal_component=0.10,
        )
        a = resolve_cylindrical_surface(coarse, intent)
        b = resolve_cylindrical_surface(fine, intent)

        self.assertEqual(a.selected_triangle_count, 24)
        self.assertEqual(b.selected_triangle_count, 72)
        self.assertAlmostEqual(a.center_mm[0], 0.0, places=12)
        self.assertAlmostEqual(a.center_mm[1], 0.0, places=12)
        self.assertAlmostEqual(b.center_mm[0], 0.0, places=12)
        self.assertAlmostEqual(b.center_mm[1], 0.0, places=12)
        self.assertAlmostEqual(a.resolved_radius_mm, 1.0, places=12)
        self.assertAlmostEqual(b.resolved_radius_mm, 1.0, places=12)

        # Analytical lateral area = 2*pi*r*L. Triangulated polygon converges toward it.
        exact_a = 2.0 * math.pi * 1.0 * 10.0
        exact_b = 2.0 * math.pi * 1.0 * 12.5
        self.assertLess(abs(a.selected_area_mm2 - exact_a) / exact_a, 0.02)
        self.assertLess(abs(b.selected_area_mm2 - exact_b) / exact_b, 0.003)
        self.assertLess(a.max_centroid_radius_error_mm, 0.08)
        self.assertLess(b.max_centroid_radius_error_mm, 0.08)

        # End caps are present in ALL_BOUNDARY but excluded by the normal signature.
        self.assertEqual(len(coarse.surface_group("ALL_BOUNDARY").triangles), 48)
        self.assertEqual(len(fine.surface_group("ALL_BOUNDARY").triangles), 144)

    def test_normalized_radius_tracks_scaled_feature(self):
        mesh = make_cylindrical_boundary(segments=24, length=8.0, radius=2.0)
        # Transverse bbox span is 4 mm; radius_fraction 0.5 resolves 2 mm.
        intent = CylindricalSurfaceIntent(
            name="CYL_INTERFACE",
            axis="x",
            radius_fraction=0.5,
            radial_tolerance_fraction=0.05,
            maximum_axis_normal_component=0.10,
        )
        result = resolve_cylindrical_surface(mesh, intent)
        self.assertAlmostEqual(result.resolved_radius_mm, 2.0, places=12)
        self.assertEqual(result.selected_triangle_count, 48)

    def test_feature_groups_are_added_without_erasing_boundary_evidence(self):
        mesh = make_cylindrical_boundary(segments=16, length=5.0)
        updated, resolutions = apply_feature_surfaces(
            mesh,
            (CylindricalSurfaceIntent(name="CONTACT_MASTER", axis="x", radius_mm=1.0,
                                      radial_tolerance_fraction=0.08,
                                      maximum_axis_normal_component=0.10),),
        )
        self.assertEqual(updated.surface_group("ALL_BOUNDARY"), mesh.surface_group("ALL_BOUNDARY"))
        self.assertGreater(len(updated.surface_group("CONTACT_MASTER").triangles), 0)
        self.assertEqual(resolutions[0].group.name, "CONTACT_MASTER")

    def test_invalid_or_unmatched_feature_fails_closed(self):
        mesh = make_cylindrical_boundary(segments=16, length=5.0)
        with self.assertRaises(FeatureSurfaceError):
            resolve_cylindrical_surface(
                mesh,
                CylindricalSurfaceIntent(name="MISSING", axis="x", radius_mm=4.0,
                                         radial_tolerance_fraction=0.02),
            )
        with self.assertRaises(FeatureSurfaceError):
            CylindricalSurfaceIntent(name="BAD", axis="q", radius_mm=1.0)
        with self.assertRaises(FeatureSurfaceError):
            CylindricalSurfaceIntent(name="BAD", axis="x", radius_mm=1.0, radius_fraction=0.5)


if __name__ == "__main__":
    unittest.main()
