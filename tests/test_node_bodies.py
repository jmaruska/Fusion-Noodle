"""Finding the bodies a node created, including in a document that was reopened."""
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.handlers.geometry_handler import GeometryHandler  # noqa: E402
from backend.utilities.geometry_naming import generate_geometry_name, geometry_name_prefix  # noqa: E402


class Body:
    def __init__(self, name, visible=True):
        self.name = name
        self.isVisible = visible


def make_handler(bodies, registry=None, node_instances=None):
    handler = GeometryHandler.__new__(GeometryHandler)
    handler.app = fusion_stub.FakeApp()
    handler.node_visibility = {}
    core = type('Core', (), {})()
    core.node_body_names = {} if registry is None else registry
    core.node_instances = node_instances or {}
    handler.context = {'core': core}
    handler._find_bodies_fresh = lambda names: [b for b in bodies if b.name in set(names)]
    handler._find_bodies_by_prefix = lambda prefix: [b for b in bodies if b.name.startswith(prefix)]
    return handler, core


MATERIALIZER = 'node_Materializer_1762800000000_4711'
OTHER = 'node_Materializer_1762800000001_9001'


class PrefixTests(unittest.TestCase):
    def test_every_generated_name_starts_with_the_nodes_prefix(self):
        cases = [('Materializer', MATERIALIZER, 'Box', 3), ('cube_generator', 'node_cube_generator_1_22', 'Box', None),
                 ('body_instance', 'node_body_instance_5_2589', 'Body1', None)]
        for node_type, node_id, source, index in cases:
            with self.subTest(node=node_type):
                name = generate_geometry_name(node_type, node_id, source, index=index)
                self.assertTrue(name.startswith(geometry_name_prefix(node_type, node_id)), name)

    def test_registered_type_and_the_name_a_node_uses_give_one_prefix(self):
        # Materializer, Pipe, and Sweep name their bodies in lowercase
        for registered, used in (('Materializer', 'materializer'), ('Pipe', 'pipe'), ('Sweep', 'sweep')):
            with self.subTest(node=registered):
                name = generate_geometry_name(used, f'node_{registered}_1_77', 'Box', index=0)
                self.assertTrue(name.startswith(geometry_name_prefix(registered, f'node_{registered}_1_77')), name)

    def test_nodes_name_bodies_by_a_type_the_prefix_understands(self):
        """Every literal type a node passes when naming bodies must lowercase to
        the node's registered type, or its bodies can't be found after reopening."""
        import re
        from pathlib import Path
        nodes_dir = Path(__file__).resolve().parent.parent / 'backend' / 'nodes'
        for path in sorted(nodes_dir.glob('*.py')):
            source = path.read_text(encoding='utf-8')
            registered = re.search(r'NODE_TYPE = "([^"]+)"', source)
            for literal in re.findall(r'generate_geometry_name\(\s*(?:node_type=)?"([^"]+)"', source):
                with self.subTest(file=path.name, literal=literal):
                    self.assertEqual(literal.lower(), registered.group(1).lower())

    def test_two_nodes_of_one_type_have_different_prefixes(self):
        self.assertNotEqual(geometry_name_prefix('Materializer', MATERIALIZER),
                            geometry_name_prefix('Materializer', OTHER))


class BodiesOfNodeTests(unittest.TestCase):
    def setUp(self):
        self.mine = [Body(generate_geometry_name('materializer', MATERIALIZER, 'Box', index=i)) for i in range(3)]
        self.theirs = [Body(generate_geometry_name('materializer', OTHER, 'Box', index=0)), Body('Body1')]
        self.bodies = self.mine + self.theirs

    def test_reopened_document_finds_bodies_by_name(self):
        handler, core = make_handler(self.bodies)  # nothing recorded: as after reopening a file
        found = handler._bodies_of_node(MATERIALIZER, 'Materializer')
        self.assertEqual(found, self.mine)
        self.assertEqual(core.node_body_names[MATERIALIZER], [b.name for b in self.mine], 'remembered for next time')

    def test_recorded_names_are_used_when_present(self):
        handler, _ = make_handler(self.bodies, registry={MATERIALIZER: [self.mine[0].name]})
        self.assertEqual(handler._bodies_of_node(MATERIALIZER, 'Materializer'), [self.mine[0]])

    def test_stale_record_falls_back_to_the_name_search(self):
        handler, _ = make_handler(self.bodies, registry={MATERIALIZER: ['gone_1', 'gone_2']})
        self.assertEqual(handler._bodies_of_node(MATERIALIZER, 'Materializer'), self.mine)

    def test_without_a_node_type_nothing_is_guessed(self):
        handler, _ = make_handler(self.bodies)
        self.assertEqual(handler._bodies_of_node(MATERIALIZER), [])

    def test_hiding_a_reopened_nodes_bodies_only_touches_its_own(self):
        handler, _ = make_handler(self.bodies)
        result = handler._set_node_visibility({'nodeId': MATERIALIZER, 'nodeType': 'Materializer', 'visible': False})
        self.assertEqual(result, {'success': True, 'matched': 3, 'changed': 3})
        self.assertTrue(all(not b.isVisible for b in self.mine))
        self.assertTrue(all(b.isVisible for b in self.theirs))

    def test_hiding_several_nodes_at_once_counts_only_real_changes(self):
        theirs = self.theirs[0]
        self.mine[0].isVisible = False  # already hidden
        handler, _ = make_handler(self.bodies)
        result = handler._set_nodes_visibility({'visible': False, 'nodes': [
            {'nodeId': MATERIALIZER, 'nodeType': 'Materializer'},
            {'nodeId': OTHER, 'nodeType': 'Materializer'}]})
        self.assertEqual((result['matched'], result['changed']), (4, 3))
        self.assertFalse(theirs.isVisible)
        self.assertTrue(self.theirs[1].isVisible, 'bodies Noodle did not make are left alone')

    def test_eye_state_reads_the_bodies(self):
        for body in self.mine:
            body.isVisible = False
        handler, _ = make_handler(self.bodies)
        result = handler._get_node_visibility({'nodeId': MATERIALIZER, 'nodeType': 'Materializer'})
        self.assertEqual((result['visible'], result['matched']), (False, 3))

    def test_a_node_with_no_bodies_reports_visible_and_matches_nothing(self):
        handler, _ = make_handler(self.bodies)
        result = handler._get_node_visibility({'nodeId': 'node_cube_generator_1_22', 'nodeType': 'cube_generator'})
        self.assertEqual((result['visible'], result['matched']), (True, 0))


if __name__ == '__main__':
    unittest.main()


class MaterializerNamingTests(unittest.TestCase):
    """Bodies must be named after the Materializer, even when a surface array
    placed the instances, or eye icons can't find them in a reopened document."""

    def test_bodies_carry_the_materializers_prefix_whatever_placed_the_instances(self):
        from unittest.mock import MagicMock
        from backend.nodes.collection_materializer import MaterializerNode
        node_id = 'node_Materializer_1762800000000_4711'
        instances = [{'transform': {'tx': float(i), 'ty': 0.0, 'tz': 0.0, 'sx': 1.0, 'sy': 1.0, 'sz': 1.0},
                      # What older surface arrays stored: a name built from the array's own id
                      'metadata': {'geometry_name': f'array_surface_spiral_999_Box_{i:03d}'}}
                     for i in range(3)]
        collection = {'source_geometries': [{'geometry': MagicMock(), 'geometry_name': 'Box'}], 'instances': instances}
        recorded = {}
        context = {'app': MagicMock(), 'base_feature': MagicMock(), 'node_id': node_id, 'node_body_names': recorded}
        MaterializerNode(node_id).execute({'collection': collection}, context)
        names = recorded[node_id]
        self.assertEqual(len(names), 3)
        prefix = geometry_name_prefix('Materializer', node_id)
        self.assertTrue(all(name.startswith(prefix) for name in names), names)
        self.assertEqual(len(set(names)), 3, 'names are unique')
