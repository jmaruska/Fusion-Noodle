"""
Checkerboard Modifier Node — outputs a per-instance ±amplitude pattern.

Connect to an Effector's strength port.  The pattern alternates sign at every
grid or strand crossing, making it the building block for woven curve offsets
when combined with UV Separator.

  phase=0  →  U channel  (or standalone use)
  phase=1  →  V channel  (inverted — opposite sign at every crossing)

Works with or without UV Separator:
  - Post-Separator: reads strand_index + strand_position
  - Post-Array:     falls back to grid_v_index + grid_u_index
"""

from typing import Dict, Any, List

from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode


@enforce_node_spec
class CheckerboardNode(BaseNode):

    NODE_TYPE = "Checkerboard"
    NODE_CATEGORY = "modifiers"
    NODE_NAME = "Checkerboard"
    NODE_DESCRIPTION = "Alternating ±1 pattern across grid/strand crossings — connect to Effector strength"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("phase", PortType.INTEGER,
                default_value=0,
                show_input_handle=False,
                description="Set to 1 to invert the pattern; use 1 on the V strands for an over-under weave.")
,
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("amplitude", PortType.FLOAT,
                default_value=1.0,
                show_input_handle=True,
                description="Strength alternates between plus and minus this value."),
            ],
            outputs=[
                PortSpec("modifier", PortType.FLOAT,
                         description="Per-instance modifier — connect to Effector strength port"),
            ],
            description=cls.NODE_DESCRIPTION
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        amplitude = inputs.get("amplitude", 1.0)
        if not isinstance(amplitude, dict):
            amplitude = float(amplitude)
        phase = int(inputs.get("phase", 0))

        return {
            "modifier": {
                "modifier_type": "checkerboard",
                "amplitude": amplitude,
                "phase": phase,
            }
        }
