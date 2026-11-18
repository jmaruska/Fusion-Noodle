"""
Aim Transform Node - V2 Implementation

Outputs a transform descriptor that tells a downstream effector to rotate each
instance so a chosen local axis (Normal) points toward a world-space position.

Pipeline: Aim → Uniform/Falloff Effector → Materializer

The per-instance quaternion is computed inside the effector loop (where the
instance's world position is known).  This node simply packages the aim
parameters so that strength/falloff can be applied in the normal effector way.
"""

import math
from typing import Dict, Any, List

from ..contracts import NodeSpec, PortSpec, PortType
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode


@enforce_node_spec
class AimTransformNode(BaseNode):
    """
    Aim Transform — outputs a TRANSFORM descriptor with transform_type='aim'.
    The effector consumes this descriptor and computes per-instance quaternions.
    """

    NODE_TYPE = "Aim_Transform"
    NODE_CATEGORY = "transform"
    NODE_NAME = "Aim"
    NODE_DESCRIPTION = "Rotate instances so a local axis points toward a world-space position"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("spacer_1", PortType.SPACER),
                PortSpec("position", PortType.VECTOR3, unit="length",
                         default_value={"x": 0.0, "y": 0.0, "z": 0.0},
                         label="Position", description="The point each instance turns to face."),
                PortSpec("spacer_2", PortType.SPACER),
                PortSpec("normal", PortType.VECTOR3,
                         default_value={"x": 0.0, "y": 1.0, "z": 0.0},
                         label="Aim Vector", description="The instance's own axis that points at the target."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("transform", PortType.TRANSFORM, label="Transform"),
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        normal = inputs.get("normal", {"x": 0.0, "y": 1.0, "z": 0.0})
        if isinstance(normal, dict):
            mag = math.sqrt(
                normal.get("x", 0.0) ** 2 +
                normal.get("y", 1.0) ** 2 +
                normal.get("z", 0.0) ** 2
            )
            if mag < 1e-6:
                errors.append("Normal cannot be a zero vector")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        import adsk.core
        app = adsk.core.Application.get()

        log(app, "*** EXECUTING AIM TRANSFORM NODE ***",
            level=LogLevel.DEBUG, module="AIM_TRANSFORM")

        pos_raw = inputs.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
        norm_raw = inputs.get("normal", {"x": 0.0, "y": 1.0, "z": 0.0})

        px = float(pos_raw.get("x", 0.0))
        py = float(pos_raw.get("y", 0.0))
        pz = float(pos_raw.get("z", 0.0))

        nx = float(norm_raw.get("x", 0.0))
        ny = float(norm_raw.get("y", 1.0))
        nz = float(norm_raw.get("z", 0.0))
        mag = math.sqrt(nx * nx + ny * ny + nz * nz)
        if mag > 1e-6:
            nx /= mag
            ny /= mag
            nz /= mag
        else:
            ny = 1.0

        result = {
            "transform_type": "aim",
            "aim_position": {"x": px, "y": py, "z": pz},
            "aim_axis": {"x": nx, "y": ny, "z": nz},
            "last_operation": "aim",
            "operation_chain": ["aim"],
        }

        log(app, f"AIM_TRANSFORM: descriptor → position=({px:.2f},{py:.2f},{pz:.2f}) "
                 f"axis=({nx:.2f},{ny:.2f},{nz:.2f})",
            level=LogLevel.DEBUG, module="AIM_TRANSFORM")

        return {"transform": result}
