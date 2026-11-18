"""Collection instance utilities for v2 - Maya-style attributes system.
Creates CollectionInstanceSpec objects with NoodleAttributes (flattened primitives).
"""

import uuid
from typing import List, Dict, Any, Tuple

# Import backend contracts
from ..contracts import CollectionInstanceSpec
from ..utilities.log_utils import log, LogLevel
from ..utilities.transform_extraction import (
    batch_extract_noodle_attributes,
    NoodleAttributes
)


def create_instances_from_transforms(
    transformation_matrices,
    uv_points: List[Tuple[float, float]],
    input_instances: List[Dict[str, Any]],
    node_type: str,
    node_id: str,
    array_type: str,
    app=None,
    source_geometries: List[Any] = None,
    grid_indices: List[Any] = None
) -> List[CollectionInstanceSpec]:
    """
    Create collection instances using Maya-style NoodleAttributes objects.
    
    This utility creates properly structured CollectionInstanceSpec objects
    with flattened attributes - no nested serialization issues!
    
    Args:
        transformation_matrices: List of Fusion 360 Matrix3D objects
        uv_points: List of (u, v) parameter coordinates corresponding to matrices
        input_instances: List of input instance dictionaries to replicate
        node_type: Node type identifier for metadata
        node_id: Node instance ID for metadata
        array_type: Array type identifier for metadata
        app: Application reference for logging
        source_geometries: List of GeometryEnvelope objects to extract names from
        
    Returns:
        List of CollectionInstanceSpec objects with Maya-style attributes
    """
    new_instances = []
    
    if not input_instances:
        log(app, "No input instances provided for replication",
            level=LogLevel.WARNING, module="INSTANCE_UTILS")
        return new_instances
    
    log(app, f"Creating instances from {len(transformation_matrices)} transforms "
             f"for {len(input_instances)} input instances (Maya-style)",
        level=LogLevel.DEBUG, module="INSTANCE_UTILS")
    
    for input_instance in input_instances:
        # Handle CollectionInstanceSpec objects (v2 spec compliance)
        from ..contracts import CollectionInstanceSpec
        if isinstance(input_instance, CollectionInstanceSpec):
            # Already a proper CollectionInstanceSpec object
            input_instance_spec = input_instance
        else:
            # Legacy dictionary format (should not occur in pure v2 implementation)
            input_instance_spec = CollectionInstanceSpec.from_dict(input_instance)
        
        # Get source scale from attributes (v2 only supports NoodleAttributes)
        if isinstance(input_instance_spec.transform, NoodleAttributes):
            # Maya-style attributes - spec guarantees these are never None
            source_scale_dict = {
                'x': input_instance_spec.transform.sx,
                'y': input_instance_spec.transform.sy,
                'z': input_instance_spec.transform.sz
            }
        else:
            # Legacy TransformSpec compatibility with None safety checks
            try:
                source_scale_dict = {
                    'x': input_instance_spec.transform.scale.x if input_instance_spec.transform.scale.x is not None else 1.0,
                    'y': input_instance_spec.transform.scale.y if input_instance_spec.transform.scale.y is not None else 1.0,
                    'z': input_instance_spec.transform.scale.z if input_instance_spec.transform.scale.z is not None else 1.0
                }
            except (AttributeError, TypeError):
                # Fallback if transform structure is unexpected
                source_scale_dict = {'x': 1.0, 'y': 1.0, 'z': 1.0}
        
        # Extract Maya-style attributes from all matrices (no nested serialization!)
        log(app, f"Source scale dict: {source_scale_dict}",
            level=LogLevel.DEBUG, module="INSTANCE_UTILS")
        noodle_attributes_list = batch_extract_noodle_attributes(transformation_matrices, source_scale_dict, app)
        
        # Create instances for this input instance across all attribute positions
        for i, (noodle_attrs, (u, v)) in enumerate(zip(noodle_attributes_list, uv_points)):
            if i >= len(transformation_matrices):
                break  # Safety check
            
            # Create instance metadata
            grid_index = grid_indices[i] if grid_indices and i < len(grid_indices) else None
            grid_u = grid_index[0] if grid_index is not None else None
            grid_v = grid_index[1] if grid_index is not None else None
            metadata = create_instance_metadata(
                node_type, node_id, array_type, i, (u, v),
                {'x': noodle_attrs.tx, 'y': noodle_attrs.ty, 'z': noodle_attrs.tz},
                input_instance_spec.instance_id,
                grid_u=grid_u, grid_v=grid_v
            )

            
            # Create new instance with Maya-style attributes (no nested objects!)
            new_instance = CollectionInstanceSpec(
                instance_id=generate_instance_id(),
                source_geometry_id=input_instance_spec.source_geometry_id,
                transform=noodle_attrs,  # NoodleAttributes object directly
                metadata=metadata
            )
            
            new_instances.append(new_instance)
    
    log(app, f"Created {len(new_instances)} collection instances with Maya-style attributes",
        level=LogLevel.DEBUG, module="INSTANCE_UTILS")
    
    return new_instances


def create_instance_metadata(
    node_type: str,
    node_id: str,
    array_type: str,
    index: int,
    uv_coordinates: Tuple[float, float],
    position: Dict[str, float],
    source_instance_id: str,
    grid_u: int = None,
    grid_v: int = None
) -> Dict[str, Any]:
    """
    Create standardized metadata for array instances.

    Args:
        node_type: Type of node creating the instance
        node_id: ID of the node instance
        array_type: Type of array (e.g., "uv_array")
        index: Index of this instance in the array
        uv_coordinates: (u, v) surface parameters
        position: World position dictionary
        source_instance_id: ID of the source instance being replicated
        grid_u: Column index in the source grid (for Interpolize sparse-grid grouping)
        grid_v: Row index in the source grid (for Interpolize sparse-grid grouping)

    Returns:
        Metadata dictionary for the instance
    """
    metadata = {
        "source_node": node_type,
        "surface_point_index": index,
        "uv_coordinates": list(uv_coordinates),
        "full_transform_matrix": True,
        "source_id": node_id,
        "array_type": array_type,
        "surface_point": position,
        "source_instance_id": source_instance_id
    }
    if grid_u is not None:
        metadata["grid_u_index"] = grid_u
    if grid_v is not None:
        metadata["grid_v_index"] = grid_v
    return metadata


def generate_instance_id() -> str:
    """Generate a unique short instance ID."""
    return str(uuid.uuid4())[:8]


def create_array_collection_metadata(
    array_type: str,
    count_u: int,
    count_v: int,
    node_id: str,
    input_instance_count: int,
    **kwargs
) -> Dict[str, Any]:
    """
    Create standardized metadata for array collections.
    
    Args:
        array_type: Type of array (e.g., "uv_array")
        count_u: Number of instances in U direction
        count_v: Number of instances in V direction  
        node_id: ID of the creating node
        input_instance_count: Number of input instances replicated
        **kwargs: Additional metadata parameters specific to array type
        
    Returns:
        Metadata dictionary for the collection
    """
    metadata = {
        "type": array_type,
        "count_u": count_u,
        "count_v": count_v,
        "input_instance_count": input_instance_count,
        "array_node_id": node_id
    }
    
    # Add any additional parameters
    metadata.update(kwargs)
    
    return metadata
