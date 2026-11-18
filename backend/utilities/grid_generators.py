"""
Array grid generation utilities for v2 - reusable functions for all array nodes.
Extracted from inline math in array nodes to maximize reusability.
"""

import math
# Conditional import for Fusion 360 compatibility
try:
    from typing import List, Tuple, Dict, Any, Optional
except ImportError:
    from typing import Tuple, Dict, Any, Optional
    List = list  # Fallback to built-in list
from .log_utils import log, LogLevel

def generate_uv_parameter_grid(
    count_u: int, 
    count_v: int, 
    u_bounds: Tuple[float, float], 
    v_bounds: Tuple[float, float],
    position_u: float = 0.5, 
    position_v: float = 0.5, 
    rotation: float = 0.0,
    app=None
) -> List[Tuple[float, float]]:
    """
    Generate simple UV parameter grid with i/(count-1) distribution and optional rotation.
    
    Args:
        count_u: Number of points in U direction
        count_v: Number of points in V direction  
        u_bounds: (u_min, u_max) parametric bounds
        v_bounds: (v_min, v_max) parametric bounds
        position_u: Grid center position in U (0.0 to 1.0)
        position_v: Grid center position in V (0.0 to 1.0)
        rotation: Rotation angle in degrees
        app: Application reference for logging
        
    Returns:
        List of (u, v) parameter coordinates
    """
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    
    # Generate base UV grid using simple i/(count-1) distribution
    u_lin = [i / (count_u - 1) if count_u > 1 else 0.5 for i in range(count_u)]
    v_lin = [j / (count_v - 1) if count_v > 1 else 0.5 for j in range(count_v)]
    
    # Convert to actual UV coordinates within bounds
    u_coords = [u_min + u * (u_max - u_min) for u in u_lin]
    v_coords = [v_min + v * (v_max - v_min) for v in v_lin]
    
    # Calculate center for positioning and rotation
    center_u = u_min + position_u * (u_max - u_min)
    center_v = v_min + position_v * (v_max - v_min)
    
    # Generate grid points
    uv_points = []
    for j, v in enumerate(v_coords):
        for i, u in enumerate(u_coords):
            uv_points.append((u, v))
    
    # Apply rotation if specified
    if abs(rotation) > 1e-6:
        uv_points = apply_uv_rotation(uv_points, rotation, center_u, center_v)
        log(app, f"Applied {rotation}° rotation around center UV({center_u:.3f}, {center_v:.3f})",
            level=LogLevel.DEBUG, module="GRID_UTILS")
    
    log(app, f"Generated {len(uv_points)} UV grid points ({count_u}x{count_v}) with i/(count-1) distribution",
        level=LogLevel.DEBUG, module="GRID_UTILS")
    
    return uv_points


def apply_uv_rotation(
    uv_points: List[Tuple[float, float]], 
    rotation: float, 
    center_u: float, 
    center_v: float
) -> List[Tuple[float, float]]:
    """
    Apply rotation to UV parameter points around a center point.
    
    Args:
        uv_points: List of (u, v) coordinates
        rotation: Rotation angle in degrees
        center_u: Rotation center U coordinate
        center_v: Rotation center V coordinate
        
    Returns:
        List of rotated (u, v) coordinates
    """
    cos_r = math.cos(math.radians(rotation))
    sin_r = math.sin(math.radians(rotation))
    
    rotated_points = []
    for u, v in uv_points:
        # Translate to center
        u_centered = u - center_u
        v_centered = v - center_v
        
        # Rotate
        u_rotated = u_centered * cos_r - v_centered * sin_r
        v_rotated = u_centered * sin_r + v_centered * cos_r
        
        # Translate back
        u_final = u_rotated + center_u
        v_final = v_rotated + center_v
        
        rotated_points.append((u_final, v_final))
    
    return rotated_points


def apply_stagger_offset(
    uv_points: List[Tuple[float, float]], 
    stagger_offset: float, 
    count_u: int, 
    count_v: int,
    u_bounds: Tuple[float, float],
    app=None
) -> List[Tuple[float, float]]:
    """
    Apply stagger offset to alternate rows of UV points.
    
    Args:
        uv_points: List of (u, v) coordinates
        stagger_offset: Offset amount (-0.5 to 0.5)
        count_u: Number of points per row
        count_v: Number of rows
        u_bounds: (u_min, u_max) for bounds checking
        app: Application reference for logging
        
    Returns:
        List of staggered (u, v) coordinates
    """
    if abs(stagger_offset) < 1e-6:
        return uv_points
    
    u_min, u_max = u_bounds
    u_range = u_max - u_min
    offset_u = stagger_offset * u_range / count_u if count_u > 1 else 0
    
    staggered_points = []
    for i, (u, v) in enumerate(uv_points):
        row = i // count_u
        if row % 2 == 1:  # Odd rows
            u_staggered = u + offset_u
            # Clamp to bounds
            u_staggered = max(u_min, min(u_max, u_staggered))
            staggered_points.append((u_staggered, v))
        else:
            staggered_points.append((u, v))
    
    log(app, f"Applied stagger offset {stagger_offset} to {len(uv_points)} UV points",
        level=LogLevel.DEBUG, module="GRID_UTILS")
    
    return staggered_points


def calculate_uv_bounds_with_margin(
    base_bounds: Tuple[float, float, float, float],
    margin_parametric: float
) -> Tuple[float, float, float, float]:
    """
    Calculate UV bounds with edge margin applied by shrinking symmetrically.
    
    Args:
        base_bounds: (u_min, u_max, v_min, v_max) original bounds
        margin_parametric: Edge margin in parametric space
        
    Returns:
        (u_min_margin, u_max_margin, v_min_margin, v_max_margin) shrunk bounds
    """
    u_min, u_max, v_min, v_max = base_bounds
    
    u_range = u_max - u_min
    v_range = v_max - v_min
    u_margin = margin_parametric * u_range
    v_margin = margin_parametric * v_range
    
    u_min_margin = u_min + u_margin
    u_max_margin = u_max - u_margin
    v_min_margin = v_min + v_margin
    v_max_margin = v_max - v_margin
    
    return (u_min_margin, u_max_margin, v_min_margin, v_max_margin)


def create_array_pipeline(
    count_u: int,
    count_v: int,
    surface_bounds: Tuple[float, float, float, float],
    edge_margin_parametric: float,
    position_u: float = 0.5,
    position_v: float = 0.5,
    rotation: float = 0.0,
    stagger_offset: float = 0.0,
    app=None
) -> List[Tuple[float, float]]:
    """
    Complete UV array generation pipeline combining all steps.
    
    This is the main function that other array nodes should use to generate
    UV parameter grids with all common transformations applied.
    
    Args:
        count_u: Number of points in U direction
        count_v: Number of points in V direction
        surface_bounds: (u_min, u_max, v_min, v_max) base surface bounds
        edge_margin_parametric: Edge margin in parametric space
        position_u: Grid center position in U (0.0 to 1.0)
        position_v: Grid center position in V (0.0 to 1.0)  
        rotation: Rotation angle in degrees
        stagger_offset: Stagger offset for alternate rows (-0.5 to 0.5)
        app: Application reference for logging
        
    Returns:
        List of final (u, v) parameter coordinates ready for surface evaluation
    """
    log(app, f"Creating UV array pipeline: {count_u}x{count_v}, rotation={rotation}°, stagger={stagger_offset}",
        level=LogLevel.DEBUG, module="GRID_UTILS")
    
    # Calculate bounds with edge margin
    u_min, u_max, v_min, v_max = calculate_uv_bounds_with_margin(
        surface_bounds, edge_margin_parametric
    )
    
    # Generate base UV grid
    uv_points = generate_uv_parameter_grid(
        count_u, count_v,
        (u_min, u_max), (v_min, v_max),
        position_u, position_v, rotation,
        app
    )
    
    # Apply stagger offset if specified
    if abs(stagger_offset) > 1e-6:
        uv_points = apply_stagger_offset(
            uv_points, stagger_offset, count_u, count_v, (u_min, u_max), app
        )
    
    log(app, f"UV array pipeline completed: {len(uv_points)} final points",
        level=LogLevel.DEBUG, module="GRID_UTILS")
    
    return uv_points