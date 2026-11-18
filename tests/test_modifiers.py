import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.utilities.modifier_utils import evaluate_modifier  # noqa: E402


class CheckerboardTests(unittest.TestCase):
    def value(self, u, v, phase=0, amplitude=1.0):
        return evaluate_modifier({'modifier_type': 'checkerboard', 'amplitude': amplitude, 'phase': phase},
                                 {'grid_u_index': u, 'grid_v_index': v})

    def test_neighbours_alternate_sign(self):
        self.assertEqual(self.value(0, 0), 1.0)
        self.assertEqual(self.value(1, 0), -1.0)
        self.assertEqual(self.value(0, 1), -1.0)
        self.assertEqual(self.value(1, 1), 1.0)

    def test_phase_inverts_the_pattern(self):
        self.assertEqual(self.value(0, 0, phase=1), -self.value(0, 0))

    def test_amplitude_scales_the_result(self):
        self.assertEqual(self.value(0, 0, amplitude=2.5), 2.5)

    def test_strand_metadata_takes_priority_over_grid_metadata(self):
        value = evaluate_modifier({'modifier_type': 'checkerboard', 'amplitude': 1.0},
                                  {'strand_index': 0, 'strand_position': 1, 'grid_u_index': 0, 'grid_v_index': 0})
        self.assertEqual(value, -1.0)


class NestedModifierTests(unittest.TestCase):
    def test_a_modifier_can_drive_another_modifiers_amplitude(self):
        inner = {'modifier_type': 'checkerboard', 'amplitude': 3.0}
        outer = {'modifier_type': 'checkerboard', 'amplitude': inner}
        # (0,0): inner = +3, outer sign = +1  ->  +3
        self.assertEqual(evaluate_modifier(outer, {'grid_u_index': 0, 'grid_v_index': 0}), 3.0)
        # (1,0): inner = -3, outer sign = -1  ->  +3
        self.assertEqual(evaluate_modifier(outer, {'grid_u_index': 1, 'grid_v_index': 0}), 3.0)


if __name__ == '__main__':
    unittest.main()
