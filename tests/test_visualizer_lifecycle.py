"""The visualizer's dots exist only while the palette is open. The design and its
graphics groups here are stand-ins; whether Fusion removes the dots is checked in Fusion."""
import unittest
from unittest.mock import MagicMock, patch
from tests import fusion_stub
fusion_stub.install()

from backend.core import Application  # noqa: E402
from backend.handlers.graph_handler import GraphHandler  # noqa: E402
from backend.visualizer import GROUP_ID, VisualizerRenderer  # noqa: E402


class Group:
    def __init__(self, groups, group_id):
        self.groups, self.id, self.isValid = groups, group_id, True

    def deleteMe(self):
        self.groups.items.remove(self)


class Groups:
    def __init__(self, *ids):
        self.items = [Group(self, i) for i in ids]

    @property
    def count(self):
        return len(self.items)

    def item(self, i):
        return self.items[i]


def document(*group_ids):
    doc = MagicMock()
    doc.design.rootComponent.customGraphicsGroups = Groups(*group_ids)
    return doc


class ClearEverywhereTests(unittest.TestCase):
    def test_dots_are_removed_from_every_open_document_and_nothing_else(self):
        docs = [document(GROUP_ID, 'someone_elses_overlay'), document(GROUP_ID), document()]
        app = MagicMock()
        app.documents.count = len(docs)
        app.documents.item = lambda i: docs[i]
        with patch('adsk.fusion.FusionDocument.cast', side_effect=lambda d: d):
            removed = VisualizerRenderer(app).clear_everywhere()
        self.assertEqual(removed, 2)
        self.assertEqual([g.id for g in docs[0].design.rootComponent.customGraphicsGroups.items], ['someone_elses_overlay'])
        self.assertEqual(docs[1].design.rootComponent.customGraphicsGroups.count, 0)


class PaletteLifecycleTests(unittest.TestCase):
    def make(self):
        app = Application.__new__(Application)
        app.fusion_app = fusion_stub.FakeApp()
        app.palette_open = True
        handler = GraphHandler.__new__(GraphHandler)
        handler.app = app.fusion_app
        handler.core = app
        return app, handler

    def test_closing_clears_and_blocks_late_redraws(self):
        app, handler = self.make()
        with patch.object(VisualizerRenderer, 'clear_everywhere', return_value=3) as clear:
            self.assertEqual(app.palette_closed(), 3)
        clear.assert_called_once()
        self.assertFalse(app.palette_open)
        with patch.object(VisualizerRenderer, 'draw') as draw:
            result = handler._update_visualizer({'visualized': ['eff'], 'nodes': [], 'edges': []})
        draw.assert_not_called()
        self.assertEqual(result['points'], 0)

    def test_a_failure_to_clear_does_not_stop_the_close(self):
        app, _ = self.make()
        with patch.object(VisualizerRenderer, 'clear_everywhere', side_effect=RuntimeError('gone')):
            self.assertEqual(app.palette_closed(), 0)
        self.assertFalse(app.palette_open)


if __name__ == '__main__':
    unittest.main()


class RedrawAfterCommandTests(unittest.TestCase):
    """Fusion rolls back graphics drawn during a command when it finishes, so the
    last visualizer request is redrawn once any command ends."""

    def make(self):
        app = Application.__new__(Application)
        app.fusion_app = fusion_stub.FakeApp()
        app.palette_open = True
        handler = GraphHandler.__new__(GraphHandler)
        handler.app = app.fusion_app
        handler.core = app
        handler._last_visualizer_request = None
        app.handlers = {'graph': handler}
        return app, handler

    def test_a_finished_command_redraws_the_last_request(self):
        app, handler = self.make()
        request = {'visualized': ['eff'], 'nodes': [], 'edges': []}
        handler._last_visualizer_request = request
        with patch.object(GraphHandler, '_update_visualizer') as update:
            handler._on_command_terminated('MoveCommand')
        update.assert_called_once_with(request)

    def test_nothing_redraws_without_an_active_visualizer_or_after_generate(self):
        app, handler = self.make()
        with patch.object(GraphHandler, '_update_visualizer') as update:
            handler._on_command_terminated('MoveCommand')
            handler._last_visualizer_request = {'visualized': ['eff']}
            handler._on_command_terminated('jm_NoodleGenerateCommand')
        update.assert_not_called()

    def test_closing_the_palette_forgets_the_request(self):
        app, handler = self.make()
        handler._last_visualizer_request = {'visualized': ['eff']}
        with patch.object(VisualizerRenderer, 'clear_everywhere', return_value=0):
            app.palette_closed()
        with patch.object(GraphHandler, '_update_visualizer') as update:
            handler._on_command_terminated('MoveCommand')
        update.assert_not_called()

    def test_clearing_the_visualizer_forgets_the_request(self):
        _, handler = self.make()
        handler._last_visualizer_request = {'visualized': ['eff']}
        with patch.object(VisualizerRenderer, 'clear', return_value=0):
            handler._clear_visualizer({})
        self.assertIsNone(handler._last_visualizer_request)
