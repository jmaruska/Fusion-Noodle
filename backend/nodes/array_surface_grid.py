"""
Surface Grid Array Node - World-space walking grid patterns on surfaces.

This node creates sophisticated grid arrays that blend between UV-conformant
and world-space uniform patterns for more regular and predictable spacing.
Unlike simple UV grids, this uses world-space walking algorithms to achieve
consistent spacing in 3D space while following surface topology.

Key Features:
- Two grid calculation methods: UV-conformant and world-uniform
- Bias blending between the two methods (u_bias, v_bias)
- World-space walking for regular patterns
- Stagger mode for brick patterns
- Comprehensive parameter control
"""

from typing import Dict, Any, List
import uuid
import math
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType, CollectionSpec, GeometryEnvelope, CollectionInstanceSpec
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel
from ..utilities.surface_grid_generators import generate_surface_grid_pipeline
from ..utilities.surface_utils import get_surface_bounds, resolve_surface_entity, inset_bounds_by_margin
from ..utilities.surface_placement_utils import create_surface_instances_with_alignment
from ..utilities.instance_creation import (
    create_instances_from_transforms, create_array_collection_metadata
)

@enforce_node_spec
class SurfaceGridNode(BaseNode):
    """
    Creates sophisticated grid arrays on surfaces using world-space walking.
    
    This node generates grids that blend between UV-conformant patterns
    (which follow surface parameterization) and world-uniform patterns
    (which maintain consistent world-space spacing). This results in more
    regular and predictable grid patterns than simple UV subdivision.
    
    The key innovation is the bias blending system:
    - u_bias = 1.0: Pure UV-conformant (follows surface flow)
    - u_bias = 0.0: Pure world-uniform (ignores surface parameterization)
    - u_bias = 0.5: 50/50 blend of both methods
    
    Similar logic applies to v_bias for the V direction.
    """
    
    NODE_TYPE = "Array_Surface_Grid"
    NODE_CATEGORY = "array"  
    NODE_NAME = "Surface Grid Array"
    NODE_DESCRIPTION = "Create world-space walking grid arrays on surfaces"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Define the node specification with all ports."""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Core inputs
                PortSpec("collection", PortType.COLLECTION, required=True, description="The instances to arrange on the surface."),
                
                # Input surface
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("surface", PortType.SURFACE, required=True, show_input_handle=False, description="Pick the face in Fusion to arrange the instances on."),
                
                # Grid count and spacing
                PortSpec("spacer_1", PortType.SPACER),
                PortSpec("count_u", PortType.INTEGER, required=False, default_value=5, min_value=1, max_value=100, description="Number of instances along the surface's U direction."),
                PortSpec("count_v", PortType.INTEGER, required=False, default_value=5, min_value=1, max_value=100, description="Number of instances along the surface's V direction."), 
                PortSpec("spacing_u", PortType.FLOAT, unit="length", required=False, default_value=3.0, min_value=0.001, description="Distance between neighboring instances along U."),
                PortSpec("spacing_v", PortType.FLOAT, unit="length", required=False, default_value=3.0, min_value=0.001, description="Distance between neighboring rows along V."),
                
                # Stagger control
                PortSpec("spacer_2", PortType.SPACER),
                PortSpec("stagger_offset", PortType.FLOAT, required=False, default_value=0.0, min_value=-0.5, max_value=0.5, description="Shifts every other row by this fraction of a column; negative shifts the other way."),
                
                # Position and alignment
                PortSpec("spacer_3", PortType.SPACER),
                PortSpec("position_u", PortType.FLOAT, required=False, default_value=0.5, min_value=0.0, max_value=1.0, description="Where the grid's center sits along U, 0 at one edge and 1 at the other."),
                PortSpec("position_v", PortType.FLOAT, required=False, default_value=0.5, min_value=0.0, max_value=1.0, description="Where the grid's center sits along V, 0 at one edge and 1 at the other."),
                PortSpec("edge_margin", PortType.FLOAT, unit="length", required=False, default_value=0.0,
                         min_value=0.0, label="Edge Margin",
                         description="Distance to keep clear of the surface edges."),
                
                # Orientation control
                PortSpec("spacer_4", PortType.SPACER),
                PortSpec("rotation", PortType.FLOAT, unit="angle", required=False, default_value=0.0, description="Turns the grid pattern, and each instance, about the surface normal."),
                PortSpec("align_to_normal", PortType.BOOLEAN, required=False, default_value=True, show_input_handle=False, description="Stand each instance along the surface normal; off keeps its original orientation."),
                
                # Bias controls (key feature for blending grid methods)
                PortSpec("spacer_5", PortType.SPACER),
                PortSpec("u_bias", PortType.FLOAT, required=False, default_value=0.0, min_value=0.0, max_value=1.0, description="Blends U placement from even real-world spacing (0) to following the surface's UV flow (1)."),
                PortSpec("v_bias", PortType.FLOAT, required=False, default_value=0.0, min_value=0.0, max_value=1.0, description="Blends V placement from even real-world spacing (0) to following the surface's UV flow (1)."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION)
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate surface grid specific input parameters."""
        # Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)
        errors = []
        if 'collection' not in inputs or inputs['collection'] is None:
            errors.append(f"{self.port_label('collection')} input is required")
        if 'surface' not in inputs or inputs['surface'] is None:
            errors.append(f"{self.port_label('surface')} input is required")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute surface grid generation with world-space walking."""
        
        app = context.get('app')
        
        try:
            # Extract input values with defaults
            input_collection = inputs.get('collection')
            surface_data = inputs.get('surface')
            count_u = int(inputs.get('count_u', 5))
            count_v = int(inputs.get('count_v', 5))
            spacing_u = float(inputs.get('spacing_u', 3.0))
            spacing_v = float(inputs.get('spacing_v', 3.0))
            stagger_offset = float(inputs.get('stagger_offset', 0.0))
            position_u = float(inputs.get('position_u', 0.5))
            position_v = float(inputs.get('position_v', 0.5))
            rotation = float(inputs.get('rotation', 0.0))
            edge_margin = float(inputs.get('edge_margin', 0.0))
            align_to_normal = bool(inputs.get('align_to_normal', True))
            u_bias = float(inputs.get('u_bias', 0.0))  # World-uniform by default
            v_bias = float(inputs.get('v_bias', 0.0))  # World-uniform by default
            
            log(app, f"Surface Grid: {count_u}×{count_v}, spacing=({spacing_u}, {spacing_v})", 
                level=LogLevel.DEBUG, module="SURFACE_GRID")
            log(app, f"Surface Grid: u_bias={u_bias}, v_bias={v_bias}, edge_margin={edge_margin} cm", 
                level=LogLevel.DEBUG, module="SURFACE_GRID")
            
            # Handle both CollectionSpec objects and dict format for backward compatibility
            if hasattr(input_collection, 'source_geometries'):
                # It's already a CollectionSpec object
                collection_spec = input_collection
            elif isinstance(input_collection, dict):
                # Convert from dict to CollectionSpec
                collection_spec = CollectionSpec.from_dict(input_collection)
            else:
                log(app, "Surface Grid: Invalid collection input", level=LogLevel.ERROR, module="SURFACE_GRID")
                return {"collection": None}
            
            # Resolve surface entity
            surface_entity = resolve_surface_entity(surface_data, app)
            if not surface_entity:
                log(app, "Surface Grid: Failed to resolve surface entity", level=LogLevel.ERROR, module="SURFACE_GRID")
                return {"collection": None}
                
            # Get surface evaluator and bounds
            surface_evaluator = surface_entity.evaluator if hasattr(surface_entity, 'evaluator') else None
            if not surface_evaluator:
                log(app, "Surface Grid: No surface evaluator available", level=LogLevel.ERROR, module="SURFACE_GRID")
                return {"collection": None}
                
            u_min, u_max, v_min, v_max = get_surface_bounds(surface_entity)
            # Edge Margin is in cm. Shrink the bounds instead of passing it on.
            u_min, u_max, v_min, v_max = inset_bounds_by_margin(
                surface_evaluator, u_min, u_max, v_min, v_max, edge_margin, app)
            
            # Determine array type from stagger offset
            array_type = 'stagger' if abs(stagger_offset) > 1e-6 else 'grid'
            
            
            # Generate UV grid points using world-space walking pipeline
            uv_points = generate_surface_grid_pipeline(
                count_u=count_u,
                count_v=count_v,
                surface_evaluator=surface_evaluator,
                u_bounds=(u_min, u_max),
                v_bounds=(v_min, v_max),
                stagger_offset=stagger_offset,
                spacing_u=spacing_u,
                spacing_v=spacing_v,
                edge_margin=0.0,  # Already applied to the bounds above
                rotation_degrees=rotation,
                u_bias=u_bias,
                v_bias=v_bias,
                pos_u=position_u,
                pos_v=position_v,
                array_type=array_type,
                app=app
            )
            
            if not uv_points:
                log(app, "Surface Grid: No UV points generated", level=LogLevel.WARNING, module="SURFACE_GRID")
                return {"collection": None}

            # Pipeline now returns (u, v, grid_i, grid_j) tuples; split and validate.
            valid_uv = []
            valid_grid_indices = []
            for i, point in enumerate(uv_points):
                u, v = point[0], point[1]
                if u is not None and v is not None and not (math.isnan(u) or math.isnan(v)):
                    valid_uv.append((u, v))
                    valid_grid_indices.append((int(point[2]), int(point[3])) if len(point) >= 4 else None)
                else:
                    log(app, f"Surface Grid: Invalid UV point at index {i}: ({u}, {v})",
                        level=LogLevel.WARNING, module="SURFACE_GRID")

            if len(valid_uv) != len(uv_points):
                log(app, f"Surface Grid: Filtered {len(uv_points) - len(valid_uv)} invalid UV points",
                    level=LogLevel.WARNING, module="SURFACE_GRID")

            uv_points = valid_uv
            grid_indices = valid_grid_indices

            if not uv_points:
                log(app, "Surface Grid: No valid UV points after filtering", level=LogLevel.ERROR, module="SURFACE_GRID")
                return {"collection": None}

            log(app, f"Surface Grid: Generated {len(uv_points)} UV points", level=LogLevel.DEBUG, module="SURFACE_GRID")
            
            # PERFORMANCE: Track post-UV generation phases
            import time
            phase_start = time.time()
            
            # Create surface instances with proper alignment
            transform_matrices = create_surface_instances_with_alignment(
                surface_evaluator=surface_evaluator,
                uv_points=uv_points,
                rotation_degrees=rotation,
                align_to_normal=align_to_normal,
                app=app
            )
            
            transform_time = time.time() - phase_start
            log(app, f"Surface Grid: Transform creation took {transform_time:.2f}s", level=LogLevel.DEBUG, module="SURFACE_GRID")
            
            if not transform_matrices:
                log(app, "Surface Grid: Failed to create transform matrices", level=LogLevel.ERROR, module="SURFACE_GRID")
                return {"collection": None}
                
            # Create instances using the same pattern as other array nodes
            # Convert CollectionInstanceSpec objects to dictionaries for the function
            input_instances_dicts = []
            for inst in collection_spec.instances:
                if hasattr(inst, 'to_dict'):
                    input_instances_dicts.append(inst.to_dict())
                elif isinstance(inst, dict):
                    input_instances_dicts.append(inst)
                else:
                    # Fallback for unknown format
                    input_instances_dicts.append(inst.__dict__ if hasattr(inst, '__dict__') else inst)
                    
            instance_start = time.time()
            new_instances = create_instances_from_transforms(
                transformation_matrices=transform_matrices,
                input_instances=input_instances_dicts,  # Pass dictionaries
                uv_points=uv_points,
                node_type=self.NODE_TYPE,
                node_id=context.get('node_id', 'unknown'),
                array_type="surface_grid",
                app=app,
                source_geometries=collection_spec.source_geometries,
                grid_indices=grid_indices
            )
            instance_time = time.time() - instance_start
            log(app, f"Surface Grid: Instance creation took {instance_time:.2f}s", level=LogLevel.DEBUG, module="SURFACE_GRID")
            
            # Convert source_geometries to GeometryEnvelope objects if needed
            collection_start = time.time()
            geo_objs = []
            for geo in collection_spec.source_geometries:
                if isinstance(geo, dict):
                    geo_objs.append(GeometryEnvelope(**geo))
                else:
                    geo_objs.append(geo)
            
            # Convert instances using from_dict pattern (same as Surface Hex Array)
            validated_instances = []
            for inst in new_instances:
                if isinstance(inst, dict):
                    validated_instances.append(CollectionInstanceSpec.from_dict(inst))
                else:
                    validated_instances.append(inst)
            
            # Create array output collection metadata (same pattern as Surface Hex Array)
            array_metadata = create_array_collection_metadata(
                "surface_grid", count_u, count_v, context.get('node_id', 'unknown'), len(collection_spec.instances),
                spacing_u=spacing_u, spacing_v=spacing_v, position_u=position_u, position_v=position_v,
                rotation=rotation, edge_margin=edge_margin, align_to_normal=align_to_normal,
                u_bias=u_bias, v_bias=v_bias, stagger_offset=stagger_offset
            )
            
            # Generate unique collection ID (same pattern as Surface Hex Array)
            collection_id = str(uuid.uuid4())[:8]
            
            # Create output collection (same pattern as Surface Hex Array)
            output_collection = CollectionSpec(
                collection_type="geometry_collection",
                collection_id=collection_id,
                source_geometries=geo_objs,
                instances=validated_instances,
                metadata=array_metadata
            )
            
            collection_time = time.time() - collection_start
            total_time = time.time() - phase_start
            log(app, f"Surface Grid: Collection finalization took {collection_time:.2f}s", level=LogLevel.DEBUG, module="SURFACE_GRID")
            log(app, f"Surface Grid: Total post-UV processing took {total_time:.2f}s", level=LogLevel.DEBUG, module="SURFACE_GRID")
            
            log(app, f"Surface Grid: Created collection with {len(validated_instances)} instances",
                level=LogLevel.DEBUG, module="SURFACE_GRID")
            
            # Validate collection before returning
            try:
                # Validate that we have instances and source geometries
                if not output_collection.instances:
                    log(app, "Surface Grid: WARNING - No instances in output collection", level=LogLevel.WARNING, module="SURFACE_GRID")
                if not output_collection.source_geometries:
                    log(app, "Surface Grid: WARNING - No source geometries in output collection", level=LogLevel.WARNING, module="SURFACE_GRID")
                    
                return {"collection": output_collection}
                
            except Exception as e:
                log(app, f"Surface Grid: Collection serialization failed: {str(e)}", level=LogLevel.ERROR, module="SURFACE_GRID")
                return {"collection": None}
            
        except Exception as e:
            log(app, f"Surface Grid error: {str(e)}", level=LogLevel.ERROR, module="SURFACE_GRID")
            return {"collection": None}
