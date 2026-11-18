"""The visualizer's pass over the graph: what runs, what is stood in for, and how
effector results become dots. Uses the real Atomizer and effectors where they
need nothing from Fusion; arrays are checked in Fusion."""
import unittest
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()

from backend.nodes import NodeRegistry  # noqa: E402
from backend.preview import creates_design_objects, evaluate_graph, preview_collections  # noqa: E402
from backend.visualizer import STRENGTHS_KEY, collect_dots  # noqa: E402
from backend.nodes.effector_base import EFFECTOR_STRENGTHS_KEY  # noqa: E402


def node(node_id, node_type, **inputs):
    return {'id': node_id, 'type': node_type, 'inputs': inputs}


def edge(source, source_port, target, target_port):
    return {'source': source, 'target': target,
            'sourceHandle': f'output-{source_port}', 'targetHandle': f'input-{target_port}'}


def run(nodes, edges, targets):
    return preview_collections(nodes, edges, targets, NodeRegistry.get_node_class, {'app': fusion_stub.FakeApp()})


class WhatMayRunTests(unittest.TestCase):
    def test_nodes_that_make_bodies_or_curves_never_run(self):
        for node_type in ('cube_generator', 'sphere_generator', 'body_instance', 'materializer',
                          'pipe', 'sweep', 'interpolize', 'apply_transform'):
            with self.subTest(node=node_type):
                self.assertTrue(creates_design_objects(NODES[node_type]))

    def test_arrays_effectors_and_calculations_may_run(self):
        allowed = [t for t, cls in NODES.items() if cls.NODE_CATEGORY in ('array', 'effector', 'modifiers', 'math')]
        allowed += ['atomizer', 'null', 'uv_separator', 'move_transform', 'scale_transform', 'rotate_transform']
        for node_type in allowed:
            with self.subTest(node=node_type):
                self.assertFalse(creates_design_objects(NODES[node_type]))

    def test_the_keys_agree(self):
        self.assertEqual(STRENGTHS_KEY, EFFECTOR_STRENGTHS_KEY)


class VisualizerPassTests(unittest.TestCase):
    def chain(self, *effectors, move=(1.0, 0.0, 0.0)):
        """Box -> Atomizer -> effectors..., each effector driven by one Move transform."""
        nodes = [node('box', 'cube_generator', width=2), node('atom', 'Atomizer'),
                 node('move', 'Move_Transform', x=move[0], y=move[1], z=move[2])]
        edges = [edge('box', 'geometry', 'atom', 'geometry')]
        previous = 'atom'
        for node_id, node_type, inputs in effectors:
            nodes.append(node(node_id, node_type, **inputs))
            edges.append(edge(previous, 'collection', node_id, 'collection'))
            edges.append(edge('move', 'transform', node_id, 'transform'))
            previous = node_id
        return nodes, edges

    def test_a_box_is_stood_in_for_and_the_effector_still_runs(self):
        nodes, edges = self.chain(('eff', 'Uniform_Effector', {'strength': 1.0}))
        result = run(nodes, edges, ['eff'])
        self.assertNotIn('box', result['outputs'], 'the Box must not run')
        self.assertEqual(result['errors'], {})
        instances = result['outputs']['eff']['collection'].instances
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].metadata[STRENGTHS_KEY], {'eff': 1.0})

    def test_only_what_feeds_the_targets_runs(self):
        nodes, edges = self.chain(('eff', 'Uniform_Effector', {}))
        nodes.append(node('lonely', 'number', value=3))
        self.assertNotIn('lonely', run(nodes, edges, ['eff'])['outputs'])

    def test_strength_input_scales_a_uniform_effector(self):
        nodes, edges = self.chain(('eff', 'Uniform_Effector', {'strength': 0.25}))
        instances = run(nodes, edges, ['eff'])['outputs']['eff']['collection'].instances
        self.assertAlmostEqual(instances[0].metadata[STRENGTHS_KEY]['eff'], 0.25)

    def test_a_falloff_far_away_gives_no_strength_and_a_near_one_gives_full(self):
        far = self.chain(('eff', 'Falloff_Effector', {'position': {'x': 500, 'y': 0, 'z': 0}, 'radius': 10}))
        near = self.chain(('eff', 'Falloff_Effector', {'position': {'x': 0, 'y': 0, 'z': 0}, 'radius': 10}))
        far_strength = run(*far, ['eff'])['outputs']['eff']['collection'].instances[0].metadata[STRENGTHS_KEY]['eff']
        near_strength = run(*near, ['eff'])['outputs']['eff']['collection'].instances[0].metadata[STRENGTHS_KEY]['eff']
        self.assertAlmostEqual(far_strength, 0.0)
        self.assertAlmostEqual(near_strength, 1.0)

    def test_chained_effectors_each_leave_their_strength(self):
        nodes, edges = self.chain(('a', 'Uniform_Effector', {'strength': 0.5}),
                                  ('b', 'Uniform_Effector', {'strength': 0.25}))
        instances = run(nodes, edges, ['a', 'b'])['outputs']['b']['collection'].instances
        self.assertEqual(instances[0].metadata[STRENGTHS_KEY], {'a': 0.5, 'b': 0.25})

    def test_an_effector_with_nothing_connected_reports_why(self):
        result = run([node('eff', 'Uniform_Effector')], [], ['eff'])
        self.assertNotIn('eff', result['outputs'])
        self.assertIn('eff', result['errors'])

    def test_a_move_displaces_the_dot_by_the_effector_strength(self):
        full = self.chain(('eff', 'Uniform_Effector', {'strength': 1.0}), move=(4.0, 0.0, 0.0))
        half = self.chain(('eff', 'Uniform_Effector', {'strength': 0.5}), move=(4.0, 0.0, 0.0))
        self.assertEqual(collect_dots(run(*full, ['eff'])['outputs'], ['eff']), [(4.0, 0.0, 0.0, 1.0)])
        self.assertEqual(collect_dots(run(*half, ['eff'])['outputs'], ['eff']), [(2.0, 0.0, 0.0, 0.5)])

    def test_an_effector_fed_through_a_sketch_maker_is_skipped_with_a_reason(self):
        # Interpolize makes a sketch, so it never runs; Array on Path then has no curve
        nodes = [node('interp', 'Interpolize'), node('path', 'Array_Path', mode='count', value=5),
                 node('atom', 'Atomizer'), node('box', 'cube_generator'), node('eff', 'Uniform_Effector')]
        edges = [edge('box', 'geometry', 'atom', 'geometry'), edge('atom', 'collection', 'path', 'collection'),
                 edge('interp', 'curves', 'path', 'curve'), edge('path', 'collection', 'eff', 'collection')]
        result = run(nodes, edges, ['eff'])
        self.assertNotIn('eff', result['outputs'])
        self.assertIn('only runs on Generate', result['errors']['path'])


def instance(x, strengths):
    return {'transform': {'tx': x, 'ty': 0, 'tz': 0}, 'metadata': {STRENGTHS_KEY: strengths}}


class CollectDotsTests(unittest.TestCase):
    def test_one_effector_shows_its_true_strength(self):
        outputs = {'a': {'collection': {'instances': [instance(1, {'a': 0.5}), instance(2, {'a': 0.0})]}}}
        self.assertEqual(collect_dots(outputs, ['a']), [(1.0, 0.0, 0.0, 0.5), (2.0, 0.0, 0.0, 0.0)])

    def test_sign_is_ignored(self):
        outputs = {'a': {'collection': {'instances': [instance(0, {'a': -1.0})]}}}
        self.assertEqual(collect_dots(outputs, ['a'])[0][3], 1.0)

    def test_chained_effectors_draw_once_with_combined_strength_scaled_to_the_peak(self):
        upstream = {'instances': [instance(0, {'a': 1.0}), instance(1, {'a': 0.5})]}
        downstream = {'instances': [instance(0, {'a': 1.0, 'b': 1.0}), instance(5, {'a': 0.5, 'b': 0.0})]}
        dots = collect_dots({'a': {'collection': upstream}, 'b': {'collection': downstream}}, ['a', 'b'])
        self.assertEqual(len(dots), 2, 'the upstream effector is not drawn a second time')
        self.assertEqual([d[0] for d in dots], [0.0, 5.0], 'dots sit where the downstream effector leaves them')
        self.assertEqual([d[3] for d in dots], [1.0, 0.25], 'combined 2.0 and 0.5, scaled so the peak is white')

    def test_turning_one_of_a_chain_off_shows_only_the_other(self):
        downstream = {'instances': [instance(0, {'a': 1.0, 'b': 0.5})]}
        dots = collect_dots({'b': {'collection': downstream}}, ['b'])
        self.assertEqual(dots, [(0.0, 0.0, 0.0, 0.5)])

    def test_separate_branches_are_both_drawn(self):
        outputs = {'a': {'collection': {'instances': [instance(0, {'a': 1.0})]}},
                   'b': {'collection': {'instances': [instance(9, {'b': 0.5})]}}}
        self.assertEqual(len(collect_dots(outputs, ['a', 'b'])), 2)

    def test_an_effector_with_no_result_draws_nothing(self):
        self.assertEqual(collect_dots({'a': {'collection': None}}, ['a', 'missing']), [])

    def test_real_instance_objects_work_too(self):
        nodes = [node('box', 'cube_generator'), node('atom', 'Atomizer'), node('eff', 'Uniform_Effector'),
                 node('scale', 'Scale_Transform', scale=0.5)]
        edges = [edge('box', 'geometry', 'atom', 'geometry'), edge('atom', 'collection', 'eff', 'collection'),
                 edge('scale', 'transform', 'eff', 'transform')]
        dots = collect_dots(run(nodes, edges, ['eff'])['outputs'], ['eff'])
        self.assertEqual(dots, [(0.0, 0.0, 0.0, 1.0)], 'a scale changes the color only, not the position')


class EvaluateGraphTests(unittest.TestCase):
    def test_live_values_still_ignore_unknown_inputs_quietly(self):
        from backend.preview import preview_values
        nodes = [node('rand', 'random'), node('sum', 'add', a=1, b=1)]
        result = preview_values(nodes, [edge('rand', 'value', 'sum', 'a')], NodeRegistry.get_node_class)
        self.assertEqual(result['errors'], {})
        self.assertNotIn('sum', result['outputs'])


if __name__ == '__main__':
    unittest.main()
