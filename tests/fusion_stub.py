"""Minimal stand-ins for Fusion's `adsk` modules so the backend can be imported."""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent


class _StubModule(types.ModuleType):
    """Any attribute is a plain class (so it can be subclassed) or a MagicMock."""

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name.endswith('Handler'):
            value = type(name, (), {'__init__': lambda self, *a, **k: None})
        else:
            value = MagicMock(name=f'adsk.{name}')
        setattr(self, name, value)
        return value


def install():
    """Install the stubs and put the repo root on sys.path. Safe to call repeatedly."""
    if 'adsk' not in sys.modules or not isinstance(sys.modules['adsk'], _StubModule):
        for name in ('adsk', 'adsk.core', 'adsk.fusion', 'adsk.cam'):
            sys.modules[name] = _StubModule(name)
        sys.modules['adsk'].core = sys.modules['adsk.core']
        sys.modules['adsk'].fusion = sys.modules['adsk.fusion']
        sys.modules['adsk'].cam = sys.modules['adsk.cam']
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


class FakeApp:
    """Stands in for the Fusion Application where code only needs somewhere to log."""

    def __init__(self):
        self.messages = []

    def log(self, message):
        self.messages.append(message)


def all_node_classes():
    """Every registered node class, keyed by normalized node type."""
    install()
    from backend.nodes import NodeRegistry
    NodeRegistry.initialize(FakeApp())
    return {key.lower().replace(' ', '_'): cls for key, cls in NodeRegistry._nodes.items()}
