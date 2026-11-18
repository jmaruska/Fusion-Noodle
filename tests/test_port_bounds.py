"""Declared bounds on number inputs: what they say, and that the node specs use them sensibly."""
import re
import unittest
from tests import fusion_stub

from backend.contracts import PortSpec, PortType, bounds_problem  # noqa: E402

COUNT_LIKE = re.compile(r'^(count|count_.+|.+_count|strands|density|sides|octaves)$')


class BoundsMessageTests(unittest.TestCase):
    def test_messages(self):
        count = PortSpec("count_x", PortType.INTEGER, min_value=1, max_value=100)
        size = PortSpec("width", PortType.FLOAT, unit="length", min_value=0.001)
        bias = PortSpec("u_bias", PortType.FLOAT, label="U Bias", max_value=1.0)
        self.assertIsNone(bounds_problem(count, 50))
        self.assertEqual(bounds_problem(count, 500), "Count X must be between 1 and 100")
        self.assertEqual(bounds_problem(count, 2.5), "Count X must be a whole number")
        self.assertEqual(bounds_problem(size, 0), "Width must be at least 0.001 cm")
        self.assertEqual(bounds_problem(bias, 2), "U Bias must be at most 1")

    def test_values_it_leaves_to_the_node(self):
        port = PortSpec("strength", PortType.FLOAT, min_value=0)
        self.assertIsNone(bounds_problem(port, {'modifier_type': 'noise'}), 'a modifier is evaluated per instance')
        self.assertIsNone(bounds_problem(port, None))

    def test_every_number_port_must_hold_a_number(self):
        angle = PortSpec("tilt", PortType.FLOAT, label="Tilt")   # unbounded, still a number
        self.assertEqual(bounds_problem(angle, "45"), "Tilt must be a number")
        self.assertEqual(bounds_problem(angle, True), "Tilt must be a number")
        self.assertIsNone(bounds_problem(angle, -720))

    def test_hidden_ports_are_not_checked(self):
        port = PortSpec("inner_radius", PortType.FLOAT, min_value=0,
                        visible_when={'port': 'shape', 'values': ['sphere'], 'default': 'sphere'})
        self.assertIsNotNone(bounds_problem(port, -1, {'shape': 'sphere'}))
        self.assertIsNone(bounds_problem(port, -1, {'shape': 'linear'}))


class NodeSpecBoundsTests(unittest.TestCase):
    def setUp(self):
        self.nodes = fusion_stub.all_node_classes()

    def ports(self):
        for key, cls in sorted(self.nodes.items()):
            for port in cls.get_spec().inputs:
                yield cls, port

    def test_counts_are_whole_numbers(self):
        for cls, port in self.ports():
            if COUNT_LIKE.match(port.name):
                with self.subTest(node=cls.NODE_NAME, port=port.name):
                    self.assertEqual(port.port_type, PortType.INTEGER, 'a count must be an INTEGER port')

    def test_every_default_is_within_its_bounds(self):
        """Otherwise a node shows an error the moment it's added."""
        for cls, port in self.ports():
            if port.port_type in (PortType.FLOAT, PortType.INTEGER) and isinstance(port.default_value, (int, float)):
                with self.subTest(node=cls.NODE_NAME, port=port.name):
                    self.assertIsNone(bounds_problem(port, port.default_value))

    def test_bounds_are_ordered(self):
        for cls, port in self.ports():
            if port.min_value is not None and port.max_value is not None:
                with self.subTest(node=cls.NODE_NAME, port=port.name):
                    self.assertLess(port.min_value, port.max_value)


if __name__ == '__main__':
    unittest.main()
