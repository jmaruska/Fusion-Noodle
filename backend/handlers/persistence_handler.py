"""
Persistence handler - manages graph saving/loading and document operations.
Stores ReactFlow state as an attribute on the Noodle BaseFeature.
"""

import json
import copy
import os
from typing import Dict, Any, List, Optional, Tuple
from ..utilities.log_utils import log
from ..specification import LogLevel
from .. import graph_format
from ..graph_format import GraphFormatError

class PersistenceHandler:
    """Handles graph persistence and document operations using ReactFlow format"""

    # Messages this handler accepts, and the method that answers each.
    # The core builds its routing table from these (see Application._build_routes),
    # so adding a message means adding one line here and nowhere else.
    ACTIONS = {
        'scanDocument': '_scan_document',
        'refreshGraph': '_refresh_graph',
        'saveGraphFile': '_save_graph_file',
        'openGraphFile': '_open_graph_file',
        'updateWorkingGraph': '_update_working_graph',
        'discardWorkingGraph': '_discard_working_graph',
    }
    
    # Constants for BaseFeature attribute storage
    ATTRIBUTE_GROUP = "noodle"
    ATTRIBUTE_NAME = "reactflow_json"  # Updated to ReactFlow format
    BASE_FEATURE_PREFIX = "Noodle_Geometry"
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.app = context['app']
        self.design = context['design']
        self.core = context['core']
        self.ui = context.get('ui')

        # Folder of the last graph file opened or saved, so the next dialog starts there
        self._last_graph_folder = None

        # Working copies: the graph as currently edited in the palette, per document.
        # See the WORKING COPY section below.
        self._working_graphs: Dict[str, Dict[str, Any]] = {}
        self._doc_saving_handler = None
        
        # Track last document to avoid unnecessary reloads
        self._last_document_id = None
        self._load_notes = []
        
        # Keep references to event handlers to prevent GC
        self._doc_activated_handler = None
        self._doc_opened_handler = None
        self._doc_closed_handler = None
        
        # Subscribe to Fusion document events to detect switches
        self._subscribe_document_events()

    def _subscribe_document_events(self):
        """Subscribe to Fusion document events to detect document switches/open/close."""
        try:
            import adsk.core  # type: ignore
            app = adsk.core.Application.get()
            if not app:
                log(self.app, "Fusion Application unavailable; cannot subscribe to document events", 
                    level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                return
            
            # Document Activated (switch current doc)
            class _DocumentActivatedHandler(adsk.core.DocumentEventHandler):
                def __init__(self, persistence_handler):
                    super().__init__()
                    self._ph = persistence_handler
                def notify(self, args):  # args: DocumentEventArgs
                    try:
                        self._ph._on_document_activated(args)
                    except Exception as e:
                        log(self._ph.app, f"DocumentActivated handler error: {e}", 
                            level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            
            # Document Opened
            class _DocumentOpenedHandler(adsk.core.DocumentEventHandler):
                def __init__(self, persistence_handler):
                    super().__init__()
                    self._ph = persistence_handler
                def notify(self, args):
                    try:
                        self._ph._on_document_opened(args)
                    except Exception as e:
                        log(self._ph.app, f"DocumentOpened handler error: {e}", 
                            level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            
            # Document Closed
            class _DocumentClosedHandler(adsk.core.DocumentEventHandler):
                def __init__(self, persistence_handler):
                    super().__init__()
                    self._ph = persistence_handler
                def notify(self, args):
                    try:
                        self._ph._on_document_closed(args)
                    except Exception as e:
                        log(self._ph.app, f"DocumentClosed handler error: {e}", 
                            level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            
            # Document Saving: write the working copy into the document just before it saves
            class _DocumentSavingHandler(adsk.core.DocumentEventHandler):
                def __init__(self, persistence_handler):
                    super().__init__()
                    self._ph = persistence_handler
                def notify(self, args):
                    try:
                        self._ph._on_document_saving(args)
                    except Exception as e:
                        log(self._ph.app, f"DocumentSaving handler error: {e}",
                            level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")

            # Subscribe
            self._doc_saving_handler = _DocumentSavingHandler(self)
            app.documentSaving.add(self._doc_saving_handler)
            self._doc_activated_handler = _DocumentActivatedHandler(self)
            self._doc_opened_handler = _DocumentOpenedHandler(self)
            self._doc_closed_handler = _DocumentClosedHandler(self)
            
            app.documentActivated.add(self._doc_activated_handler)
            app.documentOpened.add(self._doc_opened_handler)
            app.documentClosed.add(self._doc_closed_handler)
            
            log(self.app, "Subscribed to Fusion document events (activated/opened/closed)", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        except Exception as e:
            log(self.app, f"Could not subscribe to document events: {e}", 
                level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")

    def shutdown(self):
        """Unsubscribe from Fusion document events. Called when the add-in stops,
        so stale listeners don't keep firing (and pile up) across Stop/Run."""
        try:
            import adsk.core  # type: ignore
            app = adsk.core.Application.get()
            for event_name, attr in (('documentActivated', '_doc_activated_handler'),
                                     ('documentOpened', '_doc_opened_handler'),
                                     ('documentClosed', '_doc_closed_handler'),
                                     ('documentSaving', '_doc_saving_handler')):
                handler = getattr(self, attr, None)
                if app and handler:
                    try:
                        getattr(app, event_name).remove(handler)
                    except Exception as e:
                        log(self.app, f"Could not remove {event_name} handler: {e}",
                            level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                setattr(self, attr, None)
        except Exception as e:
            log(self.app, f"Error unsubscribing document events: {e}",
                level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")

    # Event callbacks
    def _on_document_activated(self, args: Any):
        """Handle when a different document becomes active."""
        try:
            # Get current document info
            current_doc_id = None
            doc_display_name = "None"
            
            if self.core.fusion_app and self.core.fusion_app.activeDocument:
                doc = self.core.fusion_app.activeDocument
                doc_display_name = doc.name

                # Identify the document by its root component id, which stays the
                # same for as long as the document lives. A Python id() of the
                # document object would not do: Fusion hands back a new wrapper
                # object on every call. Documents without a design fall back to
                # their name.
                self.core._check_design()
                current_doc_id = self._document_key(self.core.design) or f"name:{doc_display_name}"

            log(self.app, f"Document activated: {doc_display_name}",
                level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
            
            # Always process on first run, or when document actually changed
            if self._last_document_id is None or current_doc_id != self._last_document_id:
                log(self.app, f"Document switch detected: {doc_display_name}",
                    level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
                
                self._last_document_id = current_doc_id
                
                # Update design/base feature references to ACTIVE document
                self.core._check_design()
                self.context['design'] = self.core.design
                self.context['base_feature'] = self.core.base_feature
                
                # Trigger document switch (HTML reload)
                result = self._document_switch({})
            else:
                log(self.app, f"Document reactivated (no change): {doc_display_name}",
                    level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
                
        except Exception as e:
            log(self.app, f"Error during document activated handling: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")

    def _on_document_opened(self, args: Any):
        log(self.app, "Document opened event detected", 
            level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")

    def _on_document_closed(self, args: Any):
        log(self.app, "Document closed event detected", 
            level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
    
    def handle(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Route persistence actions"""
        
        
        method_name = self.ACTIONS.get(action)
        if method_name:
            return getattr(self, method_name)(data)
        
        return {'success': False, 'error': f'Unknown persistence action: {action}'}
    
    def _document_switch(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle document switch by reloading HTML palette for fresh frontend"""
        log(self.app, "🔄 Document switch detected - reloading HTML palette", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        
        try:
            # Get new document info for logging
            new_doc_name = "Unknown"
            if self.core.fusion_app and self.core.fusion_app.activeDocument:
                new_doc_name = self.core.fusion_app.activeDocument.name
            
            log(self.app, f"📋 Switching to document: {new_doc_name}", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            
            # SIMPLE & RELIABLE: Force HTML palette reload
            # This gives us a fresh frontend while keeping Python backend running
            success = self._reload_html_palette()
            
            if success:
                # Also clear backend state for good measure
                self._clear_backend_state()
                
                return {
                    'success': True,
                    'message': f'HTML palette reloaded for document: {new_doc_name}',
                    'action': 'html_reload'
                }
            else:
                # Fallback to state reset if HTML reload fails
                log(self.app, "⚠️ HTML reload failed, falling back to state reset", 
                    level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                self._thorough_state_reset()
                
                return {
                    'success': True,
                    'message': f'Fallback state reset for document: {new_doc_name}',
                    'action': 'state_reset'
                }
            
        except Exception as e:
            log(self.app, f"Error during document switch: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return {'success': False, 'error': str(e)}
    
    def _reload_html_palette(self):
        """Reload the HTML palette to get fresh frontend state"""
        try:
            log(self.app, "🔄 Reloading HTML palette for fresh frontend...", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            
            if not self.core.fusion_app:
                raise Exception("Fusion app not available")
            
            # Find the Noodle palette
            ui = self.core.fusion_app.userInterface
            palettes = ui.palettes
            
            noodle_palette = None
            for i in range(palettes.count):
                palette = palettes.item(i)
                if "noodle" in palette.name.lower():
                    noodle_palette = palette
                    break
            
            if noodle_palette:
                log(self.app, f"✨ Found palette: {noodle_palette.name}, forcing HTML reload", 
                    level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
                
                # Force HTML reload by reassigning the URL to itself
                current_url = noodle_palette.htmlFileURL
                noodle_palette.htmlFileURL = current_url
                
                log(self.app, "✅ HTML palette reload completed", 
                    level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
                return True
            else:
                log(self.app, "⚠️ Could not find Noodle palette for reload", 
                    level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                return False
                
        except Exception as e:
            log(self.app, f"❌ Error during HTML palette reload: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return False
    
    def _clear_backend_state(self):
        """Clear backend state without full restart"""
        log(self.app, "🧹 Clearing backend state for document switch", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        
        # Clear core state
        self.core.base_feature = None
        self.core.current_graph = {}
        self.core.node_instances = {}
        if hasattr(self.core, 'current_reactflow_state'):
            self.core.current_reactflow_state = None
        
        # Update to new document
        self.core._check_design()
        if self.core.design:
            self.design = self.core.design
            self.context['design'] = self.core.design
        
        log(self.app, "✅ Backend state cleared", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
    
    def _thorough_state_reset(self):
        """Perform thorough state reset without add-in restart"""
        log(self.app, "🧹 Performing thorough state reset for document switch", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        
        # Clear all core state
        self.core.base_feature = None
        self.core.design = None
        self.core.current_graph = {}
        self.core.node_instances = {}
        if hasattr(self.core, 'current_reactflow_state'):
            self.core.current_reactflow_state = None
        
        # Clear handler contexts
        for handler in self.core.handlers.values():
            if hasattr(handler, 'context'):
                handler.context['design'] = None
                handler.context['base_feature'] = None
                handler.context['noodle_base_feature'] = None
        
        # Clear own references
        self.design = None
        self.context['design'] = None
        self.context['base_feature'] = None
        
        # Update to new document
        self.core._check_design()
        if self.core.design:
            self.design = self.core.design
            self.context['design'] = self.core.design
        
        log(self.app, "✅ Thorough state reset completed", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
    
    # ========================================================================
    # DOCUMENT-BASED PERSISTENCE (BaseFeature attributes)
    # ========================================================================
    
    def _save_reactflow_state_to_base_feature(self, reactflow_state: Dict[str, Any]) -> bool:
        """Save ReactFlow state to the BaseFeature as an attribute"""
        base_feature = self.core.base_feature
        if not base_feature:
            log(self.app, "No BaseFeature available for saving ReactFlow state", 
                level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
            return False
        
        try:
            # Sanitize ReactFlow state before saving to avoid stale UI flags
            sanitized = self._sanitize_reactflow_state(reactflow_state)
            graph_format.stamp(sanitized, getattr(self.core, 'version', 'unknown'))
            reactflow_json = json.dumps(sanitized)
            log(self.app, f"Saving ReactFlow state to BaseFeature: {base_feature.name}", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            
            # Create or update the attribute
            attributes = base_feature.attributes
            
            # Remove existing attribute if it exists
            existing_attr = attributes.itemByName(self.ATTRIBUTE_GROUP, self.ATTRIBUTE_NAME)
            if existing_attr:
                log(self.app, "Removing existing ReactFlow attribute", 
                    level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
                attributes.remove(existing_attr)
            
            # Add new attribute with ReactFlow JSON
            log(self.app, f"Adding new attribute: {self.ATTRIBUTE_GROUP}.{self.ATTRIBUTE_NAME}", 
                level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
            log(self.app, f"JSON length: {len(reactflow_json)} characters", 
                level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
            
            attributes.add(self.ATTRIBUTE_GROUP, self.ATTRIBUTE_NAME, reactflow_json)
            
            log(self.app, f"Successfully saved ReactFlow state to BaseFeature: {base_feature.name}", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            return True
            
        except Exception as e:
            log(self.app, f"Error saving ReactFlow state to BaseFeature: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return False

    # ========================================================================
    # WORKING COPY
    # ========================================================================
    #
    # A document can hold two snapshots of its graph:
    #
    #   as generated   on the Noodle Base Feature. Written by Generate. Always
    #                  matches the geometry in the design.
    #   working copy   the graph as the user has edited it since. Exists only when
    #                  it differs from the generated one.
    #
    # The palette sends the working copy here shortly after each edit. It is kept
    # in memory and written into the document only when the document is saved
    # (as an attribute on the root component), so editing a graph adds nothing to
    # Fusion's undo history. Loading a document prefers the working copy.
    # Generate and Clear remove it.

    WORKING_ATTRIBUTE_NAME = "working_graph_json"

    @staticmethod
    def _document_key(design) -> Optional[str]:
        """A stable identity for a design. The root component's id never changes."""
        try:
            return str(design.rootComponent.id) if design else None
        except Exception:
            return None

    def _active_design(self):
        self.core._check_design()
        return self.core.design

    def _update_working_graph(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remember the palette's current graph for the active document. Memory only."""
        state = data.get('reactFlowState')
        try:
            graph_format.check_is_graph(state)
        except GraphFormatError as e:
            return {'success': False, 'error': str(e)}
        key = self._document_key(self._active_design())
        if not key:
            return {'success': False, 'error': 'No active design.'}
        self.set_working_graph(key, state)
        return {'success': True}

    def set_working_graph(self, key: str, state: Dict[str, Any]) -> None:
        if not state.get('nodes'):
            # An empty canvas is not kept as a working copy
            self._working_graphs.pop(key, None)
            return
        sanitized = self._sanitize_reactflow_state(state)
        graph_format.stamp(sanitized, getattr(self.core, 'version', 'unknown'))
        self._working_graphs[key] = {'state': sanitized, 'in_document': False}

    def working_graph(self, design) -> Optional[Dict[str, Any]]:
        """The working copy for `design`: from memory, else from the document."""
        key = self._document_key(design)
        if not key:
            return None
        entry = self._working_graphs.get(key)
        if entry:
            return entry['state']
        try:
            attribute = design.rootComponent.attributes.itemByName(self.ATTRIBUTE_GROUP, self.WORKING_ATTRIBUTE_NAME)
            if not attribute:
                return None
            state, notes = graph_format.migrate(json.loads(attribute.value))
            getattr(self, "_load_notes", []).extend(notes)  # Shown by palette_ready
            if not state.get('nodes'):
                return None
            self._working_graphs[key] = {'state': state, 'in_document': True}
            return state
        except Exception as e:
            log(self.app, f"Could not read the working graph from the document: {e}",
                level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
            return None

    def flush_working_graph(self, design) -> bool:
        """Write the working copy into the document if it isn't there yet."""
        key = self._document_key(design)
        entry = self._working_graphs.get(key) if key else None
        if not entry or entry.get('in_document'):
            return False
        attributes = design.rootComponent.attributes
        existing = attributes.itemByName(self.ATTRIBUTE_GROUP, self.WORKING_ATTRIBUTE_NAME)
        if existing:
            existing.deleteMe()
        attributes.add(self.ATTRIBUTE_GROUP, self.WORKING_ATTRIBUTE_NAME, json.dumps(entry['state']))
        entry['in_document'] = True
        return True

    def clear_working_graph(self, design=None) -> None:
        """Forget the working copy, in memory and in the document."""
        design = design or self._active_design()
        key = self._document_key(design)
        if not key:
            return
        self._working_graphs.pop(key, None)
        try:
            existing = design.rootComponent.attributes.itemByName(self.ATTRIBUTE_GROUP, self.WORKING_ATTRIBUTE_NAME)
            if existing:
                existing.deleteMe()
        except Exception as e:
            log(self.app, f"Could not remove the working graph from the document: {e}",
                level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")

    def _discard_working_graph(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Drop the working copy and return the as-generated graph."""
        self.clear_working_graph()
        return self._scan_document({'generatedOnly': True})

    def _on_document_saving(self, args: Any):
        """Put the working copy into the document so it is saved with it."""
        import adsk.fusion  # type: ignore
        document = adsk.fusion.FusionDocument.cast(getattr(args, 'document', None))
        design = document.design if document else None
        if design and self.flush_working_graph(design):
            log(self.app, "Saved the working graph into the document", level=LogLevel.INFO, module="PERSISTENCE_HANDLER")

    def _with_working_copy(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """If the active document has a working copy, return it in place of the generated graph."""
        working = self.working_graph(self._active_design())
        response['hasGeneratedGraph'] = bool(response.get('reactFlowStates'))
        if working:
            response['reactFlowStates'] = [working]
            response['workingCopy'] = True
        return response

    # ========================================================================
    # GRAPH FILES (.noodle)
    # ========================================================================

    GRAPH_FILE_EXTENSION = '.noodle'
    GRAPH_FILE_FILTER = 'Noodle graph (*.noodle);;JSON (*.json);;All files (*.*)'

    def _graph_file_dialog(self, title: str):
        dialog = self.ui.createFileDialog()
        dialog.title = title
        dialog.filter = self.GRAPH_FILE_FILTER
        dialog.isMultiSelectEnabled = False
        if self._last_graph_folder and os.path.isdir(self._last_graph_folder):
            dialog.initialDirectory = self._last_graph_folder
        return dialog

    def _save_graph_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ask where to save, then write the graph as a .noodle file."""
        import adsk.core  # type: ignore
        try:
            graph_format.check_is_graph(data.get('reactFlowState'))
        except GraphFormatError as e:
            return {'success': False, 'error': str(e)}
        try:
            dialog = self._graph_file_dialog('Save Noodle Graph')
            dialog.initialFilename = self._suggested_graph_filename()
            if dialog.showSave() != adsk.core.DialogResults.DialogOK:
                return {'success': True, 'cancelled': True}
            path = dialog.filename
            if not os.path.splitext(path)[1]:
                path += self.GRAPH_FILE_EXTENSION
            self.write_graph_file(path, data['reactFlowState'])
            self._last_graph_folder = os.path.dirname(path)
            return {'success': True, 'filename': os.path.basename(path)}
        except Exception as e:
            log(self.app, f"Could not save graph file: {e}", level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return {'success': False, 'error': f'Could not save the graph: {e}'}

    def _open_graph_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ask which file to open, then return its graph, migrated to the current format."""
        import adsk.core  # type: ignore
        try:
            dialog = self._graph_file_dialog('Open Noodle Graph')
            if dialog.showOpen() != adsk.core.DialogResults.DialogOK:
                return {'success': True, 'cancelled': True}
            path = dialog.filename
            state, notes = self.read_graph_file(path)
            self._last_graph_folder = os.path.dirname(path)
            return {'success': True, 'reactFlowState': state, 'warnings': notes,
                    'filename': os.path.basename(path)}
        except GraphFormatError as e:
            return {'success': False, 'error': str(e)}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {'success': False, 'error': 'That file is not a Noodle graph.'}
        except Exception as e:
            log(self.app, f"Could not open graph file: {e}", level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return {'success': False, 'error': f'Could not open the graph: {e}'}

    def _suggested_graph_filename(self) -> str:
        try:
            name = self.app.activeDocument.name
        except Exception:
            name = ''
        name = ''.join(c for c in str(name or 'graph') if c not in '\\/:*?"<>|').strip() or 'graph'
        return name + self.GRAPH_FILE_EXTENSION

    def write_graph_file(self, path: str, reactflow_state: Dict[str, Any]) -> None:
        """Write a graph to `path` in the current format."""
        state = self._sanitize_reactflow_state(reactflow_state)
        graph_format.stamp(state, getattr(self.core, 'version', 'unknown'))
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def read_graph_file(path: str) -> Tuple[Dict[str, Any], List[str]]:
        """Read a graph file and migrate it. Returns (graph, notes for the user)."""
        with open(path, encoding='utf-8') as f:
            state = json.load(f)
        return graph_format.migrate(state)

    def _sanitize_reactflow_state(self, reactflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """Remove volatile, UI-only fields so restored graphs remain editable."""
        try:
            import copy
            state = copy.deepcopy(reactflow_state)
            nodes = state.get('nodes', [])
            for node in nodes:
                data = node.get('data', {})
                # Remove computed/locked flags that could freeze inputs on restore
                if 'nodeState' in data:
                    data.pop('nodeState', None)
                if 'computedOutputs' in data:
                    data.pop('computedOutputs', None)
                data.pop('executionResult', None)
                data.pop('visualize', None)  # Visualizer eyes always start off
                # Collections flowing between nodes are recomputed on load and can hold
                # thousands of instances, so don't store them in the document attribute.
                computed = data.get('computedInputs')
                if isinstance(computed, dict):
                    for key in [k for k, v in computed.items()
                                if isinstance(v, dict) and 'instances' in v]:
                        computed.pop(key, None)
                # Optional: clear selection and measured layout to avoid stale UI
                node.pop('selected', None)
                node.pop('measured', None)
            state['nodes'] = nodes
            return state
        except Exception as e:
            log(self.app, f"Could not sanitize ReactFlow state: {e}", 
                level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
            return reactflow_state
    
    def _load_reactflow_state_from_base_feature(self, base_feature) -> Optional[Dict[str, Any]]:
        """Load ReactFlow state from a BaseFeature attribute"""
        if not base_feature:
            return None
            
        try:
            # Check if base_feature reference is still valid
            try:
                feature_name = base_feature.name
                log(self.app, f"Loading ReactFlow state from BaseFeature: '{feature_name}'",
                    level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
            except Exception:
                log(self.app, "BaseFeature reference is stale",
                    level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                return None
            
            # Get the attribute
            attributes = base_feature.attributes
            reactflow_attr = attributes.itemByName(self.ATTRIBUTE_GROUP, self.ATTRIBUTE_NAME)
            
            if not reactflow_attr:
                log(self.app, f"No ReactFlow attribute found on '{feature_name}'", 
                    level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
                return None
            
            log(self.app, f"Found ReactFlow attribute, parsing JSON...", 
                level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
            
            # Parse the JSON
            reactflow_state = json.loads(reactflow_attr.value)

            # Bring an older graph up to the current format. A graph that can't be
            # migrated (for example one saved by a newer Noodle) is loaded as it is:
            # dropping it would let the next Generate overwrite it.
            try:
                reactflow_state, notes = graph_format.migrate(reactflow_state)
                for note in notes:
                    log(self.app, f"Updated saved graph: {note}", level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
                getattr(self, "_load_notes", []).extend(notes)  # Shown by palette_ready
            except GraphFormatError as e:
                log(self.app, f"Saved graph loaded without migration: {e}",
                    level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
            
            log(self.app, f"Successfully loaded ReactFlow state from BaseFeature: {feature_name}", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            return reactflow_state
            
        except json.JSONDecodeError as e:
            log(self.app, f"Invalid JSON in BaseFeature: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return None
        except Exception as e:
            log(self.app, f"Error loading ReactFlow state: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return None
    
    def _scan_document_for_noodle_reactflow_states(self) -> List[Tuple[Any, Dict[str, Any]]]:
        """Scan the current document for all Noodle BaseFeatures with ReactFlow state data"""
        # Update design reference in case document changed
        try:
            import adsk.core # type: ignore
            app = adsk.core.Application.get()
            if not app.activeProduct or app.activeProduct.productType != 'DesignProductType':
                log(self.app, "No active design available for scanning", 
                    level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                return []
            
            design = app.activeProduct
            self.design = design
            self.context['design'] = design
        except Exception as e:
            log(self.app, f"Could not access active design: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return []
        
        found_states = []
        
        try:
            # Get the root component and its base features
            root_component = design.rootComponent
            base_features = root_component.features.baseFeatures
            
            log(self.app, f"Scanning {base_features.count} BaseFeatures for ReactFlow data", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            
            for i in range(base_features.count):
                try:
                    base_feature = base_features.item(i)
                    
                    log(self.app, f"  BaseFeature {i+1}: '{base_feature.name}'", 
                        level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
                    
                    # Check if this is a Noodle BaseFeature
                    if base_feature.name.startswith(self.BASE_FEATURE_PREFIX):
                        log(self.app, f"Found Noodle BaseFeature: '{base_feature.name}'", 
                            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
                        
                        # Try to load ReactFlow state from it
                        reactflow_state = self._load_reactflow_state_from_base_feature(base_feature)
                        if reactflow_state:
                            log(self.app, f"ReactFlow state loaded from '{base_feature.name}'", 
                                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
                            found_states.append((base_feature, reactflow_state))
                        else:
                            log(self.app, f"No ReactFlow state in '{base_feature.name}'", 
                                level=LogLevel.DEBUG, module="PERSISTENCE_HANDLER")
                
                except Exception as e:
                    log(self.app, f"Error accessing BaseFeature {i+1}: {e}", 
                        level=LogLevel.WARNING, module="PERSISTENCE_HANDLER")
                    continue
            
            log(self.app, f"Found {len(found_states)} ReactFlow states in document", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            
        except Exception as e:
            log(self.app, f"Error scanning document: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
        
        return found_states
    
    # ========================================================================
    # PUBLIC ACTION HANDLERS
    # ========================================================================
    
    def _scan_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Scan document for Noodle ReactFlow states"""
        log(self.app, "Scanning document for Noodle ReactFlow data", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        
        # Notes from updating older graphs while scanning, for the palette to show
        self._load_notes = []
        found_states = self._scan_document_for_noodle_reactflow_states()
        
        # Extract just the ReactFlow state data
        reactflow_states = []
        for base_feature, reactflow_state in found_states:
            reactflow_states.append(reactflow_state)
        
        # NEVER auto-store for restoration - that only happens on Generate
        # Document switch should: clear UI → read existing → populate (not restore)
        
        # If no states found, proactively clear backend graph state
        if not reactflow_states:
            self.core.current_graph = {}
            self.core.node_instances = {}
            if hasattr(self.core, 'current_reactflow_state'):
                self.core.current_reactflow_state = None
            log(self.app, "No ReactFlow states found; cleared backend graph state", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        
        if data.get('generatedOnly'):
            return {'success': True, 'reactFlowStates': reactflow_states, 'notes': self._load_notes}
        result = self._with_working_copy({
            'success': True,
            'reactFlowStates': reactflow_states
        })
        result['notes'] = list(dict.fromkeys(self._load_notes))  # Once each
        return result
        
    def _refresh_graph(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Manual refresh: clear everything and load from current document"""
        log(self.app, "Manual graph refresh requested - clearing state and reloading", 
            level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
        
        try:
            # Clear all cached state
            self.core.current_graph = {}
            self.core.node_instances = {}
            if hasattr(self.core, 'current_reactflow_state'):
                self.core.current_reactflow_state = None
            
            # Scan current document for ReactFlow states
            found_states = self._scan_document_for_noodle_reactflow_states()
            
            # Extract just the ReactFlow state data
            reactflow_states = []
            for base_feature, reactflow_state in found_states:
                reactflow_states.append(reactflow_state)
            
            log(self.app, f"Manual refresh complete - found {len(reactflow_states)} graph(s)", 
                level=LogLevel.INFO, module="PERSISTENCE_HANDLER")
            
            return self._with_working_copy({
                'success': True,
                'action': 'refresh',  # Tell frontend this is a refresh action
                'clearCanvas': True,  # Explicit flag to clear frontend
                'reactFlowStates': reactflow_states,
                'message': f'Refreshed - found {len(reactflow_states)} graph(s) in document'
            })
            
        except Exception as e:
            log(self.app, f"Error during manual graph refresh: {e}", 
                level=LogLevel.ERROR, module="PERSISTENCE_HANDLER")
            return {'success': False, 'error': str(e)}
    
