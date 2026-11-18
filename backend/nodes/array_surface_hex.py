"""
Array_Surface_Hex node for creating hexagonal/honeycomb array patterns on surfaces.

This node creates hexagonal (honeycomb) grid patterns using world-space stepping for uniform distribution.
Implements hex array functionality with V2 spec compliance.
"""

from typing import Dict, Any, List
import math
import uuid
import traceback  # For better error debugging
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType, CollectionInstanceSpec, CollectionSpec, GeometryEnvelope
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel

# Import v2 surface utilities
from ..utilities.surface_utils import (
    resolve_surface_face, inset_bounds_by_margin
)
from ..utilities.surface_math_v2 import create_world_spaced_hex_grid
# Import V2 surface math utilities
from ..utilities.surface_math_v2 import (
    get_surface_bounds,
    create_surface_instances_with_uv_alignment,
    create_surface_instances_translation_only
)
from ..utilities.grid_generators import create_array_pipeline
from ..utilities.instance_creation import (
    create_instances_from_transforms, create_array_collection_metadata
)

try:
    import adsk.core
    import adsk.fusion
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


@enforce_node_spec
class ArraySurfaceHexNode(BaseNode):
    """Creates hexagonal (honeycomb) array patterns on surfaces with world-space uniform distribution."""

    NODE_TYPE = "Array_Surface_Hex"
    NODE_CATEGORY = "array"
    NODE_NAME = "Surface Hex Array"
    NODE_DESCRIPTION = "Create hexagonal/honeycomb array patterns on surfaces"

    # Default values
    DEFAULT_COUNT_U = 5
    DEFAULT_COUNT_V = 5
    DEFAULT_SPACING = 3.0
    DEFAULT_POSITION_U = 0.5
    DEFAULT_POSITION_V = 0.5

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Input collection
                PortSpec("collection", PortType.COLLECTION, required=True,
                        description="Collection of geometries to array in hexagonal pattern."),
                
                # Input surface
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("surface", PortType.SURFACE, required=True, show_input_handle=False,
                        description="Target surface for hexagonal pattern distribution."),
                
                # Grid parameters - simplified for hex
                PortSpec("spacer_1", PortType.SPACER),
                PortSpec("count_u", PortType.INTEGER, min_value=1, max_value=100, default_value=5,
                        description="Number of hexagonal rows in U direction."),
                PortSpec("count_v", PortType.INTEGER, min_value=1, max_value=100, default_value=5,
                        description="Number of hexagonal columns in V direction."),
                PortSpec("spacing", PortType.FLOAT, min_value=0.001, unit="length", default_value=3.0,
                        description="Hexagonal cell spacing (geodesic distance)."),
                
                # Placement and alignment
                PortSpec("spacer_2", PortType.SPACER),
                PortSpec("position_u", PortType.FLOAT, default_value=0.5, min_value=0.0, max_value=1.0,
                        description="Center position in U direction (0.0 = start edge, 1.0 = end edge)."),
                PortSpec("position_v", PortType.FLOAT, default_value=0.5, min_value=0.0, max_value=1.0,
                        description="Center position in V direction (0.0 = start edge, 1.0 = end edge)."),
                PortSpec("edge_margin", PortType.FLOAT, unit="length", required=False, default_value=0.0,
                         min_value=0.0, label="Edge Margin",
                         description="Distance to keep clear of the surface edges."),
                
                # Orientation control
                PortSpec("spacer_3", PortType.SPACER),
                PortSpec("rotation", PortType.FLOAT, unit="angle", default_value=0.0,
                        description="Additional rotation in degrees around surface normal."),
                PortSpec("align_to_normal", PortType.BOOLEAN, default_value=True, show_input_handle=False,
                        description="Align geometry to surface normal vectors (true) or keep world orientation (false).")
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION,
                        description="Collection of geometry instances in hexagonal pattern")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate hexagonal array input parameters."""
        # Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)
        errors = []
        collection = inputs.get("collection")
        if not collection:
            errors.append("Collection input is required")
        elif not isinstance(collection, (dict, CollectionSpec)):
            errors.append("Collection must be a valid collection object")
        if not inputs.get("surface"):
            errors.append("Surface input is required")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute hexagonal array generation with optimized parameters."""
        
        try:
            log(context.get('app'), "🔍 DEBUG: Starting Array_Surface_Hex execute", 
                level=LogLevel.DEBUG, module="ARRAY_HEX_DEBUG")
            
            return self._execute_internal(inputs, context)
            
        except Exception as e:
            log(context.get('app'), f"🔍 DEBUG: Array_Surface_Hex execute failed with error: {e}", 
                level=LogLevel.ERROR, module="ARRAY_HEX_DEBUG")
            log(context.get('app'), f"🔍 DEBUG: Full traceback: {traceback.format_exc()}", 
                level=LogLevel.ERROR, module="ARRAY_HEX_DEBUG")
            raise
    
    def _execute_internal(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Internal execute method with detailed debugging."""
        
        # Input validation with clear error messages
        collection_data = inputs.get("collection")
        if not collection_data:
            log(context.get('app'), "No collection input provided to Array_Surface_Hex", 
                level=LogLevel.WARNING, module="ARRAY_HEX")
            return {"collection": None}
        
        log(context.get('app'), f"🔍 DEBUG: collection_data type = {type(collection_data)}", 
            level=LogLevel.DEBUG, module="ARRAY_HEX_DEBUG")
        
        # Handle collection input - deserialize from dict to CollectionSpec
        if hasattr(collection_data, 'source_geometries'):
            # It's already a CollectionSpec object
            collection_spec = collection_data
        elif isinstance(collection_data, dict):
            # Deserialize dict to CollectionSpec object
            collection_spec = CollectionSpec.from_dict(collection_data)
        else:
            raise TypeError(f"Expected CollectionSpec or dict, got {type(collection_data)}")
            
        source_geometries_data = collection_spec.source_geometries
        input_instances = collection_spec.instances

        surface_data = inputs.get("surface")
        if not surface_data:
            log(context.get('app'), "No surface input provided to Array_Surface_Hex", 
                level=LogLevel.WARNING, module="ARRAY_HEX")
            return {"collection": None}
        
        if not isinstance(surface_data, dict):
            raise TypeError(f"surface input must be dict, got {type(surface_data)}")
        
        # Get parameters with defaults
        count_u = int(inputs.get("count_u", self.DEFAULT_COUNT_U))
        count_v = int(inputs.get("count_v", self.DEFAULT_COUNT_V))
        spacing = float(inputs.get("spacing", self.DEFAULT_SPACING))
        position_u = float(inputs.get("position_u", self.DEFAULT_POSITION_U))
        position_v = float(inputs.get("position_v", self.DEFAULT_POSITION_V))
        rotation = float(inputs.get("rotation", 0.0))
        edge_margin = float(inputs.get("edge_margin", 0.0))
        align_to_normal = bool(inputs.get("align_to_normal", True))
        
        log(context.get('app'), 
            f"Creating hex array: {count_u}x{count_v}, spacing={spacing}, rotation={rotation:.1f}°, margin={edge_margin:.1f}, align_to_normal={align_to_normal}",
            level=LogLevel.DEBUG, module="ARRAY_HEX")
        
        # Resolve surface face (using same pattern as UV node)
        surface_face = resolve_surface_face(surface_data, context.get('app'))
        if not surface_face:
            log(context.get('app'), "Failed to resolve surface face", 
                level=LogLevel.ERROR, module="ARRAY_HEX")
            return {"collection": None}
        
        # Get surface evaluator and bounds
        if not hasattr(surface_face, 'evaluator'):
            log(context.get('app'), "Surface face has no evaluator", 
                level=LogLevel.ERROR, module="ARRAY_HEX")
            return {"collection": None}
        
        surface_evaluator = surface_face.evaluator
        u_min, u_max, v_min, v_max = get_surface_bounds(surface_face)
        # Edge Margin is in cm. Shrink the bounds instead of passing it on.
        u_min, u_max, v_min, v_max = inset_bounds_by_margin(
            surface_evaluator, u_min, u_max, v_min, v_max, edge_margin, context.get('app'))
        
        log(context.get('app'), 
            f"Surface bounds: U=[{u_min:.3f}, {u_max:.3f}], V=[{v_min:.3f}, {v_max:.3f}]",
            level=LogLevel.DEBUG, module="ARRAY_HEX")
        
        if not source_geometries_data:
            log(context.get('app'), "Input collection has no source geometries",
                level=LogLevel.WARNING, module="ARRAY_HEX")
            return {"collection": None}
        
        # Convert source geometries from dictionaries to GeometryEnvelope objects
        source_geometries = []
        for i, geo_data in enumerate(source_geometries_data):
            if isinstance(geo_data, dict):
                try:
                    geo_envelope = GeometryEnvelope(**geo_data)
                    source_geometries.append(geo_envelope)
                except Exception as e:
                    log(context.get('app'), f"Failed to convert source geometry {i}: {e}",
                        level=LogLevel.ERROR, module="ARRAY_HEX")
                    return {"collection": None}
            else:
                # Should be GeometryEnvelope already
                source_geometries.append(geo_data)
        
        # Generate hexagonal grid pattern with world walking (this is the main difference from UV node)
        uv_points = self._generate_hex_grid_pattern(
            count_u, count_v, spacing,
            u_min, u_max, v_min, v_max,
            position_u, position_v, 0.0, rotation,  # Margin already applied to the bounds
            surface_evaluator, context.get('app')  # Pass surface_evaluator for world walking
        )
        
        if not uv_points:
            log(context.get('app'), "No UV points generated",
                level=LogLevel.ERROR, module="ARRAY_HEX")
            return {"collection": None}
        
        # Create surface instances using proven utilities (same as UV node)
        # NOTE: Don't pass rotation here since it's already applied at grid level
        if align_to_normal:
            transformation_matrices = create_surface_instances_with_uv_alignment(
                surface_evaluator, uv_points, 0.0, align_to_normal  # Use 0.0 rotation since grid is already rotated
            )
            log(context.get('app'), "Using UV tangent alignment for surface instances",
                level=LogLevel.DEBUG, module="ARRAY_HEX")
        else:
            transformation_matrices = create_surface_instances_translation_only(
                surface_evaluator, uv_points
            )
            log(context.get('app'), "Using translation-only positioning (no alignment)",
                level=LogLevel.DEBUG, module="ARRAY_HEX")
        
        if not transformation_matrices:
            log(context.get('app'), "Failed to create transformation matrices",
                level=LogLevel.ERROR, module="ARRAY_HEX")
            return {"collection": None}
        
        # Create collection instances using utility (same pattern as UV node)
        node_id = context.get('node_id', 'unknown')
        new_instances = create_instances_from_transforms(
            transformation_matrices, uv_points, input_instances,
            self.NODE_TYPE, node_id, "hex_array", context.get('app'),
            source_geometries=source_geometries  # Pass source geometries for name extraction
        )
        
        # Defensive check: Ensure instances are proper CollectionInstanceSpec objects
        validated_instances = []
        for i, instance in enumerate(new_instances):
            if isinstance(instance, dict):
                # Convert dict to CollectionInstanceSpec if needed
                validated_instances.append(CollectionInstanceSpec.from_dict(instance))
                log(context.get('app'), f"Warning: Instance {i} was dict, converted to CollectionInstanceSpec",
                    level=LogLevel.WARNING, module="ARRAY_HEX")
            else:
                # Should be CollectionInstanceSpec already
                validated_instances.append(instance)
        
        # Create array output collection metadata
        array_metadata = create_array_collection_metadata(
            "hex_array", count_u, count_v, node_id, len(input_instances),
            spacing=spacing, position_u=position_u, position_v=position_v,
            rotation=rotation, edge_margin=edge_margin, align_to_normal=align_to_normal,
            count_w=count_u + count_v - 1
        )
        
        # Generate unique collection ID
        collection_id = str(uuid.uuid4())[:8]
        
        log(context.get('app'), f"🔍 DEBUG: About to create CollectionSpec with {len(source_geometries)} geometries, {len(validated_instances)} instances", 
            level=LogLevel.DEBUG, module="ARRAY_HEX_DEBUG")
        
        # Verify types before creating CollectionSpec
        for i, geo in enumerate(source_geometries):
            log(context.get('app'), f"🔍 DEBUG: source_geometries[{i}] type = {type(geo)}", 
                level=LogLevel.DEBUG, module="ARRAY_HEX_DEBUG")
        for i, inst in enumerate(validated_instances[:3]):  # Only first 3 to avoid spam
            log(context.get('app'), f"🔍 DEBUG: validated_instances[{i}] type = {type(inst)}", 
                level=LogLevel.DEBUG, module="ARRAY_HEX_DEBUG")
        
        # Create proper CollectionSpec instance
        output_collection = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=collection_id,
            source_geometries=source_geometries,
            instances=validated_instances,  # Use validated instances
            metadata=array_metadata
        )
        
        log(context.get('app'), f"🔍 DEBUG: CollectionSpec created successfully, type = {type(output_collection)}", 
            level=LogLevel.DEBUG, module="ARRAY_HEX_DEBUG")
        
        log(context.get('app'), 
            f"Created hex array collection: {len(input_instances)} → {len(validated_instances)} instances",
            level=LogLevel.DEBUG, module="ARRAY_HEX")
        
        return {"collection": output_collection}

    def _generate_hex_grid_pattern(self, count_u: int, count_v: int, spacing: float,
                                 u_min: float, u_max: float, v_min: float, v_max: float,
                                 position_u: float, position_v: float, edge_margin: float, 
                                 rotation: float, surface_evaluator=None, app=None) -> List[tuple]:
        """Generate hexagonal grid pattern with true world-space spacing using world walking."""
        uv_points = []
        
        try:
            # Calculate effective bounds with margin
            u_range = u_max - u_min
            v_range = v_max - v_min
            
            margin_u = edge_margin * u_range
            margin_v = edge_margin * v_range
            
            effective_u_min = u_min + margin_u
            effective_u_max = u_max - margin_u
            effective_v_min = v_min + margin_v
            effective_v_max = v_max - margin_v
            
            # Calculate center position in UV space based on position_u/position_v
            center_u = effective_u_min + position_u * (effective_u_max - effective_u_min)
            center_v = effective_v_min + position_v * (effective_v_max - effective_v_min)
            
            # Use world walking for accurate geodesic spacing
            if surface_evaluator:
                log(app, f"Using world walking for hex grid: spacing={spacing:.3f} world units", 
                    level=LogLevel.DEBUG, module="ARRAY_HEX")
                
                hex_points = create_world_spaced_hex_grid(
                    surface_evaluator, center_u, center_v, count_u, count_v, spacing
                )
            else:
                # Fallback to parameter approximation if no evaluator
                log(app, f"No evaluator available, using parameter approximation", 
                    level=LogLevel.WARNING, module="ARRAY_HEX")
                
                # Hexagonal grid math - offset every other row
                hex_offset_factor = 0.866025  # sqrt(3)/2 for proper hexagonal geometry
                
                # Use improved spacing calculation for fallback
                base_spacing_factor = 0.02  # Base factor for parameter space conversion
                step_u = spacing * base_spacing_factor  # U spacing
                step_v = spacing * base_spacing_factor * hex_offset_factor  # V spacing with hex factor
                
                # Calculate starting positions
                total_u_extent = (count_u - 1) * step_u
                total_v_extent = (count_v - 1) * step_v
                
                start_u = center_u - total_u_extent / 2
                start_v = center_v - total_v_extent / 2
                
                hex_points = []
                for v_idx in range(count_v):
                    for u_idx in range(count_u):
                        # Basic grid position
                        u_pos = start_u + u_idx * step_u
                        v_pos = start_v + v_idx * step_v
                        
                        # Apply hexagonal offset to every other row
                        if v_idx % 2 == 1:
                            u_pos += step_u / 2  # Offset every other row by half step
                        
                        hex_points.append((u_pos, v_pos))
            
            # Filter points to stay within bounds
            bounded_hex_points = []
            for u_pos, v_pos in hex_points:
                if (effective_u_min <= u_pos <= effective_u_max and
                    effective_v_min <= v_pos <= effective_v_max):
                    bounded_hex_points.append((u_pos, v_pos))
            
            hex_points = bounded_hex_points
            
            # Apply rotation to the entire pattern (like UV array does)
            if rotation != 0.0:
                rotation_rad = math.radians(rotation)
                cos_r = math.cos(rotation_rad)
                sin_r = math.sin(rotation_rad)
                
                # Calculate pattern center for rotation
                center_u = (effective_u_min + effective_u_max) / 2
                center_v = (effective_v_min + effective_v_max) / 2
                
                # Rotate each point around the pattern center
                rotated_points = []
                for u, v in hex_points:
                    # Translate to center
                    rel_u = u - center_u
                    rel_v = v - center_v
                    
                    # Rotate
                    rotated_u = rel_u * cos_r - rel_v * sin_r
                    rotated_v = rel_u * sin_r + rel_v * cos_r
                    
                    # Translate back
                    final_u = rotated_u + center_u
                    final_v = rotated_v + center_v
                    
                    # Check bounds after rotation
                    if (effective_u_min <= final_u <= effective_u_max and
                        effective_v_min <= final_v <= effective_v_max):
                        rotated_points.append((final_u, final_v))
                
                uv_points = rotated_points
            else:
                uv_points = hex_points
            
            if app:
                rotation_info = f" (rotated {rotation}°)" if rotation != 0.0 else ""
                log(app, f"Generated {len(uv_points)} hex pattern points from {count_u}x{count_v} grid{rotation_info}",
                    level=LogLevel.DEBUG, module="ARRAY_HEX")
            
            return uv_points
            
        except Exception as e:
            if app:
                log(app, f"Error generating hex grid pattern: {e}",
                    level=LogLevel.ERROR, module="ARRAY_HEX")
            return []
