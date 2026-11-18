"""
Noise Node - V2 Implementation

Outputs a NUMBER descriptor that the effector evaluates per instance using the
instance's world-space position.  Increasing octaves layers fBm detail on top
of the base Simplex signal.

Typical chain:  Noise → Effector (strength port)

Parameters
----------
frequency   Controls spatial scale.  Low = broad smooth blobs.
            High = rapid choppy variation (the "voxelated" look).
octaves     Number of fBm layers.  1 = pure smooth Simplex.
            4+ = turbulent organic detail.
lacunarity  Frequency multiplier between octaves (default 2.0).
persistence Amplitude multiplier between octaves (default 0.5).
min / max   Output range remapped from the raw [-1, 1] signal.
seed        Deterministic seed — same seed always produces the same field.
"""

from typing import Dict, Any, List

from ..contracts import NodeSpec, PortSpec, PortType
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode


@enforce_node_spec
class NoiseNode(BaseNode):
    """
    Noise — outputs a per-instance NUMBER descriptor evaluated at world position.
    """

    NODE_TYPE = "noise"
    NODE_CATEGORY = "modifiers"
    NODE_NAME = "Noise"
    NODE_DESCRIPTION = "3D Simplex noise with optional fBm layering, evaluated per instance position"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("size",        PortType.FLOAT, min_value=0.001,   default_value=100.0, label="Size", description="Size of the noise features in cm; larger gives broader, smoother variation."),
                PortSpec("octaves",     PortType.INTEGER, default_value=1,    min_value=1, max_value=8, label="Octaves", description="Layers of finer detail added on top of the base noise."),
                PortSpec("lacunarity",  PortType.FLOAT, min_value=1.0,   default_value=2.0,  label="Lacunarity", description="How much finer each added layer of detail is than the one before."),
                PortSpec("persistence", PortType.FLOAT, min_value=0.0, max_value=1.0,   default_value=0.5,  label="Persistence", description="How strongly each added layer of detail counts compared with the one before."),
                PortSpec("spacer_1",    PortType.SPACER),
                PortSpec("min",         PortType.FLOAT,   default_value=0.0,  label="Min", description="The lowest value the noise produces."),
                PortSpec("max",         PortType.FLOAT,   default_value=1.0,  label="Max", description="The highest value the noise produces."),
                PortSpec("seed",        PortType.INTEGER, default_value=0,    label="Seed", description="Change it for a different noise pattern; the same seed always gives the same one."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("value", PortType.FLOAT, label="Value"),
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        # Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)
        errors = []
        mn = inputs.get("min", 0.0)
        mx = inputs.get("max", 1.0)
        if isinstance(mn, (int, float)) and isinstance(mx, (int, float)) and mn > mx:
            errors.append("Min cannot be greater than Max")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        import adsk.core
        app = adsk.core.Application.get()

        size        = float(inputs.get("size",        100.0))
        octaves     = int(inputs.get("octaves",       1))
        lacunarity  = float(inputs.get("lacunarity",  2.0))
        persistence = float(inputs.get("persistence", 0.5))
        min_val     = float(inputs.get("min",         0.0))
        max_val     = float(inputs.get("max",         1.0))
        seed        = int(inputs.get("seed",          0))

        frequency = 1.0 / size if size > 0 else 1.0

        descriptor = {
            "number_type": "noise",
            "frequency":   frequency,
            "octaves":     octaves,
            "lacunarity":  lacunarity,
            "persistence": persistence,
            "min":         min_val,
            "max":         max_val,
            "seed":        seed,
        }

        log(app, f"NOISE: descriptor size={size} (freq={frequency:.4f}) oct={octaves} "
                 f"range=[{min_val},{max_val}] seed={seed}",
            level=LogLevel.DEBUG, module="NOISE_NODE")

        return {"value": descriptor}
