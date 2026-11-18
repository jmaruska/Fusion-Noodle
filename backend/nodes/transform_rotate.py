"""
Rotate Transform Node - V2 Implementation

Creates rotate transform objects that can be applied to collections via effectors.
This node outputs a TransformSpec with rotation information.
"""

import math
from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType, NoodleAttributes, Vector3Spec
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode

@enforce_node_spec
class RotateTransformNode(BaseNode):
    """
    Rotate transform node for creating rotation operations.
    
    Creates rotation transforms that can be applied to geometry collections
    via effector nodes. Rotation operations are applied around the object
    centers in local space (spin in place).
    """

    NODE_TYPE = "Rotate_Transform"
    NODE_CATEGORY = "transform"
    NODE_NAME = "Rotate"
    NODE_DESCRIPTION = "Create rotation transform"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return the node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Transform chaining
                PortSpec("input_transform", PortType.TRANSFORM, required=False, label="Input Transform", description="An earlier transform to build on; this rotation is applied after it."),
                
                # Euler angle rotation parameters (XYZ order)
                PortSpec("rotation_spacer", PortType.SPACER),
                PortSpec("rx", PortType.FLOAT, unit="angle", required=False, default_value=0.0, label="Rotate X", description="How far to turn about the X axis."),
                PortSpec("ry", PortType.FLOAT, unit="angle", required=False, default_value=0.0, label="Rotate Y", description="How far to turn about the Y axis."),
                PortSpec("rz", PortType.FLOAT, unit="angle", required=False, default_value=0.0, label="Rotate Z", description="How far to turn about the Z axis."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("transform", PortType.TRANSFORM, label="Transform")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate rotate transform inputs"""
        errors = []
        
        # Validate rotation angles
        for axis in ['rx', 'ry', 'rz']:
            angle = inputs.get(axis, 0.0)
            if not isinstance(angle, (int, float)):
                errors.append(f"{self.port_label(axis)} must be a number")
                
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute rotate transform creation with matrix chaining"""
        app = context.get('app')
        log(app, "*** EXECUTING ROTATE TRANSFORM NODE ***", 
            level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
        
        # Get Euler angle rotation inputs
        rx = float(inputs.get('rx', 0.0))  # X-axis rotation (degrees)
        ry = float(inputs.get('ry', 0.0))  # Y-axis rotation (degrees) 
        rz = float(inputs.get('rz', 0.0))  # Z-axis rotation (degrees)
        input_transform = inputs.get('input_transform')
        
        log(app, f"Rotate inputs: rx={rx}°, ry={ry}°, rz={rz}°", 
            level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
        
        try:
            # Import matrix utilities for chaining
            from ..utilities.transform_utils import (
                create_identity_matrix_dict, create_rotation_xyz_matrix_dict, multiply_matrix_dicts
            )
            
            # Create this transform's rotation matrix using XYZ Euler order
            rotation_matrix = create_rotation_xyz_matrix_dict(rx, ry, rz)
            
            # Chain with input transform if provided
            if input_transform and isinstance(input_transform, dict):
                input_matrix = input_transform.get('transform_matrix')
                if input_matrix:
                    # Multiply: input_matrix * rotation_matrix (input applied first, then rotation)
                    final_matrix = multiply_matrix_dicts(input_matrix, rotation_matrix)
                    
                    # Get chain info from input
                    chained_ops = input_transform.get('operation_chain', [])
                    chained_ops.append('rotate')
                    
                    log(app, "Chained with input transform matrix", 
                        level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
                else:
                    final_matrix = rotation_matrix
                    chained_ops = ['rotate']
                    log(app, "Input transform found but no matrix - using rotation only", 
                        level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
            else:
                final_matrix = rotation_matrix
                chained_ops = ['rotate']
                log(app, "Creating new standalone rotation transform", 
                    level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
            
            # Prepare clean matrix-only result (no component preservation)
            result_dict = {
                # Matrix-based format (pure approach)
                'transform_type': 'matrix_chained',
                'transform_matrix': final_matrix,
                'chained': bool(input_transform),
                'last_operation': 'rotate',
                'operation_chain': chained_ops
            }
            
            log(app, f"Created matrix-based rotation transform: rx={rx}°, ry={ry}°, rz={rz}°, chained={bool(input_transform)}", 
                level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
            log(app, f"Operation chain: {' → '.join(chained_ops)}", 
                level=LogLevel.DEBUG, module="TRANSFORM_ROTATE")
            
            return {"transform": result_dict}
                
        except Exception as e:
            log(app, f"Rotate Transform: Execution error: {e}", 
                level=LogLevel.ERROR, module="TRANSFORM_ROTATE")
            import traceback
            log(app, f"Traceback: {traceback.format_exc()}", 
                level=LogLevel.ERROR, module="TRANSFORM_ROTATE")
            
            # Return identity transform on error
            from ..utilities.transform_utils import create_identity_matrix_dict
            identity = create_identity_matrix_dict()
            return {"transform": {
                'transform_type': 'matrix_chained',
                'transform_matrix': identity,
                'rotation_angle_degrees': 0.0,
                'rotation_axis': {"x": 0.0, "y": 0.0, "z": 1.0},
                'chained': False,
                'last_operation': 'identity'
            }}
