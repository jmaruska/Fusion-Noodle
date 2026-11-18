"""
Move Transform Node - Matrix-based translation with chaining support

Creates translation transforms that can be chained with other transforms.
Supports 3D translation (tx, ty, tz) with matrix-based composition.
"""

import math
from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType, Vector3Spec
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode


@enforce_node_spec
class MoveTransformNode(BaseNode):
    """
    Move Transform Node - creates translation transforms with matrix chaining.
    
    Translates geometry by specified X, Y, Z offsets. Can chain with other transforms
    to create composite transformations respecting graph topology order.
    """

    NODE_TYPE = "Move_Transform"
    NODE_CATEGORY = "transform"
    NODE_NAME = "Move"
    NODE_DESCRIPTION = "Create translation transforms with chaining support"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Transform chaining
                PortSpec("input_transform", PortType.TRANSFORM, required=False, label="Input Transform", description="An earlier transform to build on; this move is applied after it."),
                
                # Translation parameters
                PortSpec("translation_spacer", PortType.SPACER),
                PortSpec("x", PortType.FLOAT, unit="length", required=False, default_value=0.0, label="X", description="Distance to move along X."),
                PortSpec("y", PortType.FLOAT, unit="length", required=False, default_value=0.0, label="Y", description="Distance to move along Y."), 
                PortSpec("z", PortType.FLOAT, unit="length", required=False, default_value=0.0, label="Z", description="Distance to move along Z."),
                
                # Future: Reference point and local coordinates
                # PortSpec("reference_spacer", PortType.SPACER),
                # PortSpec("reference", PortType.VECTOR3, required=False, default_value={"x": 0.0, "y": 0.0, "z": 0.0}, label="Reference"),
                # PortSpec("local_space", PortType.BOOLEAN, required=False, default_value=False, label="Local Space"),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("transform", PortType.TRANSFORM, label="Transform")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate move transform inputs"""
        errors = []
        
        # Validate translation values
        for coord in ['x', 'y', 'z']:
            value = inputs.get(coord, 0.0)
            if not isinstance(value, (int, float)):
                errors.append(f"{self.port_label(coord)} must be a number")
                
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute move transform creation with matrix chaining"""
        app = context.get('app')
        log(app, "*** EXECUTING MOVE TRANSFORM NODE ***", 
            level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
        
        # Get translation inputs
        tx = float(inputs.get('x', 0.0))
        ty = float(inputs.get('y', 0.0))
        tz = float(inputs.get('z', 0.0))
        input_transform = inputs.get('input_transform')
        
        log(app, f"Move inputs: tx={tx}, ty={ty}, tz={tz}", 
            level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
        
        try:
            # Import matrix utilities for chaining
            from ..utilities.transform_utils import (
                create_identity_matrix_dict, create_translation_matrix_dict, multiply_matrix_dicts
            )
            
            # Create this transform's translation matrix
            translation_matrix = create_translation_matrix_dict(tx, ty, tz)
            
            # Chain with input transform if provided
            if input_transform and isinstance(input_transform, dict):
                input_matrix = input_transform.get('transform_matrix')
                if input_matrix:
                    # Multiply: input_matrix * translation_matrix (input applied first, then translation)
                    final_matrix = multiply_matrix_dicts(input_matrix, translation_matrix)
                    
                    # Get chain info from input
                    chained_ops = input_transform.get('operation_chain', [])
                    chained_ops.append('move')
                    
                    log(app, "Chained with input transform matrix", 
                        level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
                else:
                    final_matrix = translation_matrix
                    chained_ops = ['move']
                    log(app, "Input transform found but no matrix - using translation only", 
                        level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
            else:
                final_matrix = translation_matrix
                chained_ops = ['move']
                log(app, "Creating new standalone move transform", 
                    level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
            
            # Prepare clean matrix-only result (no component preservation)
            result_dict = {
                # Matrix-based format (pure approach)
                'transform_type': 'matrix_chained',
                'transform_matrix': final_matrix,
                'chained': bool(input_transform),
                'last_operation': 'move',
                'operation_chain': chained_ops
            }
            
            log(app, f"Created matrix-based move transform: tx={tx}, ty={ty}, tz={tz}, chained={bool(input_transform)}", 
                level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
            log(app, f"Operation chain: {' → '.join(chained_ops)}", 
                level=LogLevel.DEBUG, module="TRANSFORM_MOVE")
            
            return {"transform": result_dict}
                
        except Exception as e:
            log(app, f"Error in move transform execution: {e}", 
                level=LogLevel.ERROR, module="TRANSFORM_MOVE")
            
            # Return identity transform on error
            from ..utilities.transform_utils import create_identity_matrix_dict
            identity = create_identity_matrix_dict()
            return {"transform": {
                'transform_type': 'matrix_chained',
                'transform_matrix': identity,
                'translation_vector': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                'chained': False,
                'last_operation': 'identity'
            }}
