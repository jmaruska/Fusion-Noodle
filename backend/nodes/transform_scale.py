"""
Scale Transform Node - V2 Implementation

Creates scale transform objects that can be applied to collections via effectors.
This node outputs a TransformSpec with scale information.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType, NoodleAttributes, Vector3Spec
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode

@enforce_node_spec
class ScaleTransformNode(BaseNode):
    """
    Scale transform node for creating scale operations.
    
    Creates uniform or non-uniform scale transforms that can be applied
    to geometry collections via effector nodes. Scale operations are
    applied around the object centers.
    """

    NODE_TYPE = "Scale_Transform"
    NODE_CATEGORY = "transform"
    NODE_NAME = "Scale"
    NODE_DESCRIPTION = "Create scale transform"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return the node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Primary scale factor for uniform scaling  
                PortSpec("scale", PortType.FLOAT, min_value=0.001, required=True, default_value=1.0, label="Scale Factor", description="Multiplies size equally in every direction; 1 leaves it unchanged."),
                
                # Reference point for scaling (default: object centers)
                # PortSpec("reference", PortType.VECTOR3, required=False, 
                #         default_value={"x": 0.0, "y": 0.0, "z": 0.0}, 
                #         label="Scale Reference Point"),
                
                # Optional input transform for chaining
                PortSpec("input_transform", PortType.TRANSFORM, required=False, label="Input Transform", description="An earlier transform to build on; this scale is applied after it."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("transform", PortType.TRANSFORM, label="Transform")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate scale transform inputs"""
        # Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)
        errors = []
        reference = inputs.get('reference', {"x": 0.0, "y": 0.0, "z": 0.0})
        if isinstance(reference, dict):
            for coord in ['x', 'y', 'z']:
                if coord in reference:
                    val = reference[coord]
                    if not isinstance(val, (int, float)):
                        errors.append(f"Reference point {coord} must be a number")
        else:
            errors.append("Reference point must be a valid vector3 object")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute scale transform creation with matrix chaining"""
        app = context.get('app')
        log(app, "*** EXECUTING SCALE TRANSFORM NODE ***", 
            level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
        
        # Get scale inputs
        scale = float(inputs.get('scale', 1.0))
        reference_input = inputs.get('reference', {"x": 0.0, "y": 0.0, "z": 0.0})
        input_transform = inputs.get('input_transform')
        
        log(app, f"Scale inputs: scale={scale}, reference={reference_input}", 
            level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
        
        try:
            # Import matrix utilities for chaining
            from ..utilities.transform_utils import (
                create_identity_matrix_dict, create_scale_matrix_dict, multiply_matrix_dicts
            )
            
            # Create this transform's scale matrix
            scale_matrix = create_scale_matrix_dict(scale, scale, scale)  # Uniform scaling
            
            # Chain with input transform if provided
            if input_transform and isinstance(input_transform, dict):
                input_matrix = input_transform.get('transform_matrix')
                if input_matrix:
                    # Multiply: input_matrix * scale_matrix (input applied first, then scale)
                    final_matrix = multiply_matrix_dicts(input_matrix, scale_matrix)
                    
                    # Get chain info from input
                    chained_ops = input_transform.get('operation_chain', [])
                    chained_ops.append('scale')
                    
                    log(app, "Chained with input transform matrix", 
                        level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
                else:
                    final_matrix = scale_matrix
                    chained_ops = ['scale']
                    log(app, "Input transform found but no matrix - using scale only", 
                        level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
            else:
                final_matrix = scale_matrix
                chained_ops = ['scale']
                log(app, "Creating new standalone scale transform", 
                    level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
            
            # Prepare clean matrix-only result (no component preservation)
            result_dict = {
                # Matrix-based format (pure approach)
                'transform_type': 'matrix_chained',
                'transform_matrix': final_matrix,
                'chained': bool(input_transform),
                'last_operation': 'scale',
                'operation_chain': chained_ops
            }
            
            # Store reference point information (for future use)
            if isinstance(reference_input, dict):
                result_dict['reference_point'] = reference_input
            
            log(app, f"Created matrix-based scale transform: scale={scale}x, chained={bool(input_transform)}", 
                level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
            log(app, f"Operation chain: {' → '.join(chained_ops)}", 
                level=LogLevel.DEBUG, module="TRANSFORM_SCALE")
            
            return {"transform": result_dict}
                
        except Exception as e:
            log(app, f"Scale Transform: Execution error: {e}", 
                level=LogLevel.ERROR, module="TRANSFORM_SCALE")
            import traceback
            log(app, f"Traceback: {traceback.format_exc()}", 
                level=LogLevel.ERROR, module="TRANSFORM_SCALE")
            
            # Return identity transform on error
            from ..utilities.transform_utils import create_identity_matrix_dict
            identity = create_identity_matrix_dict() 
            return {"transform": {
                'transform_type': 'matrix_chained',
                'transform_matrix': identity,
                'scale_factor': 1.0,
                'chained': False,
                'last_operation': 'identity'
            }}
