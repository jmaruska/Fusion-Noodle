"""One composed matrix must place a body exactly as scale, rotate, move did."""
import math
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.utilities.transform_utils import transform_matrix_rows  # noqa: E402


def apply(rows, point):
    x, y, z = point
    return tuple(rows[4 * i] * x + rows[4 * i + 1] * y + rows[4 * i + 2] * z + rows[4 * i + 3] for i in range(3))


def rotate_axis(point, axis, degrees):
    """Rotate a point about a world axis through the origin (right-handed)."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    x, y, z = point
    if axis == 'x':
        return (x, c * y - s * z, s * y + c * z)
    if axis == 'y':
        return (c * x + s * z, y, -s * x + c * z)
    return (c * x - s * y, s * x + c * y, z)


def rotate_quaternion(point, q):
    qx, qy, qz, qw = q
    x, y, z = point
    # v' = q v q*, written out
    ix = qw * x + qy * z - qz * y
    iy = qw * y + qz * x - qx * z
    iz = qw * z + qx * y - qy * x
    iw = -qx * x - qy * y - qz * z
    return (ix * qw + iw * -qx + iy * -qz - iz * -qy,
            iy * qw + iw * -qy + iz * -qx - ix * -qz,
            iz * qw + iw * -qz + ix * -qy - iy * -qx)


class TransformMatrixTests(unittest.TestCase):
    POINT = (1.5, -2.0, 0.75)

    def assertPointEqual(self, a, b):
        for u, v in zip(a, b):
            self.assertAlmostEqual(u, v, places=9)

    def test_euler_matches_scale_then_x_y_z_then_move(self):
        t = {'tx': 4, 'ty': -1, 'tz': 2, 'rx': 30, 'ry': -50, 'rz': 70, 'sx': 2, 'sy': 0.5, 'sz': 3}
        p = (self.POINT[0] * 2, self.POINT[1] * 0.5, self.POINT[2] * 3)
        for axis, key in (('x', 'rx'), ('y', 'ry'), ('z', 'rz')):
            p = rotate_axis(p, axis, t[key])
        expected = (p[0] + 4, p[1] - 1, p[2] + 2)
        self.assertPointEqual(apply(transform_matrix_rows(t), self.POINT), expected)

    def test_quaternion_matches_scale_then_rotate_then_move(self):
        half = math.radians(40) / 2
        axis = (1 / math.sqrt(3),) * 3
        q = (axis[0] * math.sin(half), axis[1] * math.sin(half), axis[2] * math.sin(half), math.cos(half))
        t = {'tx': -3, 'ty': 0, 'tz': 5, 'sx': 1.5, 'sy': 1.5, 'sz': 0.25,
             'qx': q[0], 'qy': q[1], 'qz': q[2], 'qw': q[3], 'use_quaternion': True}
        p = rotate_quaternion((self.POINT[0] * 1.5, self.POINT[1] * 1.5, self.POINT[2] * 0.25), q)
        self.assertPointEqual(apply(transform_matrix_rows(t), self.POINT), (p[0] - 3, p[1], p[2] + 5))

    def test_identity_and_unknown_formats_need_no_transform(self):
        self.assertIsNone(transform_matrix_rows({'tx': 0, 'ty': 0, 'tz': 0}))
        self.assertIsNone(transform_matrix_rows({'qw': 1, 'use_quaternion': True, 'tx': 0}))
        self.assertIsNone(transform_matrix_rows({}))
        self.assertIsNone(transform_matrix_rows({'translation': [1, 2, 3]}))


if __name__ == '__main__':
    unittest.main()
