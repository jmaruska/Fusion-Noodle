"""Live values: the backend runs the pure nodes so the palette needs no copy of them."""
import ast
import inspect
import json
import unittest
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()

from backend.nodes import NodeRegistry  # noqa: E402
from backend.preview import preview_values  # noqa: E402
from backend.handlers.graph_handler import GraphHandler  # noqa: E402


def node(node_id, node_type, **inputs):
    return {'id': node_id, 'type': node_type, 'inputs': inputs}


def edge(source, source_port, target, target_port):
    return {'source': source, 'target': target,
            'sourceHandle': f'output-{source_port}', 'targetHandle': f'input-{target_port}'}


def preview(nodes, edges):
    return preview_values(nodes, edges, NodeRegistry.get_node_class, fusion_stub.FakeApp())


class PreviewTests(unittest.TestCase):
    def test_a_number_reports_its_value(self):
        result = preview([node('n', 'number', value=4.5)], [])
        self.assertEqual(result['outputs']['n']['number'], 4.5)

    def test_values_flow_through_a_chain(self):
        nodes = [node('a', 'number', value=3), node('b', 'number', value=4),
                 node('sum', 'add', a=0, b=0), node('twice', 'multiply', a=1, b=2)]
        edges = [edge('a', 'number', 'sum', 'a'), edge('b', 'number', 'sum', 'b'),
                 edge('sum', 'result', 'twice', 'a')]
        outputs = preview(nodes, edges)['outputs']
        self.assertEqual(outputs['sum']['result'], 7)
        self.assertEqual(outputs['twice']['result'], 14)

    def test_absolute_and_vector(self):
        nodes = [node('n', 'number', value=-2), node('abs', 'absolute'), node('v', 'vector3', x=0, y=5, z=0)]
        edges = [edge('n', 'number', 'abs', 'value'), edge('abs', 'absolute', 'v', 'x')]
        outputs = preview(nodes, edges)['outputs']
        self.assertEqual(outputs['abs']['absolute'], 2)
        self.assertEqual(outputs['v']['vector'], {'x': 2, 'y': 5, 'z': 0})

    def test_nodes_that_touch_fusion_are_never_run(self):
        nodes = [node('n', 'number', value=2), node('box', 'cube_generator', width=1),
                 node('atom', 'Atomizer'), node('grid', 'Array_2D_Grid')]
        edges = [edge('n', 'number', 'box', 'width'), edge('box', 'geometry', 'atom', 'geometry'),
                 edge('atom', 'collection', 'grid', 'collection')]
        result = preview(nodes, edges)
        self.assertEqual(set(result['outputs']), {'n'})
        self.assertEqual(result['errors'], {})

    def test_a_pure_node_fed_by_an_unknown_value_is_skipped(self):
        # A modifier's output can't be shown as a number, so Add has nothing to compute from
        nodes = [node('rand', 'random'), node('sum', 'add', a=1, b=1)]
        result = preview(nodes, [edge('rand', 'value', 'sum', 'a')])
        self.assertNotIn('sum', result['outputs'])

    def test_known_outputs_are_used_without_running_the_node(self):
        point = {'id': 'p', 'type': '3D_POINT', 'inputs': {}, 'known': {'position': {'x': 1, 'y': 2, 'z': 3}}}
        vector = node('v', 'vector3', x=0, y=0, z=0)
        outputs = preview([point, vector], [])['outputs']
        self.assertEqual(outputs['p']['position'], {'x': 1, 'y': 2, 'z': 3})

    def test_a_loop_does_not_hang_or_fail(self):
        nodes = [node('a', 'add', a=1, b=1), node('b', 'add', a=1, b=1)]
        edges = [edge('a', 'result', 'b', 'a'), edge('b', 'result', 'a', 'a')]
        result = preview(nodes, edges)
        self.assertEqual(result['outputs'], {})

    def test_a_failing_node_is_reported_and_others_still_run(self):
        nodes = [node('bad', 'add', a='not a number', b=1), node('ok', 'number', value=1)]
        result = preview(nodes, [])
        self.assertIn('bad', result['errors'])
        self.assertEqual(result['outputs']['ok']['number'], 1)

    def test_edges_to_missing_nodes_and_unknown_types_are_ignored(self):
        nodes = [node('n', 'number', value=1), node('x', 'no_such_node')]
        result = preview(nodes, [edge('ghost', 'number', 'n', 'value'), edge('n', 'number', 'gone', 'a')])
        self.assertEqual(result['errors'], {})

    def test_the_message_handler_returns_json(self):
        handler = GraphHandler.__new__(GraphHandler)
        handler.app = fusion_stub.FakeApp()
        response = handler._preview_values({'nodes': [node('n', 'number', value=2), node('v', 'vector3', x=1, y=2, z=3)],
                                            'edges': []})
        self.assertTrue(response['success'])
        self.assertEqual(json.loads(json.dumps(response))['outputs']['v']['vector'], {'x': 1, 'y': 2, 'z': 3})


class PreviewableNodeTests(unittest.TestCase):
    """A previewable node runs on every edit, outside Generate. It must not use Fusion."""

    def test_some_nodes_are_previewable(self):
        self.assertGreaterEqual(sum(1 for cls in NODES.values() if cls.PREVIEWABLE), 5)

    def test_previewable_nodes_never_reference_fusion(self):
        for node_type, cls in NODES.items():
            if not cls.PREVIEWABLE:
                continue
            names = {n.id for n in ast.walk(ast.parse(inspect.getsource(inspect.getmodule(cls))))
                     if isinstance(n, ast.Name)}
            imports = {a.name.split('.')[0] for n in ast.walk(ast.parse(inspect.getsource(inspect.getmodule(cls))))
                       if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            with self.subTest(node=node_type):
                self.assertNotIn('adsk', names | imports)

    def test_previewable_nodes_run_on_their_defaults(self):
        for node_type, cls in NODES.items():
            if not cls.PREVIEWABLE:
                continue
            spec = cls.get_spec()
            defaults = {p.name: p.default_value for p in spec.inputs if p.default_value is not None}
            with self.subTest(node=node_type):
                result = cls('t').execute(defaults, {'app': fusion_stub.FakeApp()})
                json.dumps(result)  # must be plain data
                self.assertEqual(set(result), {p.name for p in spec.outputs if p.port_type.value != 'spacer'})


if __name__ == '__main__':
    unittest.main()
