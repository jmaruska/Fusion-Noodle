"""Edge Margin is a distance in cm, turned into surface parameters by measuring."""
import math
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.utilities.surface_utils import margin_in_parameters  # noqa: E402


class MarginInParametersTests(unittest.TestCase):

    def test_a_stretched_flat_surface_gets_the_same_margin_in_cm_both_ways(self):
        # U from 0 to 1 spans 20 cm, V from 0 to 2 spans 10 cm
        point_at = lambda u, v: (u * 20.0, v * 5.0, 0.0)
        du, dv = margin_in_parameters(2.0, point_at, (0.0, 1.0), (0.0, 2.0))
        self.assertAlmostEqual(du, 0.1)   # 2 cm of 20 cm
        self.assertAlmostEqual(dv, 0.4)   # 2 cm of 10 cm, in a range of 2

    def test_a_curved_surface_is_measured_along_the_surface(self):
        # Half a cylinder of radius 10: U goes around (arc length 10 * pi), V along 30 cm
        point_at = lambda u, v: (10 * math.cos(u), 10 * math.sin(u), v)
        du, _ = margin_in_parameters(1.0, point_at, (0.0, math.pi), (0.0, 30.0), samples=200)
        self.assertAlmostEqual(du, 0.1, places=3)  # 1 cm is 0.1 radians at radius 10

    def test_no_margin_or_an_unmeasurable_surface_gives_none(self):
        self.assertEqual(margin_in_parameters(0.0, lambda u, v: (u, v, 0), (0, 1), (0, 1)), (0.0, 0.0))
        self.assertEqual(margin_in_parameters(1.0, lambda u, v: None, (0, 1), (0, 1)), (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
