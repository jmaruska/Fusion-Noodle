"""
Geometry handler - manages geometry visibility and base feature operations.
Spec-compliant implementation.
"""

from typing import Dict, Any, Optional
from ..utilities.log_utils import log
from ..specification import LogLevel

class GeometryHandler:
    """Handles geometry operations and visibility"""

    # Messages this handler accepts, and the method that answers each.
    # The core builds its routing table from these (see Application._build_routes),
    # so adding a message means adding one line here and nowhere else.
    ACTIONS = {
        'clearBaseFeature': '_clear_base_feature',
        'set_node_visibility': '_set_node_visibility',
        'set_nodes_visibility': '_set_nodes_visibility',
        'get_node_visibility': '_get_node_visibility',
    }
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.app = context['app']
        self.design = context['design']
        self.base_feature = context['base_feature']
        self.core = context['core']  # Add core reference for _delete_base_feature
        
        # Visibility state
        self.node_visibility = {}
    
    def handle(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Route geometry actions"""
        # Always refresh design and base feature references from core
        try:
            core = self.context.get('core')
            if core:
                if self.design is None or self.design != core.design:
                    self.design = core.design
                if self.base_feature is None or self.base_feature != core.base_feature:
                    self.base_feature = core.base_feature
        except Exception:
            pass
        
        
        method_name = self.ACTIONS.get(action)
        if method_name:
            return getattr(self, method_name)(data)
        
        return {'success': False, 'error': f'Unknown geometry action: {action}'}
    
    def _find_bodies_fresh(self, body_names):
        """Get fresh body references from root_comp.bRepBodies by exact name.

        Always does a live scan — never returns stale references held across finishEdit().
        Returns a list of matching body objects in scene order.
        """
        try:
            import adsk.core  # type: ignore
            app = adsk.core.Application.get()
            design = app.activeProduct
            if not design:
                return []
            root_comp = design.rootComponent
            name_set = set(body_names)
            found = []
            bbs = root_comp.bRepBodies
            for i in range(bbs.count):
                body = bbs.item(i)
                if getattr(body, 'name', '') in name_set:
                    found.append(body)
            return found
        except Exception as e:
            log(self.app, f"Fresh body lookup error: {e}", level=LogLevel.WARNING, module="GEOMETRY_HANDLER")
            return []
    
    def _clear_base_feature(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Delete the BaseFeature from timeline (clears all geometry)"""
        try:
            log(self.app, "Clearing BaseFeature from timeline", 
                level=LogLevel.INFO, module="GEOMETRY_HANDLER")
            
            # Use core method to delete BaseFeature
            success = self.core._delete_base_feature()
            
            if success:
                log(self.app, "✅ BaseFeature successfully deleted from timeline", 
                    level=LogLevel.INFO, module="GEOMETRY_HANDLER")
                return {'success': True, 'message': 'BaseFeature cleared from timeline'}
            else:
                log(self.app, "⚠️ Failed to delete BaseFeature - may not exist", 
                    level=LogLevel.WARNING, module="GEOMETRY_HANDLER")
                return {'success': False, 'error': 'Failed to delete BaseFeature'}
        except Exception as e:
            log(self.app, f"Error clearing base feature: {e}", 
                level=LogLevel.ERROR, module="GEOMETRY_HANDLER")
            return {'success': False, 'error': str(e)}
    
    def _bodies_of_node(self, node_id: str, node_type: Optional[str] = None) -> list:
        """The bodies a node created, looked up fresh from the design.

        During a Generate each node records the names of the bodies it makes. That
        record is gone after the document is closed and reopened, so when it is
        missing the bodies are found by name: every body a node makes starts with
        '<type>_<short id>_'. What is found is recorded, so later lookups are direct.
        """
        core = self.context.get('core')
        registry = getattr(core, 'node_body_names', None) if core else None

        if registry is not None and registry.get(node_id):
            bodies = self._find_bodies_fresh(registry[node_id])
            if bodies:
                return bodies

        if not node_type and core:
            node_type = getattr(core.node_instances.get(node_id), 'NODE_TYPE', None)
        if not node_type:
            return []

        from ..utilities.geometry_naming import geometry_name_prefix
        prefix = geometry_name_prefix(node_type, node_id)
        bodies = self._find_bodies_by_prefix(prefix)
        if bodies and registry is not None:
            registry[node_id] = [body.name for body in bodies]
        return bodies

    def _find_bodies_by_prefix(self, prefix: str) -> list:
        """Bodies in the root component whose name starts with `prefix`."""
        try:
            import adsk.core  # type: ignore
            design = adsk.core.Application.get().activeProduct
            if not design:
                return []
            bodies = design.rootComponent.bRepBodies
            return [bodies.item(i) for i in range(bodies.count)
                    if str(getattr(bodies.item(i), 'name', '')).startswith(prefix)]
        except Exception as e:
            log(self.app, f"Body lookup by name failed: {e}", level=LogLevel.WARNING, module="GEOMETRY_HANDLER")
            return []

    def _set_node_visibility(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Show or hide every body a node created."""
        node_id = data.get('nodeId')
        if not node_id:
            return {'success': False, 'error': 'Missing nodeId'}
        return self._set_visibility([{'nodeId': node_id, 'nodeType': data.get('nodeType')}],
                                    bool(data.get('visible', True)))

    def _set_nodes_visibility(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Show or hide the bodies of several nodes at once: {nodes: [{nodeId, nodeType}], visible}.

        The visualizer hides every node's bodies together, in one undo step.
        """
        nodes = [n for n in (data.get('nodes') or []) if isinstance(n, dict) and n.get('nodeId')]
        return self._set_visibility(nodes, bool(data.get('visible', True)))

    def _set_visibility(self, nodes: list, visible: bool) -> Dict[str, Any]:
        """Set the bodies of `nodes` visible or hidden.

        Run from Noodle's visibility command (see Noodle.py), this is one undo step and
        fast. Run straight from a palette message, every body would be its own undo step
        with its own redraw: seconds for a few thousand bodies.
        """
        for node in nodes:
            self.node_visibility[node['nodeId']] = visible
        try:
            bodies = []
            for node in nodes:
                bodies.extend(self._bodies_of_node(node['nodeId'], node.get('nodeType')))
            changed = 0
            for body in bodies:
                try:
                    if bool(body.isVisible) != visible:
                        body.isVisible = visible
                        changed += 1
                except Exception as e:
                    log(self.app, f"Failed to set visibility on '{getattr(body, 'name', '?')}': {e}",
                        level=LogLevel.WARNING, module="GEOMETRY_HANDLER")
            if not bodies:
                log(self.app, f"No bodies found for {[n['nodeId'] for n in nodes]}",
                    level=LogLevel.DEBUG, module="GEOMETRY_HANDLER")
            return {'success': True, 'matched': len(bodies), 'changed': changed}
        except Exception as e:
            log(self.app, f"Error setting visibility: {e}", level=LogLevel.ERROR, module="GEOMETRY_HANDLER")
            return {'success': False, 'error': str(e)}

    def _get_node_visibility(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Whether a node's bodies are showing. A node with no bodies reports its last set state."""
        node_id = data.get('nodeId')
        if not node_id:
            return {'success': False, 'error': 'Missing nodeId'}

        visible = self.node_visibility.get(node_id, True)
        bodies = []
        try:
            bodies = self._bodies_of_node(node_id, data.get('nodeType'))
            if bodies:
                visible = bool(bodies[0].isVisible)
        except Exception as e:
            log(self.app, f"Error in get_node_visibility: {e}", level=LogLevel.WARNING, module="GEOMETRY_HANDLER")
        return {'success': True, 'visible': visible, 'matched': len(bodies)}
