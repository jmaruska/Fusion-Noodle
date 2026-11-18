"""
Number node - outputs a configurable number value.
V2 implementation following specification.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log
from ..specification import LogLevel


@enforce_node_spec
class NumberNode(BaseNode):
    """Outputs a configurable number value"""
    
    NODE_TYPE = "number"
    NODE_CATEGORY = "math"
    NODE_NAME = "Number"
    NODE_DESCRIPTION = "Output a number value"
    PREVIEWABLE = True  # Pure calculation: safe to run for live values
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("value", PortType.FLOAT, default_value=1.0, description="The number this node outputs."),
            ],
            outputs=[
                PortSpec("number", PortType.FLOAT)
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
        """Execute the number node"""
        app = context.get('app')
        
        # Get the number value with default
        value = inputs.get("value", 1.0)
        
        # Ensure it's a float
        result = float(value)
        
        log(app, f"Number node output: {result}", 
            level=LogLevel.DEBUG, module="NUMBER_NODE")
        
        return {
            "number": result
        }
    
