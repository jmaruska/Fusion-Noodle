"""The aim rotation Apply Transform uses, and effector strength without a floor."""
import math
import unittest
from tests import fusion_stub

from backend.utilities.vector_math import aim_rotation  # noqa: E402


def rotate(v, angle, axis):
    """Rodrigues' rotation of v about a unit axis."""
    c, s = math.cos(angle), math.sin(angle)
    dot = sum(a * b for a, b in zip(axis, v))
    cross = (axis[1] * v[2] - axis[2] * v[1], axis[2] * v[0] - axis[0] * v[2], axis[0] * v[1] - axis[1] * v[0])
    return tuple(v[i] * c + cross[i] * s + axis[i] * dot * (1 - c) for i in range(3))


class AimRotationTests(unittest.TestCase):
    def assertPointsAt(self, centre, axis, target):
        angle, about = aim_rotation(centre, axis, target)
        turned = rotate(axis, angle, about)
        d = [t - c for t, c in zip(target, centre)]
        n = math.sqrt(sum(x * x for x in d))
        for got, want in zip(turned, [x / n for x in d]):
            self.assertAlmostEqual(got, want, places=9)

    def test_turns_the_axis_toward_the_target(self):
        self.assertPointsAt((0, 0, 0), (0, 1, 0), (10, 0, 0))
        self.assertPointsAt((1, 2, 3), (0, 0, 1), (4, -2, 7))

    def test_pointing_straight_away_turns_half_a_circle(self):
        self.assertPointsAt((0, 0, 0), (0, 1, 0), (0, -5, 0))

    def test_nothing_to_do(self):
        self.assertIsNone(aim_rotation((0, 0, 0), (0, 1, 0), (0, 5, 0)), 'already aimed')
        self.assertIsNone(aim_rotation((1, 1, 1), (0, 1, 0), (1, 1, 1)), 'target at the centre')


class StrengthTests(unittest.TestCase):
    def setUp(self):
        self.effector = fusion_stub.all_node_classes()['uniform_effector']('n')

    def test_negative_strength_is_kept(self):
        self.assertEqual(self.effector._resolve_number(-0.5, 0), -0.5)

    def test_random_can_go_negative(self):
        values = [self.effector._resolve_number({'number_type': 'random', 'min': -1.0, 'max': -0.5, 'seed': 3}, i)
                  for i in range(20)]
        self.assertTrue(all(-1.0 <= v <= -0.5 for v in values))


if __name__ == '__main__':
    unittest.main()
