"""Node registry handler - provides node operations"""

from typing import Dict, Any
from ..utilities.log_utils import log
from ..specification import LogLevel

class NodeRegistryHandler:
    """Handles node registry operations"""

    # Messages this handler accepts, and the method that answers each.
    # The core builds its routing table from these (see Application._build_routes),
    # so adding a message means adding one line here and nowhere else.
    ACTIONS = {
        'deleteNode': '_delete_node',
    }
    
    def __init__(self, app):
        """Initialize with Fusion app reference"""
        self.fusion_app = app
        log(app, "NodeRegistryHandler initialized", 
            level=LogLevel.DEBUG, module="NODE_REGISTRY")
    
    def handle(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Route node-related actions"""
        
        method_name = self.ACTIONS.get(action)
        if method_name:
            return getattr(self, method_name)(data)
        
        # Not our action
        return {'success': False, 'error': f'Unknown node action: {action}'}
    
    def _delete_node(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Acknowledge a node deletion from the frontend"""
        node_id = data.get('id') or data.get('nodeId')
        
        if not node_id:
            return {'success': False, 'error': 'Missing node ID'}
        
        return {'success': True}
