"""The progress helper's own rules: throttling, cancel, and never failing a Generate.
The dialog here is a stand-in that records what it is told; how Fusion's real
dialog looks and behaves is checked in Fusion."""
import unittest
from tests import fusion_stub
fusion_stub.install()

from backend.utilities.progress import GenerateProgress, GenerationCancelled  # noqa: E402


class RecordingDialog:
    def __init__(self):
        self.shown = None
        self.hidden = False
        self.wasCancelled = False
        self.messages = []
        self.maximumValue = None
        self.progressValue = None

    def show(self, title, message, minimum, maximum, delay):
        self.shown = (title, message, minimum, maximum, delay)

    def hide(self):
        self.hidden = True

    @property
    def message(self):
        return self.messages[-1] if self.messages else ''

    @message.setter
    def message(self, value):
        self.messages.append(value)


class RecordingUI:
    def __init__(self, fail=False):
        self.dialog = RecordingDialog()
        self.fail = fail

    def createProgressDialog(self):
        if self.fail:
            raise RuntimeError('no dialog available')
        return self.dialog


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make(ui=None, enabled=True):
    clock = Clock()
    progress = GenerateProgress(ui, enabled=enabled, clock=clock)
    progress._pump_events = lambda: None  # doEvents only exists inside Fusion
    return progress, clock


class ProgressTests(unittest.TestCase):
    def test_dialog_opens_with_a_delay_and_closes(self):
        ui = RecordingUI()
        progress, _ = make(ui)
        progress.start(4)
        self.assertEqual(ui.dialog.shown[3], 4)
        self.assertGreater(ui.dialog.shown[4], 0, 'short Generates should not flash a dialog')
        progress.finish()
        progress.finish()  # safe to call twice
        self.assertTrue(ui.dialog.hidden)

    def test_node_progress_names_the_node(self):
        ui = RecordingUI()
        progress, _ = make(ui)
        progress.start(3)
        progress.node(2, 3, 'Materializer')
        self.assertIn('Materializer (2 of 3)', ui.dialog.message)

    def test_steps_are_throttled(self):
        ui = RecordingUI()
        progress, clock = make(ui)
        progress.start(1)
        progress.node(1, 1, 'Materializer')
        before = len(ui.dialog.messages)
        for done in range(1, 500):
            progress.step(done, 1000)  # clock does not advance
        self.assertEqual(len(ui.dialog.messages), before)
        clock.now += 1.0
        progress.step(500, 1000)
        self.assertEqual(len(ui.dialog.messages), before + 1)
        self.assertIn('500 of 1000', ui.dialog.message)

    def test_cancel_raises_inside_the_loop(self):
        ui = RecordingUI()
        progress, clock = make(ui)
        progress.start(1)
        progress.node(1, 1, 'Materializer')
        ui.dialog.wasCancelled = True
        clock.now += GenerateProgress.PUMP_INTERVAL_S + 0.1
        with self.assertRaises(GenerationCancelled):
            progress.step(10, 100)
        self.assertTrue(progress.cancelled)

    def test_events_are_pumped_rarely_but_the_bar_keeps_moving(self):
        """Pumping events redraws Fusion's viewport, so it is kept to every couple of seconds."""
        ui = RecordingUI()
        progress, clock = make(ui)
        pumps = []
        progress._pump_events = lambda: pumps.append(clock.now)
        progress.start(1)
        progress.node(1, 1, 'Materializer')
        for done in range(1, 41):  # 4 seconds of work, an item every 0.1 s
            clock.now += 0.1
            progress.step(done, 100)
        self.assertLessEqual(len(pumps), 3)
        self.assertGreaterEqual(ui.dialog.progressValue, 35)  # Values still updated every 0.5 s

    def test_disabled_progress_does_nothing(self):
        ui = RecordingUI()
        progress, _ = make(ui, enabled=False)
        progress.start(5)
        progress.node(1, 5, 'Box')
        progress.step(1, 10)
        progress.finish()
        self.assertIsNone(ui.dialog.shown)

    def test_a_dialog_that_cannot_open_never_fails_the_generate(self):
        progress, _ = make(RecordingUI(fail=True))
        progress.start(5)
        progress.node(1, 5, 'Box')
        progress.step(1, 10)
        progress.check_cancelled()
        progress.finish()

    def test_no_ui_at_all_is_fine(self):
        progress, _ = make(None)
        progress.start(5)
        progress.step(1, 10)
        progress.finish()



class GenerateTimingTests(unittest.TestCase):
    """The timing block written after each Generate."""

    def test_report_lists_each_node_with_its_output_size(self):
        from backend.handlers.graph_handler import _timing_report, _output_size
        from backend.contracts import CollectionSpec, CollectionInstanceSpec, NoodleAttributes
        instance = CollectionInstanceSpec(instance_id='i', source_geometry_id='g', transform=NoodleAttributes(), metadata={})
        grid = CollectionSpec(collection_type='geometry_collection', collection_id='c',
                              instances=[instance] * 3, source_geometries=[])
        report = _timing_report([
            ('Box', 0.012, _output_size({'geometry': object()})),
            ('Array 2D Grid', 0.4, _output_size({'collection': grid})),
            ('Materializer', 4.1, _output_size({'geometry': {'instance_count': 1600}})),
        ], 4.6)
        self.assertEqual(report.splitlines(), [
            'Generate ran 3 nodes in 4.60 s',
            '  Box: 0.01 s',
            '  Array 2D Grid: 0.40 s (3 instances)',
            '  Materializer: 4.10 s (1600 bodies)',
        ])


if __name__ == '__main__':
    unittest.main()
