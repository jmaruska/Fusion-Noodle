"""Which helper nodes the palette adds alongside a new node."""
import unittest
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()

from backend.nodes import NodeRegistry  # noqa: E402
from backend.nodes.companions import companions_for  # noqa: E402


def companions(node_type):
    return companions_for(NODES[node_type], NodeRegistry.get_node_class)


BOTH = [
    {'type': 'Atomizer', 'side': 'before', 'sourcePort': 'collection', 'targetPort': 'collection'},
    {'type': 'Materializer', 'side': 'after', 'sourcePort': 'collection', 'targetPort': 'collection'},
]


class CompanionRuleTests(unittest.TestCase):
    def test_every_array_gets_an_atomizer_and_a_materializer(self):
        arrays = [t for t, cls in NODES.items() if cls.NODE_CATEGORY == 'array']
        self.assertGreaterEqual(len(arrays), 6)
        for node_type in arrays:
            with self.subTest(node=node_type):
                self.assertEqual(companions(node_type), BOTH)

    def test_effectors_get_both(self):
        for node_type in ('uniform_effector', 'falloff_effector'):
            with self.subTest(node=node_type):
                self.assertEqual(companions(node_type), BOTH)

    def test_the_helpers_themselves_get_none(self):
        self.assertEqual(companions('atomizer'), [])
        self.assertEqual(companions('materializer'), [])

    def test_nodes_without_a_collection_input_get_none(self):
        for node_type in ('cube_generator', 'number', 'move_transform', 'null', 'random'):
            with self.subTest(node=node_type):
                self.assertEqual(companions(node_type), [])

    def test_nodes_that_need_an_array_upstream_opt_out(self):
        self.assertEqual(companions('uv_separator'), [])
        self.assertEqual(companions('interpolize'), [])

    def test_companion_ports_exist_and_types_match(self):
        for node_type, cls in NODES.items():
            spec = cls.get_spec()
            for companion in companions(node_type):
                helper = NodeRegistry.get_node_class(companion['type']).get_spec()
                with self.subTest(node=node_type, companion=companion['type']):
                    if companion['side'] == 'before':
                        source = {p.name: p for p in helper.outputs}[companion['sourcePort']]
                        target = {p.name: p for p in spec.inputs}[companion['targetPort']]
                    else:
                        source = {p.name: p for p in spec.outputs}[companion['sourcePort']]
                        target = {p.name: p for p in helper.inputs}[companion['targetPort']]
                    self.assertEqual(source.port_type, target.port_type)

    def test_specs_sent_to_the_palette_carry_companions(self):
        specs = {s['type']: s for s in NodeRegistry.get_all_specs()}
        self.assertEqual(specs['Array_2D_Grid']['companions'], BOTH)
        self.assertEqual(specs['cube_generator']['companions'], [])


if __name__ == '__main__':
    unittest.main()
