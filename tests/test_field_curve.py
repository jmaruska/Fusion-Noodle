"""The falloff curve: Python must agree with the curve editor's JavaScript, example for example."""

import json
import unittest
from pathlib import Path

from backend.utilities import field_curve as fc

VECTORS = json.loads((Path(__file__).parent / 'fixtures' / 'field_curve_vectors.json').read_text())


class SharedExamples(unittest.TestCase):

    def test_every_example_matches_the_javascript_values(self):
        for case in VECTORS['cases']:
            curve = fc.FieldCurve(case['curve'], case['start_flat'], case['open_ends'])
            for t, expected in case['samples']:
                with self.subTest(case=case['name'], t=t):
                    self.assertAlmostEqual(curve.value(t, exact=True), expected, places=9)

    def test_the_lookup_table_stays_close_to_the_exact_curve(self):
        for case in VECTORS['cases']:
            curve = fc.FieldCurve(case['curve'], case['start_flat'], case['open_ends'])
            worst = max(abs(curve.value(t) - expected) for t, expected in case['samples'])
            self.assertLess(worst, 5e-4, case['name'])


class Curves(unittest.TestCase):

    def test_anything_unreadable_becomes_the_default_curve(self):
        for value in (None, '', 'not json', '{"points": []}', 42):
            self.assertEqual(fc.normalize_curve(value), fc.preset_curve(fc.DEFAULT_CURVE_NAME))

    def test_a_stored_curve_survives_a_round_trip(self):
        curve = fc.preset_curve('Pulse')
        self.assertEqual(fc.normalize_curve(json.dumps(curve)), curve)

    def test_problems_are_reported_in_words(self):
        self.assertEqual(fc.curve_problems(fc.default_curve_json()), [])
        self.assertTrue(fc.curve_problems('{oops'))
        self.assertTrue(fc.curve_problems('{"points": [[0, 1], [0.5, 1], [0.4, 0], [1, 0]]}'))

    def test_mirror_repeats_count_the_drawn_shape(self):
        self.assertEqual(fc.FieldCurve(fc.preset_curve('Ripple')).n, 9)
        self.assertEqual(fc.FieldCurve(fc.preset_curve('Pulse')).n, 4)


class Sphere(unittest.TestCase):

    def test_full_inside_the_inner_radius_and_none_past_the_radius(self):
        smooth = fc.default_curve_json()
        self.assertAlmostEqual(fc.sphere_strength(0, 10, 2, smooth), 1.0)
        self.assertAlmostEqual(fc.sphere_strength(1.5, 10, 2, smooth), 1.0)
        self.assertAlmostEqual(fc.sphere_strength(10, 10, 2, smooth), 0.0)
        self.assertAlmostEqual(fc.sphere_strength(500, 10, 2, smooth), 0.0)

    def test_linear_matches_the_old_straight_falloff(self):
        linear = fc.preset_curve('Linear')
        for d in (0, 2.5, 5, 7.5, 10):
            self.assertAlmostEqual(fc.sphere_strength(d, 10, 0, linear), 1 - d / 10, places=3)

    def test_a_radius_no_bigger_than_the_inner_radius_is_a_hard_edge(self):
        smooth = fc.default_curve_json()
        self.assertEqual(fc.sphere_strength(4, 5, 5, smooth), 1.0)
        self.assertEqual(fc.sphere_strength(6, 5, 5, smooth), 0.0)


if __name__ == '__main__':
    unittest.main()
