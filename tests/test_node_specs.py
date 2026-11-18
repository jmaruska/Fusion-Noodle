"""Consistency checks across every registered node. These catch the class of bug
where a node declares something in its spec that its code never handles."""
import ast
import inspect
import unittest
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()

from backend.contracts import PortType  # noqa: E402
from backend.nodes.menu_config import MENU_SECTIONS  # noqa: E402


def string_constants_outside_spec(module):
    """Every string literal in a module, except those inside get_spec() or a shared spec
    builder (a function named *_ports), where a port name is declared rather than read."""
    tree = ast.parse(inspect.getsource(module))
    spec_ranges = [(n.lineno, n.end_lineno) for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and (n.name == 'get_spec' or n.name.endswith('_ports'))]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not any(start <= node.lineno <= end for start, end in spec_ranges):
                found.add(node.value)
    return found


def code_strings(cls):
    """String literals a node's code can read: its own module, its base classes' modules, and
    the backend utility modules those import (shared code such as field_sources)."""
    import importlib
    modules = []
    for klass in cls.__mro__:
        module = inspect.getmodule(klass)
        if module and module.__name__.startswith('backend.') and module not in modules:
            modules.append(module)
    for module in list(modules):
        for node in ast.walk(ast.parse(inspect.getsource(module))):
            if isinstance(node, ast.ImportFrom) and node.level and (node.module or '').startswith('utilities.'):
                package = module.__name__.rsplit('.', node.level)[0]
                imported = importlib.import_module(f'{package}.{node.module}')
                if imported not in modules:
                    modules.append(imported)
    found = set()
    for module in modules:
        found |= string_constants_outside_spec(module)
    return found


class NodeSpecTests(unittest.TestCase):
    def test_nodes_are_registered(self):
        self.assertGreaterEqual(len(NODES), 30)

    def test_port_names_are_unique_per_node(self):
        for node_type, cls in NODES.items():
            spec = cls.get_spec()
            for ports, kind in ((spec.inputs, 'input'), (spec.outputs, 'output')):
                names = [p.name for p in ports]
                with self.subTest(node=node_type, kind=kind):
                    self.assertEqual(len(names), len(set(names)), f'duplicate {kind} port names')

    def test_enum_ports_are_well_formed(self):
        for node_type, cls in NODES.items():
            for port in cls.get_spec().inputs:
                if port.port_type != PortType.ENUM:
                    continue
                with self.subTest(node=node_type, port=port.name):
                    options = port.enum_options or []
                    self.assertTrue(options, 'enum port has no options')
                    self.assertIn(port.default_value, options, 'default is not one of the options')
                    labels = getattr(port, 'enum_labels', None) or {}
                    self.assertFalse(set(labels) - set(options), 'label for an option that does not exist')

    def test_enum_options_are_handled_by_the_node(self):
        """Each option a dropdown offers must appear in the node's code outside the
        spec. A lookup table keyed 'Circular' while the spec says 'circular' fails here."""
        for node_type, cls in NODES.items():
            enum_ports = [p for p in cls.get_spec().inputs if p.port_type == PortType.ENUM]
            if not enum_ports:
                continue
            handled = code_strings(cls)
            for port in enum_ports:
                for option in port.enum_options or []:
                    with self.subTest(node=node_type, port=port.name, option=option):
                        self.assertIn(option, handled, 'option is offered but never referenced in code')

    def test_declared_inputs_are_read_by_the_node(self):
        """An input the node never mentions is a control that does nothing."""
        ignore_types = {PortType.SPACER}
        for node_type, cls in NODES.items():
            referenced = code_strings(cls)
            for port in cls.get_spec().inputs:
                if port.port_type in ignore_types:
                    continue
                with self.subTest(node=node_type, port=port.name):
                    self.assertIn(port.name, referenced, 'input is declared but never read')

    def test_units_are_known_and_only_on_numbers(self):
        numeric = {PortType.FLOAT, PortType.INTEGER, PortType.VECTOR3}
        for node_type, cls in NODES.items():
            for port in cls.get_spec().inputs:
                if port.unit is None:
                    continue
                with self.subTest(node=node_type, port=port.name):
                    self.assertIn(port.unit, ('length', 'angle'))
                    self.assertIn(port.port_type, numeric)
                    self.assertEqual(port.to_dict().get('unit'), port.unit)

    def test_labels_do_not_repeat_the_unit(self):
        """The input shows the unit as a suffix, so the label must not carry it too."""
        for node_type, cls in NODES.items():
            for port in cls.get_spec().inputs:
                if port.unit:
                    with self.subTest(node=node_type, port=port.name):
                        self.assertNotIn('°', port.label)
                        self.assertNotIn('(cm)', port.label)

    def test_validate_accepts_or_rejects_cleanly(self):
        """validate() must return a list for default inputs, never raise."""
        for node_type, cls in NODES.items():
            spec = cls.get_spec()
            defaults = {p.name: p.default_value for p in spec.inputs if p.default_value is not None}
            with self.subTest(node=node_type):
                result = cls(f'test_{node_type}').validate(defaults)
                self.assertIsInstance(result, list)


class MenuTests(unittest.TestCase):
    def test_menu_only_lists_registered_nodes(self):
        for section, node_types in MENU_SECTIONS.items():
            for node_type in node_types:
                with self.subTest(section=section, node=node_type):
                    self.assertIn(node_type, NODES)

    def test_every_node_is_in_exactly_one_section(self):
        listed = [t for types in MENU_SECTIONS.values() for t in types]
        self.assertEqual(len(listed), len(set(listed)), 'a node appears in two menu sections')


if __name__ == '__main__':
    unittest.main()


class WideNodeTests(unittest.TestCase):
    """A node is wide when it has a dropdown, or its title wraps beside the eye icon.
    A dropdown is checked here; title wrapping depends on the font, so it's judged by eye
    and marked in the node (Uniform Effector, for one)."""

    def test_a_node_with_a_dropdown_is_wide(self):
        from tests import fusion_stub
        from backend.contracts import PortType
        for key, cls in sorted(fusion_stub.all_node_classes().items()):
            spec = cls.get_spec()
            dropdowns = [p.name for p in spec.inputs if p.port_type == PortType.ENUM and p.show_input_field]
            if dropdowns:
                with self.subTest(node=cls.NODE_NAME, dropdowns=dropdowns):
                    self.assertTrue(spec.wide, 'a node with a dropdown is wide')
