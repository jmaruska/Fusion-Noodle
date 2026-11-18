"""House rules for the palette source that the build does not check."""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted(list((REPO_ROOT / 'ui' / 'src').rglob('*.js')) + list((REPO_ROOT / 'ui' / 'src').rglob('*.jsx'))
                 + [REPO_ROOT / 'ui' / 'index.html'])


class PaletteSourceTests(unittest.TestCase):
    def test_no_console_log_calls(self):
        """Progress chatter doesn't belong in the console. Report problems with
        console.warn or console.error; trace the bridge with FusionBridge's debug flag."""
        offenders = []
        for path in SOURCES:
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if re.search(r'console\.log\s*\(', line):
                    offenders.append(f'{path.relative_to(REPO_ROOT)}:{number}')
        self.assertEqual(offenders, [])

    def test_bridge_debug_logging_is_off(self):
        text = (REPO_ROOT / 'ui' / 'src' / 'bridge' / 'FusionBridge.js').read_text(encoding='utf-8')
        self.assertIn('new FusionBridge({ debug: false })', text)

    def test_palette_loads_nothing_from_the_network(self):
        html = (REPO_ROOT / 'ui' / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'(?:src|href)="(https?://[^"]+)"', html), [])


if __name__ == '__main__':
    unittest.main()


class CssTokenTests(unittest.TestCase):
    """A var(--x) that's never defined doesn't fall back quietly: the declaration
    becomes "unset", which can override other rules. Every token used must exist."""

    def test_every_css_variable_used_is_defined(self):
        styles = list((REPO_ROOT / 'ui' / 'styles').rglob('*.css'))
        texts = {path: path.read_text(encoding='utf-8') for path in styles + SOURCES}
        defined = set()
        for text in texts.values():
            defined |= set(re.findall(r'(--[\w-]+)\s*:', text))
            defined |= set(re.findall(r"['\"](--[\w-]+)['\"]\s*:", text))      # style={{ '--fill': ... }}
            defined |= set(re.findall(r"setProperty\('(--[\w-]+)'", text))
        missing = []
        for path, text in texts.items():
            for match in re.finditer(r'var\((--[\w-]+)', text):
                if match.group(1) not in defined:
                    line = text[:match.start()].count('\n') + 1
                    missing.append(f"{path.relative_to(REPO_ROOT)}:{line} {match.group(1)}")
        self.assertEqual(missing, [], 'define these in ui/styles/theme.css, or use an existing token')
