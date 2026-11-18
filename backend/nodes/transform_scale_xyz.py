"""
Scale Non-Uniform Transform Node - V2 Implementation

Creates a non-proportional scale transform with independent X, Y, Z scale factors.
Mirrors transform_scale.py exactly; the only difference is three axis inputs instead of one.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode

@enforce_node_spec
class ScaleXYZTransformNode(BaseNode):

    NODE_TYPE = "scale_xyz"
    NODE_CATEGORY = "transform"
    NODE_NAME = "Scale Non-Uniform"
    NODE_DESCRIPTION = "Create non-uniform scale transform with independent X, Y, Z factors"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("scale_x", PortType.FLOAT, min_value=0.001, required=False, default_value=1.0, label="Scale X", description="Multiplies size along X; 1 leaves it unchanged."),
                PortSpec("scale_y", PortType.FLOAT, min_value=0.001, required=False, default_value=1.0, label="Scale Y", description="Multiplies size along Y; 1 leaves it unchanged."),
                PortSpec("scale_z", PortType.FLOAT, min_value=0.001, required=False, default_value=1.0, label="Scale Z", description="Multiplies size along Z; 1 leaves it unchanged."),
                PortSpec("input_transform", PortType.TRANSFORM, required=False, label="Input Transform", description="An earlier transform to build on; this scale is applied after it."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("transform", PortType.TRANSFORM, label="Transform")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        app = context.get('app')
        log(app, "*** EXECUTING SCALE XYZ TRANSFORM NODE ***",
            level=LogLevel.DEBUG, module="TRANSFORM_SCALE_XYZ")

        scale_x = float(inputs.get('scale_x', 1.0))
        scale_y = float(inputs.get('scale_y', 1.0))
        scale_z = float(inputs.get('scale_z', 1.0))
        input_transform = inputs.get('input_transform')

        log(app, f"Scale XYZ inputs: sx={scale_x}, sy={scale_y}, sz={scale_z}",
            level=LogLevel.DEBUG, module="TRANSFORM_SCALE_XYZ")

        try:
            from ..utilities.transform_utils import (
                create_scale_matrix_dict, multiply_matrix_dicts
            )

            scale_matrix = create_scale_matrix_dict(scale_x, scale_y, scale_z)

            if input_transform and isinstance(input_transform, dict):
                input_matrix = input_transform.get('transform_matrix')
                if input_matrix:
                    final_matrix = multiply_matrix_dicts(input_matrix, scale_matrix)
                    chained_ops = list(input_transform.get('operation_chain', []))
                    chained_ops.append('scale')
                    log(app, "Chained with input transform matrix",
                        level=LogLevel.DEBUG, module="TRANSFORM_SCALE_XYZ")
                else:
                    final_matrix = scale_matrix
                    chained_ops = ['scale']
            else:
                final_matrix = scale_matrix
                chained_ops = ['scale']
                log(app, "Creating new standalone scale_xyz transform",
                    level=LogLevel.DEBUG, module="TRANSFORM_SCALE_XYZ")

            result_dict = {
                'transform_type': 'matrix_chained',
                'transform_matrix': final_matrix,
                'chained': bool(input_transform),
                'last_operation': 'scale',
                'operation_chain': chained_ops
            }

            log(app, f"Created scale_xyz transform: sx={scale_x}, sy={scale_y}, sz={scale_z}, chained={bool(input_transform)}",
                level=LogLevel.DEBUG, module="TRANSFORM_SCALE_XYZ")
            log(app, f"Operation chain: {' → '.join(chained_ops)}",
                level=LogLevel.DEBUG, module="TRANSFORM_SCALE_XYZ")

            return {"transform": result_dict}

        except Exception as e:
            log(app, f"Scale XYZ Transform: Execution error: {e}",
                level=LogLevel.ERROR, module="TRANSFORM_SCALE_XYZ")
            import traceback
            log(app, f"Traceback: {traceback.format_exc()}",
                level=LogLevel.ERROR, module="TRANSFORM_SCALE_XYZ")

            from ..utilities.transform_utils import create_identity_matrix_dict
            identity = create_identity_matrix_dict()
            return {"transform": {
                'transform_type': 'matrix_chained',
                'transform_matrix': identity,
                'chained': False,
                'last_operation': 'identity'
            }}
