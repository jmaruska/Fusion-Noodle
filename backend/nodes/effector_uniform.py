"""
Uniform Effector Node - V2 Implementation

Applies transform operations uniformly to all instances in a collection.
Unlike falloff effectors, this applies the transform with full strength
to every instance, providing consistent transformation across the collection.
"""

from typing import Dict, Any, List
from ..contracts import (
    NodeSpec, PortSpec, PortType, CollectionInstanceSpec
)
from ..enforcement import enforce_node_spec
from .effector_base import BaseEffectorNode

@enforce_node_spec
class UniformEffectorNode(BaseEffectorNode):
    """
    Uniform effector node for applying transforms to collections.
    
    Takes a collection and a transform, then applies the transform uniformly
    (with full strength) to every instance in the collection. This provides
    consistent transformation across all geometry without spatial falloff.
    """

    NODE_TYPE = "Uniform_Effector"
    NODE_CATEGORY = "effector"
    NODE_NAME = "Uniform Effector"
    NODE_DESCRIPTION = "Apply transform uniformly to collection"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return the node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            wide=True,  # The title wraps beside the eye icon when narrow
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True, label="Collection", description="The instances to transform."),
                PortSpec("transform_spacer", PortType.SPACER),
                PortSpec("transform", PortType.TRANSFORM, required=True, label="Transform", description="The move, rotate, scale or aim to apply to every instance."),
                PortSpec("spacer_2", PortType.SPACER),
                PortSpec("strength", PortType.FLOAT, default_value=1.0, label="Strength", description="How much of the transform to apply; negative pushes the other way. Connect a modifier to vary it."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION, label="Collection")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs for uniform effector"""
        errors = []
        
        # Check collection input
        collection = inputs.get('collection')
        if not collection:
            errors.append("Collection input is required")
        elif not (isinstance(collection, dict) or hasattr(collection, 'collection_type')):
            errors.append("Collection must be a valid collection object")
        elif isinstance(collection, dict) and not collection.get('source_geometries'):
            errors.append("Collection must contain source geometries")
        elif hasattr(collection, 'source_geometries') and not collection.source_geometries:
            errors.append("Collection must contain source geometries")
        
        # Check transform input
        transform = inputs.get('transform')
        if not transform:
            errors.append("Transform input is required")
        elif not isinstance(transform, dict):
            errors.append("Transform must be a valid transform object")
            
        return errors

    def calculate_strength(self, instance: CollectionInstanceSpec, transform_data: Dict[str, Any], 
                          context: Dict[str, Any]) -> float:
        """
        Calculate strength for uniform effector - always full strength.
        
        Returns 1.0 for all instances to apply transforms uniformly.
        """
        return 1.0