"""
Array Surface Spiral Node - V2 Implementation

Specialized spiral array node with domain-appropriate parameters for creating
spiral arrays on surfaces. Particularly optimized for revolved objects with
provisions for Fusion's radian values.

This implements sophisticated spiral array functionality with spec compliance.
nuanced spiral functionality including helical mathematics and orientation controls.
"""

import math
import uuid
from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType, CollectionSpec, GeometryEnvelope, CollectionInstanceSpec
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from ..utilities.surface_utils import resolve_surface_face, get_surface_bounds
from ..utilities.surface_math_v2 import (
    create_surface_instances_with_uv_alignment,
    create_surface_instances_translation_only
)
from ..utilities.instance_creation import (
    create_instances_from_transforms, create_array_collection_metadata
)
from ..utilities.surface_grid_generators import generate_surface_grid_pipeline
from .base import BaseNode

@enforce_node_spec
class ArraySurfaceSpiralNode(BaseNode):
    """
    Surface spiral array node with proper spiral terminology.
    
    Uses sophisticated helical mathematics with domain-appropriate
    parameter names for spiral arrays:
    - Strands: Number of separate spiral arms/strands (maps to count_v)
    - Density: Number of instances per strand (maps to count_u)
    - Tilt: Angle of spiral progression (maps to rotation_degrees)
    - Uniformity: Balance between world-space and parametric spacing (maps to bias)
    
    Targeted at revolved objects with provisions for Fusion's radian values.
    """

    NODE_TYPE = "Array_Surface_Spiral"
    NODE_CATEGORY = "array"
    NODE_NAME = "Surface Spiral"
    NODE_DESCRIPTION = "Create spiral arrays on revolved surfaces"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return the node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Core inputs
                PortSpec("collection", PortType.COLLECTION, required=True, description="The instances to place along the spirals."),
                
                # Input surface
                PortSpec("surface_spacer", PortType.SPACER),
                PortSpec("surface", PortType.SURFACE, required=True, show_input_handle=False, description="Pick the revolved face in Fusion to wrap the spirals around."),
                
                # Spiral-specific parameters with proper terminology
                PortSpec("geometry_spacer", PortType.SPACER),
                PortSpec("strands", PortType.INTEGER, required=False, default_value=3, min_value=1, label="Strands", description="Number of spirals, spaced evenly around the surface."),
                PortSpec("density", PortType.INTEGER, required=False, default_value=30, min_value=1, label="Density", description="Number of instances along each strand."),
                PortSpec("tilt", PortType.FLOAT, unit="angle", required=False, default_value=45.0, label="Tilt", description="How steeply the strands wind: 0 runs straight along the surface, larger angles wrap more turns."),
                
                # TODO Alignment control - local instance alignment to spiral progression (helical tangent)
                # PortSpec("flow_spacer", PortType.SPACER),
                # PortSpec("align_to_spiral", PortType.BOOLEAN, required=False, default_value=True, label="Align to Spiral", show_input_handle=False),
                
                # Position and margin controls
                PortSpec("position_spacer", PortType.SPACER),
                PortSpec("position", PortType.FLOAT, min_value=-0.5, max_value=0.5, required=False, default_value=0.0, label="Position", description="Shifts where the strands start around the surface, as a fraction of a full turn."),
                PortSpec("edge_margin", PortType.FLOAT, min_value=0.0, unit="length", required=False, default_value=0.0,
                         label="Edge Margin",
                         description="Distance to keep clear of the surface edges along its length."),
                
                # Surface alignment
                PortSpec("alignment_spacer", PortType.SPACER),
                PortSpec("align_to_normal", PortType.BOOLEAN, required=False, default_value=True, label="Align to Normal", show_input_handle=False, description="Stand each instance along the surface normal; off keeps its original orientation."),
                
                # Bias control
                PortSpec("bias_spacer", PortType.SPACER),
                PortSpec("u_bias", PortType.FLOAT, min_value=0.0, max_value=1.0, required=False, default_value=1.0, label="U Bias", description="Spacing along each strand, from even real-world distance (0) to following the surface's UV flow (1)."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION, label="Collection")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)."""
        return []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the spiral array generation"""
        app = context.get('app')
        log(app, "*** EXECUTING SPIRAL ARRAY NODE ***", 
            level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
        
        # Get inputs with spiral-appropriate names (updated terminology)
        input_collection = inputs.get('collection')
        surface_data = inputs.get('surface')
        strands = int(inputs.get('strands', 3))
        density = int(inputs.get('density', 30))
        tilt = float(inputs.get('tilt', 45.0))
        u_bias = float(inputs.get('u_bias', 1.0))  # Default=1.0 for UV-conformant
        align_to_spiral = inputs.get('align_to_spiral', True)
        position = float(inputs.get('position', 0.0))
        edge_margin = float(inputs.get('edge_margin', 0.0))
        align_to_normal = inputs.get('align_to_normal', True)
        
        log(app, f"Spiral parameters: {strands} strands, {density} density, {tilt}° tilt, u_bias={u_bias:.3f}", 
            level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
        log(app, f"Edge margin: {edge_margin}cm, Position: {position}, Alignment: align_to_spiral={align_to_spiral}, align_to_normal={align_to_normal}", 
            level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
        
        # Validate inputs
        if not input_collection or not surface_data:
            log(app, "No input collection or surface provided", 
                level=LogLevel.WARNING, module="ARRAY_SURFACE_SPIRAL")
            return {"collection": None}
        
        try:
            # Handle both CollectionSpec objects and dict format for backward compatibility
            if hasattr(input_collection, 'source_geometries'):
                # It's a CollectionSpec object
                source_geometries_data = input_collection.source_geometries
                input_instances = input_collection.instances
            elif isinstance(input_collection, dict):
                # It's a dictionary (backward compatibility or legacy format)
                source_geometries_data = input_collection.get("source_geometries", [])
                input_instances = input_collection.get("instances", [])
            else:
                log(app, "Spiral Array: Invalid collection input", level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}
            
            if not source_geometries_data:
                log(app, "Input collection has no source geometries",
                    level=LogLevel.WARNING, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}
            
            # Convert source geometries from dictionaries to GeometryEnvelope objects
            source_geometries = []
            for i, geo_data in enumerate(source_geometries_data):
                if isinstance(geo_data, dict):
                    try:
                        geo_envelope = GeometryEnvelope(**geo_data)
                        source_geometries.append(geo_envelope)
                    except Exception as e:
                        log(app, f"Failed to convert source geometry {i}: {e}",
                            level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
                        return {"collection": None}
                else:
                    # Should be GeometryEnvelope already
                    source_geometries.append(geo_data)
            
            # Get surface face and evaluator
            surface_face = resolve_surface_face(surface_data, app)
            if not surface_face:
                log(app, "Spiral Array: Failed to resolve surface face", level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}
                
            surface_evaluator = surface_face.evaluator
            u_min, u_max, v_min, v_max = get_surface_bounds(surface_face)
            
            log(app, f"Spiral Array: Surface bounds U=[{u_min:.3f}, {u_max:.3f}], V=[{v_min:.3f}, {v_max:.3f}]", 
                level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            
            # Map spiral parameters to surface grid parameters
            # Correct mapping based on helical parameter semantics:
            count_u = density   # Density (points per strand) maps to count_u
            count_v = strands   # Strands (number of strands) maps to count_v
            spacing_u = 3.0     # Default, not used in spiral mode
            spacing_v = 3.0     # Default, not used in spiral mode
            pos_u = 0.5         # Center U position (spiral center)
            pos_v = 0.5 + position  # Map position offset to pos_v
            # Note: u_bias already received directly from input
            v_bias = u_bias     # Use same bias for V direction
            rotation_degrees = tilt     # Map tilt to rotation_degrees (spiral incline angle)
            
            log(app, f"DEBUG SPIRAL PARAMS: edge_margin={edge_margin}cm will be applied to surface bounds",
                level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"DEBUG SPIRAL PARAMS: u_bias={u_bias:.3f} - 0.0=world-uniform, 1.0=UV-conformant",
                level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            
            # Debug parameter mapping
            log(app, f"Mapped parameters:", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"  count_u={count_u} (density)", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"  count_v={count_v} (strands)", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"  rotation_degrees={rotation_degrees}° (tilt)", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"  pos_u={pos_u}, pos_v={pos_v}", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"  u_bias={u_bias}, v_bias={v_bias}", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            log(app, f"  edge_margin={edge_margin}cm", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            
            # Generate spiral UV points using the v2 surface grid utilities
            # This follows the established pattern using V2 utilities
            uv_points = generate_surface_grid_pipeline(
                count_u=count_u,
                count_v=count_v,
                surface_evaluator=surface_evaluator,
                u_bounds=(u_min, u_max),
                v_bounds=(v_min, v_max),
                spacing_u=spacing_u,
                spacing_v=spacing_v,
                edge_margin=edge_margin,
                rotation_degrees=rotation_degrees,
                u_bias=u_bias,
                v_bias=v_bias,
                pos_u=pos_u,
                pos_v=pos_v,
                array_type='spiral',
                app=app
            )
            
            if not uv_points:
                log(app, "Spiral Array: No UV points generated by surface grid pipeline",
                    level=LogLevel.WARNING, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}

            # Pipeline returns (u, v, grid_i, grid_j) tuples; strip to (u, v) for downstream use.
            uv_points = [(point[0], point[1]) for point in uv_points]

            log(app, f"Spiral Array: Generated {len(uv_points)} UV points", level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            
            # Create surface instances with proper alignment (same pattern as hex array)
            # NOTE: Don't pass tilt rotation here since it's already applied at spiral level
            if align_to_normal:
                transformation_matrices = create_surface_instances_with_uv_alignment(
                    surface_evaluator, uv_points, 0.0, align_to_normal  # Use 0.0 rotation since spiral is already rotated
                )
                log(app, "Using UV tangent alignment for surface instances",
                    level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            else:
                transformation_matrices = create_surface_instances_translation_only(
                    surface_evaluator, uv_points
                )
                log(app, "Using translation-only positioning (no alignment)",
                    level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            
            if not transformation_matrices:
                log(app, "Spiral Array: Failed to create transform matrices", 
                    level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}
                
            if not transformation_matrices:
                log(app, "Failed to create transformation matrices",
                    level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}
            
            log(app, f"Spiral Array: Created {len(transformation_matrices)} transform matrices", 
                level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            
            # Create collection instances using utility (same pattern as hex array)
            node_id = context.get('node_id', 'unknown')
            new_instances = create_instances_from_transforms(
                transformation_matrices, uv_points, input_instances,
                self.NODE_TYPE, node_id, "spiral_array", app,
                source_geometries=source_geometries  # Pass source geometries for name extraction
            )
            
            # Defensive check: Ensure instances are proper CollectionInstanceSpec objects
            validated_instances = []
            for i, instance in enumerate(new_instances):
                if isinstance(instance, dict):
                    # Convert dict to CollectionInstanceSpec if needed
                    validated_instances.append(CollectionInstanceSpec.from_dict(instance))
                    log(app, f"Warning: Instance {i} was dict, converted to CollectionInstanceSpec",
                        level=LogLevel.WARNING, module="ARRAY_SURFACE_SPIRAL")
                else:
                    validated_instances.append(instance)
            
            if not validated_instances:
                log(app, "Spiral Array: Failed to create instances", 
                    level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
                return {"collection": None}
            
            # Create result collection (same pattern as hex array)
            collection_id = str(uuid.uuid4())[:8]  # Generate unique collection ID
            
            array_metadata = {
                'type': 'spiral_array',
                'count_u': density,
                'count_v': strands,
                'strands': strands,
                'density': density,
                'tilt': tilt,
                'u_bias': u_bias,  # Updated from uniformity to u_bias
                'align_to_spiral': align_to_spiral,
                'align_to_normal': align_to_normal,
                'position': position,
                'edge_margin': edge_margin,
                'array_node_id': context.get('node_id', 'unknown')
            }
            
            result_collection = CollectionSpec(
                collection_type="geometry_collection",
                collection_id=collection_id,
                source_geometries=source_geometries,  # Use the converted source geometries
                instances=validated_instances,  # Use validated instances 
                metadata=array_metadata
            )
            
            log(app, f"Spiral Array: Generated with {len(result_collection.instances)} instances",
                level=LogLevel.DEBUG, module="ARRAY_SURFACE_SPIRAL")
            return {"collection": result_collection}
                
        except Exception as e:
            log(app, f"Spiral Array: Execution error: {e}", 
                level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
            import traceback
            log(app, f"Traceback: {traceback.format_exc()}", 
                level=LogLevel.ERROR, module="ARRAY_SURFACE_SPIRAL")
            
            return {"collection": None}
