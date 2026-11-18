"""
Multiply node - multiplies two numbers together.
V2 implementation following specification.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log
from ..specification import LogLevel


@enforce_node_spec
class MultiplyNode(BaseNode):
    """Multiplies two numbers together"""
    
    NODE_TYPE = "multiply"
    NODE_CATEGORY = "math"
    NODE_NAME = "Multiply"
    NODE_DESCRIPTION = "Multiply two numbers"
    PREVIEWABLE = True  # Pure calculation: safe to run for live values
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("a", PortType.FLOAT, default_value=1.0, description="The first number to multiply."),
                PortSpec("b", PortType.FLOAT, default_value=1.0, description="The second number to multiply."),
            ],
            outputs=[
                PortSpec("result", PortType.FLOAT)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs"""
        errors = []
        
        # Check that a and b are numbers
        for input_name in ["a", "b"]:
            value = inputs.get(input_name)
            if value is not None and not isinstance(value, (int, float)):
                errors.append(f"{self.port_label(input_name)} must be a number")
        
        return errors
    
    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the multiplication"""
        app = context.get('app')
        
        # Get values with defaults
        a = float(inputs.get("a", 1.0))
        b = float(inputs.get("b", 1.0))
        
        # Perform multiplication
        result = a * b
        
        log(app, f"Multiply: {a} * {b} = {result}", 
            level=LogLevel.DEBUG, module="MULTIPLY_NODE")
        
        return {
            "result": result
        }
    
