"""
Gradient Modifier: the falloff curve along a strand, for any Effector's strength port.

t runs from 0 at a strand's first instance to 1 at its last (strand_position / (strand_length - 1),
or grid_u_index / (count_u - 1) after an Array with no Separator). The falloff curve, stored on the
`curve` port as JSON and edited in the palette's curve editor, turns t into a value.
See backend/utilities/field_curve.py.
"""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.field_curve import curve_problems, default_curve_json
from .base import BaseNode


@enforce_node_spec
class GradientModifierNode(BaseNode):

    NODE_TYPE = "Modifier_Gradient"
    NODE_CATEGORY = "modifiers"
    NODE_NAME = "Gradient"
    NODE_DESCRIPTION = "A curve along each strand, from its first instance to its last"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("curve", PortType.STRING, default_value=default_curve_json('Linear'),
                         show_input_field=False, show_input_handle=False, label="Curve",
                         description="The value along each strand, first instance to last; shape it in the curve editor."),
                PortSpec(
                    "amplitude",
                    PortType.FLOAT,
                    default_value=1.0,
                    label="Amplitude",
                    description="Output multiplier — scales the gradient result.",
                ),
            ],
            outputs=[
                PortSpec("modifier", PortType.FLOAT, label="Modifier"),
            ],
            description=cls.NODE_DESCRIPTION,
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        return curve_problems(inputs.get("curve"))

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        amplitude = inputs.get("amplitude", 1.0)
        return {
            "modifier": {
                "modifier_type": "gradient",
                "curve":         inputs.get("curve"),
                "amplitude":     amplitude if isinstance(amplitude, dict) else float(amplitude),
            }
        }
