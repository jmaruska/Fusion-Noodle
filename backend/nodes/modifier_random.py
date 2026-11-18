"""
Random Number Node - V2 Implementation

Outputs a NUMBER descriptor that the downstream effector evaluates once per
instance, producing a different value for each using (seed + instance_index)
as the per-instance seed.  This keeps the transform descriptor constant while
varying how strongly it is applied across the collection.

Typical chain:  Random → Effector (strength port)
"""

import random as _random
from typing import Dict, Any, List

from ..contracts import NodeSpec, PortSpec, PortType
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode


@enforce_node_spec
class RandomNode(BaseNode):
    """
    Random Number — outputs a per-instance NUMBER descriptor.
    Each instance receives an independent random value in [min, max].
    """

    NODE_TYPE = "random"
    NODE_CATEGORY = "modifiers"
    NODE_NAME = "Random"
    NODE_DESCRIPTION = "Generate a per-instance random number within a min/max range"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("min", PortType.FLOAT, default_value=0.0, label="Min", description="The lowest value an instance can receive."),
                PortSpec("max", PortType.FLOAT, default_value=1.0, label="Max", description="The highest value an instance can receive."),
                PortSpec("seed", PortType.INTEGER, default_value=0, label="Seed", description="Change it for a different set of values; the same seed always gives the same set."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("value", PortType.FLOAT, label="Value"),
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        min_val = inputs.get("min")
        max_val = inputs.get("max")
        if min_val is not None and not isinstance(min_val, (int, float)):
            errors.append("Min must be a number")
        if max_val is not None and not isinstance(max_val, (int, float)):
            errors.append("Max must be a number")
        if (isinstance(min_val, (int, float)) and isinstance(max_val, (int, float))
                and min_val > max_val):
            errors.append("Min value cannot be greater than max value")
        seed = inputs.get("seed")
        if seed is not None and not isinstance(seed, int):
            errors.append("Seed must be an integer")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        import adsk.core
        app = adsk.core.Application.get()

        min_val = float(inputs.get("min", 0.0))
        max_val = float(inputs.get("max", 1.0))
        seed = int(inputs.get("seed", 0))

        descriptor = {
            "number_type": "random",
            "min": min_val,
            "max": max_val,
            "seed": seed,
        }

        log(app, f"RANDOM: descriptor min={min_val} max={max_val} seed={seed}",
            level=LogLevel.DEBUG, module="RANDOM_NODE")

        return {"value": descriptor}
