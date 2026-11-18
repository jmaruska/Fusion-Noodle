"""Run in a separate process by test_packaging.py. Loads the add-in the way Fusion
does (as a package named after its folder), runs Run / Stop / Run, and prints what
it observed as JSON. Not a test module itself."""
import importlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

repo_root = Path(__file__).resolve().parent.parent

# Fusion requires the folder to be called Noodle; a checkout may not be.
holder = tempfile.mkdtemp()
os.symlink(repo_root, os.path.join(holder, 'Noodle'), target_is_directory=True)
path_before = list(sys.path)
sys.path.insert(0, holder)  # stands in for Fusion's own add-in loader


class Event:
    def __init__(self):
        self.handlers = []

    def add(self, handler):
        self.handlers.append(handler)
        return True

    def remove(self, handler):
        self.handlers.remove(handler)
        return True


fake_app = MagicMock()
events = [Event(), Event(), Event()]
fake_app.documentActivated, fake_app.documentOpened, fake_app.documentClosed = events
fake_app.log = lambda message: None


class Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name.endswith('Handler'):
            value = type(name, (), {'__init__': lambda self, *a, **k: None})
        elif name == 'Application':
            value = type('Application', (), {'get': staticmethod(lambda: fake_app)})
        else:
            value = MagicMock()
        setattr(self, name, value)
        return value


for module_name in ('adsk', 'adsk.core', 'adsk.fusion'):
    sys.modules[module_name] = Stub(module_name)
sys.modules['adsk'].core, sys.modules['adsk'].fusion = sys.modules['adsk.core'], sys.modules['adsk.fusion']


def ours():
    return sorted(m for m in sys.modules if m.startswith('Noodle.'))


def listeners():
    return [len(e.handlers) for e in events]


def global_leaks():
    return sorted(m for m in sys.modules if m.split('.')[0] in ('backend', 'config', 'ui', 'specification'))


report = {}
entry = importlib.import_module('Noodle.Noodle')
entry.run({})
first_core = sys.modules['Noodle.backend.core']
report['after_run'] = {'listeners': listeners(), 'module_count': len(ours()), 'leaks': global_leaks(),
                       'path_added': [p for p in sys.path if p not in path_before and p != holder],
                       'version': entry.VERSION}
entry.run({})
report['run_twice_listeners'] = listeners()

# Generate as a single undo step: the request is acknowledged as deferred, then the
# command's execute handler runs the work and pushes the result to the palette.
ack = entry._start_generate_in_command({'reactFlowState': {'nodes': [], 'edges': []}})
pending_before = entry._pending_generate is not None
entry.GenerateCommandExecuteHandler().notify(None)
push = fake_app.userInterface.palettes.itemById.return_value.sendInfoToHTML.call_args
report['deferred_generate'] = {
    'ack': ack, 'pending_before': pending_before, 'pending_after': entry._pending_generate is not None,
    'pushed_action': push[0][0] if push else None,
    'pushed_has_success_key': 'success' in json.loads(push[0][1]) if push else False,
    'switch_default': entry.config.GENERATE_AS_SINGLE_UNDO,
}
entry.stop({})
report['after_stop'] = {'listeners': listeners(), 'modules_left': ours(),
                        'package_keeps_backend_attr': hasattr(sys.modules['Noodle'], 'backend')}
entry = importlib.reload(entry)  # Fusion re-runs the entry file on Run
entry.run({})
second_core = sys.modules['Noodle.backend.core']
report['after_rerun'] = {'listeners': listeners(),
                         'fresh_backend': second_core is not first_core,
                         'entry_uses_fresh_backend': entry.backend is sys.modules['Noodle.backend'],
                         'routing': entry.backend.handle_message('cancelSelection', {})}
entry.stop({})
print(json.dumps(report))
