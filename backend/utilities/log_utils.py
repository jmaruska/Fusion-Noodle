"""
Logging utility that conforms to the specification.
This is the ONLY way to log in backend.
"""

from typing import Any, Dict, Optional
from datetime import datetime
from ..specification import LogLevel, SPECIFICATION
from ..enforcement import enforce_logging

# Logging config lives in config.py at the add-in root. Noodle.py reads it and passes
# the settings in through configure_logging(), so this package never imports a
# top-level `config` module (which could belong to another add-in).
_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
MODULE_LOGGING_ENABLED: Dict[str, bool] = {}  # default: all modules enabled
_MIN_LEVEL = _LEVEL_ORDER["INFO"]


def configure_logging(log_level: Optional[str] = None,
                      module_logging: Optional[Dict[str, bool]] = None) -> None:
    """Apply the settings from config.py. Called once by Noodle.py at startup."""
    global _MIN_LEVEL, MODULE_LOGGING_ENABLED
    if log_level is not None:
        _MIN_LEVEL = _LEVEL_ORDER.get(str(log_level).upper(), _LEVEL_ORDER["INFO"])
    if module_logging is not None:
        MODULE_LOGGING_ENABLED = dict(module_logging)

# Most recent WARNING/ERROR message, so a node that fails by logging and returning
# an empty output can still report its reason to the palette (see enforcement.py).
_last_problem: Optional[str] = None


def reset_last_problem() -> None:
    global _last_problem
    _last_problem = None


def get_last_problem() -> Optional[str]:
    return _last_problem

@enforce_logging
def log(app: Any, message: str, *, level: LogLevel, module: str) -> None:
    """
    The ONLY logging function for backend.
    
    Args:
        app: Fusion app instance
        message: Log message
        level: LogLevel enum value
        module: Module name for context
    """
    # Handle both LogLevel enum and string
    level_str = level.value if hasattr(level, 'value') else str(level)
    level_num = _LEVEL_ORDER.get(level_str.upper(), 20)

    if level_num >= _LEVEL_ORDER["WARNING"]:
        global _last_problem
        _last_problem = message

    # Check if logging is enabled for this module and level
    if level_num < _MIN_LEVEL:
        return
    # A module switched off in config.py goes quiet, but its warnings and errors
    # are always written: those are the lines a bug report needs.
    if level_num < _LEVEL_ORDER["WARNING"] and not MODULE_LOGGING_ENABLED.get(module, True):
        return
    
    fusion_app = app
    
    # Format according to specification
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    
    formatted_message = SPECIFICATION.logging.format_template.format(
        timestamp=timestamp,
        module=module,
        level=level_str,
        message=message
    )
    
    # Output to Fusion's text commands palette
    if fusion_app:
        try:
            # Try Fusion's log method
            if hasattr(fusion_app, 'log'):
                fusion_app.log(formatted_message)
            # Try text commands palette
            elif hasattr(fusion_app, 'userInterface'):
                palettes = fusion_app.userInterface.palettes
                text_palette = palettes.itemById('TextCommands')
                if text_palette:
                    text_palette.writeText(formatted_message)
        except Exception:
            # Silently fail if Fusion logging doesn't work
            # We cannot use print as it violates spec
            pass