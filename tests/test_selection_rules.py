"""The selection handler's bookkeeping: one pending pick at a time, cancel, expiry.
The parts that read Fusion's active selection are replaced, so nothing here
depends on what Fusion would return."""
import time
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.handlers.selection_handler import SelectionHandler  # noqa: E402


def make_handler():
    handler = SelectionHandler.__new__(SelectionHandler)
    handler.app = fusion_stub.FakeApp()
    handler.active_selections = {}

    def start(kind):
        def _start(data):
            handler.active_selections[f'{kind}_selection_pending'] = {
                'node_id': data['nodeId'], 'timestamp': int(time.time() * 1000)}
            return {'success': True, 'selection_active': True}
        return _start

    for kind in ('surface', 'body', 'point', 'curve'):
        setattr(handler, f'_select_{kind}', start(kind))
        setattr(handler, f'_check_{kind}_selection', lambda data: {'success': True, 'selection_pending': True})
    return handler


class SelectionRuleTests(unittest.TestCase):
    def setUp(self):
        self.handler = make_handler()
        self.a = {'nodeId': 'A', 'portName': 'surface'}
        self.b = {'nodeId': 'B', 'portName': 'body'}

    def test_owner_can_poll_its_pending_selection(self):
        self.handler.handle('selectSurface', self.a)
        self.assertTrue(self.handler.handle('checkSurfaceSelection', self.a).get('selection_pending'))

    def test_starting_a_second_selection_cancels_the_first(self):
        self.handler.handle('selectSurface', self.a)
        self.handler.handle('selectBody', self.b)
        self.assertFalse(self.handler.handle('checkSurfaceSelection', self.a)['success'])
        self.assertTrue(self.handler.handle('checkBodySelection', self.b)['success'])

    def test_another_node_cannot_take_a_pending_selection(self):
        self.handler.handle('selectSurface', self.a)
        other = {'nodeId': 'Z', 'portName': 'surface'}
        self.assertFalse(self.handler.handle('checkSurfaceSelection', other)['success'])

    def test_cancel_clears_pending_state(self):
        self.handler.handle('selectSurface', self.a)
        self.assertTrue(self.handler.handle('cancelSelection', {})['success'])
        self.assertEqual(self.handler.active_selections, {})
        self.assertFalse(self.handler.handle('checkSurfaceSelection', self.a)['success'])

    def test_a_late_cancel_from_a_replaced_node_keeps_the_new_pick(self):
        self.handler.handle('selectSurface', self.a)
        self.handler.handle('selectBody', self.b)
        self.handler.handle('cancelSelection', {'nodeId': 'A'})
        self.assertTrue(self.handler.handle('checkBodySelection', self.b)['success'])

    def test_the_picking_node_can_cancel_its_own_pick(self):
        self.handler.handle('selectBody', self.b)
        self.handler.handle('cancelSelection', {'nodeId': 'B'})
        self.assertEqual(self.handler.active_selections, {})

    def test_stale_selection_times_out(self):
        self.handler.handle('selectSurface', self.a)
        self.handler.active_selections['surface_selection_pending']['timestamp'] -= \
            SelectionHandler.SELECTION_TIMEOUT_MS + 1000
        result = self.handler.handle('checkSurfaceSelection', self.a)
        self.assertFalse(result['success'])
        self.assertIn('timed out', result['error'])

    def test_completed_selection_clears_pending_state(self):
        self.handler.handle('selectBody', self.b)
        self.handler._check_body_selection = lambda data: {
            'success': True, 'selection_complete': True, 'body_data': {'body_name': 'x'}}
        self.handler.handle('checkBodySelection', self.b)
        self.assertNotIn('body_selection_pending', self.handler.active_selections)

    def test_unknown_action_is_an_error(self):
        self.assertFalse(self.handler.handle('selectBrep', {})['success'])


if __name__ == '__main__':
    unittest.main()
