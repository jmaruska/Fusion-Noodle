import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.handlers.graph_handler import GraphHandler  # noqa: E402


def make_handler():
    handler = GraphHandler.__new__(GraphHandler)
    handler.app = fusion_stub.FakeApp()
    return handler


def edge(source, target, source_port='value', target_port='value'):
    return {'source': source, 'target': target,
            'sourceHandle': f'output-{source_port}', 'targetHandle': f'input-{target_port}'}


class TopologicalSortTests(unittest.TestCase):
    def setUp(self):
        self.handler = make_handler()
        self.handler._find_connected_nodes = lambda graph: set(graph['nodes'])

    def test_dependencies_run_before_dependents(self):
        graph = {'nodes': {'c': {}, 'b': {}, 'a': {}},
                 'edges': [edge('a', 'b'), edge('b', 'c')]}
        self.assertEqual(self.handler._topological_sort(graph), ['a', 'b', 'c'])

    def test_diamond_runs_each_node_once(self):
        graph = {'nodes': {n: {} for n in 'abcd'},
                 'edges': [edge('a', 'b'), edge('a', 'c'), edge('b', 'd'), edge('c', 'd')]}
        order = self.handler._topological_sort(graph)
        self.assertEqual(sorted(order), ['a', 'b', 'c', 'd'])
        self.assertLess(order.index('a'), order.index('b'))
        self.assertLess(order.index('b'), order.index('d'))
        self.assertLess(order.index('c'), order.index('d'))

    def test_duplicate_edges_do_not_block_execution(self):
        graph = {'nodes': {'a': {}, 'b': {}},
                 'edges': [edge('a', 'b', target_port='x'), edge('a', 'b', target_port='y')]}
        self.assertEqual(self.handler._topological_sort(graph), ['a', 'b'])

    def test_cycle_is_rejected(self):
        graph = {'nodes': {'a': {}, 'b': {}}, 'edges': [edge('a', 'b'), edge('b', 'a')]}
        self.assertIsNone(self.handler._topological_sort(graph))

    def test_empty_graph_has_nothing_to_run(self):
        self.handler._find_connected_nodes = lambda graph: set()
        self.assertEqual(self.handler._topological_sort({'nodes': {}, 'edges': []}), [])


class ResolveInputsTests(unittest.TestCase):
    def setUp(self):
        self.handler = make_handler()

    def test_connected_value_overrides_manual_value(self):
        graph = {'edges': [edge('num', 'box', 'value', 'width')]}
        resolved = self.handler._resolve_inputs(
            'box', {'inputs': {'width': 1.0, 'height': 2.0}}, graph, {'num': {'value': 7.0}})
        self.assertEqual(resolved, {'width': 7.0, 'height': 2.0})

    def test_missing_upstream_result_keeps_manual_value(self):
        graph = {'edges': [edge('num', 'box', 'value', 'width')]}
        resolved = self.handler._resolve_inputs('box', {'inputs': {'width': 1.0}}, graph, {})
        self.assertEqual(resolved, {'width': 1.0})


class ConvertReactFlowTests(unittest.TestCase):
    def test_computed_inputs_override_current_inputs(self):
        handler = make_handler()
        state = {'nodes': [
            {'id': 'n1', 'position': {'x': 1, 'y': 2},
             'data': {'nodeType': 'Number', 'currentInputs': {'value': 1, 'other': 5},
                      'computedInputs': {'value': 9}}},
            {'id': 'ignored', 'data': {}},
        ], 'edges': [{'source': 'n1', 'target': 'n2'}]}
        graph = handler._convert_reactflow_to_graph(state)
        self.assertEqual(list(graph['nodes']), ['n1'])
        self.assertEqual(graph['nodes']['n1']['inputs'], {'value': 9, 'other': 5})
        self.assertEqual(graph['nodes']['n1']['type'], 'Number')
        self.assertEqual(len(graph['edges']), 1)


class AutoVisibilityTests(unittest.TestCase):
    """Bodies that only serve as templates for instances are hidden after Generate."""

    def hidden(self, nodes, edges):
        handler = make_handler()
        graph = {'nodes': {k: {'type': t} for k, t in nodes.items()}, 'edges': edges}
        return handler._auto_hidden_nodes(graph)

    def test_body_feeding_an_atomizer_is_hidden(self):
        nodes = {'box': 'cube_generator', 'atom': 'Atomizer', 'grid': 'Array_2D_Grid', 'mat': 'Materializer'}
        edges = [edge('box', 'atom'), edge('atom', 'grid'), edge('grid', 'mat')]
        self.assertEqual(self.hidden(nodes, edges), {'box', 'atom'})

    def test_body_feeding_a_transform_stays_visible(self):
        nodes = {'box': 'cube_generator', 'apply': 'Apply_Transform'}
        self.assertEqual(self.hidden(nodes, [edge('box', 'apply')]), set())

    def test_materializer_output_stays_visible(self):
        nodes = {'grid': 'Array_2D_Grid', 'mat': 'Materializer'}
        self.assertNotIn('mat', self.hidden(nodes, [edge('grid', 'mat')]))

    def test_edges_to_missing_nodes_are_ignored(self):
        self.assertEqual(self.hidden({'box': 'cube_generator'}, [edge('box', 'ghost'), edge('ghost', 'box')]), set())


if __name__ == '__main__':
    unittest.main()
