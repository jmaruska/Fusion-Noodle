"""Effector transforms compose component-wise onto an instance:
scale multiplies, translation is rotated through the base orientation then added,
rotation multiplies as quaternions. Matrix multiplication would be wrong here."""
import math
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.contracts import NoodleAttributes  # noqa: E402
from backend.services.transform_composition_service import TransformCompositionService  # noqa: E402

HALF = math.sqrt(0.5)  # sin/cos of 45 degrees: a 90 degree turn about Z


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.service = TransformCompositionService(fusion_stub.FakeApp())
        self.base = NoodleAttributes(tx=10.0, ty=0.0, tz=0.0, sx=2.0, sy=2.0, sz=2.0,
                                     qx=0.0, qy=0.0, qz=HALF, qw=HALF, use_quaternion=True)

    def test_scale_multiplies_and_does_not_move_the_instance(self):
        result = self.service.compose_noodle_attributes(self.base, NoodleAttributes(sx=0.5, sy=0.5, sz=0.5))
        self.assertAlmostEqual(result.sx, 1.0)
        self.assertAlmostEqual(result.sy, 1.0)
        self.assertAlmostEqual(result.sz, 1.0)
        self.assertAlmostEqual(result.tx, 10.0)
        self.assertAlmostEqual(result.ty, 0.0)

    def test_translation_follows_the_instance_orientation(self):
        # Local +X on an instance turned 90 degrees about Z points along world +Y
        result = self.service.compose_noodle_attributes(self.base, NoodleAttributes(tx=1.0))
        self.assertAlmostEqual(result.tx, 10.0, places=5)
        self.assertAlmostEqual(result.ty, 1.0, places=5)
        self.assertAlmostEqual(result.tz, 0.0, places=5)

    def test_identity_effector_changes_nothing(self):
        result = self.service.compose_noodle_attributes(self.base, NoodleAttributes())
        for field in ('tx', 'ty', 'tz', 'sx', 'sy', 'sz', 'qx', 'qy', 'qz', 'qw'):
            self.assertAlmostEqual(getattr(result, field), getattr(self.base, field), places=6, msg=field)

    def test_rotation_compounds(self):
        # Another 90 degrees about Z on top of the base gives 180 degrees about Z
        result = self.service.compose_noodle_attributes(self.base, NoodleAttributes(rz=90.0))
        self.assertAlmostEqual(abs(result.qz), 1.0, places=5)
        self.assertAlmostEqual(result.qw, 0.0, places=5)


class QuaternionHelperTests(unittest.TestCase):
    def test_rotating_x_by_90_about_z_gives_y(self):
        x, y, z = TransformCompositionService._rotate_vector_by_quaternion((1.0, 0.0, 0.0), (0.0, 0.0, HALF, HALF))
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 1.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)


if __name__ == '__main__':
    unittest.main()
