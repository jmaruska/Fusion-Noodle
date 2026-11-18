"""The add-in must load as a self-contained package and reload cleanly."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run([sys.executable, str(REPO_ROOT / 'tests' / '_package_probe.py')],
                                capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'package probe failed:\n{result.stderr[-2000:]}')
        cls.report = json.loads(result.stdout.strip().splitlines()[-1])

    def test_nothing_is_imported_under_a_global_name(self):
        self.assertEqual(self.report['after_run']['leaks'], [])

    def test_sys_path_is_not_modified(self):
        self.assertEqual(self.report['after_run']['path_added'], [])

    def test_running_twice_does_not_stack_document_listeners(self):
        self.assertEqual(self.report['after_run']['listeners'], [1, 1, 1])
        self.assertEqual(self.report['run_twice_listeners'], [1, 1, 1])

    def test_stop_removes_listeners_and_unloads_modules(self):
        after_stop = self.report['after_stop']
        self.assertEqual(after_stop['listeners'], [0, 0, 0])
        self.assertEqual(after_stop['modules_left'], ['Noodle.Noodle'])
        self.assertFalse(after_stop['package_keeps_backend_attr'])

    def test_run_after_stop_imports_fresh_code(self):
        after_rerun = self.report['after_rerun']
        self.assertTrue(after_rerun['fresh_backend'])
        self.assertTrue(after_rerun['entry_uses_fresh_backend'])
        self.assertEqual(after_rerun['listeners'], [1, 1, 1])
        self.assertTrue(after_rerun['routing']['success'])


class DeferredGenerateTests(unittest.TestCase):
    """Generate can run inside a Fusion command so it is one undo step. This checks
    the hand-off only; whether Fusion groups the undo is tested in Fusion."""

    def setUp(self):
        if not hasattr(PackagingTests, 'report'):
            PackagingTests.setUpClass()
        self.result = PackagingTests.report['deferred_generate']

    def test_request_is_acknowledged_as_deferred(self):
        self.assertEqual(self.result['ack'], {'success': True, 'deferred': True})
        self.assertTrue(self.result['pending_before'])

    def test_result_is_pushed_to_the_palette(self):
        self.assertEqual(self.result['pushed_action'], 'generateResult')
        self.assertTrue(self.result['pushed_has_success_key'])
        self.assertFalse(self.result['pending_after'])

    def test_single_undo_is_on_by_default(self):
        self.assertTrue(self.result['switch_default'])


class VersionTests(unittest.TestCase):
    def test_version_is_the_same_everywhere(self):
        manifest = json.loads((REPO_ROOT / 'Noodle.manifest').read_text())['version']
        self.assertRegex(manifest, r'^\d+\.\d+\.\d+$')
        for package_file in ('package.json', 'ui/package.json'):
            with self.subTest(file=package_file):
                self.assertEqual(json.loads((REPO_ROOT / package_file).read_text())['version'], manifest)

    def test_entry_reads_the_manifest_version(self):
        manifest = json.loads((REPO_ROOT / 'Noodle.manifest').read_text())['version']
        self.assertEqual(PackagingTests.report['after_run']['version'], manifest)

    def setUp(self):
        if not hasattr(PackagingTests, 'report'):
            PackagingTests.setUpClass()


class NoAbsoluteImportTests(unittest.TestCase):
    """Runtime code must not import `backend` or `config` by a global name."""
    DEV_SCRIPTS = {'spec_tests.py', 'contract_validation_tests.py', 'frontend_integration_check.py'}

    def test_backend_uses_relative_imports(self):
        import re
        pattern = re.compile(r'^\s*(from backend[.\s]|import backend\b|import config\b|from config\b)')
        offenders = []
        for path in [REPO_ROOT / 'Noodle.py', *sorted((REPO_ROOT / 'backend').rglob('*.py'))]:
            if path.name in self.DEV_SCRIPTS:
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if pattern.match(line):
                    offenders.append(f'{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}')
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
