"""
Geometry naming utilities - standardized naming for all geometry nodes.
All geometry-creating nodes MUST use these functions to ensure consistency.
"""

import re
from typing import Optional
from ..specification import SPECIFICATION

def generate_geometry_name(
    node_type: str,
    node_id: str, 
    source_name: str = "Geometry",
    index: Optional[int] = None
) -> str:
    """
    Generate standardized geometry name following the specification.
    Intelligently prunes nested geometry names to prevent unwieldy chaining.
    
    Args:
        node_type: The node type (e.g., "body_instance", "cube_generator")
        node_id: The full node ID (e.g., "node_body_instance_1769218448555_2589") 
        source_name: Source geometry name or descriptive name
        index: Optional index for arrays (0-based, will be formatted as 3-digit)
        
    Returns:
        Formatted geometry name following specification
        
    Examples:
        generate_geometry_name("body_instance", "node_body_instance_123_456", "Body1")
        -> "body_instance_456_Body1"
        
        generate_geometry_name("linear_array", "node_linear_array_789_012", "Cylinder", 0)
        -> "linear_array_012_Cylinder_000"
        
        # Intelligent pruning for nested arrays:
        generate_geometry_name("linear_array", "node_linear_array_789_012", "linear_array_456_Body1_001", 0)
        -> "linear_array_012_Body1_L2_000"  # Preserves original source, adds level indicator
    """
    spec = SPECIFICATION.geometry_naming
    
    # Extract short ID from full node ID (last numeric part)
    short_id_match = re.search(r'_(\d+)$', node_id)
    short_id = short_id_match.group(1) if short_id_match else node_id
    
    # Map node type if needed
    # Lowercase, so a node's registered type ('Materializer') and the name it
    # passes when creating bodies ('materializer') give the same prefix.
    mapped_node_type = spec.node_type_mappings.get(node_type, node_type).lower()
    
    # INTELLIGENT PRUNING: Check if source_name is already a generated geometry name
    clean_source = _prune_nested_geometry_name(source_name, mapped_node_type)
    
    # Clean source name (remove invalid characters, truncate if needed)
    clean_source = re.sub(r'[^A-Za-z0-9_L]', '', clean_source)  # Allow 'L' for level indicators
    if len(clean_source) > spec.length_limits['max_source_name_length']:
        clean_source = clean_source[:spec.length_limits['max_source_name_length']]
    
    # Generate name based on pattern
    if index is not None:
        # Array pattern with 3-digit zero-padded index
        name = spec.array_pattern.format(
            node_type=mapped_node_type,
            short_id=short_id,
            source_name=clean_source,
            index=index
        )
    else:
        # Single body pattern
        name = spec.base_pattern.format(
            node_type=mapped_node_type,
            short_id=short_id,
            source_name=clean_source
        )
    
    # Validate and truncate if needed
    if len(name) > spec.length_limits['max_total_length']:
        # Truncate source name to fit
        max_source_len = spec.length_limits['max_total_length'] - len(name) + len(clean_source)
        clean_source = clean_source[:max_source_len]
        
        # Regenerate with truncated source
        if index is not None:
            name = spec.array_pattern.format(
                node_type=mapped_node_type,
                short_id=short_id,
                source_name=clean_source,
                index=index
            )
        else:
            name = spec.base_pattern.format(
                node_type=mapped_node_type,
                short_id=short_id,
                source_name=clean_source
            )
    
    return name

def geometry_name_prefix(node_type: str, node_id: str) -> str:
    """The start of every body name a node produces: '<type>_<short id>_'.

    Body names are how a node's bodies are found again, including in a document
    that was closed and reopened, when nothing else links a body to its node.
    """
    spec = SPECIFICATION.geometry_naming
    short_id_match = re.search(r'_(\d+)$', node_id)
    short_id = short_id_match.group(1) if short_id_match else node_id
    # Lowercase, so a node's registered type ('Materializer') and the name it
    # passes when creating bodies ('materializer') give the same prefix.
    mapped_node_type = spec.node_type_mappings.get(node_type, node_type).lower()
    return f"{mapped_node_type}_{short_id}_"

def extract_node_info_from_name(name: str) -> dict:
    """
    Extract node information from a geometry name.
    
    Args:
        name: The geometry name to parse
        
    Returns:
        Dict with 'node_type', 'short_id', 'source_name', 'index' (if array)
        
    Example:
        extract_node_info_from_name("body_instance_2589_Body1")
        -> {'node_type': 'body_instance', 'short_id': '2589', 'source_name': 'Body1', 'index': None}
        
        extract_node_info_from_name("linear_array_012_Cylinder_000")  
        -> {'node_type': 'linear_array', 'short_id': '012', 'source_name': 'Cylinder', 'index': 0}
    """
    # Match array pattern first
    array_match = re.match(r'^([a-z_]+)_(\d+)_([A-Za-z0-9_]+)_(\d{3})$', name)
    if array_match:
        return {
            'node_type': array_match.group(1),
            'short_id': array_match.group(2), 
            'source_name': array_match.group(3),
            'index': int(array_match.group(4))
        }
    
    # Match single body pattern
    single_match = re.match(r'^([a-z_]+)_(\d+)_([A-Za-z0-9_]+)$', name)
    if single_match:
        return {
            'node_type': single_match.group(1),
            'short_id': single_match.group(2),
            'source_name': single_match.group(3), 
            'index': None
        }
    
    # Invalid format
    return {}

def _prune_nested_geometry_name(source_name: str, current_node_type: str) -> str:
    """
    Intelligently prune nested geometry names to prevent unwieldy chaining.
    
    Examples:
        _prune_nested_geometry_name("linear_array_456_Body1_001", "linear_array")
        -> "Body1_L2"  # Extract original source, add level indicator
        
        _prune_nested_geometry_name("body_instance_789_Cylinder", "linear_array")  
        -> "Cylinder_L2"  # Extract original source, add level indicator
        
        _prune_nested_geometry_name("Body1", "linear_array")
        -> "Body1"  # Not a generated name, return as-is
    """
    # Try to parse as existing geometry name
    parsed = extract_node_info_from_name(source_name)
    
    if not parsed:
        # Not a generated geometry name, return as-is
        return source_name
    
    # It's a generated geometry name, extract the original source
    original_source = parsed['source_name']
    
    # Check if the original source itself has level indicators
    level_match = re.search(r'_L(\d+)$', original_source)
    if level_match:
        # Already has a level indicator, increment it
        current_level = int(level_match.group(1))
        new_level = current_level + 1
        base_source = original_source[:level_match.start()]
        return f"{base_source}_L{new_level}"
    else:
        # First level of nesting, add L2
        return f"{original_source}_L2"
