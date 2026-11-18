import unittest
from tests import fusion_stub
fusion_stub.install()

from backend import graph_format  # noqa: E402
from backend.graph_format import GraphFormatError, migrate, stamp, format_of  # noqa: E402


def graph(node_type='old_box', inputs=None, edges=None, fmt=None):
    state = {
        'nodes': [
            {'id': 'a', 'data': {'nodeType': node_type, 'currentInputs': dict(inputs or {'depth': 3, 'mode': 'join'}),
                                 'computedInputs': {}}},
            {'id': 'b', 'data': {'nodeType': 'Atomizer', 'currentInputs': {}}},
        ],
        'edges': edges if edges is not None else [
            {'id': 'e1', 'source': 'a', 'target': 'b', 'sourceHandle': 'output-geometry', 'targetHandle': 'input-geometry'}],
    }
    if fmt is not None:
        state['noodle'] = {'format': fmt, 'version': '0.0.1'}
    return state


STEPS = [
    {'to': 2, 'note': 'Box was renamed', 'rename_node_types': {'old_box': 'box'}},
    {'to': 3, 'note': 'Box ports were renamed',
     'rename_inputs': {'box': {'depth': 'length'}},
     'rename_outputs': {'box': {'geometry': 'body'}},
     'rename_options': {'box': {'mode': {'join': 'add'}}}},
]


class MigrationTests(unittest.TestCase):
    def test_unstamped_graph_is_format_one(self):
        self.assertEqual(format_of(graph()), 1)

    def test_all_steps_apply_in_order_to_an_old_graph(self):
        result, notes = migrate(graph(), STEPS, current_format=3)
        box = result['nodes'][0]['data']
        self.assertEqual(box['nodeType'], 'box')
        self.assertEqual(box['currentInputs'], {'length': 3, 'mode': 'add'})
        self.assertEqual(result['edges'][0]['sourceHandle'], 'output-body')
        self.assertEqual(result['edges'][0]['targetHandle'], 'input-geometry')
        self.assertEqual(notes, ['Box was renamed', 'Box ports were renamed'])
        self.assertEqual(result['noodle']['format'], 3)

    def test_only_newer_steps_apply(self):
        state = graph(node_type='box', fmt=2)
        result, notes = migrate(state, STEPS, current_format=3)
        self.assertEqual(notes, ['Box ports were renamed'])
        self.assertEqual(result['nodes'][0]['data']['currentInputs']['length'], 3)

    def test_current_graph_is_untouched_and_gets_no_notes(self):
        state = graph(node_type='box', inputs={'length': 1}, fmt=3)
        result, notes = migrate(state, STEPS, current_format=3)
        self.assertEqual(notes, [])
        self.assertEqual(result['nodes'], state['nodes'])

    def test_input_is_not_modified(self):
        state = graph()
        migrate(state, STEPS, current_format=3)
        self.assertEqual(state['nodes'][0]['data']['nodeType'], 'old_box')

    def test_a_step_that_changes_nothing_adds_no_note(self):
        state = graph(node_type='Sphere', inputs={'radius': 1})
        _, notes = migrate(state, STEPS, current_format=3)
        self.assertEqual(notes, [])

    def test_graph_from_a_newer_noodle_is_refused(self):
        with self.assertRaises(GraphFormatError) as caught:
            migrate(graph(fmt=9), STEPS, current_format=3)
        self.assertIn('newer version', str(caught.exception))

    def test_non_graphs_are_refused(self):
        for bad in (None, [], {}, {'nodes': 'x'}, {'nodes': [{'id': 'a', 'data': {}}]},
                    {'nodes': [], 'edges': {}}):
            with self.subTest(bad=bad):
                with self.assertRaises(GraphFormatError):
                    migrate(bad, STEPS, current_format=3)

    def test_stamp_marks_the_current_format(self):
        state = stamp(graph(), '1.2.3')
        self.assertEqual(state['noodle'], {'format': graph_format.GRAPH_FORMAT, 'version': '1.2.3'})


class FlaggedInputTests(unittest.TestCase):
    """An input whose meaning changed is reported, not converted."""

    STEP = [{'to': 2, 'note': 'Margin is now cm', 'flag_inputs': {'old_box': ['depth']}}]

    def test_a_set_value_produces_the_note_and_is_kept(self):
        result, notes = migrate(graph(inputs={'depth': 5}), self.STEP, current_format=2)
        self.assertEqual(notes, ['Margin is now cm'])
        self.assertEqual(result['nodes'][0]['data']['currentInputs']['depth'], 5)

    def test_a_zero_or_missing_value_says_nothing(self):
        self.assertEqual(migrate(graph(inputs={'depth': 0}), self.STEP, current_format=2)[1], [])
        self.assertEqual(migrate(graph(inputs={'mode': 'join'}), self.STEP, current_format=2)[1], [])


class FalloffCurveMigrationTests(unittest.TestCase):
    """Format 3: the falloff range, repeat, fade and edge inputs became one falloff curve."""

    def falloff(self, inputs, edges=None):
        state = graph('Falloff_Effector', inputs, edges=edges, fmt=2)
        result, notes = migrate(state)
        return result, notes, result['nodes'][0]['data']['currentInputs']

    def test_a_plain_falloff_becomes_the_linear_curve_without_a_note(self):
        import json
        from backend.utilities.field_curve import sphere_strength
        _, notes, inputs = self.falloff({'radius': 10, 'range_start': 80, 'range_end': 20})
        self.assertEqual(notes, [])
        self.assertNotIn('range_start', inputs)
        curve = json.loads(inputs['curve'])
        self.assertEqual(curve['output'], {'start': 0.8, 'end': 0.2})
        # The old straight fade from 80% to 20%
        self.assertAlmostEqual(sphere_strength(5, 10, 0, inputs['curve']), 0.5, places=3)

    def test_repeats_are_approximated_and_flagged(self):
        import json
        _, notes, inputs = self.falloff({'repeat_count': 3, 'fade_repeats': True})
        self.assertEqual(len(notes), 1)
        curve = json.loads(inputs['curve'])
        self.assertEqual((curve['repeat'], curve['decay']), (4, 1.0))

    def test_a_connection_into_a_removed_input_is_dropped(self):
        edges = [{'id': 'e1', 'source': 'b', 'target': 'a', 'sourceHandle': 'output-value', 'targetHandle': 'input-range_end'},
                 {'id': 'e2', 'source': 'b', 'target': 'a', 'sourceHandle': 'output-value', 'targetHandle': 'input-radius'}]
        result, notes, _ = self.falloff({}, edges=edges)
        self.assertEqual([e['id'] for e in result['edges']], ['e2'])
        self.assertEqual(len(notes), 1)

    def test_the_falloff_modifier_converts_the_same_way(self):
        state = graph('Modifier_Falloff', {'range_start': 100, 'range_end': 0, 'amplitude': 2}, fmt=2)
        result, _ = migrate(state)
        inputs = result['nodes'][0]['data']['currentInputs']
        self.assertIn('curve', inputs)
        self.assertEqual(inputs['amplitude'], 2)


class GradientCurveMigrationTests(unittest.TestCase):
    """Format 4: the Gradient's stops became a falloff curve fitted to the old values."""

    def gradient(self, stops, clamp=False):
        import json
        state = graph('Modifier_Gradient', {'stops': json.dumps(stops), 'interpolation': 'linear',
                                            'clamp': clamp, 'amplitude': 1.5}, fmt=3)
        result, notes = migrate(state)
        return result['nodes'][0]['data']['currentInputs'], notes

    def test_a_straight_ramp_converts_exactly_without_a_note(self):
        from backend.utilities.field_curve import field_curve
        inputs, notes = self.gradient([{'position': 0, 'value': 1}, {'position': 1, 'value': 0}])
        self.assertEqual(notes, [])
        self.assertEqual(set(inputs), {'curve', 'amplitude'})
        for t in (0, 0.3, 0.7, 1):
            self.assertAlmostEqual(field_curve(inputs['curve'], open_ends=True).value(t), 1 - t, places=6)

    def test_a_smooth_gradient_lands_within_one_percent(self):
        from backend.utilities.field_curve import field_curve
        from backend.utilities.legacy_gradient import evaluate
        stops = [{'position': 0, 'value': 0, 'interp': 'smooth'},
                 {'position': 0.3, 'value': 1, 'interp': 'influence'},
                 {'position': 1, 'value': 0.2, 'interp': 'flat', 'tension': 0.3}]
        inputs, notes = self.gradient(stops)
        self.assertEqual(notes, [])
        for i in range(21):
            t = i / 20
            self.assertAlmostEqual(field_curve(inputs['curve'], open_ends=True).value(t), evaluate(stops, t), delta=0.01)

    def test_steps_cannot_be_matched_and_are_flagged(self):
        _, notes = self.gradient([{'position': 0, 'value': 0, 'interp': 'step'},
                                  {'position': 0.5, 'value': 1, 'interp': 'step'},
                                  {'position': 1, 'value': 1}])
        self.assertEqual(len(notes), 1)

    def test_values_outside_zero_to_one_keep_their_range(self):
        import json
        inputs, _ = self.gradient([{'position': 0, 'value': -1}, {'position': 1, 'value': 2}])
        self.assertEqual(json.loads(inputs['curve'])['output'], {'start': 2.0, 'end': -1.0})


class MigrationTableTests(unittest.TestCase):
    """The real MIGRATIONS list must stay consistent with GRAPH_FORMAT."""

    def test_steps_are_numbered_without_gaps_up_to_the_current_format(self):
        targets = sorted(step['to'] for step in graph_format.MIGRATIONS)
        self.assertEqual(targets, list(range(2, graph_format.GRAPH_FORMAT + 1)))

    def test_steps_only_use_known_keys(self):
        known = {'to', 'note', 'rename_node_types', 'rename_inputs', 'rename_outputs', 'rename_options', 'flag_inputs',
                 'convert_inputs', 'removed_inputs'}
        for step in graph_format.MIGRATIONS:
            with self.subTest(to=step['to']):
                self.assertFalse(set(step) - known)


if __name__ == '__main__':
    unittest.main()


class PolygonHeightTests(unittest.TestCase):
    """Format 5: Polygon Height became the total thickness. Saved shapes must not change."""

    def test_a_saved_height_is_doubled_without_a_note(self):
        result, notes = migrate(graph('polygon_generator', {'height': 1.5}, fmt=4))
        self.assertEqual(result['nodes'][0]['data']['currentInputs']['height'], 3.0)
        self.assertFalse(any('Height' in n for n in notes), 'an exact conversion needs no note')

    def test_an_unset_height_stays_unset(self):
        result, _ = migrate(graph('polygon_generator', {'sides': 6}, fmt=4))
        self.assertNotIn('height', result['nodes'][0]['data']['currentInputs'])

    def test_the_new_default_matches_the_old_default_thickness(self):
        from backend.nodes.geometry_polygon import PolygonNode as Polygon
        height = next(p for p in Polygon.get_spec().inputs if p.name == 'height')
        self.assertEqual(height.default_value, 2.0, 'the old default of 1 each side was 2 cm in total')


class StaggerOffsetTests(unittest.TestCase):
    """Format 6: Surface Grid's Stagger Offset now means what it says."""

    def test_a_set_offset_is_kept_and_noted(self):
        result, notes = migrate(graph('Array_Surface_Grid', {'stagger_offset': 0.2}, fmt=5))
        self.assertEqual(result['nodes'][0]['data']['currentInputs']['stagger_offset'], 0.2)
        self.assertTrue(any('Stagger Offset' in n for n in notes))

    def test_no_offset_says_nothing(self):
        _, notes = migrate(graph('Array_Surface_Grid', {'stagger_offset': 0.0}, fmt=5))
        self.assertEqual(notes, [])


class PolygonRadiusTests(unittest.TestCase):
    """Format 7: Polygon Radius is measured to the flats. Saved shapes must not change."""

    def test_a_saved_radius_keeps_its_shape(self):
        import math
        result, _ = migrate(graph('polygon_generator', {'sides': 6, 'radius': 5.0}, fmt=6), current_format=7)
        self.assertAlmostEqual(result['nodes'][0]['data']['currentInputs']['radius'], 5.0 * math.cos(math.pi / 6))

    def test_an_unset_radius_takes_the_old_default(self):
        import math
        result, _ = migrate(graph('polygon_generator', {'sides': 4}, fmt=6), current_format=7)
        self.assertAlmostEqual(result['nodes'][0]['data']['currentInputs']['radius'], math.cos(math.pi / 4))


class PolygonSizeTests(unittest.TestCase):
    """Format 8: Radius (to a side) became Size across the flats, and connections follow."""

    def test_radius_becomes_size_across_flats(self):
        state = graph('polygon_generator', {'sides': 6, 'radius': 4.3301}, fmt=7, edges=[
            {'id': 'e', 'source': 'n', 'target': 'a', 'sourceHandle': 'output-value', 'targetHandle': 'input-radius'}])
        result, notes = migrate(state)
        inputs = result['nodes'][0]['data']['currentInputs']
        self.assertAlmostEqual(inputs['size'], 8.6602)
        self.assertNotIn('radius', inputs)
        self.assertEqual(result['edges'][0]['targetHandle'], 'input-size')

    def test_old_graphs_keep_their_shape_all_the_way(self):
        """A format-6 radius (to the corners) of 5 is a hexagon 5·√3 across the flats."""
        import math
        result, _ = migrate(graph('polygon_generator', {'sides': 6, 'radius': 5.0}, fmt=6))
        self.assertAlmostEqual(result['nodes'][0]['data']['currentInputs']['size'], 5 * math.sqrt(3))
