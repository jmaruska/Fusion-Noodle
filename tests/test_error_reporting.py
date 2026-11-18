"""What the user sees when a node fails: the node's own reason, not a generic one."""
import unittest
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()

from backend.enforcement import SpecificationError  # noqa: E402
from backend.contracts import bounds_problem  # noqa: E402


def all_problems(node, inputs):
    """What a node rejects before running: declared bounds first, then its own validate()."""
    bounds = [problem for port in node.get_spec().inputs if port.name in inputs
              for problem in [bounds_problem(port, inputs[port.name], inputs)] if problem]
    return bounds + node.validate(inputs)
from backend.utilities import log_utils  # noqa: E402
from backend.specification import LogLevel  # noqa: E402


class NodeFailureMessageTests(unittest.TestCase):
    def setUp(self):
        self.context = {'app': fusion_stub.FakeApp()}

    def test_logged_reason_replaces_generic_none_error(self):
        node = NODES['body_instance']('n1')
        node._resolve_body_from_token = lambda data, app: None
        with self.assertRaises(SpecificationError) as caught:
            node.execute({'body': {'body_name': 'Bracket', 'entity_token': 'x'}}, self.context)
        message = str(caught.exception)
        self.assertIn('Bracket', message)
        self.assertNotIn('cannot be None', message)

    def test_validation_errors_are_plain_sentences(self):
        with self.assertRaises(SpecificationError) as caught:
            NODES['scale_xyz']('n1').execute({'scale_x': 0, 'scale_y': 1, 'scale_z': 1}, self.context)
        message = str(caught.exception)
        self.assertIn('Scale X', message)  # named as the node shows it
        self.assertFalse(message.startswith('['), 'error should not be a Python list repr')

    def test_modifier_wired_into_a_number_input_is_explained(self):
        with self.assertRaises(SpecificationError) as caught:
            NODES['cube_generator']('n1').execute({'width': {'modifier_type': 'random'}}, self.context)
        self.assertIn('modifier', str(caught.exception).lower())
        self.assertIn("'Width'", str(caught.exception))

    def test_materializer_refuses_too_many_instances(self):
        cls = NODES['materializer']
        collection = {'source_geometries': [{'geometry': object()}], 'instances': [{}] * (cls.MAX_BODIES + 1)}
        with self.assertRaises(SpecificationError) as caught:
            cls('n1').execute({'collection': collection}, self.context)
        self.assertIn(str(cls.MAX_BODIES), str(caught.exception))


class ValidationRuleTests(unittest.TestCase):
    def test_scale_xyz_rejects_zero_and_negative(self):
        errors = all_problems(NODES['scale_xyz']('n'), {'scale_x': 0, 'scale_y': -1, 'scale_z': 2})
        self.assertEqual(len(errors), 2)

    def test_surface_grid_caps_counts(self):
        node = NODES['array_surface_grid']('n')
        errors = all_problems(node, {'collection': {}, 'surface': {}, 'count_u': 101, 'count_v': 5})
        self.assertTrue(any('Count U' in e and '100' in e for e in errors))

    def test_array_path_caps_count(self):
        cls = NODES['array_path']
        errors = cls('n').validate({'collection': {}, 'curve': {'entity_token': 't'},
                                    'mode': 'count', 'value': cls.MAX_INSTANCES + 1})
        self.assertTrue(any('exceed' in e for e in errors))


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self._level, self._modules = log_utils._MIN_LEVEL, log_utils.MODULE_LOGGING_ENABLED
        self.app = fusion_stub.FakeApp()

    def tearDown(self):
        log_utils._MIN_LEVEL, log_utils.MODULE_LOGGING_ENABLED = self._level, self._modules

    def test_messages_below_the_level_are_dropped(self):
        log_utils.configure_logging(log_level='INFO', module_logging={})
        log_utils.log(self.app, 'debug detail', level=LogLevel.DEBUG, module='X')
        log_utils.log(self.app, 'info line', level=LogLevel.INFO, module='X')
        self.assertEqual(len(self.app.messages), 1)

    def test_a_silenced_module_drops_routine_messages(self):
        log_utils.configure_logging(log_level='DEBUG', module_logging={'NOISY': False})
        log_utils.log(self.app, 'x', level=LogLevel.DEBUG, module='NOISY')
        log_utils.log(self.app, 'x', level=LogLevel.INFO, module='NOISY')
        self.assertEqual(self.app.messages, [])

    def test_a_silenced_module_still_reports_problems(self):
        """Switching a module off must never hide its warnings and errors."""
        log_utils.configure_logging(log_level='DEBUG', module_logging={'NOISY': False})
        log_utils.log(self.app, 'careful', level=LogLevel.WARNING, module='NOISY')
        log_utils.log(self.app, 'broken', level=LogLevel.ERROR, module='NOISY')
        self.assertEqual(len(self.app.messages), 2)

    def test_last_problem_is_recorded_even_when_not_written(self):
        log_utils.configure_logging(log_level='CRITICAL', module_logging={})
        log_utils.reset_last_problem()
        log_utils.log(self.app, 'the reason', level=LogLevel.ERROR, module='X')
        self.assertEqual(log_utils.get_last_problem(), 'the reason')


if __name__ == '__main__':
    unittest.main()
