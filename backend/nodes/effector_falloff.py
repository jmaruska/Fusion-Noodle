"""
Falloff Effector: applies a transform with a strength that depends on where each instance sits.

The Shape dropdown picks how position becomes t (0 to 1): distance from a center (Sphere),
progress from a start point to an end point (Linear), or distance outside a box (Box). The
falloff curve, edited in the palette's curve editor, turns t into strength. See
backend/utilities/field_sources.py, field_curve.py and docs/dev/falloff-fields.md.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType, CollectionInstanceSpec
from ..enforcement import enforce_node_spec
from ..utilities.field_sources import field_strength, shape_problems, shape_ports
from .effector_base import BaseEffectorNode


@enforce_node_spec
class FalloffEffectorNode(BaseEffectorNode):
    """Transform strength fades with distance from a point, shaped by the falloff curve."""

    NODE_TYPE = "Falloff_Effector"
    NODE_CATEGORY = "effector"
    NODE_NAME = "Falloff Effector"
    NODE_DESCRIPTION = "Apply spatial falloff effects to collections"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return the node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            wide=True,  # Shape dropdown
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True, label="Collection", description="The instances to transform."),
                PortSpec("transform", PortType.TRANSFORM, required=True, label="Transform", description="The move, rotate, scale or aim to apply, weighted by the falloff at each instance."),
                PortSpec("spacer_1", PortType.SPACER),
                *shape_ports("position"),
                PortSpec("spacer_3", PortType.SPACER),
                PortSpec("strength", PortType.FLOAT, default_value=1.0, label="Strength", description="Multiplies the falloff's strength; negative pushes the other way. Connect a modifier to vary it."),
            ],
            outputs=[
                PortSpec("collection", PortType.COLLECTION, label="Collection")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs for falloff effector"""
        errors = []

        collection = inputs.get('collection')
        if not collection:
            errors.append("Collection input is required")
        elif not (isinstance(collection, dict) or hasattr(collection, 'collection_type')):
            errors.append("Collection must be a valid collection object")
        elif isinstance(collection, dict) and not collection.get('source_geometries'):
            errors.append("Collection must contain source geometries")
        elif hasattr(collection, 'source_geometries') and not collection.source_geometries:
            errors.append("Collection must contain source geometries")

        transform = inputs.get('transform')
        if not transform:
            errors.append("Transform input is required")
        elif not isinstance(transform, dict):
            errors.append("Transform must be a valid transform object")

        errors.extend(shape_problems(inputs))
        return errors

    def calculate_strength(self, instance: CollectionInstanceSpec, transform_data: Dict[str, Any],
                           context: Dict[str, Any]) -> float:
        """Strength from the falloff curve at this instance's place in the field."""
        p = self._extract_position_from_instance(instance)
        return field_strength(context.get('inputs', {}), (p.x, p.y, p.z), 'position')
