"""
Absolute node - outputs the absolute value of a number.
V2 implementation following specification.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log
from ..specification import LogLevel


@enforce_node_spec
class AbsoluteNode(BaseNode):
    """Outputs the absolute value of a number"""
    
    NODE_TYPE = "absolute"
    NODE_CATEGORY = "math"
    NODE_NAME = "Absolute"
    NODE_DESCRIPTION = "Output the absolute value of a number"
    PREVIEWABLE = True  # Pure calculation: safe to run for live values
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("value", PortType.FLOAT, default_value=1.0, show_input_field=False, description="The number to make non-negative."),
            ],
            outputs=[
                PortSpec("absolute", PortType.FLOAT)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs"""
        errors = []
        
        # Value should be a number
        value = inputs.get("value")
        if value is not None and not isinstance(value, (int, float)):
            errors.append("Value must be a number")
        
        return errors
    
    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the absolute value calculation"""
        app = context.get('app')
        
        value = inputs.get("value", 1.0)
        
        # Calculate absolute value
        result = abs(value)
        
        log(app, f"Absolute node: abs({value}) = {result}", 
            level=LogLevel.DEBUG, module="ABSOLUTE_NODE")
        
        return {"absolute": result}
    
