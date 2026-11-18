"""
Array_Surface_UV node for creating uniform UV parameter space arrays on surfaces.
Creates collection instances distributed evenly across surface UV space using i/(count-1) distribution.
"""

from typing import Dict, Any, Tuple
import uuid
import math
import traceback  # For better error debugging
from ..enforcement import enforce_node_spec
        # Clean up Array_UV imports - remove unused TransformSpec
from ..contracts import NodeSpec, PortSpec, PortType, CollectionInstanceSpec, CollectionSpec, Vector3Spec, GeometryEnvelope
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel
from ..utilities.surface_utils import (
    resolve_surface_face, inset_bounds_by_margin
)
# Import surface math utilities
from ..utilities.surface_math_v2 import (
    get_surface_bounds,
    create_surface_instances_with_uv_alignment,
    create_surface_instances_translation_only
)
# Import v2 grid and instance utilities (extracted from inline math)
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
class ArraySurfaceUVNode(BaseNode):
    """Creates uniform UV parameter space arrays on surfaces with simple i/(count-1) distribution."""
    
    NODE_TYPE = "Array_Surface_UV"
    NODE_CATEGORY = "array"
    NODE_NAME = "Surface UV Array"
    NODE_DESCRIPTION = "Create uniform arrays distributed across UV parameter space"
    
    # Default values
    DEFAULT_COUNT_U = 5
    DEFAULT_COUNT_V = 5
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
                        description="Collection of geometries to array across the surface."),
                
                # Input surface
                PortSpec("spacer_surface", PortType.SPACER),
                PortSpec("surface", PortType.SURFACE, required=True, show_input_handle=False,
                        description="Target surface for UV parameter space distribution."),
                
                # Array configuration
                PortSpec("spacer_array", PortType.SPACER),
                PortSpec("count_u", PortType.INTEGER, default_value=5, min_value=1, max_value=100,
                        description="Number of instances in U direction (surface width)."),
                PortSpec("count_v", PortType.INTEGER, default_value=5, min_value=1, max_value=100,
                        description="Number of instances in V direction (surface height)."),
                
                # Stagger options
                PortSpec("spacer_stagger", PortType.SPACER),
                PortSpec("stagger_offset", PortType.FLOAT, default_value=0.0, min_value=-0.5, max_value=0.5,
                        description="Offset every other row by this fraction (0.0 = no stagger, 0.5 = half spacing)."),
                
                # Position and layout  
                PortSpec("spacer_position", PortType.SPACER),
                PortSpec("position_u", PortType.FLOAT, default_value=0.5, min_value=0.0, max_value=1.0,
                        description="Center position in U direction (0.0 = start edge, 1.0 = end edge)."),
                PortSpec("position_v", PortType.FLOAT, default_value=0.5, min_value=0.0, max_value=1.0,
                        description="Center position in V direction (0.0 = start edge, 1.0 = end edge)."),
                PortSpec("edge_margin", PortType.FLOAT, unit="length", required=False, default_value=0.0,
                         min_value=0.0, label="Edge Margin",
                         description="Distance to keep clear of the surface edges."),
                
                # Orientation control
                PortSpec("spacer_orientation", PortType.SPACER),
                PortSpec("rotation", PortType.FLOAT, unit="angle", default_value=0.0,
                        description="Additional rotation in degrees around surface normal."),
                PortSpec("align_to_normal", PortType.BOOLEAN, default_value=True, show_input_handle=False,
                        description="Align geometry to surface normal vectors (true) or keep world orientation (false).")
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION,
                        description="Collection of geometry instances distributed across the surface")
            ]
        )

    def validate(self, inputs: Dict[str, Any]):
        """Validate UV array inputs."""
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
        """Create UV array collection from input collection on surface."""
        
        try:
            log(context.get('app'), "🔍 DEBUG: Starting Array_UV execute", 
                level=LogLevel.DEBUG, module="ARRAY_UV_DEBUG")
            
            return self._execute_internal(inputs, context)
            
        except Exception as e:
            log(context.get('app'), f"🔍 DEBUG: Array_UV execute failed with error: {e}", 
                level=LogLevel.ERROR, module="ARRAY_UV_DEBUG")
            log(context.get('app'), f"🔍 DEBUG: Full traceback: {traceback.format_exc()}", 
                level=LogLevel.ERROR, module="ARRAY_UV_DEBUG")
            raise
    
    def _execute_internal(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Internal execute method with detailed debugging."""
        
        # Input validation with clear error messages
        collection_data = inputs.get("collection")
        if not collection_data:
            log(context.get('app'), "No collection input provided to Array_UV", 
                level=LogLevel.WARNING, module="ARRAY_UV")
            return {"collection": None}
        
        log(context.get('app'), f"🔍 DEBUG: collection_data type = {type(collection_data)}", 
            level=LogLevel.DEBUG, module="ARRAY_UV_DEBUG")
        
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
            log(context.get('app'), "No surface input provided to Array_UV", 
                level=LogLevel.WARNING, module="ARRAY_UV")
            return {"collection": None}
        
        if not isinstance(surface_data, dict):
            raise TypeError(f"surface input must be dict, got {type(surface_data)}")
        
        # Get parameters with defaults
        count_u = int(inputs.get("count_u", self.DEFAULT_COUNT_U))
        count_v = int(inputs.get("count_v", self.DEFAULT_COUNT_V))
        stagger_offset = float(inputs.get("stagger_offset", 0.0))
        position_u = float(inputs.get("position_u", self.DEFAULT_POSITION_U))
        position_v = float(inputs.get("position_v", self.DEFAULT_POSITION_V))
        rotation = float(inputs.get("rotation", 0.0))
        edge_margin = float(inputs.get("edge_margin", 0.0))
        align_to_normal = bool(inputs.get("align_to_normal", True))
        
        log(context.get('app'), 
            f"Creating UV array: {count_u}x{count_v}, stagger={stagger_offset:.3f}, rotation={rotation:.1f}°, margin={edge_margin:.1f}, align_to_normal={align_to_normal}",
            level=LogLevel.DEBUG, module="ARRAY_UV")
        
        # Resolve surface face
        surface_face = resolve_surface_face(surface_data, context.get('app'))
        if not surface_face:
            log(context.get('app'), "Failed to resolve surface face", 
                level=LogLevel.ERROR, module="ARRAY_UV")
            return {"collection": None}
        
        # Get surface evaluator and bounds
        if not hasattr(surface_face, 'evaluator'):
            log(context.get('app'), "Surface face has no evaluator", 
                level=LogLevel.ERROR, module="ARRAY_UV")
            return {"collection": None}
        
        surface_evaluator = surface_face.evaluator
        u_min, u_max, v_min, v_max = get_surface_bounds(surface_face)
        
        log(context.get('app'), 
            f"Surface bounds: U=[{u_min:.3f}, {u_max:.3f}], V=[{v_min:.3f}, {v_max:.3f}]",
            level=LogLevel.DEBUG, module="ARRAY_UV")
        
        # Edge Margin is in cm. Shrink the bounds instead of passing it on.
        u_min, u_max, v_min, v_max = inset_bounds_by_margin(
            surface_evaluator, u_min, u_max, v_min, v_max, edge_margin, context.get('app'))
        
        # Generate UV parameter grid using utility pipeline
        uv_points = create_array_pipeline(
            count_u, count_v,
            (u_min, u_max, v_min, v_max),  # Surface bounds
            0.0,  # Margin already applied to the bounds
            position_u, position_v, rotation, stagger_offset,
            context.get('app')
        )
        
        if not uv_points:
            log(context.get('app'), "No UV points generated",
                level=LogLevel.ERROR, module="ARRAY_UV")
            return {"collection": None}
        
        # source_geometries_data and input_instances already set above from collection_spec
        if not source_geometries_data:
            log(context.get('app'), "Input collection has no source geometries",
                level=LogLevel.WARNING, module="ARRAY_UV")
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
                        level=LogLevel.ERROR, module="ARRAY_UV")
                    return {"collection": None}
            else:
                # Should be GeometryEnvelope already
                source_geometries.append(geo_data)
        
        # Create surface instances
        if align_to_normal:
            transformation_matrices = create_surface_instances_with_uv_alignment(
                surface_evaluator, uv_points, rotation, align_to_normal
            )
            log(context.get('app'), "Using UV tangent alignment for surface instances",
                level=LogLevel.DEBUG, module="ARRAY_UV")
        else:
            transformation_matrices = create_surface_instances_translation_only(
                surface_evaluator, uv_points
            )
            log(context.get('app'), "Using translation-only positioning (no alignment)",
                level=LogLevel.DEBUG, module="ARRAY_UV")
        
        if not transformation_matrices:
            log(context.get('app'), "Failed to create transformation matrices",
                level=LogLevel.ERROR, module="ARRAY_UV")
            return {"collection": None}
        
        # Create collection instances using utility
        node_id = context.get('node_id', 'unknown')
        new_instances = create_instances_from_transforms(
            transformation_matrices, uv_points, input_instances,
            self.NODE_TYPE, node_id, "uv_array", context.get('app'),
            source_geometries=source_geometries  # Pass source geometries for name extraction
        )
        
        # Defensive check: Ensure instances are proper CollectionInstanceSpec objects
        validated_instances = []
        for i, instance in enumerate(new_instances):
            if isinstance(instance, dict):
                # Convert dict to CollectionInstanceSpec if needed
                validated_instances.append(CollectionInstanceSpec.from_dict(instance))
                log(context.get('app'), f"Warning: Instance {i} was dict, converted to CollectionInstanceSpec",
                    level=LogLevel.WARNING, module="ARRAY_UV")
            else:
                # Should be CollectionInstanceSpec already
                validated_instances.append(instance)
        
        # Create array output collection metadata
        array_metadata = create_array_collection_metadata(
            "uv_array", count_u, count_v, node_id, len(input_instances),
            stagger_offset=stagger_offset, position_u=position_u, position_v=position_v,
            rotation=rotation, edge_margin=edge_margin, align_to_normal=align_to_normal
        )
        
        # Generate unique collection ID
        collection_id = str(uuid.uuid4())[:8]
        
        log(context.get('app'), f"🔍 DEBUG: About to create CollectionSpec with {len(source_geometries)} geometries, {len(validated_instances)} instances", 
            level=LogLevel.DEBUG, module="ARRAY_UV_DEBUG")
        
        # Verify types before creating CollectionSpec
        for i, geo in enumerate(source_geometries):
            log(context.get('app'), f"🔍 DEBUG: source_geometries[{i}] type = {type(geo)}", 
                level=LogLevel.DEBUG, module="ARRAY_UV_DEBUG")
        for i, inst in enumerate(validated_instances[:3]):  # Only first 3 to avoid spam
            log(context.get('app'), f"🔍 DEBUG: validated_instances[{i}] type = {type(inst)}", 
                level=LogLevel.DEBUG, module="ARRAY_UV_DEBUG")
        
        # Create proper CollectionSpec instance
        output_collection = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=collection_id,
            source_geometries=source_geometries,
            instances=validated_instances,  # Use validated instances
            metadata=array_metadata
        )
        
        log(context.get('app'), f"🔍 DEBUG: CollectionSpec created successfully, type = {type(output_collection)}", 
            level=LogLevel.DEBUG, module="ARRAY_UV_DEBUG")
        
        log(context.get('app'), 
            f"Created UV array collection: {len(input_instances)} → {len(validated_instances)} instances",
            level=LogLevel.DEBUG, module="ARRAY_UV")
        
        return {"collection": output_collection}
