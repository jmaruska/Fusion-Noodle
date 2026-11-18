"""The working copy: the graph as edited since the last Generate.
The document here is a stand-in that stores attributes in a dict, so these tests
cover our bookkeeping. Whether Fusion keeps an attribute written during a save
is checked in Fusion."""
import json
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend import graph_format  # noqa: E402
from backend.handlers.persistence_handler import PersistenceHandler  # noqa: E402


class FakeAttribute:
    def __init__(self, store, key, value):
        self._store, self._key, self.value = store, key, value

    def deleteMe(self):
        self._store.pop(self._key, None)
        return True


class FakeAttributes:
    def __init__(self):
        self.store = {}
        self.writes = 0

    def itemByName(self, group, name):
        return self.store.get((group, name))

    def add(self, group, name, value):
        self.writes += 1
        self.store[(group, name)] = FakeAttribute(self.store, (group, name), value)
        return self.store[(group, name)]


class FakeDesign:
    def __init__(self, component_id):
        self.rootComponent = type('Root', (), {})()
        self.rootComponent.id = component_id
        self.rootComponent.attributes = FakeAttributes()


def graph(width=2):
    return {'nodes': [{'id': 'n1', 'selected': True,
                       'data': {'nodeType': 'cube_generator', 'currentInputs': {'width': width}}}],
            'edges': []}


def make_handler(design):
    handler = PersistenceHandler.__new__(PersistenceHandler)
    handler.app = fusion_stub.FakeApp()
    handler._working_graphs = {}
    handler.core = type('Core', (), {'version': '1.0.0', 'design': design, '_check_design': lambda self: True})()
    handler._scan_document_for_noodle_reactflow_states = lambda: []
    return handler


class WorkingGraphTests(unittest.TestCase):
    def setUp(self):
        self.design = FakeDesign('doc-A')
        self.handler = make_handler(self.design)
        self.attributes = self.design.rootComponent.attributes

    def test_an_edit_is_kept_in_memory_and_not_written_to_the_document(self):
        self.assertTrue(self.handler._update_working_graph({'reactFlowState': graph(5)})['success'])
        self.assertEqual(self.attributes.writes, 0)
        working = self.handler.working_graph(self.design)
        self.assertEqual(working['nodes'][0]['data']['currentInputs']['width'], 5)
        self.assertNotIn('selected', working['nodes'][0])
        self.assertEqual(working['noodle']['format'], graph_format.GRAPH_FORMAT)

    def test_saving_the_document_writes_the_working_copy_once(self):
        self.handler._update_working_graph({'reactFlowState': graph(5)})
        self.assertTrue(self.handler.flush_working_graph(self.design))
        self.assertFalse(self.handler.flush_working_graph(self.design), 'unchanged copy must not be rewritten')
        self.assertEqual(self.attributes.writes, 1)
        self.handler._update_working_graph({'reactFlowState': graph(6)})
        self.assertTrue(self.handler.flush_working_graph(self.design))
        self.assertEqual(self.attributes.writes, 2)
        self.assertEqual(len(self.attributes.store), 1)

    def test_nothing_is_written_when_there_is_no_working_copy(self):
        self.assertFalse(self.handler.flush_working_graph(self.design))
        self.assertEqual(self.attributes.writes, 0)

    def test_a_reopened_document_restores_the_working_copy_from_the_document(self):
        self.handler._update_working_graph({'reactFlowState': graph(7)})
        self.handler.flush_working_graph(self.design)
        fresh = make_handler(self.design)  # a new session: memory is empty
        working = fresh.working_graph(self.design)
        self.assertEqual(working['nodes'][0]['data']['currentInputs']['width'], 7)
        self.assertFalse(fresh.flush_working_graph(self.design), 'already in the document')

    def test_each_document_has_its_own_working_copy(self):
        other = FakeDesign('doc-B')
        self.handler._update_working_graph({'reactFlowState': graph(5)})
        self.assertIsNone(self.handler.working_graph(other))

    def test_generate_or_clear_removes_it_from_memory_and_document(self):
        self.handler._update_working_graph({'reactFlowState': graph(5)})
        self.handler.flush_working_graph(self.design)
        self.handler.clear_working_graph(self.design)
        self.assertIsNone(self.handler.working_graph(self.design))
        self.assertEqual(self.attributes.store, {})

    def test_an_empty_canvas_is_not_kept(self):
        self.handler._update_working_graph({'reactFlowState': graph(5)})
        self.handler._update_working_graph({'reactFlowState': {'nodes': [], 'edges': []}})
        self.assertIsNone(self.handler.working_graph(self.design))

    def test_non_graphs_are_refused(self):
        self.assertFalse(self.handler._update_working_graph({'reactFlowState': {'hello': 1}})['success'])

    def test_loading_prefers_the_working_copy_and_says_so(self):
        generated = graph(2)
        self.handler._scan_document_for_noodle_reactflow_states = lambda: [(None, generated)]
        plain = self.handler._scan_document({})
        self.assertNotIn('workingCopy', plain)
        self.assertTrue(plain['hasGeneratedGraph'])
        self.handler._update_working_graph({'reactFlowState': graph(9)})
        loaded = self.handler._scan_document({})
        self.assertTrue(loaded['workingCopy'])
        self.assertEqual(loaded['reactFlowStates'][0]['nodes'][0]['data']['currentInputs']['width'], 9)

    def test_discard_returns_the_generated_graph(self):
        generated = graph(2)
        self.handler._scan_document_for_noodle_reactflow_states = lambda: [(None, generated)]
        self.handler._update_working_graph({'reactFlowState': graph(9)})
        result = self.handler._discard_working_graph({})
        self.assertEqual(result['reactFlowStates'], [generated])
        self.assertIsNone(self.handler.working_graph(self.design))


if __name__ == '__main__':
    unittest.main()
