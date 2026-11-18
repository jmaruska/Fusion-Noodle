"""
Null Node — outputs a single identity-transform instance with no real geometry.

Purpose: seed the array system with an origin position when no geometry is
needed in the pipeline.  Canonical use: Null → Array → Interpolize → curves.

The sentinel GeometryEnvelope (kind="null", geometry=None) satisfies the
non-empty source_geometries check in array nodes without supplying a real BRep.
Materializer will fail gracefully on a null collection — that path is
semantically wrong and not supported.
"""

import uuid
from typing import Dict, Any, List

from ..enforcement import enforce_node_spec
from ..contracts import (
    NodeSpec, PortSpec, PortType,
    CollectionSpec, CollectionInstanceSpec, GeometryEnvelope, NoodleAttributes
)
from .base import BaseNode


@enforce_node_spec
class NullNode(BaseNode):

    NODE_TYPE = "Null"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Null to Collection"
    NODE_DESCRIPTION = "Seed node — single origin instance with no geometry"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION,
                         description="Single origin instance at world zero"),
            ],
            description=cls.NODE_DESCRIPTION
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        sentinel = GeometryEnvelope(
            kind="null",
            id="null",
            geometry=None,
            geometry_name="Null"
        )

        instance = CollectionInstanceSpec(
            instance_id="null_0",
            source_geometry_id="null",
            transform=NoodleAttributes.identity(),
            metadata={}
        )

        collection = CollectionSpec(
            collection_type="point_collection",
            collection_id=str(uuid.uuid4())[:8],
            source_geometries=[sentinel],
            instances=[instance],
            metadata={"array_type": "null", "count_u": 1, "count_v": 1}
        )

        return {"collection": collection}
