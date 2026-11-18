"""
Reusable selection port utility following specification patterns.
"""

from typing import Dict, Any, Optional
from ..contracts import PortSpec, PortType
from ..specification import SPECIFICATION

def create_selection_port(
    port_name: str,
    selection_type: str,
    required: bool = False,
    description: Optional[str] = None,
    show_input_handle: bool = True
) -> PortSpec:
    """
    Create a standardized selection port following specification patterns.
    
    Args:
        port_name: Name of the port (e.g., 'body', 'surface')
        selection_type: Type of selection ('body', 'surface', 'brep')
        required: Whether the port is required
        description: Optional description
        show_input_handle: Whether to show the input connection handle/dot
        
    Returns:
        PortSpec configured for selection pattern
    """
    
    # Get selection config from specification
    selection_config = SPECIFICATION.selection_patterns.selection_types.get(selection_type)
    if not selection_config:
        raise ValueError(f"Unknown selection type: {selection_type}")
    
    # Get port type from config
    port_type = getattr(PortType, selection_config['port_type'])
    
    # Create port spec with selection pattern rules
    # Map selection type to display name for description
    display_names = {
        'body': 'Body',
        'surface': 'Surface',
        'brep': 'B-Rep',
        'point': 'Point',
        'curve': 'Curve'
    }
    display_name = display_names.get(selection_type, selection_type.title())
    
    return PortSpec(
        name=port_name,
        port_type=port_type,
        required=required,
        description=description or f"Select a {display_name.lower()}",
        selection_type=selection_type,
        show_input_handle=show_input_handle
    )

def validate_selection_value(value: Any, selection_type: str) -> bool:
    """Validate that a selection value is properly formatted"""
    if not value:
        return False
        
    selection_config = SPECIFICATION.selection_patterns.selection_types.get(selection_type)
    if not selection_config:
        return False
        
    # Check for required validation field
    validation_field = selection_config['validation_field']
    return isinstance(value, dict) and validation_field in value

class SelectionMixin:
    """Mixin for nodes that use selection patterns"""
    
    def resolve_selection_value(self, inputs: Dict[str, Any], port_name: str, selection_type: str) -> Optional[Any]:
        """Resolve selection value with validation"""
        value = inputs.get(port_name)
        if not validate_selection_value(value, selection_type):
            return None
        return value
    