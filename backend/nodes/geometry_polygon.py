"""Polygon geometry node - spec-compliant implementation."""

import math
from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.log_utils import log
from ..utilities.geometry_naming import generate_geometry_name
from ..specification import LogLevel
from .base import BaseNode

MEASURES = ("across_flats", "across_corners", "side")


def corner_distance(sides: int, size: float, measured: str = "across_flats") -> float:
    """How far a regular polygon's corners are from its center, for a `size` measured
    as Fusion's three polygon tools do:
      across_flats   — twice the distance to the middle of a side (Circumscribed). A
                       hexagon of size 10 is 10 across its flats, as nuts and bar stock
                       are specified; on a grid, spacing = size + gap.
      across_corners — the distance between opposite corners (Inscribed).
      side           — the length of one side (Edge Polygon); natural for odd sides.
    """
    half_angle = math.pi / sides
    if measured == "across_corners":
        return size / 2
    if measured == "side":
        return size / (2 * math.sin(half_angle))
    return (size / 2) / math.cos(half_angle)


def polygon_corners(sides: int, size: float, measured: str = "across_flats"):
    """The corners of a regular polygon on the XY plane (see corner_distance for `size`).

    The first corner sits half a side past +X, so a flat side faces +X (and, for an
    even number of sides, every axis direction it can). That is how the arrays lay
    instances out: a hexagon then tiles the 2D Grid's Hexagonal layout, whose
    neighbours sit along X, and a square lines up with its plain Grid.
    """
    start = math.pi / sides
    reach = corner_distance(sides, size, measured)
    return [(reach * math.cos(start + 2 * math.pi * i / sides),
             reach * math.sin(start + 2 * math.pi * i / sides)) for i in range(sides)]


@enforce_node_spec
class PolygonNode(BaseNode):
    """Creates regular polygon geometry with specified sides and size"""
    
    # Required attributes per specification
    NODE_TYPE = "polygon_generator"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Polygon"
    NODE_DESCRIPTION = "Create Polygon"
    
    # Store defaults as class attributes
    DEFAULT_SIDES = 6.0
    DEFAULT_SIZE = 2.0
    DEFAULT_HEIGHT = 2.0
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            wide=True,  # Measured dropdown
            inputs=[
                PortSpec("sides", PortType.INTEGER, default_value=6, min_value=3, description="Number of sides of the prism's cross-section."),
                PortSpec("size", PortType.FLOAT, min_value=0.001, unit="length", default_value=2.0, label="Size",
                         description="The polygon's width, measured as Measured says; on a grid, spacing = size + gap."),
                PortSpec("measured", PortType.ENUM, default_value="across_flats", label="Measured",
                         enum_options=list(MEASURES),
                         enum_labels={"across_flats": "Across flats", "across_corners": "Across corners", "side": "Side length"},
                         show_input_handle=False,
                         description="What Size measures: across the flats (as nuts are sized), across the corners, or one side."),
                PortSpec("height", PortType.FLOAT, min_value=0.001, unit="length", default_value=2.0, description="Total thickness of the polygon, centered on the XY plane."),
            ],
            outputs=[
                PortSpec("geometry", PortType.GEOMETRY)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        measured = inputs.get("measured", "across_flats")
        if measured not in MEASURES:
            return [f"{self.port_label('measured')} must be one of: Across flats, Across corners, Side length"]
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute polygon creation using sketch and extrude"""
        
        # Import Fusion API only in execution layer (allowed per spec)
        import adsk.core # type: ignore
        import adsk.fusion # type: ignore
        import math
        
        app = context.get('app') or adsk.core.Application.get()
        
        log(app, "Creating polygon using sketch and extrude", 
            level=LogLevel.DEBUG, module="POLYGON_NODE")
        
        fusion_app = adsk.core.Application.get()
        design = fusion_app.activeProduct
        root_comp = design.rootComponent
        
        # Get BaseFeature from context (required for sketch-based geometry creation)
        noodle_base_feature = context.get('base_feature') or context.get('noodle_base_feature')
        if not noodle_base_feature:
            raise ValueError("No BaseFeature available for polygon creation")
        
        # Get inputs with class-level defaults and validation
        sides = int(inputs.get("sides", self.DEFAULT_SIDES))
        size = inputs.get("size", self.DEFAULT_SIZE)
        measured = inputs.get("measured", "across_flats")
        height = inputs.get("height", self.DEFAULT_HEIGHT)
        
        # Auto-correct polygon sides (minimum 3)
        if sides < 3:
            sides = 3
            log(app, "Auto-corrected sides to minimum value: 3", 
                level=LogLevel.WARNING, module="POLYGON_NODE")
        
        log(app, f"Creating {sides}-sided polygon, size={size} ({measured}), h={height}", 
            level=LogLevel.DEBUG, module="POLYGON_NODE")
        
        # Create sketch
        sketches = root_comp.sketches
        xy_plane = root_comp.xYConstructionPlane
        sketch = sketches.add(xy_plane)
        
        log(app, "Created sketch", level=LogLevel.DEBUG, module="POLYGON_NODE")
        
        # Draw polygon
        points = [adsk.core.Point3D.create(x, y, 0) for x, y in polygon_corners(sides, size, measured)]
        
        # Add lines to form polygon
        lines = sketch.sketchCurves.sketchLines
        for i in range(sides):
            start_point = points[i]
            end_point = points[(i + 1) % sides]
            lines.addByTwoPoints(start_point, end_point)
        
        log(app, "Created polygon geometry", level=LogLevel.DEBUG, module="POLYGON_NODE")
        
        # Get profile
        profile = sketch.profiles.item(0)
        
        # Create extrusion - CENTER the polygon by extruding symmetrically
        extrudes = root_comp.features.extrudeFeatures
        extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        # A symmetric extent goes this far to each side, so half the height gives a
        # total thickness of Height, centred on the origin, like Box
        distance = adsk.core.ValueInput.createByReal(height / 2.0)
        extrude_input.setDistanceExtent(True, distance)
        extrude = extrudes.add(extrude_input)
        
        log(app, "Created extrusion", level=LogLevel.DEBUG, module="POLYGON_NODE")
        
        body = extrude.bodies.item(0)
        
        # Set body name using standardized naming (with descriptive polygon name)
        sides = inputs.get("sides", self.DEFAULT_SIDES)
        polygon_names = {3: "Triangle", 4: "Square", 5: "Pentagon", 6: "Hexagon", 
                        7: "Heptagon", 8: "Octagon", 9: "Nonagon", 10: "Decagon"}
        polygon_name = polygon_names.get(int(sides), f"{int(sides)}Gon")
        
        target_name = generate_geometry_name(
            node_type=self.NODE_TYPE,
            node_id=self.id,
            source_name=polygon_name
        )
        self._set_body_name_with_retry(app, body, target_name)
        self._register_body_name(context, target_name)

        
        # Clean up: Delete the sketch to keep timeline tidy
        sketch.deleteMe()
        
        log(app, f"Created polygon body: {body.name} (sketch cleaned up)", 
            level=LogLevel.DEBUG, module="POLYGON_NODE")
        
        # Return in spec-compliant format
        return {
            "geometry": {
                "kind": "polygon",
                "id": f"polygon_{self.id}",
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
                    level=LogLevel.WARNING, module="POLYGON_NODE")
            except Exception as e:
                log(app, f"Failed to set body name on attempt {attempt+1}: {str(e)}", 
                    level=LogLevel.WARNING, module="POLYGON_NODE")
        
        # Final attempt without error handling
        body.name = target_name
