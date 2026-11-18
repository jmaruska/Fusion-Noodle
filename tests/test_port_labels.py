"""Messages for the user name a port the way the node shows it, never by its internal name."""
import re
import unittest
from tests import fusion_stub

NODES = list(fusion_stub.all_node_classes().values())

from backend.contracts import PortSpec, PortType, port_label  # noqa: E402


class PortLabelTests(unittest.TestCase):

    def test_a_ports_own_label_wins(self):
        self.assertEqual(port_label('direction', 'X Axis'), 'X Axis')

    def test_a_port_without_a_label_shows_its_name_in_title_case(self):
        self.assertEqual(port_label('count_x'), 'Count X')
        self.assertEqual(port_label('inner_radius'), 'Inner Radius')

    def test_title_case_matches_the_palette(self):
        # ui/src/utils/nodeSpec.js uppercases the first character of each word and leaves
        # the rest alone; Python's str.title() would turn "2d" into "2D" and "UV" into "Uv".
        self.assertEqual(port_label('size_2d'), 'Size 2d')
        self.assertEqual(port_label('UV_count'), 'UV Count')

    def test_the_palette_receives_the_same_label(self):
        self.assertEqual(PortSpec('count_x', PortType.INTEGER).to_dict()['label'], 'Count X')
        self.assertEqual(PortSpec('rx', PortType.FLOAT, label='Rotate X').to_dict()['label'], 'Rotate X')

    def test_a_node_finds_its_ports_label(self):
        grid = next(cls for cls in NODES if cls.NODE_TYPE == 'Array_2D_Grid')
        self.assertEqual(grid.port_label('count_x'), 'Count X')
        self.assertEqual(grid.port_label('array_type'), 'Type')

    def test_validation_messages_do_not_name_ports_by_their_internal_name(self):
        bad_values = ('not a number', -1e9, 1e9, 0, {})
        for cls in NODES:
            spec = cls.get_spec()
            names = [p.name for p in spec.inputs if p.port_type != PortType.SPACER]
            node = cls('n1')
            for name in names:
                if '_' not in name:
                    continue  # a one-word name like "radius" reads as an ordinary word
                pattern = re.compile(r'\b' + re.escape(name) + r'\b')
                for value in bad_values:
                    try:
                        errors = node.validate({name: value})
                    except Exception:
                        continue  # a value of the wrong kind may not get as far as a message
                    for message in errors:
                        with self.subTest(node=cls.NODE_TYPE, port=name, value=value):
                            self.assertIsNone(pattern.search(str(message)), message)


if __name__ == '__main__':
    unittest.main()
