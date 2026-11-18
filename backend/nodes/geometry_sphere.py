"""Sphere geometry node - spec-compliant implementation."""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.log_utils import log
from ..utilities.geometry_naming import generate_geometry_name
from ..specification import LogLevel
from .base import BaseNode

@enforce_node_spec
class SphereNode(BaseNode):
    """Creates sphere geometry using efficient TemporaryBRepManager approach"""
    
    # Required attributes per specification
    NODE_TYPE = "sphere_generator"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Sphere"
    NODE_DESCRIPTION = "Create Sphere"
    
    # Store defaults as class attributes
    DEFAULT_RADIUS = 1.0
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("radius", PortType.FLOAT, min_value=0.001, unit="length", default_value=1.0, description="Radius of the sphere, centered on the origin."),
            ],
            outputs=[
                PortSpec("geometry", PortType.GEOMETRY)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute sphere creation using efficient TemporaryBRepManager approach."""
        
        # Import Fusion API only in execution layer (allowed per spec)
        import adsk.core # type: ignore
        import adsk.fusion # type: ignore
        
        app = context.get('app') or adsk.core.Application.get()
        
        log(app, "Creating sphere using TemporaryBRepManager", 
            level=LogLevel.DEBUG, module="SPHERE_NODE")
        
        fusion_app = adsk.core.Application.get()
        design = fusion_app.activeProduct
        root_comp = design.rootComponent
        
        # Get inputs with class-level defaults
        radius = inputs.get("radius", self.DEFAULT_RADIUS)
        
        log(app, f"Creating sphere with radius {radius}", 
            level=LogLevel.DEBUG, module="SPHERE_NODE")
        
        # Create centered sphere using TemporaryBRepManager
        center_point = adsk.core.Point3D.create(0, 0, 0)
        temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        temp_sphere = temp_brep_mgr.createSphere(center_point, radius)
        
        # Get BaseFeature from context (required for geometry creation)
        noodle_base_feature = context.get('base_feature') or context.get('noodle_base_feature')
        if not noodle_base_feature:
            raise ValueError("No BaseFeature available for sphere creation")
        
        # Set body name using standardized naming
        target_name = generate_geometry_name(
            node_type=self.NODE_TYPE,
            node_id=self.id,
            source_name="Sphere"
        )
        
        # Add to design using BaseFeature target
        bodies = root_comp.bRepBodies
        body = bodies.add(temp_sphere, noodle_base_feature)
        
        # Use direct naming like polygon node (no enhanced tracking complexity)
        self._set_body_name_with_retry(app, body, target_name)
        self._register_body_name(context, target_name)

        
        log(app, f"Created sphere body with direct naming: {body.name}", 
            level=LogLevel.DEBUG, module="SPHERE_NODE")
        
        # Return in spec-compliant format
        return {
            "geometry": {
                "kind": "sphere",
                "id": f"sphere_{self.id}",
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
                    level=LogLevel.WARNING, module="SPHERE_NODE")
            except Exception as e:
                log(app, f"Failed to set body name on attempt {attempt+1}: {str(e)}", 
                    level=LogLevel.WARNING, module="SPHERE_NODE")
        
        # Final attempt without error handling
        body.name = target_name
