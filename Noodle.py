"""
Noodle - A node-based geometry add-in for Fusion 360
"""

import adsk.core # type: ignore
import adsk.fusion # type: ignore
import os
import sys
sys.dont_write_bytecode = True  # Avoid .pyc files
import traceback
import json

addon_path = os.path.dirname(os.path.realpath(__file__))

# Fusion loads each add-in as a Python package named after its folder, so all of
# Noodle's modules are imported relative to that package (Noodle.backend, ...).
# Nothing is added to sys.path: top-level names like `backend` or `config` would be
# shared with every other add-in running in Fusion's single interpreter.
from . import backend
from . import config
from .backend.utilities.log_utils import log, configure_logging
from .backend.specification import LogLevel

configure_logging(
    log_level=getattr(config, 'LOG_LEVEL', None),
    module_logging=getattr(config, 'MODULE_LOGGING_ENABLED', None),
)

def _read_version() -> str:
    """The version lives in Noodle.manifest; it is the only place to change it."""
    try:
        with open(os.path.join(addon_path, 'Noodle.manifest'), encoding='utf-8') as f:
            return str(json.load(f).get('version', 'unknown'))
    except Exception:
        return 'unknown'

VERSION = _read_version()

# Command and UI identifiers
PALETTE_ID = 'NoodlePalette'
PALETTE_NAME = 'Noodle'
BUTTON_ID = 'jm_NoodleCommand'
BUTTON_NAME = 'Noodle'
BUTTON_DESC = 'Open the Noodle node-based geometry palette'
GENERATE_CMD_ID = 'jm_NoodleGenerateCommand'
GENERATE_CMD_NAME = 'Noodle Generate'  # Shown in Fusion's undo history
VISIBILITY_CMD_ID = 'jm_NoodleVisibilityCommand'
VISIBILITY_CMD_NAME = 'Noodle Show/Hide Bodies'  # Shown in Fusion's undo history
VISIBILITY_ACTIONS = ('set_node_visibility', 'set_nodes_visibility')
TARGET_WORKSPACE_ID = 'FusionSolidEnvironment'
TARGET_PANEL_ID = 'SolidCreatePanel'
ANCHOR_COMMAND_ID = 'PatternDropDown'

# Global variables
_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_handlers = []
_palette = None
_backend_app = None
_pending_generate = None  # Graph data waiting for the generate command to run
# Bodies waiting for the visibility command: {nodeId: (nodeType, visible)}, latest request wins
_pending_visibility = {}
_visibility_started_at = 0.0  # When the visibility command was last started
VISIBILITY_RETRY_S = 2.0  # A command that hasn't run by then is taken as dropped and started again

class ShowPaletteCommandExecuteHandler(adsk.core.CommandEventHandler):
    """Handler for showing the HTML palette when command executes"""
    
    def __init__(self):
        super().__init__()
        
    def notify(self, args: adsk.core.CommandEventArgs):
        try:
            global _palette, _app, _ui
            
            # Create palette if it doesn't exist
            if not _palette or not _palette.isValid:
                # Remove old palette if it exists
                old_palette = _ui.palettes.itemById(PALETTE_ID)
                if old_palette:
                    old_palette.deleteMe()
                
                # Create new palette
                # os.path.join builds an OS path; a palette needs a local URL.
                # On Windows the backslashes must become forward slashes.
                ui_path = os.path.join(addon_path, 'ui', 'index.html').replace('\\', '/')
                _palette = _ui.palettes.add(
                    PALETTE_ID,
                    PALETTE_NAME,
                    ui_path,
                    True,   # isVisible
                    True,   # showCloseButton
                    True,   # isResizable
                    650,    # width
                    600     # height
                )
                
                # Set docking state
                _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
                
                # Connect palette handlers
                onHTMLEvent = PaletteHTMLEventHandler()
                _palette.incomingFromHTML.add(onHTMLEvent)
                _handlers.append(onHTMLEvent)
                
                onClosed = PaletteCloseHandler()
                _palette.closed.add(onClosed)
                _handlers.append(onClosed)
                
                log(_app, "Palette created", level=LogLevel.INFO, module="NOODLE_MAIN")
            else:
                # Make visible if already exists
                _palette.isVisible = True
                log(_app, "Palette shown", level=LogLevel.INFO, module="NOODLE_MAIN")
                
        except Exception as e:
            error_msg = f'Failed to show palette:\n{str(e)}\n{traceback.format_exc()}'
            if _ui:
                _ui.messageBox(error_msg)
            if _app:
                log(_app, f"ERROR showing palette: {e}", level=LogLevel.ERROR, module="NOODLE_MAIN")

class ShowPaletteCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for when the command is created"""
    
    def __init__(self):
        super().__init__()
        
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        try:
            command = args.command
            # Add the execute handler to the command
            on_execute = ShowPaletteCommandExecuteHandler()
            command.execute.add(on_execute)
            _handlers.append(on_execute)
        except Exception as e:
            if _ui:
                _ui.messageBox(f'Failed to create command:\n{str(e)}')

def _send_to_palette(action: str, payload: dict) -> bool:
    """Push a message to the palette (see ui/src/bridge/backendEvents.js)."""
    try:
        palette = _ui.palettes.itemById(PALETTE_ID) if _ui else None
        if not palette:
            return False
        palette.sendInfoToHTML(action, json.dumps(payload))
        return True
    except Exception as e:
        if _app:
            log(_app, f"Could not send '{action}' to the palette: {e}", level=LogLevel.ERROR, module="NOODLE_MAIN")
        return False


def _start_generate_in_command(data: dict):
    """Run Generate inside a Fusion command so it is a single undo step.

    Work done in a command's execute handler is grouped into one undo entry;
    work done directly in a palette message is not. A command runs after the
    current message handler returns, so the palette is told the result is
    deferred and receives it later through _send_to_palette('generateResult').

    Returns the immediate response, or None if the command is unavailable and
    the caller should generate directly.
    """
    global _pending_generate
    cmd_def = _ui.commandDefinitions.itemById(GENERATE_CMD_ID) if _ui else None
    if not cmd_def:
        return None
    _pending_generate = data
    cmd_def.execute()
    return {'success': True, 'deferred': True}


class GenerateCommandExecuteHandler(adsk.core.CommandEventHandler):
    """Runs the pending Generate. Everything done here is one undo step."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _pending_generate
        data, _pending_generate = _pending_generate, None
        if data is None:
            return
        try:
            response = backend.handle_message('generateGeometry', data)
            if not isinstance(response, dict):
                response = {'success': False, 'error': 'No response from backend'}
        except Exception as e:
            log(_app, f"Generate failed inside command: {e}\n{traceback.format_exc()}",
                level=LogLevel.ERROR, module="NOODLE_MAIN")
            response = {'success': False, 'error': str(e)}
        if response.get('success', False) and 'error' in response:
            del response['error']
        _send_to_palette('generateResult', response)


class GenerateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """The generate command has no inputs, so Fusion executes it immediately."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            command = args.command
            command.isExecutedWhenPreEmpted = False
            # One handler instance is reused so _handlers doesn't grow with every Generate
            on_execute = next((h for h in _handlers if isinstance(h, GenerateCommandExecuteHandler)), None)
            if on_execute is None:
                on_execute = GenerateCommandExecuteHandler()
                _handlers.append(on_execute)
            command.execute.add(on_execute)
        except Exception as e:
            log(_app, f"Could not set up the generate command: {e}", level=LogLevel.ERROR, module="NOODLE_MAIN")
            _send_to_palette('generateResult', {'success': False, 'error': f'Could not start Generate: {e}'})


def _start_visibility_in_command(action: str, data: dict):
    """Show or hide bodies inside a Fusion command, so it is one undo step.

    Set straight from a palette message, every body is its own undo step with its own
    redraw, which takes seconds for a few thousand bodies. Inside a command it is one
    step and well under a second. Requests that arrive before the command runs are
    merged, the latest one for each node winning.

    Returns the immediate response, or None if the command is unavailable and the
    caller should set visibility directly.
    """
    cmd_def = _ui.commandDefinitions.itemById(VISIBILITY_CMD_ID) if _ui else None
    if not cmd_def:
        return None
    global _visibility_started_at
    import time
    nodes = data.get('nodes') if action == 'set_nodes_visibility' else [data]
    visible = bool(data.get('visible', True))
    # A command already on its way will pick these up too, unless it seems to have been dropped
    waiting = bool(_pending_visibility) and time.monotonic() - _visibility_started_at < VISIBILITY_RETRY_S
    for node in nodes or []:
        if isinstance(node, dict) and node.get('nodeId'):
            _pending_visibility[node['nodeId']] = (node.get('nodeType'), visible)
    if _pending_visibility and not waiting:
        try:
            _visibility_started_at = time.monotonic()
            cmd_def.execute()
        except Exception as e:
            log(_app, f"Could not start the visibility command, setting it directly: {e}",
                level=LogLevel.WARNING, module="NOODLE_MAIN")
            _pending_visibility.clear()
            return None
    return {'success': True, 'deferred': True}


class VisibilityCommandExecuteHandler(adsk.core.CommandEventHandler):
    """Applies the waiting visibility changes. Everything done here is one undo step."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        pending = dict(_pending_visibility)
        _pending_visibility.clear()
        for visible in (False, True):
            nodes = [{'nodeId': node_id, 'nodeType': node_type}
                     for node_id, (node_type, v) in pending.items() if v == visible]
            if not nodes:
                continue
            try:
                response = backend.handle_message('set_nodes_visibility', {'nodes': nodes, 'visible': visible})
                if isinstance(response, dict) and not response.get('success', False):
                    log(_app, f"Could not {'show' if visible else 'hide'} bodies: {response.get('error')}",
                        level=LogLevel.WARNING, module="NOODLE_MAIN")
            except Exception as e:
                log(_app, f"Visibility failed inside command: {e}\n{traceback.format_exc()}",
                    level=LogLevel.ERROR, module="NOODLE_MAIN")


class VisibilityCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """The visibility command has no inputs, so Fusion executes it immediately."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            command = args.command
            command.isExecutedWhenPreEmpted = False
            on_execute = next((h for h in _handlers if isinstance(h, VisibilityCommandExecuteHandler)), None)
            if on_execute is None:
                on_execute = VisibilityCommandExecuteHandler()
                _handlers.append(on_execute)
            command.execute.add(on_execute)
        except Exception as e:
            _pending_visibility.clear()
            log(_app, f"Could not set up the visibility command: {e}", level=LogLevel.ERROR, module="NOODLE_MAIN")


class PaletteHTMLEventHandler(adsk.core.HTMLEventHandler):
    """Handler for messages from the HTML palette"""
    
    def __init__(self):
        super().__init__()
        self.message_count = 0
        # Track timing to see if there are rapid follow-up messages
        self.last_message_time = None
        
    def notify(self, args: adsk.core.HTMLEventArgs):
        html_args = None  # Initialize to None for clean error handling
        
        try:
            global _backend_app, _app
            import time
            current_time = time.time()
            
            html_args = adsk.core.HTMLEventArgs.cast(args)
            self.message_count += 1
            
            # Get action and data
            action = html_args.action if html_args.action else ''
            data_str = html_args.data if html_args.data else '{}'
            
            # Calculate time since last message
            time_delta = ""
            if self.last_message_time:
                delta = current_time - self.last_message_time
                time_delta = f" (Δt={delta:.3f}s)"
            self.last_message_time = current_time
            
            log(_app, f"[#{self.message_count}]{time_delta} Action: '{action}'",
                level=LogLevel.DEBUG, module="PALETTE_HANDLER")
            
            # Parse data
            try:
                data = json.loads(data_str) if data_str and data_str != '{}' else {}
            except (json.JSONDecodeError, ValueError):
                data = {}
            
            # Fusion answers every sendInfoToHTML with an event whose action is
            # 'response', carrying what the page returned. Nothing waits for it.
            if action == 'response':
                return

            # Handle empty action (frontend might send empty action as a check)
            if not action:
                log(_app, "Received empty action - returning success", 
                    level=LogLevel.DEBUG, module="PALETTE_HANDLER")
                response = {'success': True, 'status': 'ready'}
                response_json = json.dumps(response)
                html_args.returnData = response_json
                return
            
            # Route ALL messages to backend
            try:
                response = None
                if action == 'generateGeometry' and getattr(config, 'GENERATE_AS_SINGLE_UNDO', False):
                    response = _start_generate_in_command(data)
                elif action in VISIBILITY_ACTIONS:
                    response = _start_visibility_in_command(action, data)
                if response is None:
                    response = backend.handle_message(action, data)
                
                if response is None:
                    log(_app, f"Backend returned None for action '{action}'", 
                        level=LogLevel.ERROR, module="PALETTE_HANDLER")
                    response = {'success': False, 'error': 'No response from backend'}
                elif not isinstance(response, dict):
                    log(_app, f"Backend returned non-dict for action '{action}': {type(response)}", 
                        level=LogLevel.ERROR, module="PALETTE_HANDLER")
                    response = {'success': False, 'error': 'Invalid response format'}
                
                # Clean successful responses - remove error field if success is true
                if response.get('success', False) and 'error' in response:
                    del response['error']

            except Exception as e:
                log(_app, f"Backend error for '{action}': {e}", 
                    level=LogLevel.ERROR, module="PALETTE_HANDLER")
                import traceback
                log(_app, f"Traceback: {traceback.format_exc()}", 
                    level=LogLevel.ERROR, module="PALETTE_HANDLER")
                response = {'success': False, 'error': str(e)}
            
            # Send response back
            response_json = json.dumps(response)
            
            response_size = len(response_json)
            if response_size > 16384:  # 16KB. Fusion copes; this is for diagnosis only.
                log(_app, f"Large response for '{action}': {response_size} chars",
                    level=LogLevel.DEBUG, module="PALETTE_HANDLER")

            html_args.returnData = response_json
            log(_app, f"[#{self.message_count}] Response for '{action}': {response_json[:200]}{'...' if len(response_json) > 200 else ''}",
                level=LogLevel.DEBUG, module="PALETTE_HANDLER")
                
        except Exception as e:
            log(_app, f"Critical error in palette handler: {str(e)}", 
                level=LogLevel.ERROR, module="PALETTE_HANDLER")
            
            # Try to send error response if we have html_args
            if html_args:
                try:
                    html_args.returnData = json.dumps({'success': False, 'error': str(e)})
                except Exception:
                    log(_app, "Failed to send error response to palette",
                        level=LogLevel.ERROR, module="PALETTE_HANDLER")
            else:
                log(_app, "Could not cast HTMLEventArgs - cannot send response to palette", 
                    level=LogLevel.CRITICAL, module="PALETTE_HANDLER")

class PaletteCloseHandler(adsk.core.UserInterfaceGeneralEventHandler):
    """Handler for palette close event"""
    
    def __init__(self):
        super().__init__()
        
    def notify(self, args):
        global _app, _palette
        if _app:
            log(_app, "Palette closed", level=LogLevel.INFO, module="NOODLE_MAIN")

        # The visualizer's dots only make sense while the palette is open
        try:
            backend.palette_closed()
        except Exception as e:
            if _app:
                log(_app, f"Could not clear visualizer dots: {e}", level=LogLevel.WARNING, module="NOODLE_MAIN")
        
        # Mark palette as None when closed
        if _palette:
            _palette.isVisible = False
            _palette = None

def cleanup_application():
    """Clean up all UI elements and handlers"""
    global _palette, _handlers, _app, _ui
    
    try:
        if _app:
            log(_app, "Starting cleanup...", level=LogLevel.DEBUG, module="NOODLE_MAIN")

        # Clean up palette
        if _ui and _palette:
            try:
                _palette.isVisible = False
                _palette.deleteMe()
                _palette = None
                if _app:
                    log(_app, "Palette cleaned up", level=LogLevel.DEBUG, module="NOODLE_MAIN")
            except Exception as e:
                if _app:
                    log(_app, f"Palette cleanup warning: {e}", level=LogLevel.WARNING, module="NOODLE_MAIN")

        # Remove command definitions
        if _ui:
            for command_id in (BUTTON_ID, GENERATE_CMD_ID, VISIBILITY_CMD_ID):
                cmd_def = _ui.commandDefinitions.itemById(command_id)
                if cmd_def:
                    try:
                        cmd_def.deleteMe()
                        if _app:
                            log(_app, f"Command definition {command_id} deleted", level=LogLevel.DEBUG, module="NOODLE_MAIN")
                    except Exception as e:
                        if _app:
                            log(_app, f"Command cleanup warning: {e}", level=LogLevel.WARNING, module="NOODLE_MAIN")

            # Remove control from all panels to avoid duplicates
            try:
                for i in range(_ui.allToolbarPanels.count):
                    panel = _ui.allToolbarPanels.item(i)
                    control = panel.controls.itemById(BUTTON_ID)
                    if control:
                        control.deleteMe()
                        if _app:
                            log(_app, f"Removed control from panel {panel.id}", level=LogLevel.DEBUG, module="NOODLE_MAIN")
            except Exception:
                pass
        
        # Clear handlers
        _handlers.clear()
        global _pending_generate
        _pending_generate = None
        _pending_visibility.clear()
        
    except Exception as e:
        if _app:
            log(_app, f"Cleanup error: {e}", level=LogLevel.ERROR, module="NOODLE_MAIN")

def _unload_package_modules():
    """Drop this add-in's modules from Python's import cache.

    Fusion re-runs this file on Stop then Run, but Python would hand back the
    already-imported backend. Removing our modules makes the next Run import
    fresh code, so Python changes don't need a Fusion restart. This is only safe
    because every module lives under this add-in's own package name.
    """
    package = __package__ or __name__.rpartition('.')[0]
    if not package:
        return
    prefix = package + '.'
    package_module = sys.modules.get(package)
    for name in [n for n in sys.modules if n.startswith(prefix) and n != __name__]:
        del sys.modules[name]
        # `from . import backend` returns a leftover attribute before it looks
        # in the cache, so remove direct children from the package object too.
        child = name[len(prefix):]
        if package_module is not None and '.' not in child and hasattr(package_module, child):
            try:
                delattr(package_module, child)
            except Exception:
                pass

def run(context):
    """Entry point for the add-in"""
    try:
        global _app, _ui, _backend_app
        
        # Get Fusion application references - MUST BE FIRST
        _app = adsk.core.Application.get()
        if not _app:
            raise RuntimeError("Failed to get Fusion application reference")
            
        _ui = _app.userInterface
        if not _ui:
            raise RuntimeError("Failed to get Fusion UI reference")
        
        # Clean up any previous instances
        cleanup_application()
        
        # Initialize backend
        try:
            log(_app, "Initializing backend...", level=LogLevel.DEBUG, module="NOODLE_MAIN")
            _backend_app = backend.initialize({
                'app': _app,
                'ui': _ui,
                'version': VERSION,
                'settings': {
                    'show_progress': getattr(config, 'SHOW_GENERATE_PROGRESS', True),
                }
            })
            log(_app, f"Backend initialized: {type(_backend_app)}", level=LogLevel.DEBUG, module="NOODLE_MAIN")
        except Exception as e:
            error_msg = f"Failed to initialize backend:\n{str(e)}\n{traceback.format_exc()}"
            log(_app, f"❌ BACKEND INIT FAILED: {error_msg}", level=LogLevel.ERROR, module="NOODLE_MAIN")
            _ui.messageBox(error_msg)
            raise
        
        
        # Hidden command that Generate runs inside when GENERATE_AS_SINGLE_UNDO is on.
        # It is never added to a toolbar; the palette triggers it.
        if not _ui.commandDefinitions.itemById(GENERATE_CMD_ID):
            generate_def = _ui.commandDefinitions.addButtonDefinition(
                GENERATE_CMD_ID, GENERATE_CMD_NAME, 'Generate geometry from the Noodle graph')
            generate_created = GenerateCommandCreatedHandler()
            generate_def.commandCreated.add(generate_created)
            _handlers.append(generate_created)

        # Hidden command that showing and hiding bodies runs inside, as one undo step
        if not _ui.commandDefinitions.itemById(VISIBILITY_CMD_ID):
            visibility_def = _ui.commandDefinitions.addButtonDefinition(
                VISIBILITY_CMD_ID, VISIBILITY_CMD_NAME, 'Show or hide the bodies Noodle made')
            visibility_created = VisibilityCommandCreatedHandler()
            visibility_def.commandCreated.add(visibility_created)
            _handlers.append(visibility_created)

        # Create command definition if it doesn't exist
        cmd_def = _ui.commandDefinitions.itemById(BUTTON_ID)
        if not cmd_def:
            # Set up resources path
            resources_path = os.path.join(addon_path, 'resources')
            
            # Check if resources folder exists
            if not os.path.exists(resources_path):
                log(_app, f"Resources folder not found at {resources_path}, using default icon", 
                    level=LogLevel.WARNING, module="NOODLE_MAIN")
                resources_path = ""  # Empty string = use Fusion's default icon
            
            # Create command definition
            cmd_def = _ui.commandDefinitions.addButtonDefinition(
                BUTTON_ID, 
                BUTTON_NAME, 
                BUTTON_DESC, 
                resources_path
            )
            
            # Add command created handler
            created_handler = ShowPaletteCommandCreatedHandler()
            cmd_def.commandCreated.add(created_handler)
            _handlers.append(created_handler)
            
            log(_app, "Command definition created", level=LogLevel.DEBUG, module="NOODLE_MAIN")
        else:
            log(_app, "Reusing existing command definition", level=LogLevel.DEBUG, module="NOODLE_MAIN")
        
        # Find target panel - try workspace-specific first
        panel = None
        ws = _ui.workspaces.itemById(TARGET_WORKSPACE_ID)
        if ws:
            try:
                panel = ws.toolbarPanels.itemById(TARGET_PANEL_ID)
                if panel:
                    log(_app, f"Located target panel {TARGET_PANEL_ID} in workspace {TARGET_WORKSPACE_ID}",
                        level=LogLevel.DEBUG, module="NOODLE_MAIN")
            except Exception:
                pass
        
        # Fallback to general panels if workspace-specific not found
        if not panel:
            fallbacks = ['SolidCreatePanel', 'ToolsAddinsPanel', 'QATPanel']
            for panel_id in fallbacks:
                test_panel = _ui.allToolbarPanels.itemById(panel_id)
                if test_panel:
                    panel = test_panel
                    log(_app, f"Using fallback panel {panel_id}",
                        level=LogLevel.DEBUG, module="NOODLE_MAIN")
                    break
        
        if not panel:
            log(_app, "No suitable panel found; aborting button creation", 
                level=LogLevel.ERROR, module="NOODLE_MAIN")
            _ui.messageBox('Noodle: No suitable toolbar panel found for button.')
            return
        
        # Add control to panel if not already present
        control = panel.controls.itemById(BUTTON_ID)
        if not control:
            # Try to find anchor for placement
            anchor_id = None
            
            # First try explicit anchor
            if panel.controls.itemById(ANCHOR_COMMAND_ID):
                anchor_id = ANCHOR_COMMAND_ID
                log(_app, f"Found explicit anchor {ANCHOR_COMMAND_ID}",
                    level=LogLevel.DEBUG, module="NOODLE_MAIN")
            else:
                # Dynamic discovery: look for Pattern-related controls
                try:
                    for i in range(panel.controls.count):
                        c = panel.controls.item(i)
                        try:
                            test_cmd_def = c.commandDefinition
                            if test_cmd_def and 'pattern' in test_cmd_def.name.lower():
                                anchor_id = c.id
                                log(_app, f"Auto-detected Pattern anchor: {anchor_id}",
                                    level=LogLevel.DEBUG, module="NOODLE_MAIN")
                                break
                        except Exception:
                            pass
                except Exception as e:
                    log(_app, f"Pattern anchor scan failed: {e}",
                        level=LogLevel.WARNING, module="NOODLE_MAIN")
            
            # Add control with or without anchor
            if anchor_id and panel.controls.itemById(anchor_id):
                control = panel.controls.addCommand(cmd_def, anchor_id, False)
                log(_app, f"Added command after anchor {anchor_id}",
                    level=LogLevel.DEBUG, module="NOODLE_MAIN")
            else:
                control = panel.controls.addCommand(cmd_def)
                log(_app, "Added command at panel end",
                    level=LogLevel.DEBUG, module="NOODLE_MAIN")
        else:
            log(_app, f"Reusing existing control in panel {panel.id}",
                level=LogLevel.DEBUG, module="NOODLE_MAIN")
        
        # Try to promote the control
        try:
            control.isPromotedByDefault = True
            control.isPromoted = True
        except Exception:
            log(_app, "Could not set promotion flags (may be unsupported)",
                level=LogLevel.WARNING, module="NOODLE_MAIN")
        
        # Verify control registration
        present = panel.controls.itemById(BUTTON_ID) is not None
        log(_app, f"Control present after add: {present}",
            level=LogLevel.DEBUG, module="NOODLE_MAIN")
        
        log(_app, "✅ Noodle initialized successfully", level=LogLevel.INFO, module="NOODLE_MAIN")
        
    except Exception as e:
        error_msg = f'Failed to run Noodle:\n{str(e)}\n{traceback.format_exc()}'
        if _ui:
            _ui.messageBox(error_msg)
        # Emergency fallback logging (spec exception for initialization failures)
        sys.stderr.write(error_msg + '\n')
        raise

def stop(context):
    """Clean up when the add-in is stopped"""
    try:
        global _app, _ui
        
        # Try to get references if they don't exist
        if not _app:
            _app = adsk.core.Application.get()
        if not _ui and _app:
            _ui = _app.userInterface
        
        if _app:
            log(_app, "Stopping Noodle...", level=LogLevel.INFO, module="NOODLE_MAIN")
        
        # Release the backend's Fusion event subscriptions before the UI goes away
        try:
            backend.shutdown()
        except Exception as e:
            if _app:
                log(_app, f"Backend shutdown warning: {e}", level=LogLevel.WARNING, module="NOODLE_MAIN")

        # Run cleanup
        cleanup_application()
        
        if _app:
            log(_app, "✅ Noodle stopped cleanly", level=LogLevel.INFO, module="NOODLE_MAIN")

        # Last: forget our imported modules so the next Run loads code from disk
        _unload_package_modules()
        
    except Exception as e:
        if _ui:
            _ui.messageBox(f'Error during stop:\n{str(e)}')