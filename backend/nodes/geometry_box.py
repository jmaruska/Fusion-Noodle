"""Box geometry node - spec-compliant implementation."""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.log_utils import log
from ..utilities.geometry_naming import generate_geometry_name
from ..specification import LogLevel
from .base import BaseNode

@enforce_node_spec
class BoxNode(BaseNode):
    """Creates box geometry using efficient OrientedBoundingBox3D approach"""
    
    # Required attributes per specification
    NODE_TYPE = "cube_generator"  # Stable type ID persisted in saved graphs
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Box"
    NODE_DESCRIPTION = "Create Box"
    
    # Store defaults as class attributes since PortSpec may not support them
    DEFAULT_WIDTH = 2.0
    DEFAULT_HEIGHT = 2.0
    DEFAULT_DEPTH = 2.0
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("width", PortType.FLOAT, min_value=0.001, unit="length", default_value=2.0, description="Size of the box along X, centered on the origin."),
                PortSpec("height", PortType.FLOAT, min_value=0.001, unit="length", default_value=2.0, description="Size of the box along Y, centered on the origin."),
                PortSpec("depth", PortType.FLOAT, min_value=0.001, unit="length", default_value=2.0, description="Size of the box along Z, centered on the origin."),
            ],
            outputs=[
                PortSpec("geometry", PortType.GEOMETRY)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the cube creation using efficient OrientedBoundingBox3D approach."""
        
        # Import Fusion API only in execution layer (allowed per spec)
        import adsk.core # type: ignore
        import adsk.fusion # type: ignore
        
        app = context.get('app') or adsk.core.Application.get()
        
        fusion_app = adsk.core.Application.get()
        design = fusion_app.activeProduct
        root_comp = design.rootComponent
        
        # Get inputs with class-level defaults
        width = inputs.get("width", self.DEFAULT_WIDTH)
        height = inputs.get("height", self.DEFAULT_HEIGHT)
        depth = inputs.get("depth", self.DEFAULT_DEPTH)
        
        # Create centered cube using OrientedBoundingBox3D
        center_point = adsk.core.Point3D.create(0, 0, 0)
        length_direction = adsk.core.Vector3D.create(1, 0, 0)
        width_direction = adsk.core.Vector3D.create(0, 1, 0)
        oriented_box = adsk.core.OrientedBoundingBox3D.create(
            center_point, length_direction, width_direction, width, height, depth
        )
        temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        temp_box = temp_brep_mgr.createBox(oriented_box)
        
        # Get BaseFeature from context (required for geometry creation)
        noodle_base_feature = context.get('base_feature') or context.get('noodle_base_feature')
        if not noodle_base_feature:
            raise ValueError("No BaseFeature available for cube creation")
        
        # Set body name using standardized naming
        target_name = generate_geometry_name(
            node_type=self.NODE_TYPE,
            node_id=self.id, 
            source_name="Box"
        )
        
        # Add to design using BaseFeature target
        bodies = root_comp.bRepBodies
        body = bodies.add(temp_box, noodle_base_feature)
        
        # Use direct naming like polygon node (no enhanced tracking complexity)
        self._set_body_name_with_retry(app, body, target_name)
        self._register_body_name(context, target_name)

        
        log(app, f"Created box body with direct naming: {body.name}", 
            level=LogLevel.DEBUG, module="BOX_NODE")
        
        # Return in spec-compliant format
        return {
            "geometry": {
                "kind": "box",
                "id": f"box_{self.id}",
                "geometry": body,
                "geometry_name": body.name
            }
        }
    
    def _set_body_name_with_retry(self, app: Any, body: Any, target_name: str, max_attempts: int = 3) -> None:
        """Set body name with retry logic to handle Fusion API timing issues."""
        for attempt in range(max_attempts):
            try:
                body.name = target_name
                if body.name == target_name:
                    return  # Success
                log(app, f"Name mismatch on attempt {attempt+1}: expected '{target_name}', got '{body.name}'", 
                    level=LogLevel.WARNING, module="BOX_NODE")
            except Exception as e:
                log(app, f"Failed to set body name on attempt {attempt+1}: {str(e)}", 
                    level=LogLevel.WARNING, module="BOX_NODE")
        
        # Final attempt without error handling
        body.name = target_name
