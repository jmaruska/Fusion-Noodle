"""
Vector3 node - creates a 3D vector from X, Y, Z components.
V2 implementation with strict Vector3Spec contract adherence.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType, Vector3Spec
from .base import BaseNode
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log
from ..specification import LogLevel


@enforce_node_spec
class Vector3Node(BaseNode):
    """Creates a 3D vector from X, Y, Z components"""
    
    NODE_TYPE = "vector3"
    NODE_CATEGORY = "math"
    NODE_NAME = "Vector3"
    NODE_DESCRIPTION = "Create 3D vector from X, Y, Z components"
    PREVIEWABLE = True  # Pure calculation: safe to run for live values
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("x", PortType.FLOAT, default_value=0.0, description="The vector's X component."),
                PortSpec("y", PortType.FLOAT, default_value=0.0, description="The vector's Y component."),
                PortSpec("z", PortType.FLOAT, default_value=0.0, description="The vector's Z component."),
            ],
            outputs=[
                PortSpec("vector", PortType.VECTOR3)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs"""
        errors = []
        
        # Check that x, y, z are numbers
        for component in ["x", "y", "z"]:
            value = inputs.get(component)
            if value is not None and not isinstance(value, (int, float)):
                errors.append(f"{self.port_label(component)} must be a number")
        
        return errors
    
    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the vector creation"""
        app = context.get('app')
        
        # Get component values with defaults
        x = float(inputs.get("x", 0.0))
        y = float(inputs.get("y", 0.0))
        z = float(inputs.get("z", 0.0))
        
        # Create Vector3Spec following the contract
        vector_spec = Vector3Spec(x=x, y=y, z=z)
        
        log(app, f"Vector3: created ({x}, {y}, {z})", 
            level=LogLevel.DEBUG, module="VECTOR3_NODE")
        
        return {
            "vector": vector_spec.to_dict()  # Always return dict format per contract
        }
    
