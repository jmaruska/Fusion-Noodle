"""Polygon orientation: a flat side faces +X, so polygons tile the arrays they're used with."""
import math
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.nodes.geometry_polygon import polygon_corners, corner_distance  # noqa: E402


def edge_midpoints(corners):
    n = len(corners)
    return [((corners[i][0] + corners[(i + 1) % n][0]) / 2, (corners[i][1] + corners[(i + 1) % n][1]) / 2)
            for i in range(n)]


class PolygonCornerTests(unittest.TestCase):
    def test_a_flat_side_faces_plus_x(self):
        for sides in range(3, 11):
            with self.subTest(sides=sides):
                mids = edge_midpoints(polygon_corners(sides, 1.0))
                self.assertTrue(any(abs(y) < 1e-9 and x > 0 for x, y in mids), 'a side is centred on +X')

    def test_hexagons_tile_the_hexagonal_grid(self):
        """The 2D Grid's Hexagonal layout puts neighbours Spacing X apart along X, and the next
        row at ±60°. Hexagons spaced their Size (across flats) apart meet edge to edge there."""
        size = 2.0
        corners = polygon_corners(6, size)
        across_flats = size
        for angle in (0, 60, 120, 180, 240, 300):
            direction = (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
            reach = max(x * direction[0] + y * direction[1] for x, y in corners)
            with self.subTest(neighbour_at=angle):
                self.assertAlmostEqual(reach, across_flats / 2, places=9, msg='a flat side faces each neighbour')

    def test_a_square_is_axis_aligned(self):
        xs = sorted({round(x, 9) for x, _ in polygon_corners(4, 2.0)})
        self.assertEqual(xs, [-1.0, 1.0])

    def test_size_across_flats_is_twice_the_distance_to_each_side(self):
        for sides in range(3, 11):
            with self.subTest(sides=sides):
                for d in (math.hypot(x, y) for x, y in edge_midpoints(polygon_corners(sides, 10.0))):
                    self.assertAlmostEqual(d, 5.0, places=9)

    def test_size_across_corners_and_side_length(self):
        for sides in range(3, 11):
            with self.subTest(sides=sides):
                self.assertAlmostEqual(corner_distance(sides, 10.0, 'across_corners'), 5.0)
                corners = polygon_corners(sides, 3.0, 'side')
                side = math.dist(corners[0], corners[1])
                self.assertAlmostEqual(side, 3.0, places=9)


if __name__ == '__main__':
    unittest.main()


class HexSpacingTests(unittest.TestCase):
    """The 2D Grid's Hexagonal layout: whichever spacing is connected drives (X if both)."""

    def test_the_driving_spacing(self):
        from backend.nodes.array_2d_grid import hex_column_spacing, HEX_ROW
        self.assertEqual(hex_column_spacing('hexagonal', 3.0, 9.0, set()), 3.0, 'typed: X (the palette keeps Y in step)')
        self.assertEqual(hex_column_spacing('hexagonal', 3.0, 9.0, {'spacing_x'}), 3.0)
        self.assertAlmostEqual(hex_column_spacing('hexagonal', 3.0, 4.0, {'spacing_y'}), 4.0 / HEX_ROW)
        self.assertEqual(hex_column_spacing('hexagonal', 3.0, 4.0, {'spacing_x', 'spacing_y'}), 3.0)
        self.assertEqual(hex_column_spacing('grid', 3.0, 4.0, {'spacing_y'}), 3.0, 'other layouts use both as given')
