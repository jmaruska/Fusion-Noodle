"""The visualizer's color steps, grouping, and dot images. Drawing is checked in Fusion."""
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend import visualizer  # noqa: E402
from backend.visualizer import STEPS, group_by_step, ramp_color, step_color, step_for  # noqa: E402


class RampTests(unittest.TestCase):
    def test_unaffected_is_black_and_fully_affected_is_white(self):
        self.assertEqual(ramp_color(0), (0, 0, 0))
        self.assertEqual(ramp_color(1), (255, 255, 255))
        self.assertEqual(step_color(0), (0, 0, 0))
        self.assertEqual(step_color(STEPS - 1), (255, 255, 255))

    def test_ramp_gets_brighter_all_the_way_up(self):
        brightness = [sum(step_color(step)) for step in range(STEPS)]
        self.assertEqual(brightness, sorted(brightness))
        self.assertEqual(len(set(step_color(step) for step in range(STEPS))), STEPS, 'every step is a distinct color')

    def test_out_of_range_values_are_clamped(self):
        self.assertEqual(ramp_color(-3), (0, 0, 0))
        self.assertEqual(ramp_color(7), (255, 255, 255))


class StepTests(unittest.TestCase):
    def test_strength_maps_across_all_steps(self):
        self.assertEqual(step_for(0), 0)
        self.assertEqual(step_for(1), STEPS - 1)
        self.assertEqual(step_for(0.5), round(0.5 * (STEPS - 1)))

    def test_sign_is_ignored(self):
        self.assertEqual(step_for(-1), step_for(1))
        self.assertEqual(step_for(-0.4), step_for(0.4))

    def test_values_beyond_full_strength_stay_in_the_top_step(self):
        self.assertEqual(step_for(2.5), STEPS - 1)

    def test_points_are_grouped_into_flat_coordinate_lists(self):
        grouped = group_by_step([(1, 2, 3, 0.0), (4, 5, 6, 1.0), (7, 8, 9, -1.0)])
        self.assertEqual(grouped, {0: [1.0, 2.0, 3.0], STEPS - 1: [4.0, 5.0, 6.0, 7.0, 8.0, 9.0]})

    def test_a_refresh_never_needs_more_batches_than_steps(self):
        points = [(i, 0, 0, i / 1599) for i in range(1600)]
        self.assertLessEqual(len(group_by_step(points)), STEPS)


class DiskTests(unittest.TestCase):
    def test_disk_is_a_closed_fan(self):
        from backend.visualizer import disk_geometry, DISK_SEGMENTS
        coords, indices, normals = disk_geometry()
        self.assertEqual(len(coords), (DISK_SEGMENTS + 1) * 3)
        self.assertEqual(len(normals), len(coords))
        self.assertEqual(len(indices), DISK_SEGMENTS * 3)
        self.assertEqual(set(indices), set(range(DISK_SEGMENTS + 1)))

    def test_dots_draw_in_front_by_being_just_short_of_opaque(self):
        self.assertTrue(0.9 <= visualizer.SHOW_THROUGH_OPACITY < 1.0)


if __name__ == '__main__':
    unittest.main()


class OutlineDrawingTests(unittest.TestCase):
    """Falloff outlines are drawn as faint lines; this checks the calls, not Fusion's drawing."""

    def setUp(self):
        from tests import fusion_stub
        fusion_stub.install()
        from unittest.mock import MagicMock
        from backend.visualizer import VisualizerRenderer
        self.renderer = VisualizerRenderer(MagicMock())
        self.group = MagicMock()

    def test_a_box_draws_its_outer_edges_solid_and_the_inner_box_dashed(self):
        from backend.utilities.field_sources import field_outline
        outline = field_outline({'shape': 'box', 'radius': 3, 'inner_radius': 1}, 'position')
        self.renderer._draw_outline(self.group, outline)
        calls = self.group.addLines.call_args_list
        self.assertEqual([len(c.args[1]) for c in calls], [24, 24])   # 12 edges, 2 indices each

    def test_an_ellipsoid_is_traced_from_the_camera(self):
        from backend.utilities.field_sources import field_outline
        outline = field_outline({'shape': 'sphere', 'radius': 5, 'inner_radius': 2}, 'position')
        self.renderer._draw_outline(self.group, outline, {'eye': (0.0, 0.0, 50.0)})
        self.assertEqual(self.group.addLines.call_count, 2)
        coords = [c.args[0] for c in self.group.addLines.call_args_list]
        self.assertTrue(coords)

    def test_nothing_to_draw_adds_nothing(self):
        self.renderer._draw_outline(self.group, {'solid': [], 'dashed': [], 'ellipsoids': []})
        self.group.addLines.assert_not_called()
