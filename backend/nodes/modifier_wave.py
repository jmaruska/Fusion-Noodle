"""
Wave Modifier — sinusoidal strength pattern along strand_position.

Outputs a modifier config dict to any Effector strength port.
The Effector evaluates it per-instance via evaluate_modifier().
"""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode


@enforce_node_spec
class WaveModifierNode(BaseNode):

    NODE_TYPE = "Modifier_Wave"
    NODE_CATEGORY = "modifiers"
    NODE_NAME = "Wave"
    NODE_DESCRIPTION = "Sinusoidal strength pattern along strand position"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("amplitude",     PortType.FLOAT, default_value=1.0,  label="Amplitude", description="Height of the wave; strength swings between plus and minus this value."),
                PortSpec("frequency",     PortType.FLOAT, min_value=0.0, default_value=1.0,  label="Frequency", description="How fast the wave cycles from one instance to the next, in radians per instance."),
                PortSpec("phase_offset",  PortType.FLOAT, default_value=0.0,  label="Phase Offset", description="Shifts the wave along the strand, in radians."),
            ],
            outputs=[
                PortSpec("modifier", PortType.FLOAT, label="Modifier"),
            ],
            description=cls.NODE_DESCRIPTION
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "modifier": {
                "modifier_type":  "wave",
                "amplitude":      inputs.get("amplitude", 1.0) if isinstance(inputs.get("amplitude", 1.0), dict) else float(inputs.get("amplitude", 1.0)),
                "frequency":      float(inputs.get("frequency",    1.0)),
                "phase_offset":   float(inputs.get("phase_offset", 0.0)),
            }
        }
