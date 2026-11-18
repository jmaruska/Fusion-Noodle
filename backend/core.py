"""
Core application singleton - lightweight orchestrator.
Only handles system messages and delegates to specialized handlers.
"""

from typing import Dict, Any, Optional
from .utilities.log_utils import log
from .specification import LogLevel

class Application:
    """Central orchestrator - delegates to specialized handlers"""
    
    _instance: Optional['Application'] = None
    
    def __init__(self):
        self.fusion_app = None
        self.fusion_ui = None
        self.design = None
        self.initialized = False
        self.base_feature = None
        self.handlers = {}
        self._routes = {}  # message -> handler name, built from the handlers' ACTIONS
        self.palette_open = True  # False between a palette close and the next palette_ready
        
        # Minimal state for orchestration
        self.current_graph = {}
        self.node_instances = {}
        
        # Name registry: node_id → [body_name, ...] populated during each execution.
        # Cleared at the start of every execute; used by the visibility handler for
        # fresh, exact name-based lookups that survive finishEdit().
        self.node_body_names = {}
    
    @classmethod
    def get_instance(cls) -> 'Application':
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def initialize(self, fusion_context: Dict[str, Any]):
        """Initialize with Fusion context and handlers"""
        self.fusion_app = fusion_context.get('app')
        self.fusion_ui = fusion_context.get('ui')
        self.version = fusion_context.get('version', 'unknown')
        self.settings = dict(fusion_context.get('settings') or {})
        
        # Safely get the active product
        try:
            self.design = self.fusion_app.activeProduct if self.fusion_app else None
        except Exception as e:
            log(self.fusion_app, f"No active document (this is OK): {e}", 
                level=LogLevel.DEBUG, module="APPLICATION")
            self.design = None
        
        # Don't auto-create BaseFeature on startup - only when actually needed
        # This prevents unwanted timeline features when just enabling the add-in
        log(self.fusion_app, "Core initialized - BaseFeature will be created when first needed", 
            level=LogLevel.INFO, module="APPLICATION")
        
        # Initialize all handlers
        self._initialize_handlers()
        
        self.initialized = True
        log(self.fusion_app, "Core application initialized", 
            level=LogLevel.INFO, module="APPLICATION")
    
    def _share_base_feature(self):
        """Give every handler the current Base Feature (or None after Clear).

        Handlers that read it straight from this object through a read-only
        property need nothing, and assigning to them would raise.
        """
        for handler in self.handlers.values():
            if hasattr(handler, 'context'):
                handler.context['base_feature'] = self.base_feature
                handler.context['noodle_base_feature'] = self.base_feature
            if isinstance(getattr(type(handler), 'base_feature', None), property):
                continue
            if hasattr(handler, 'base_feature'):
                handler.base_feature = self.base_feature

    def _recreate_base_feature(self):
        """Delete and recreate the BaseFeature for fast clearing"""
        if not self.design:
            return False
            
        root_comp = self.design.rootComponent
        if not root_comp:
            return False
            
        base_features = root_comp.features.baseFeatures
        
        # Delete existing Noodle base feature if it exists
        try:
            # Find features by name prefix to avoid touching stale references
            for i in range(base_features.count):
                try:
                    feature = base_features.item(i)
                    name = feature.name  # Access once inside try to avoid stale issues
                    if name.startswith("Noodle_Geometry"):
                        feature.deleteMe()
                        log(self.fusion_app, "Deleted existing Noodle base feature", 
                            level=LogLevel.DEBUG, module="APPLICATION")
                        # Do not break; delete all matching to be safe
                except Exception as inner_e:
                    log(self.fusion_app, f"Skipping deletion of a stale BaseFeature: {inner_e}", 
                        level=LogLevel.WARNING, module="APPLICATION")
        except Exception as e:
            log(self.fusion_app, f"Error while scanning/deleting base features: {e}", 
                level=LogLevel.WARNING, module="APPLICATION")
        
        # Clear stored reference unconditionally
        self.base_feature = None
        
        # Create new base feature
        try:
            self.base_feature = base_features.add()
            self.base_feature.name = "Noodle_Geometry"
            log(self.fusion_app, "Recreated Noodle base feature for fast clearing", 
                level=LogLevel.INFO, module="APPLICATION")
            
            self._share_base_feature()
                    
            return True
            
        except Exception as e:
            log(self.fusion_app, f"Could not recreate base feature: {e}", 
                level=LogLevel.ERROR, module="APPLICATION")
            return False
    
    def _delete_base_feature(self) -> bool:
        """Delete ALL Noodle BaseFeatures from the ACTIVE document timeline"""
        try:
            deleted_count = 0
            
            # Always use the currently active document
            active_design = None
            if self.fusion_app and self.fusion_app.activeDocument:
                active_design = self.fusion_app.activeDocument.design
                log(self.fusion_app, f"🎯 Clearing BaseFeatures from active document: {self.fusion_app.activeDocument.name}", 
                    level=LogLevel.INFO, module="APPLICATION")
            
            # Get the feature collection and delete by index/reference
            if active_design and active_design.rootComponent:
                base_features = active_design.rootComponent.features.baseFeatures
                
                # Iterate backwards to avoid index shifting during deletion
                for i in range(base_features.count - 1, -1, -1):
                    feature = base_features.item(i)
                    if feature and feature.name and feature.name.startswith("Noodle_Geometry"):
                        log(self.fusion_app, f"Deleting BaseFeature: {feature.name}",
                            level=LogLevel.DEBUG, module="APPLICATION")
                        feature.deleteMe()
                        deleted_count += 1
            
            # Clear our reference regardless
            self.base_feature = None

            # Clear also discards any unsaved edits to the graph
            persistence = self.handlers.get('persistence')
            if persistence and active_design:
                persistence.clear_working_graph(active_design)
            
            self._share_base_feature()
            
            if deleted_count > 0:
                log(self.fusion_app, f"✅ Deleted {deleted_count} Noodle BaseFeature(s) from timeline", 
                    level=LogLevel.INFO, module="APPLICATION")
            else:
                log(self.fusion_app, "📭 No Noodle BaseFeatures found to delete", 
                    level=LogLevel.INFO, module="APPLICATION")
            
            return True
        except Exception as e:
            log(self.fusion_app, f"❌ Error deleting BaseFeature: {e}", 
                level=LogLevel.ERROR, module="APPLICATION")
            return False
    
    # Messages the core answers itself, and the method that answers each.
    SYSTEM_ACTIONS = {
        'palette_ready': '_handle_palette_ready',
    }

    def palette_closed(self) -> int:
        """The palette was closed: remove the visualizer's dots from every open
        document, and refuse redraws until it opens again. The dots only mean
        something while the palette is there to change or turn them off."""
        self.palette_open = False
        graph = self.handlers.get('graph') if getattr(self, 'handlers', None) else None
        if graph is not None:
            graph._last_visualizer_request = None
            graph._last_outlines = None
        try:
            from .visualizer import VisualizerRenderer
            return VisualizerRenderer(self.fusion_app).clear_everywhere()
        except Exception as e:
            log(self.fusion_app, f"Could not clear visualizer dots: {e}", level=LogLevel.WARNING, module="APPLICATION")
            return 0

    @classmethod
    def build_routes(cls, handlers: Dict[str, Any]) -> Dict[str, str]:
        """Build {message: handler name} from each handler's ACTIONS table.

        Handlers are the single place a message is declared. Two handlers claiming
        the same message, or a handler naming a method it doesn't have, is a
        programming error and stops startup with a clear message.
        """
        routes: Dict[str, str] = {}
        for handler_name, handler in handlers.items():
            for action, method_name in getattr(handler, 'ACTIONS', {}).items():
                if action in cls.SYSTEM_ACTIONS:
                    raise RuntimeError(f"Message '{action}' is answered by the core; "
                                       f"handler '{handler_name}' cannot also declare it")
                if action in routes:
                    raise RuntimeError(f"Message '{action}' is declared by both "
                                       f"'{routes[action]}' and '{handler_name}'")
                if not callable(getattr(handler, method_name, None)):
                    raise RuntimeError(f"Handler '{handler_name}' declares '{action}' -> "
                                       f"'{method_name}', which is not a method")
                routes[action] = handler_name
        return routes

    def _shutdown_handlers(self):
        """Let handlers release Fusion event subscriptions, then drop them."""
        for name, handler in list(self.handlers.items()):
            if hasattr(handler, 'shutdown'):
                try:
                    handler.shutdown()
                except Exception as e:
                    log(self.fusion_app, f"Handler '{name}' shutdown failed: {e}",
                        level=LogLevel.WARNING, module="APPLICATION")
        self.handlers = {}
        self._routes = {}

    def shutdown(self):
        """Release everything held against Fusion and forget the singleton, so the
        next Run starts from freshly imported code."""
        # Don't leave visualizer dots behind in the viewport
        self.palette_closed()
        self._shutdown_handlers()
        self.initialized = False
        self.base_feature = None
        self.node_instances = {}
        type(self)._instance = None

    def _initialize_handlers(self):
        """Initialize all specialized handlers"""
        # A second initialize() without a stop would otherwise double-subscribe
        self._shutdown_handlers()
        context = {
            'app': self.fusion_app,
            'ui': self.fusion_ui,
            'design': self.design,
            'base_feature': self.base_feature,
            'core': self
        }
        
        # Import and initialize handlers
        from .handlers.node_registry_handler import NodeRegistryHandler
        from .handlers.graph_handler import GraphHandler
        from .handlers.geometry_handler import GeometryHandler
        from .handlers.selection_handler import SelectionHandler
        from .handlers.persistence_handler import PersistenceHandler
        
        self.handlers = {
            'node_registry': NodeRegistryHandler(self.fusion_app),
            'graph': GraphHandler(context),
            'geometry': GeometryHandler(context),
            'selection': SelectionHandler(context),
            'persistence': PersistenceHandler(context),
        }
        self._routes = self.build_routes(self.handlers)
        
        log(self.fusion_app, f"Initialized {len(self.handlers)} handlers",
            level=LogLevel.DEBUG, module="APPLICATION")
    
    def _is_parametric_design(self) -> bool:
        """True unless the active design is a direct-modeling (no history) design."""
        try:
            import adsk.fusion  # type: ignore
            return self.design.designType != adsk.fusion.DesignTypes.DirectDesignType
        except Exception:
            return True  # Don't block on an unexpected API shape

    def _check_design(self) -> bool:
        """Check if we have an active design, try to get it if not"""
        try:
            # Get current active design. Only a Design product counts: CAM or Drawing
            # products have no rootComponent and would fail later with an AttributeError.
            import adsk.fusion  # type: ignore
            product = self.fusion_app.activeProduct if self.fusion_app else None
            current_design = adsk.fusion.Design.cast(product) if product else None
            
            # Check if design has actually changed (different object/document)
            if self.design != current_design:
                # CRITICAL: Complete state reset when switching documents
                old_design_name = getattr(self.design, 'name', 'None') if self.design else 'None'
                new_design_name = getattr(current_design, 'name', 'None') if current_design else 'None'
                
                log(self.fusion_app, f"🔄 Design changed: {old_design_name} → {new_design_name}", 
                    level=LogLevel.INFO, module="APPLICATION")
                
                # Clear all state for document isolation
                self.design = current_design
                self.base_feature = None
                self.current_graph = {}
                self.node_instances = {}
                
                if hasattr(self, 'current_reactflow_state'):
                    self.current_reactflow_state = None
                
                # Update handlers with new design
                for handler in self.handlers.values():
                    if hasattr(handler, 'context'):
                        handler.context['design'] = current_design
                        handler.context['base_feature'] = None
                        handler.context['noodle_base_feature'] = None
                
                log(self.fusion_app, "✅ Complete state reset performed for document switch", 
                    level=LogLevel.INFO, module="APPLICATION")
            else:
                # Same design, just ensure it's set
                self.design = current_design
                if current_design:
                    # Update handlers anyway to ensure consistency
                    for handler in self.handlers.values():
                        if hasattr(handler, 'context'):
                            handler.context['design'] = current_design
                            
        except Exception as e:
            log(self.fusion_app, f"Error checking design: {e}", 
                level=LogLevel.ERROR, module="APPLICATION")
            self.design = None
            
        return self.design is not None
    
    def handle_message(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Route messages to appropriate handlers"""
        
        # For certain actions that need a design, check first
        needs_design = ['generateGeometry']
        if action in needs_design:
            if not self._check_design():
                has_product = bool(self.fusion_app and self.fusion_app.activeProduct)
                return {
                    'success': False,
                    'error': ('Noodle works in the Design workspace. Switch to Design and try again.'
                              if has_product else
                              'No active document. Please create or open a document first.')
                }
            if not self._is_parametric_design():
                return {
                    'success': False,
                    'error': ('This design has "Do not capture design history" turned on. '
                              'Noodle needs the timeline: right-click the root component in the browser '
                              'and choose "Capture Design History", then try again.')
                }
        
        # Messages the core answers itself
        system_method = self.SYSTEM_ACTIONS.get(action)
        if system_method:
            try:
                return getattr(self, system_method)(data)
            except Exception as e:
                log(self.fusion_app, f"Error in system action {action}: {e}", 
                    level=LogLevel.ERROR, module="APPLICATION")
                return {'success': False, 'error': str(e)}
        
        # Everything else goes to the handler that declared it
        handler_name = self._routes.get(action)
        handler = self.handlers.get(handler_name) if handler_name else None
        if handler:
            try:
                return handler.handle(action, data)
            except Exception as e:
                log(self.fusion_app, f"Error in {handler_name}.{action}: {e}", 
                    level=LogLevel.ERROR, module="APPLICATION")
                return {'success': False, 'error': str(e)}
        
        log(self.fusion_app, f"Unknown action: {action}", 
            level=LogLevel.WARNING, module="APPLICATION")
        return {'success': False, 'error': f'Unknown action: {action}'}
    
    def _handle_palette_ready(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle palette ready event - initialize and return node registry"""
        # Check if we have a document now
        has_document = self._check_design()

        # A freshly opened palette has no visualizers on, so no dots should remain
        # from before it was closed or reloaded.
        self.palette_open = True
        if has_document:
            try:
                from .visualizer import VisualizerRenderer
                VisualizerRenderer(self.fusion_app).clear()
            except Exception as e:
                log(self.fusion_app, f"Could not clear visualizer dots: {e}", level=LogLevel.WARNING, module="APPLICATION")
        
        log(self.fusion_app, f"palette_ready: has_document={has_document}", 
            level=LogLevel.INFO, module="APPLICATION")
        
        # Scan for existing ReactFlow state when palette opens
        current_reactflow_state = None
        if has_document and 'persistence' in self.handlers:
            try:
                persistence_handler = self.handlers['persistence']
                scan_result = persistence_handler._scan_document({})
                
                if scan_result.get('success') and scan_result.get('reactFlowStates'):
                    states = scan_result['reactFlowStates']
                    log(self.fusion_app, f"Found {len(states)} existing ReactFlow states in document", 
                        level=LogLevel.INFO, module="APPLICATION")
                    
                    # Use the first state as the current state
                    if states:
                        current_reactflow_state = states[0]
                        log(self.fusion_app, f"Will restore ReactFlow state with {len(current_reactflow_state.get('nodes', []))} nodes", 
                            level=LogLevel.INFO, module="APPLICATION")
                else:
                    log(self.fusion_app, "No existing ReactFlow states found in document", 
                        level=LogLevel.INFO, module="APPLICATION")
            except Exception as e:
                log(self.fusion_app, f"Could not scan for existing ReactFlow states: {e}", 
                    level=LogLevel.WARNING, module="APPLICATION")
        
        # Initialize node registry and get specs
        from .nodes import NodeRegistry
        NodeRegistry.ensure_initialized(self.fusion_app)
        node_specs = NodeRegistry.get_all_specs()
        
        log(self.fusion_app, f"Returning palette_ready with {len(node_specs)} nodes", 
            level=LogLevel.INFO, module="APPLICATION")
        
        # Return both node specs and ReactFlow state for restoration
        response = {
            'success': True,
            'data': {
                'nodes': node_specs,
                'sections': NodeRegistry.get_menu_sections(),
                'version': getattr(self, 'version', 'unknown')
            }
        }
        
        if current_reactflow_state:
            response['reactFlowState'] = current_reactflow_state
            response['workingCopy'] = bool(scan_result.get('workingCopy'))
            response['notes'] = scan_result.get('notes', [])
        
        return response
