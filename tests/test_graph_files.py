"""Graph files: writing, reading, and the examples that ship with the add-in."""
import json
import tempfile
import unittest
from pathlib import Path
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()

from backend import graph_format  # noqa: E402
from backend.contracts import PortType  # noqa: E402
from backend.handlers.persistence_handler import PersistenceHandler  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((REPO_ROOT / 'examples').glob('*.noodle'))


def make_handler(version='9.9.9'):
    handler = PersistenceHandler.__new__(PersistenceHandler)
    handler.app = fusion_stub.FakeApp()
    handler.core = type('Core', (), {'version': version})()
    return handler


SAMPLE = {
    'nodes': [
        {'id': 'n1', 'selected': True, 'measured': {'width': 1},
         'data': {'nodeType': 'cube_generator', 'currentInputs': {'width': 2},
                  'computedOutputs': {'geometry': 'big'}, 'nodeState': 'computed', 'executionResult': {'x': 1},
                  'computedInputs': {'collection': {'instances': [1, 2, 3]}, 'width': 2}}},
    ],
    'edges': [],
    'viewport': {'x': 0, 'y': 0, 'zoom': 1},
}


class GraphFileTests(unittest.TestCase):
    def test_round_trip_keeps_the_graph_and_stamps_the_format(self):
        handler = make_handler()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'sample.noodle')
            handler.write_graph_file(path, SAMPLE)
            state, notes = PersistenceHandler.read_graph_file(path)
        self.assertEqual(notes, [])
        self.assertEqual(state['noodle'], {'format': graph_format.GRAPH_FORMAT, 'version': '9.9.9'})
        self.assertEqual(state['nodes'][0]['data']['currentInputs'], {'width': 2})
        self.assertEqual(state['viewport'], SAMPLE['viewport'])

    def test_volatile_and_bulky_data_is_not_written(self):
        handler = make_handler()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'sample.noodle')
            handler.write_graph_file(path, SAMPLE)
            node = json.loads(Path(path).read_text())['nodes'][0]
        self.assertNotIn('selected', node)
        self.assertNotIn('measured', node)
        for key in ('computedOutputs', 'nodeState', 'executionResult'):
            self.assertNotIn(key, node['data'])
        self.assertNotIn('collection', node['data']['computedInputs'])
        self.assertEqual(node['data']['computedInputs'], {'width': 2})

    def test_writing_does_not_modify_the_live_graph(self):
        handler = make_handler()
        before = json.dumps(SAMPLE, sort_keys=True)
        with tempfile.TemporaryDirectory() as folder:
            handler.write_graph_file(str(Path(folder) / 'x.noodle'), SAMPLE)
        self.assertEqual(json.dumps(SAMPLE, sort_keys=True), before)

    def test_a_file_that_is_not_a_graph_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.noodle'
            path.write_text('{"hello": "world"}')
            with self.assertRaises(graph_format.GraphFormatError):
                PersistenceHandler.read_graph_file(str(path))


def port_names(cls, direction):
    spec = cls.get_spec()
    ports = spec.inputs if direction == 'input' else spec.outputs
    return {p.name for p in ports if p.port_type != PortType.SPACER}


class ExampleFileTests(unittest.TestCase):
    """Every example must load against the current nodes. This is what stops
    examples going stale when a node is renamed or restructured."""

    def test_examples_load_and_match_current_nodes(self):
        for path in EXAMPLES:
            with self.subTest(example=path.name):
                state, _ = PersistenceHandler.read_graph_file(str(path))
                classes = {}
                for node in state['nodes']:
                    node_type = node['data']['nodeType']
                    key = node_type.lower().replace(' ', '_')
                    self.assertIn(key, NODES, f'unknown node type {node_type!r}')
                    classes[node['id']] = NODES[key]
                    known_inputs = port_names(NODES[key], 'input')
                    spec = {p.name: p for p in NODES[key].get_spec().inputs}
                    for name, value in (node['data'].get('currentInputs') or {}).items():
                        if name in spec and spec[name].port_type == PortType.ENUM:
                            self.assertIn(value, spec[name].enum_options,
                                          f'{node_type}.{name} has an option that no longer exists')
                    self.assertTrue(known_inputs is not None)
                for edge in state.get('edges', []):
                    self.assertIn(edge.get('source'), classes, 'edge starts at a missing node')
                    self.assertIn(edge.get('target'), classes, 'edge ends at a missing node')
                    source_port = (edge.get('sourceHandle') or '').replace('output-', '', 1)
                    target_port = (edge.get('targetHandle') or '').replace('input-', '', 1)
                    self.assertIn(source_port, port_names(classes[edge['source']], 'output'),
                                  f'edge uses missing output {source_port!r}')
                    self.assertIn(target_port, port_names(classes[edge['target']], 'input'),
                                  f'edge uses missing input {target_port!r}')

    def test_examples_are_in_the_current_format(self):
        for path in EXAMPLES:
            with self.subTest(example=path.name):
                raw = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(graph_format.format_of(raw), graph_format.GRAPH_FORMAT,
                                 'open this example in Noodle and save it again')


if __name__ == '__main__':
    unittest.main()
