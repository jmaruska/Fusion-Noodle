"""Cylinder geometry node - spec-compliant implementation."""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.log_utils import log
from ..utilities.geometry_naming import generate_geometry_name
from ..specification import LogLevel
from .base import BaseNode

@enforce_node_spec
class CylinderNode(BaseNode):
    """Creates cylinder geometry using efficient TemporaryBRepManager approach"""
    
    # Required attributes per specification
    NODE_TYPE = "cylinder_generator"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Cylinder"
    NODE_DESCRIPTION = "Create Cylinder"
    
    # Store defaults as class attributes
    DEFAULT_RADIUS = 1.0
    DEFAULT_HEIGHT = 2.0
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("radius", PortType.FLOAT, min_value=0.001, unit="length", default_value=1.0, description="Radius of the cylinder, around the Z axis."),
                PortSpec("height", PortType.FLOAT, min_value=0.001, unit="length", default_value=2.0, description="Length of the cylinder along Z, centered on the origin."),
            ],
            outputs=[
                PortSpec("geometry", PortType.GEOMETRY)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute cylinder creation using efficient TemporaryBRepManager approach."""
        
        # Import Fusion API only in execution layer (allowed per spec)
        import adsk.core # type: ignore
        import adsk.fusion # type: ignore
        
        app = context.get('app') or adsk.core.Application.get()
        
        log(app, "Creating cylinder using TemporaryBRepManager", 
            level=LogLevel.DEBUG, module="CYLINDER_NODE")
        
        fusion_app = adsk.core.Application.get()
        design = fusion_app.activeProduct
        root_comp = design.rootComponent
        
        # Get inputs with class-level defaults
        radius = inputs.get("radius", self.DEFAULT_RADIUS)
        height = inputs.get("height", self.DEFAULT_HEIGHT)
        
        log(app, f"Creating cylinder r={radius}, h={height}", 
            level=LogLevel.DEBUG, module="CYLINDER_NODE")
        
        # Create centered cylinder using TemporaryBRepManager with correct API
        # API: createCylinderOrCone(pointOne, pointOneRadius, pointTwo, pointTwoRadius)
        point_one = adsk.core.Point3D.create(0, 0, -height/2)  # Bottom center
        point_two = adsk.core.Point3D.create(0, 0, height/2)   # Top center
        temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        
        # Create cylinder with same radius at both ends (true cylinder, not cone)
        temp_cylinder = temp_brep_mgr.createCylinderOrCone(
            point_one, radius, point_two, radius
        )
        
        # Get BaseFeature from context (required for geometry creation)
        noodle_base_feature = context.get('base_feature') or context.get('noodle_base_feature')
        if not noodle_base_feature:
            raise ValueError("No BaseFeature available for cylinder creation")
        
        # Set body name using standardized naming
        target_name = generate_geometry_name(
            node_type=self.NODE_TYPE,
            node_id=self.id,
            source_name="Cylinder"
        )
        
        # Add to design using BaseFeature target
        bodies = root_comp.bRepBodies
        body = bodies.add(temp_cylinder, noodle_base_feature)
        
        # Use direct naming like polygon node (no enhanced tracking complexity)
        self._set_body_name_with_retry(app, body, target_name)
        self._register_body_name(context, target_name)

        
        log(app, f"Created cylinder body with direct naming: {body.name}", 
            level=LogLevel.DEBUG, module="CYLINDER_NODE")
        
        # Return in spec-compliant format
        return {
            "geometry": {
                "kind": "cylinder",
                "id": f"cylinder_{self.id}",
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
                    level=LogLevel.WARNING, module="CYLINDER_NODE")
            except Exception as e:
                log(app, f"Failed to set body name on attempt {attempt+1}: {str(e)}", 
                    level=LogLevel.WARNING, module="CYLINDER_NODE")
        
        # Final attempt without error handling
        body.name = target_name
