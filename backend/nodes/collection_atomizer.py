"""
Atomizer node for converting geometry into collection data structure.
Creates virtual collection instances that can be materialized later.
"""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType, CollectionInstanceSpec, CollectionSpec, GeometryEnvelope, NoodleAttributes
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel
import uuid


@enforce_node_spec
class AtomizerNode(BaseNode):
    """Converts geometry into virtual collection instances for processing."""
    
    NODE_TYPE = "Atomizer"
    NODE_CATEGORY = "collection"
    NODE_NAME = "Atomizer"
    NODE_DESCRIPTION = "Convert geometry into virtual collection instances"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("geometry", PortType.GEOMETRY, required=True, description="The geometry to turn into a collection that arrays can repeat."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION, description="Collection")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate atomizer inputs."""
        errors = []
        
        # Check that geometry input is provided
        if not inputs.get("geometry"):
            errors.append("Geometry input is required")
            
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Convert geometry input into a virtual collection."""
        
        geometry = inputs.get("geometry")
        if not geometry:
            log(context.get('app'), "No geometry input provided to atomizer", 
                level=LogLevel.WARNING, module="ATOMIZER")
            return {"collection": None}
        
        # Create collection data structure using proper contracts
        geometry_envelope = GeometryEnvelope(
            kind=geometry.get("kind", "brep"),
            id=geometry.get("id", str(uuid.uuid4())[:8]),
            geometry=geometry.get("geometry"),
            geometry_name=geometry.get("geometry_name", "Unknown")
        )
        
        # Create instance with proper Maya-style identity transform
        instance = CollectionInstanceSpec(
            instance_id=str(uuid.uuid4())[:8],
            source_geometry_id=geometry_envelope.id,
            transform=NoodleAttributes.identity(),  # Maya-style identity transform
            metadata={
                "source_node": self.NODE_TYPE,
                "source_id": context.get('node_id', 'unknown')
            }
        )
        
        # Create collection with proper contract
        collection_spec = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=str(uuid.uuid4())[:8],
            source_geometries=[geometry_envelope],
            instances=[instance]
        )
        
        log(context.get('app'), 
            f"Atomized geometry into collection with {len(collection_spec.instances)} instance(s)",
            level=LogLevel.DEBUG, module="ATOMIZER")
        
        return {"collection": collection_spec}
