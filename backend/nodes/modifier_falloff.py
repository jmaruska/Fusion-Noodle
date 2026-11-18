"""
Falloff Modifier: a falloff field as a modifier, for any Effector's strength port.

The Effector evaluates it per instance through evaluate_modifier(), reading surface_point from
instance metadata for the world position. Shape, placement and curve work as on the Falloff
Effector; see backend/utilities/field_sources.py.
"""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.field_sources import shape_problems, shape_ports
from .base import BaseNode


@enforce_node_spec
class FalloffModifierNode(BaseNode):

    NODE_TYPE = "Modifier_Falloff"
    NODE_CATEGORY = "modifiers"
    NODE_NAME = "Falloff"
    NODE_DESCRIPTION = "Spatial strength falloff from a world-space center point"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            wide=True,  # Shape dropdown
            inputs=[
                *shape_ports("center"),
                PortSpec("spacer_3",      PortType.SPACER),
                PortSpec("amplitude",     PortType.FLOAT,   default_value=1.0,  label="Amplitude", description="Multiplies the falloff's value; connect another modifier to vary it."),
            ],
            outputs=[
                PortSpec("modifier", PortType.FLOAT, label="Modifier"),
            ],
            description=cls.NODE_DESCRIPTION
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        return shape_problems(inputs)

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        # Every shape port goes to the evaluator, named from the shared list so a new
        # or renamed port can't be left behind (Scale once was)
        config = {port.name: inputs.get(port.name) for port in shape_ports("center")
                  if inputs.get(port.name) is not None}
        amplitude = inputs.get("amplitude", 1.0)
        config.update({
            "modifier_type": "falloff",
            "amplitude": amplitude if isinstance(amplitude, dict) else float(amplitude),
        })
        return {"modifier": config}
