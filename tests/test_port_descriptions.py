"""Every node input carries a description for its hover tip (ui/src/components/PortTip.jsx).

Spacers are layout only (no label, no tip), so they're skipped."""
import unittest
from tests import fusion_stub

from backend.contracts import PortType  # noqa: E402

NODES = fusion_stub.all_node_classes()
MAX_LENGTH = 140


class PortDescriptionTests(unittest.TestCase):

    def test_every_input_has_a_short_sentence(self):
        problems = []
        for node_type, cls in sorted(NODES.items()):
            for port in cls.get_spec().inputs:
                if port.port_type == PortType.SPACER:
                    continue
                text = (port.description or '').strip()
                where = f'{node_type}.{port.name}'
                if not text:
                    problems.append(f'{where}: no description')
                elif not text.endswith('.'):
                    problems.append(f'{where}: should end with a period')
                elif len(text) >= MAX_LENGTH:
                    problems.append(f'{where}: {len(text)} characters, keep it under {MAX_LENGTH}')
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
