"""Every message the palette can send must reach a handler.

Each handler declares the messages it accepts in a class-level ACTIONS table, and
the core builds its routing table from those. These tests check that the tables
are sound and that the palette only sends messages the add-in knows.
"""
import re
import unittest
from pathlib import Path
from tests import fusion_stub
fusion_stub.install()

from backend.core import Application  # noqa: E402
from backend.handlers.graph_handler import GraphHandler  # noqa: E402
from backend.handlers.geometry_handler import GeometryHandler  # noqa: E402
from backend.handlers.selection_handler import SelectionHandler  # noqa: E402
from backend.handlers.persistence_handler import PersistenceHandler  # noqa: E402
from backend.handlers.node_registry_handler import NodeRegistryHandler  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDLERS = {
    'node_registry': NodeRegistryHandler,
    'graph': GraphHandler,
    'geometry': GeometryHandler,
    'selection': SelectionHandler,
    'persistence': PersistenceHandler,
}
ROUTES = Application.build_routes(HANDLERS)


class RoutingTableTests(unittest.TestCase):
    def test_every_declared_message_is_routed_to_its_handler(self):
        for name, handler in HANDLERS.items():
            self.assertTrue(handler.ACTIONS, f'{name} declares no messages')
            for action in handler.ACTIONS:
                with self.subTest(handler=name, action=action):
                    self.assertEqual(ROUTES[action], name)

    def test_every_declared_message_names_a_real_method(self):
        for name, handler in HANDLERS.items():
            for action, method_name in handler.ACTIONS.items():
                with self.subTest(handler=name, action=action):
                    self.assertTrue(callable(getattr(handler, method_name, None)))

    def test_two_handlers_cannot_claim_the_same_message(self):
        class Other:
            ACTIONS = {'generateGeometry': 'run'}

            def run(self, data):
                return {}
        with self.assertRaises(RuntimeError) as caught:
            Application.build_routes({'graph': GraphHandler, 'other': Other})
        self.assertIn('generateGeometry', str(caught.exception))

    def test_a_handler_cannot_claim_a_core_message(self):
        class Other:
            ACTIONS = {'palette_ready': 'run'}

            def run(self, data):
                return {}
        with self.assertRaises(RuntimeError):
            Application.build_routes({'other': Other})

    def test_a_message_naming_a_missing_method_is_refused(self):
        class Broken:
            ACTIONS = {'doThing': '_not_there'}
        with self.assertRaises(RuntimeError) as caught:
            Application.build_routes({'broken': Broken})
        self.assertIn('_not_there', str(caught.exception))

    def test_core_messages_name_real_methods(self):
        for action, method_name in Application.SYSTEM_ACTIONS.items():
            with self.subTest(action=action):
                self.assertTrue(callable(getattr(Application, method_name, None)))


class DispatchTests(unittest.TestCase):
    """A message travels core -> handler -> method through the built tables."""

    def make_app(self):
        app = Application.__new__(Application)
        app.fusion_app = fusion_stub.FakeApp()
        calls = []

        class Recorder:
            ACTIONS = {'ping': '_ping'}

            def handle(self, action, data):
                return getattr(self, self.ACTIONS[action])(data)

            def _ping(self, data):
                calls.append(data)
                return {'success': True, 'echo': data.get('x')}

        app.handlers = {'recorder': Recorder()}
        app._routes = Application.build_routes(app.handlers)
        return app, calls

    def test_declared_message_reaches_its_method(self):
        app, calls = self.make_app()
        self.assertEqual(app.handle_message('ping', {'x': 7}), {'success': True, 'echo': 7})
        self.assertEqual(calls, [{'x': 7}])

    def test_undeclared_message_is_reported_as_unknown(self):
        app, _ = self.make_app()
        result = app.handle_message('pong', {})
        self.assertFalse(result['success'])
        self.assertIn('Unknown action', result['error'])


class PaletteActionTests(unittest.TestCase):
    """Message names written literally in the palette source must be known to the add-in."""

    PATTERNS = [
        r"sendMessage\(\s*'([A-Za-z_]+)'",
        r"fusionSendData\(\s*'([A-Za-z_]+)'",
        r"callAddin\(\s*'([A-Za-z_]+)'",
        r"sendBackendMessage\(\s*'([A-Za-z_]+)'",
        r"action:\s*'([A-Za-z_]+)'",
    ]

    def test_palette_messages_are_known(self):
        known = set(ROUTES) | set(Application.SYSTEM_ACTIONS)
        found = {}
        for path in list((REPO_ROOT / 'ui' / 'src').rglob('*.js')) + list((REPO_ROOT / 'ui' / 'src').rglob('*.jsx')):
            text = path.read_text(encoding='utf-8')
            for pattern in self.PATTERNS:
                for action in re.findall(pattern, text):
                    found.setdefault(action, path.name)
        self.assertGreater(len(found), 8, 'no palette messages found; the patterns need updating')
        for action, filename in sorted(found.items()):
            with self.subTest(action=action, file=filename):
                self.assertIn(action, known, 'the palette sends a message the add-in does not accept')


if __name__ == '__main__':
    unittest.main()


class BaseFeatureRecreationTests(unittest.TestCase):
    """Recreating the Base Feature must not fail because of how a handler stores it."""

    def test_recreate_succeeds_with_a_read_only_handler_property(self):
        from backend.core import Application
        from backend.handlers.graph_handler import GraphHandler

        class Feature:
            name = 'Noodle_Geometry'
            def deleteMe(self):
                return True

        class BaseFeatures:
            def __init__(self):
                self.items = []
            @property
            def count(self):
                return len(self.items)
            def item(self, i):
                return self.items[i]
            def add(self):
                feature = Feature()
                self.items.append(feature)
                return feature

        class Design:
            def __init__(self):
                features = type('F', (), {})()
                features.baseFeatures = BaseFeatures()
                self.rootComponent = type('R', (), {'features': features})()

        app = Application.__new__(Application)
        app.fusion_app = None
        app.design = Design()
        app.base_feature = None
        graph = GraphHandler.__new__(GraphHandler)
        graph.core = app
        graph.context = {}
        app.handlers = {'graph': graph}

        self.assertTrue(app._recreate_base_feature())
        self.assertIs(graph.base_feature, app.base_feature)
