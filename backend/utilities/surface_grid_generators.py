"""
Surface Grid Generators - World-space walking grid generation.

This module provides sophisticated grid generation that blends between
UV-conformant patterns (following surface parameterization) and world-uniform
patterns (maintaining consistent world-space spacing).

Key Features:
- World-space walking algorithms for regular spacing
- UV-conformant grids that follow surface flow
- Bias blending between the two methods
- Support for stagger patterns and rotation
- Edge margin and culling capabilities
"""

import math
from typing import List, Tuple, Optional, Any
from .log_utils import log, LogLevel


def distance(p0, p1):
    """Euclidean distance between two 3D points. Handles Vector3/Vector3D or tuple."""
    def to_tuple(pt):
        if pt is None:
            return None
        if hasattr(pt, 'asArray'):
            return tuple(pt.asArray())
        if hasattr(pt, 'x') and hasattr(pt, 'y') and hasattr(pt, 'z'):
            return (pt.x, pt.y, pt.z)
        if isinstance(pt, (tuple, list)) and len(pt) >= 3:
            return (pt[0], pt[1], pt[2])
        return None
    
    p0_tuple = to_tuple(p0)
    p1_tuple = to_tuple(p1)
    
    # Return None if either point is invalid
    if p0_tuple is None or p1_tuple is None:
        return None
        
    try:
        return ((p0_tuple[0] - p1_tuple[0]) ** 2 + (p0_tuple[1] - p1_tuple[1]) ** 2 + (p0_tuple[2] - p1_tuple[2]) ** 2) ** 0.5
    except (TypeError, IndexError):
        return None

def generate_surface_grid_pipeline(
    count_u: int,
    count_v: int,
    surface_evaluator: Any,
    u_bounds: Tuple[float, float],
    v_bounds: Tuple[float, float],
    spacing_u: float = 1.0,
    spacing_v: float = 1.0,
    edge_margin: float = 0.0,
    rotation_degrees: float = 0.0,
    u_bias: float = 1.0,
    v_bias: float = 1.0,
    pos_u: float = 0.5,
    pos_v: float = 0.5,
    array_type: str = 'grid',
    stagger_offset: float = 0.5,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Full surface grid generation pipeline with world-space walking.
    
    This is the main entry point, including the key bias blending between
    UV-conformant and world-uniform patterns.
    
    Args:
        count_u, count_v: Grid dimensions
        surface_evaluator: Fusion surface evaluator
        u_bounds, v_bounds: Surface parameter bounds
        spacing_u, spacing_v: World-space spacing in cm
        edge_margin: Edge margin in parametric space
        rotation_degrees: Grid rotation angle
        u_bias, v_bias: Blend factors (0.0=world-uniform, 1.0=UV-conformant)
        pos_u, pos_v: Grid center position (0.0-1.0)
        array_type: 'grid' or 'stagger'
        app: Application reference for logging
    
    Returns:
        List of (u, v) parameter coordinates
    """
    # PIPELINE DEBUG: Log all input parameters
    log(app, f"🔍 PIPELINE ENTRY: array_type='{array_type}', count_u={count_u}, count_v={count_v}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"🔍 PIPELINE ENTRY: edge_margin={edge_margin}cm, u_bias={u_bias:.3f}, v_bias={v_bias:.3f}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN") 
    log(app, f"🔍 PIPELINE ENTRY: pos_u={pos_u:.3f}, pos_v={pos_v:.3f}, rotation={rotation_degrees}°",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    log(app, f"Surface Grid Pipeline: {count_u}×{count_v}, bias=({u_bias}, {v_bias})",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Validate inputs
    if spacing_u is None or spacing_v is None or edge_margin is None or pos_u is None or pos_v is None or array_type is None:
        raise ValueError("Missing required parameters in generate_surface_grid_pipeline")
    
    # Handle special array types with simpler algorithms
    if array_type == 'uv':
        uv_grid = generate_uv_grid(
            count_u, count_v, surface_evaluator, u_bounds, v_bounds,
            u_bias=u_bias, v_bias=v_bias,
            center_u=pos_u, center_v=pos_v, rotation_degrees=rotation_degrees,
            app=app
        )
        # Annotate with row-major grid indices before culling
        annotated = [(u, v, i % count_u, i // count_u) for i, (u, v) in enumerate(uv_grid)]
        return cull_grid_points_to_surface_bounds(
            annotated, u_bounds, v_bounds, surface_evaluator, edge_margin, app
        )

    # Main grid and stagger logic with bias blending
    if array_type == 'grid' or array_type == 'stagger':
        # Generate world-uniform grid (ignores surface parameterization)
        world_grid = generate_uniform_surface_grid(
            count_u, count_v, surface_evaluator, u_bounds, v_bounds,
            spacing_u=spacing_u, spacing_v=spacing_v,
            edge_margin=edge_margin, rotation_degrees=rotation_degrees,
            center_u=pos_u, center_v=pos_v, array_type=array_type,
            stagger_offset=stagger_offset, app=app
        )

        # Generate UV-conformant grid (follows surface flow)
        uv_grid = generate_uv_conformant_grid(
            count_u, count_v, surface_evaluator, u_bounds, v_bounds,
            spacing_u=spacing_u, spacing_v=spacing_v,
            edge_margin=edge_margin, rotation_degrees=rotation_degrees,
            min_pitch_u=spacing_u, min_pitch_v=spacing_v,
            center_u=pos_u, center_v=pos_v, array_type=array_type,
            stagger_offset=stagger_offset, app=app
        )

        # Blend the two grids based on bias values
        blended_grid = blend_grid_points_with_bias(
            world_grid, uv_grid, False, u_bias, v_bias, app
        )

        # Annotate blended grid with row-major (grid_i, grid_j) before culling.
        # Blend preserves row-major order so position i → col=i%count_u, row=i//count_u.
        annotated = [(u, v, i % count_u, i // count_u) for i, (u, v) in enumerate(blended_grid)]
        return cull_grid_points_to_surface_bounds(
            annotated, u_bounds, v_bounds, surface_evaluator, edge_margin, app
        )

    if array_type == 'spiral':
        log(app, "🔴 CRITICAL: Surface Grid Pipeline entering SPIRAL mode", 
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        log(app, f"🔴 CRITICAL: SPIRAL PARAMS - edge_margin={edge_margin}cm, u_bias={u_bias:.3f}", 
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        log(app, f"🔴 CRITICAL: SPIRAL PARAMS - count_u={count_u}, count_v={count_v}, pos_u={pos_u:.3f}, pos_v={pos_v:.3f}", 
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        log(app, "Surface Grid: Spiral mode detected; calling helical generator", 
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        spiral_grid = generate_helical_surface_grid(
            count_u=count_u, count_v=count_v, surface_evaluator=surface_evaluator,
            u_bounds=u_bounds, v_bounds=v_bounds,
            spacing_u=spacing_u, spacing_v=spacing_v,
            edge_margin=edge_margin, rotation_degrees=rotation_degrees,
            center_u=pos_u, center_v=pos_v, u_bias=u_bias, app=app
        )
        
        log(app, f"🔴 CRITICAL: SPIRAL RESULT - Generated {len(spiral_grid)} points", 
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        if len(spiral_grid) > 0:
            log(app, f"🔴 CRITICAL: SPIRAL FIRST POINT - UV=({spiral_grid[0][0]:.6f}, {spiral_grid[0][1]:.6f})", 
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            log(app, f"🔴 CRITICAL: SPIRAL LAST POINT - UV=({spiral_grid[-1][0]:.6f}, {spiral_grid[-1][1]:.6f})", 
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        log(app, f"Surface Grid: Spiral result points={len(spiral_grid)}", 
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Edge margin is now applied during spiral generation, no post-culling needed.
        # Annotate with flat (i, 0) indices — spiral is 1D so column index == position.
        return [(u, v, i, 0) for i, (u, v) in enumerate(spiral_grid)]
    
    log(app, f"Surface Grid: Unsupported array type '{array_type}'", 
        level=LogLevel.WARNING, module="SURFACE_GRID_GEN")
    return []


def generate_uv_grid(
    count_u: int,
    count_v: int,
    surface_evaluator: Any,
    u_bounds: Tuple[float, float],
    v_bounds: Tuple[float, float],
    u_bias: float = 1.0,
    v_bias: float = 1.0,
    center_u: float = 0.5,
    center_v: float = 0.5,
    rotation_degrees: float = 0.0,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Generate simple UV parameter grid with i/(count-1) distribution.
    This creates evenly spaced points in parameter space.
    """
    log(app, f"UV Grid: {count_u}×{count_v}, center=({center_u}, {center_v})",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    
    # Create base grid indices
    u_indices = [i / (count_u - 1) if count_u > 1 else 0.5 for i in range(count_u)]
    v_indices = [j / (count_v - 1) if count_v > 1 else 0.5 for j in range(count_v)]
    
    # Convert to parametric coordinates
    u_coords = [u_min + u * (u_max - u_min) for u in u_indices]
    v_coords = [v_min + v * (v_max - v_min) for v in v_indices]
    
    # Calculate absolute center for rotation
    center_u_abs = u_min + center_u * (u_max - u_min)
    center_v_abs = v_min + center_v * (v_max - v_min)
    
    # Generate grid points
    uv_points = []
    for v in v_coords:
        for u in u_coords:
            uv_points.append((u, v))
    
    # Apply rotation if specified
    if abs(rotation_degrees) > 1e-6:
        uv_points = apply_uv_rotation(uv_points, rotation_degrees, center_u_abs, center_v_abs)
    
    log(app, f"UV Grid: Generated {len(uv_points)} points", level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    return uv_points


def generate_uniform_surface_grid(
    count_u: int,
    count_v: int,
    surface_evaluator: Any,
    u_bounds: Tuple[float, float],
    v_bounds: Tuple[float, float],
    spacing_u: float,
    spacing_v: float,
    edge_margin: float,
    rotation_degrees: float,
    center_u: float,
    center_v: float,
    array_type: str,
    stagger_offset: float = 0.5,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Generate world-uniform grid using the world-stepping algorithm.
    This creates straight world-space lines that create "pixelated" patterns on curved surfaces.
    
    Key: Uses step_uv_by_world_distance with V-then-U walking pattern for accuracy.
    """
    log(app, f"Uniform Grid: {count_u}×{count_v}, spacing=({spacing_u}, {spacing_v})",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    if not surface_evaluator or spacing_u <= 0 or spacing_v <= 0:
        return []
    
    # Import world-space stepping function
    from .surface_math_v2 import step_uv_by_world_distance
    
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    center_u_abs = u_min + center_u * (u_max - u_min)
    center_v_abs = v_min + center_v * (v_max - v_min)
    
    # Apply rotation to step directions  
    rotation_rad = math.radians(rotation_degrees)
    cos_r = math.cos(rotation_rad)
    sin_r = math.sin(rotation_rad)
    
    def calculate_uniform_point(grid_i: int, grid_j: int, is_staggered: bool = False):
        """Calculate uniform grid point using the V-then-U algorithm"""
        # Convert grid indices to centered offsets
        i_offset = grid_i - (count_u - 1) / 2
        j_offset = grid_j - (count_v - 1) / 2
        
        # Apply stagger offset if needed
        if is_staggered and grid_j % 2 == 1:
            i_offset += stagger_offset  # Fraction of a column; odd rows shift by it
        
        # Calculate world-space position using consistent spacing
        world_u_offset = i_offset * spacing_u
        world_v_offset = j_offset * spacing_v
        
        # DEBUG: Log spacing calculations for first few points
        if grid_i < 2 and grid_j < 2:
            log(app, f"DEBUG Point ({grid_i},{grid_j}): i_offset={i_offset:.3f}, j_offset={j_offset:.3f}",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            log(app, f"DEBUG Point ({grid_i},{grid_j}): spacing_u={spacing_u}, spacing_v={spacing_v}",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            log(app, f"DEBUG Point ({grid_i},{grid_j}): world_u_offset={world_u_offset:.3f}, world_v_offset={world_v_offset:.3f}",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Apply rotation
        rotated_u = world_u_offset * cos_r - world_v_offset * sin_r
        rotated_v = world_u_offset * sin_r + world_v_offset * cos_r
        
        # DEBUG: Log rotation results for first few points
        if grid_i < 2 and grid_j < 2:
            log(app, f"DEBUG Point ({grid_i},{grid_j}): rotated_u={rotated_u:.3f}, rotated_v={rotated_v:.3f}",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Step from center in world space
        start_uv = (center_u_abs, center_v_abs)
        
        try:
            # Step in V direction first
            if abs(rotated_v) > 1e-8:
                direction_v_u = 0.0
                direction_v_v = 1.0 if rotated_v > 0 else -1.0
                # DEBUG: Log world stepping parameters
                if grid_i < 2 and grid_j < 2:
                    log(app, f"DEBUG V-step ({grid_i},{grid_j}): distance={abs(rotated_v):.6f}, direction=({direction_v_u},{direction_v_v})",
                        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
                stepped_uv = step_uv_by_world_distance(surface_evaluator, start_uv[0], start_uv[1], direction_v_u, direction_v_v, abs(rotated_v))
                if not stepped_uv:
                    if grid_i < 2 and grid_j < 2:
                        log(app, f"DEBUG V-step ({grid_i},{grid_j}): FAILED - returned None",
                            level=LogLevel.ERROR, module="SURFACE_GRID_GEN")
                    return None  # World stepping failed - no fallback
            else:
                stepped_uv = start_uv
            
            # Then step in U direction from V position
            if abs(rotated_u) > 1e-8:
                direction_u_u = 1.0 if rotated_u > 0 else -1.0
                direction_u_v = 0.0
                # DEBUG: Log U stepping
                if grid_i < 2 and grid_j < 2:
                    log(app, f"DEBUG U-step ({grid_i},{grid_j}): distance={abs(rotated_u):.6f}, direction=({direction_u_u},{direction_u_v})",
                        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
                final_uv = step_uv_by_world_distance(surface_evaluator, stepped_uv[0], stepped_uv[1], direction_u_u, direction_u_v, abs(rotated_u))
                if not final_uv:
                    if grid_i < 2 and grid_j < 2:
                        log(app, f"DEBUG U-step ({grid_i},{grid_j}): FAILED - returned None",
                            level=LogLevel.ERROR, module="SURFACE_GRID_GEN")
                    return None  # World stepping failed - no fallback
            else:
                final_uv = stepped_uv
            
            # Ensure final result is valid
            if final_uv and len(final_uv) == 2 and final_uv[0] is not None and final_uv[1] is not None:
                return final_uv
            else:
                return None  # World stepping failed completely
                
        except Exception as e:
            # Log the real error instead of masking with fallback
            if app:
                log(app, f"World stepping error: {e}", level=LogLevel.ERROR, module="SURFACE_GRID_GEN")
            return None
    
    # Generate grid using standard indexing (V outer, U inner)
    grid_points = []
    is_staggered = (array_type == 'stagger')
    failed_points = 0
    
    for grid_j in range(count_v):  # V rows (outer loop)
        for grid_i in range(count_u):  # U columns (inner loop)
            point = calculate_uniform_point(grid_i, grid_j, is_staggered)
            if point is not None and len(point) == 2 and point[0] is not None and point[1] is not None:
                grid_points.append(point)
            else:
                failed_points += 1
                # Skip failed points - no fallback

    if failed_points > 0:
        log(app, f"Uniform Grid: {failed_points} points FAILED world stepping (no fallbacks)",
            level=LogLevel.ERROR, module="SURFACE_GRID_GEN")
    
    return grid_points


def generate_uv_conformant_grid(
    count_u: int,
    count_v: int,
    surface_evaluator: Any,
    u_bounds: Tuple[float, float],
    v_bounds: Tuple[float, float],
    spacing_u: float,
    spacing_v: float,
    edge_margin: float,
    rotation_degrees: float,
    min_pitch_u: float,
    min_pitch_v: float,
    center_u: float,
    center_v: float,
    array_type: str,
    stagger_offset: float = 0.5,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Generate UV-conformant grid that follows surface parameterization but uses world distances.
    This creates grids that flow with the surface's natural UV layout.
    
    This is the algorithm that creates the "flowy" pattern when bias=1.
    Unlike simple UV subdivision, this still uses world-space distances for consistency.
    """
    log(app, f"UV Conformant Grid: {count_u}×{count_v}, pitch=({min_pitch_u}, {min_pitch_v})",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    if not surface_evaluator or spacing_u <= 0 or spacing_v <= 0:
        return []
    
    # Import world-space functions  
    from .surface_math_v2 import measure_edge_length
    
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    center_u_abs = u_min + center_u * (u_max - u_min)
    center_v_abs = v_min + center_v * (v_max - v_min)
    
    # Fast surface scaling estimation (reduced complexity for performance)
    probe_distance = min(u_max - u_min, v_max - v_min) * 0.1  # Smaller probe for speed
    
    # Simplified measurement approach
    try:
        from .surface_math_v2 import measure_edge_length
        
        u_start = (center_u_abs - probe_distance, center_v_abs)
        u_end = (center_u_abs + probe_distance, center_v_abs)
        v_start = (center_u_abs, center_v_abs - probe_distance)
        v_end = (center_u_abs, center_v_abs + probe_distance)
        
        u_edge_length = measure_edge_length(surface_evaluator, u_start, u_end)
        v_edge_length = measure_edge_length(surface_evaluator, v_start, v_end)
        
        # Quick validation and fallback
        if u_edge_length <= 0 or v_edge_length <= 0 or u_edge_length > 1000 or v_edge_length > 1000:
            # Use parameter-space fallback for performance
            u_uv_step = spacing_u * 0.02  # Reasonable default
            v_uv_step = spacing_v * 0.02
        else:
            # Calculate UV steps for target world spacing
            u_world_per_uv = u_edge_length / (probe_distance * 2)
            v_world_per_uv = v_edge_length / (probe_distance * 2)
            
            u_uv_step = spacing_u / u_world_per_uv if u_world_per_uv > 0 else spacing_u * 0.02
            v_uv_step = spacing_v / v_world_per_uv if v_world_per_uv > 0 else spacing_v * 0.02
    
    except Exception as e:
        log(app, f"UV Conform: Measurement failed ({e}), using fast fallback",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")  # Reduce to DEBUG level
        # Fast fallback
        u_uv_step = spacing_u * 0.02
        v_uv_step = spacing_v * 0.02
    
    log(app, f"UV Conform: world/uv ratios U={u_world_per_uv:.3f}, V={v_world_per_uv:.3f}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Apply rotation to UV step directions
    rotation_rad = math.radians(rotation_degrees)
    cos_r = math.cos(rotation_rad)
    sin_r = math.sin(rotation_rad)
    
    grid_points = []
    is_staggered = (array_type == 'stagger')
    
    # Generate grid using UV-conformant stepping
    for grid_j in range(count_v):  # V rows (outer loop)  
        for grid_i in range(count_u):  # U columns (inner loop)
            # Calculate centered offsets
            i_offset = grid_i - (count_u - 1) / 2
            j_offset = grid_j - (count_v - 1) / 2
            
            # Apply stagger offset if needed
            if is_staggered and grid_j % 2 == 1:
                i_offset += stagger_offset  # Fraction of a column; odd rows shift by it
            
            # Calculate UV offsets using measured spacing
            u_offset = i_offset * u_uv_step
            v_offset = j_offset * v_uv_step
            
            # Apply rotation in UV space
            rotated_u = u_offset * cos_r - v_offset * sin_r
            rotated_v = u_offset * sin_r + v_offset * cos_r
            
            # Final UV coordinates
            final_u = center_u_abs + rotated_u
            final_v = center_v_abs + rotated_v
            
            grid_points.append((final_u, final_v))
    
    log(app, f"UV-conformant grid: {len(grid_points)} points",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    return grid_points


def blend_grid_points_with_bias(
    world_grid: List[Tuple[float, float]],
    uv_grid: List[Tuple[float, float]],
    use_adaptive: bool,
    u_bias: float,
    v_bias: float,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Blend between world-uniform and UV-conformant grid points.
    
    This is a key feature that allows smooth transitions between
    regular world-space patterns and surface-conformant patterns.
    
    Args:
        world_grid: World-uniform grid points
        uv_grid: UV-conformant grid points  
        use_adaptive: Whether to use adaptive blending (not used in surface grid)
        u_bias: Blend factor for U direction (0.0=world, 1.0=UV)
        v_bias: Blend factor for V direction (0.0=world, 1.0=UV)
        app: Application reference for logging
    
    Returns:
        Blended grid points
    """
    log(app, f"Grid Blending: u_bias={u_bias}, v_bias={v_bias}, adaptive={use_adaptive}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    if len(world_grid) != len(uv_grid):
        log(app, f"Grid Blending: Grid size mismatch ({len(world_grid)} vs {len(uv_grid)})",
            level=LogLevel.WARNING, module="SURFACE_GRID_GEN")
        # Return the larger grid
        return world_grid if len(world_grid) > len(uv_grid) else uv_grid
    
    blended_points = []
    for (wu, wv), (uu, uv) in zip(world_grid, uv_grid):
        # Blend U coordinate using u_bias
        blended_u = wu * (1.0 - u_bias) + uu * u_bias
        # Blend V coordinate using v_bias  
        blended_v = wv * (1.0 - v_bias) + uv * v_bias
        blended_points.append((blended_u, blended_v))
    
    log(app, f"Grid Blending: Created {len(blended_points)} blended points",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    return blended_points


def apply_uv_rotation(
    uv_points: List[Tuple[float, float]],
    rotation_degrees: float,
    center_u: float,
    center_v: float
) -> List[Tuple[float, float]]:
    """Apply rotation to UV points around a center point."""
    cos_r = math.cos(math.radians(rotation_degrees))
    sin_r = math.sin(math.radians(rotation_degrees))
    
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


def cull_grid_points_to_surface_bounds(
    grid_points: List[Tuple[float, float]],
    u_bounds: Tuple[float, float],
    v_bounds: Tuple[float, float],
    surface_evaluator: Any,
    edge_margin: float,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Remove grid points that fall outside surface bounds with edge margin.
    Enhanced to properly handle edge margins and prevent over-building.
    """
    if not grid_points:
        return grid_points
    
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    
    # Apply margin to bounds (edge_margin is in parametric space)
    margin_u = (u_max - u_min) * edge_margin
    margin_v = (v_max - v_min) * edge_margin
    
    # Create inset bounds
    safe_u_min = u_min + margin_u
    safe_u_max = u_max - margin_u
    safe_v_min = v_min + margin_v
    safe_v_max = v_max - margin_v
    
    # Filter points within safe bounds.
    # Tuples may be (u, v) or (u, v, grid_i, grid_j) — preserve extra elements.
    culled_points = []
    for point in grid_points:
        u, v = point[0], point[1]
        # Check if point is within safe parametric bounds
        if (safe_u_min <= u <= safe_u_max and safe_v_min <= v <= safe_v_max):
            # Additional check: ensure point is actually on surface
            try:
                if surface_evaluator:
                    # Quick validation that surface evaluation works at this point
                    try:
                        import adsk.core
                        point_3d = surface_evaluator.pointAtParameter(adsk.core.Point2D(u, v))
                        if point_3d:
                            culled_points.append(point)
                    except Exception:
                        # If adsk not available or evaluation fails, still include point
                        culled_points.append(point)
                else:
                    culled_points.append(point)  # No evaluator, assume valid
            except Exception:
                # Skip points that cause evaluation errors
                continue
    
    removed_count = len(grid_points) - len(culled_points)
    if removed_count > 0:
        log(app, f"Edge margin culling: removed {removed_count} points outside bounds",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    return culled_points


def generate_helical_surface_grid(
    count_u: int,
    count_v: int,
    surface_evaluator: Any,
    u_bounds: Tuple[float, float],
    v_bounds: Tuple[float, float],
    spacing_u: float = 1.0,
    spacing_v: float = 1.0,
    edge_margin: float = 0.0,
    rotation_degrees: float = 45.0,
    center_u: float = 0.5,
    center_v: float = 0.5,
    u_bias: float = 1.0,
    app: Any = None
) -> List[Tuple[float, float]]:
    """
    Generate helical spiral grids on surfaces with dual density/spacing modes.
    
    Creates proper spiral arrays on surfaces, particularly optimized for
    revolved objects.
    
    Parameters:
    - count_u: UI "Count U" → POINTS PER STRAND (density along U/axial direction)
    - count_v: UI "Count V" → NUMBER OF STRANDS (distribution around V/angular direction)  
    - rotation_degrees: Incline angle (0°=flat disc, 45°=balanced, 90°=vertical thread)
    - u_bias: 1.0 = UV conformant, 0.0 = world uniform
    
    Coordinate System: U=axial (0-1), V=angular (0-2π radians)
    """
    # CRITICAL ENTRY CHECKPOINT
    log(app, "🔴 CRITICAL: HELICAL GRID ENTRY", level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"🔴 CRITICAL: edge_margin={edge_margin}cm, u_bias={u_bias:.3f}", level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"🔴 CRITICAL: u_bounds=({u_bounds[0]:.6f}, {u_bounds[1]:.6f}), v_bounds=({v_bounds[0]:.6f}, {v_bounds[1]:.6f})", level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    if not surface_evaluator:
        return []
    
    log(app, f"Helical Grid: Starting with count_u={count_u}, count_v={count_v}, rotation={rotation_degrees}°",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Import surface math for evaluations
    from .surface_math_v2 import evaluate_surface_point, step_uv_by_world_distance
    
    # Basic setup
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    
    # Convert center from 0-1 to absolute UV space
    center_u_abs = u_min + center_u * (u_max - u_min)
    center_v_abs = v_min + center_v * (v_max - v_min)
    
    # HELICAL PARAMETER MAPPING: 
    # For helical spirals, use this mapping:
    # UI "Count U" → points per strand (U progression)
    # UI "Count V" → number of strands (V distribution)
    points_per_strand = count_u    # Density along U axis
    num_strands = count_v          # Strands around V axis
    
    if num_strands <= 0 or points_per_strand <= 0:
        log(app, f"Helical Grid: Invalid parameters - num_strands={num_strands}, points_per_strand={points_per_strand}",
            level=LogLevel.ERROR, module="SURFACE_GRID_GEN")
        return []
    
    log(app, f"Helical Grid: {points_per_strand} points per strand, {num_strands} strands",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Calculate helical parameters with special handling for revolved surfaces
    incline_rad = math.radians(rotation_degrees)
    rise_factor = math.tan(incline_rad) if abs(incline_rad) < math.pi/2 else 1000
    u_range = u_max - u_min
    v_range = v_max - v_min
    
    # Detect revolved surfaces: V range ≈ 2π indicates full revolution
    is_revolved = abs(v_range - 2 * math.pi) < 0.1
    
    # Apply edge margin in world space for U axis (longitudinal/height)
    effective_u_min = u_min
    effective_u_max = u_max
    
    log(app, f"DEBUG EDGE MARGIN: Input edge_margin={edge_margin}cm, original U bounds=[{u_min:.6f}, {u_max:.6f}]",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    if edge_margin != 0.0:
        log(app, f"Helical Grid: Applying edge margin {edge_margin}cm along U axis",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Calculate world-space length along U axis to convert cm to U units
        # Sample points at center V to measure U axis world length
        u_sample_points = 10
        u_world_distance = 0.0
        valid_measurements = 0
        
        for i in range(1, u_sample_points):
            u_curr = u_min + (i / (u_sample_points - 1)) * u_range
            u_prev = u_min + ((i-1) / (u_sample_points - 1)) * u_range
            
            # FIXED: Unpack the tuple returned by evaluate_surface_point
            pt_curr_result = evaluate_surface_point(surface_evaluator, u_curr, center_v_abs)
            pt_prev_result = evaluate_surface_point(surface_evaluator, u_prev, center_v_abs)
            
            # Extract just the position (first element) from the (position, normal) tuple
            pt_curr = pt_curr_result[0] if pt_curr_result and pt_curr_result[0] else None
            pt_prev = pt_prev_result[0] if pt_prev_result and pt_prev_result[0] else None
            
            # DEBUG: Log the first few evaluations to verify the fix
            if i <= 2:
                log(app, f"🟢 SURFACE FIX: i={i}, pt_curr={pt_curr}, pt_prev={pt_prev}",
                    level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            
            if pt_curr and pt_prev:
                segment_distance = distance(pt_curr, pt_prev)
                if segment_distance is not None and segment_distance > 0:
                    u_world_distance += segment_distance
                    valid_measurements += 1
                    
                    # DEBUG: Log successful measurements
                    if i <= 2:
                        log(app, f"🟢 SURFACE FIX: Measured segment {i}: {segment_distance:.6f}cm",
                            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        if u_world_distance > 0 and valid_measurements > 0:
            # Convert edge margin from cm to U parameter units
            u_units_per_cm = u_range / u_world_distance
            edge_margin_u_units = edge_margin * u_units_per_cm
            
            # Apply margin (positive values inset, negative values expand)
            effective_u_min = u_min + edge_margin_u_units
            effective_u_max = u_max - edge_margin_u_units
            
            log(app, f"🔴 CRITICAL: EDGE MARGIN APPLIED - {edge_margin}cm = {edge_margin_u_units:.6f} U units",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            log(app, f"🔴 CRITICAL: BOUNDS CHANGE - original=[{u_min:.6f}, {u_max:.6f}] -> effective=[{effective_u_min:.6f}, {effective_u_max:.6f}]",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            
            log(app, f"DEBUG EDGE MARGIN: U world length = {u_world_distance:.3f}cm ({valid_measurements} valid segments), margin = {edge_margin_u_units:.6f} U units",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            log(app, f"DEBUG EDGE MARGIN: Effective U bounds [{effective_u_min:.6f}, {effective_u_max:.6f}] (was [{u_min:.6f}, {u_max:.6f}])",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        else:
            log(app, f"DEBUG EDGE MARGIN: Could not measure U axis world length ({valid_measurements} valid measurements), ignoring edge margin",
                level=LogLevel.WARNING, module="SURFACE_GRID_GEN")
    
    # Update bounds for strand generation
    effective_u_bounds = (effective_u_min, effective_u_max)
    
    log(app, f"Helical Grid: rise_factor={rise_factor:.3f}, u_range={u_range:.3f}, v_range={v_range:.3f}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"Helical Grid: Detected {'revolved' if is_revolved else 'generic'} surface (v_range={'~2π' if is_revolved else f'{v_range:.3f}'})",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # STAGE 1: Generate master strand template using helical mathematics
    log(app, f"Helical Grid: Generating master strand with effective U bounds [{effective_u_min:.6f}, {effective_u_max:.6f}]", 
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Convert u_bias to uniformity: u_bias=1.0 means UV-conformant (uniformity=0.0), u_bias=0.0 means world-uniform (uniformity=1.0)
    uniformity = 1.0 - u_bias
    log(app, f"DEBUG U_BIAS: Input u_bias={u_bias:.3f} -> uniformity={uniformity:.3f}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"DEBUG U_BIAS: u_bias=0.0 means world-uniform, u_bias=1.0 means UV-conformant",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
    raw_master_strand = generate_helical_strand_revolved(
        center_u_abs, center_v_abs, effective_u_bounds, v_bounds,
        points_per_strand, rise_factor, rotation_degrees, u_bias,  # FIXED: Pass u_bias instead of uniformity
        is_revolved, surface_evaluator, app
    )
    
    log(app, f"🔴 CRITICAL: MASTER STRAND RESULT - Generated {len(raw_master_strand) if raw_master_strand else 0} points",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    if raw_master_strand and len(raw_master_strand) > 0:
        log(app, f"🔴 CRITICAL: MASTER STRAND FIRST POINT - UV=({raw_master_strand[0][0]:.6f}, {raw_master_strand[0][1]:.6f})",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        log(app, f"🔴 CRITICAL: MASTER STRAND LAST POINT - UV=({raw_master_strand[-1][0]:.6f}, {raw_master_strand[-1][1]:.6f})",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    if not raw_master_strand:
        log(app, "Helical Grid: Failed to generate master strand", level=LogLevel.ERROR, module="SURFACE_GRID_GEN")
        return []
        
    log(app, f"Helical Grid: Generated master strand with {len(raw_master_strand)} points",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # STAGE 2: Multi-strand distribution via angular V offsets
    log(app, f"Helical Grid: Distributing {num_strands} strands via angular V offsets",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    all_final_points = []
    for strand_idx in range(num_strands):
        # Perfect angular distribution: V offsets evenly across 2π radians
        v_offset_radians = strand_idx * (2 * math.pi / num_strands)
        
        log(app, f"Helical Grid: Strand {strand_idx+1}/{num_strands} V_offset={v_offset_radians:.3f} rad",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Clone master strand with V offset for angular distribution
        for u, v in raw_master_strand:
            # Apply V offset for angular distribution (allows V > 2π for seam crossing)
            offset_v = v + v_offset_radians
            all_final_points.append((u, offset_v))
    
    log(app, f"Helical Grid: Generated {len(all_final_points)} total points from {num_strands} strands",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    return all_final_points


def generate_helical_strand_simple(
    center_u_abs: float, 
    center_v_abs: float, 
    u_bounds: Tuple[float, float], 
    v_bounds: Tuple[float, float],
    count_v: int,
    rise_factor: float, 
    rotation_degrees: float, 
    uniformity: float, 
    surface_evaluator: Any,
    app: Any
) -> List[Tuple[float, float]]:
    """
    Generate fixed number of points along one helical strand.
    
    This is the core helical mathematics for spiral generation.
    """
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds
    
    # STAGE 1: Generate UV helical path (may have uneven world spacing)
    uv_path = []
    
    # Calculate helical parameters based on angle and full V coverage
    u_range = u_max - u_min
    v_range = v_max - v_min
    
    # Calculate turns per strand based directly on angle
    # Simple rule: 45° = 1 turn, other angles scale proportionally
    turns_per_strand = math.tan(math.radians(rotation_degrees))
    
    # Calculate v_advance_per_u to ensure full U coverage (swapped roles)
    # We want the spiral to cover the full U range regardless of angle
    if turns_per_strand > 0 and v_range > 0:
        v_advance_per_u = u_range / (turns_per_strand * v_range)
    else:
        v_advance_per_u = 0.0  # Fallback for degenerate cases
    
    log(app, f"Helical Strand: rotation={rotation_degrees}°, turns_per_strand={turns_per_strand:.6f}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"Helical Strand: u_range={u_range:.6f}, v_range={v_range:.6f}, v_advance_per_u={v_advance_per_u:.6f}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Generate dense UV path first (more points than needed)
    dense_count = count_v * 3  # Generate 3x points for smooth path
    for point_idx in range(dense_count):
        # Ensure the last point reaches exactly turns_per_strand revolutions
        if point_idx == dense_count - 1:
            t = 1.0  # Force exact end
        else:
            t = point_idx / max(dense_count - 1, 1)
        
        # HELICAL PATH in UV space (SWAPPED U/V ROLES):
        # 1. Revolution progression (starts from strand's center_v)
        revolutions = t * turns_per_strand  # 0 to turns_per_strand
        
        # 2. V parameter: start from this strand's center_v and advance (wraps around)
        v_param = center_v_abs + revolutions * (v_max - v_min)
        
        # 3. U parameter: UV-based incline (goes up/down the surface)
        v_advance = revolutions * v_range  # Use revolution count for U calculation
        u_rise = v_advance * v_advance_per_u  # Use pre-calculated v_advance_per_u
        u_param = center_u_abs + u_rise
        
        # Allow V extrapolation for proper helical behavior (V wrapping is handled elsewhere)
        uv_path.append((u_param, v_param))
    
    log(app, f"Helical Strand: Generated {len(uv_path)} UV path points", level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # STAGE 2: Apply uniformity compensation for world-space uniform distribution
    if uniformity > 0.0 and len(uv_path) > 1:
        log(app, f"Helical Strand: Applying uniformity compensation (factor={uniformity:.3f})",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Import surface math for world-space calculations
        from .surface_math_v2 import evaluate_surface_point
        
        # Build world-distance lookup along the entire spiral path
        spiral_world_distances = [0.0]  # Start at 0
        spiral_world_points = []
        
        for i, (u, v) in enumerate(uv_path):
            try:
                world_pt, _ = evaluate_surface_point(surface_evaluator, u, v)
                spiral_world_points.append(world_pt)
                
                if i > 0:
                    # Calculate distance from previous point
                    prev_pt = spiral_world_points[i-1]
                    distance = math.sqrt(
                        (world_pt[0] - prev_pt[0])**2 +
                        (world_pt[1] - prev_pt[1])**2 +
                        (world_pt[2] - prev_pt[2])**2
                    )
                    spiral_world_distances.append(spiral_world_distances[-1] + distance)
                    
            except Exception as e:
                log(app, f"Helical Strand: Surface evaluation failed at ({u:.3f}, {v:.3f}): {e}",
                    level=LogLevel.WARNING, module="SURFACE_GRID_GEN")
                # Use UV path as fallback
                break
        
        # If we successfully built world distances, resample uniformly
        if len(spiral_world_distances) == len(uv_path):
            total_world_length = spiral_world_distances[-1]
            uniform_path = []
            
            for target_idx in range(count_v):
                target_distance = (target_idx / max(count_v - 1, 1)) * total_world_length
                
                # Find closest points in spiral_world_distances
                for j in range(len(spiral_world_distances) - 1):
                    if spiral_world_distances[j] <= target_distance <= spiral_world_distances[j + 1]:
                        # Linear interpolation between j and j+1
                        t_local = (target_distance - spiral_world_distances[j]) / max(spiral_world_distances[j + 1] - spiral_world_distances[j], 0.001)
                        
                        u_interp = uv_path[j][0] + t_local * (uv_path[j + 1][0] - uv_path[j][0])
                        v_interp = uv_path[j][1] + t_local * (uv_path[j + 1][1] - uv_path[j][1])
                        
                        uniform_path.append((u_interp, v_interp))
                        break
            
            # Blend between UV path and uniform path based on uniformity
            final_path = []
            for i in range(min(len(uv_path[:count_v]), len(uniform_path))):
                uv_point = uv_path[i] if i < len(uv_path) else uv_path[-1]
                uniform_point = uniform_path[i]
                
                # Blend: uniformity=0 → UV path, uniformity=1 → uniform path
                blended_u = uv_point[0] * (1 - uniformity) + uniform_point[0] * uniformity
                blended_v = uv_point[1] * (1 - uniformity) + uniform_point[1] * uniformity
                
                final_path.append((blended_u, blended_v))
            
            log(app, f"Helical Strand: Applied uniformity blending, final path has {len(final_path)} points",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            return final_path
    
    # Fallback: Just take the first count_v points from UV path
    return uv_path[:count_v]


def generate_spiral_world_uniform_distribution(
    uv_path: List[Tuple[float, float]], 
    surface_evaluator: Any, 
    app: Any
) -> List[Tuple[float, float]]:
    """
    Generate world-uniform U distribution for spirals while preserving V structure.
    
    This creates a new spiral path where:
    - V coordinates follow the same progression (preserving helical structure)
    - U coordinates are redistributed for uniform world-space spacing along the strand
    
    Args:
        uv_path: Original UV path with UV-conformant distribution
        surface_evaluator: Fusion surface evaluator
        app: Application for logging
    
    Returns:
        New UV path with world-uniform U distribution
    """
    if len(uv_path) < 2:
        return uv_path
    
    # Import utilities
    from .surface_math_v2 import evaluate_surface_point
    
    # STEP 1: Measure total world length along the original spiral path
    world_distances = [0.0]
    total_distance = 0.0
    
    for i in range(1, len(uv_path)):
        prev_u, prev_v = uv_path[i-1]
        curr_u, curr_v = uv_path[i]
        
        # Get world points
        prev_result = evaluate_surface_point(surface_evaluator, prev_u, prev_v)
        curr_result = evaluate_surface_point(surface_evaluator, curr_u, curr_v)
        
        if prev_result and curr_result and prev_result[0] and curr_result[0]:
            prev_pt = prev_result[0]
            curr_pt = curr_result[0]
            
            segment_dist = distance(prev_pt, curr_pt)
            if segment_dist and segment_dist > 0:
                total_distance += segment_dist
        
        world_distances.append(total_distance)
    
    if total_distance <= 0:
        log(app, "Spiral Uniform: Could not measure world distance, returning original",
            level=LogLevel.WARNING, module="SURFACE_GRID_GEN")
        return uv_path
    
    log(app, f"Spiral Uniform: Measured total distance = {total_distance:.3f}cm",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # STEP 2: Create new U distribution for uniform world spacing
    uniform_path = []
    
    for i, (orig_u, orig_v) in enumerate(uv_path):
        # Target uniform world distance
        if len(uv_path) == 1:
            target_distance = total_distance * 0.5
        else:
            target_distance = (i / (len(uv_path) - 1)) * total_distance
        
        # Find the U coordinate that gives us this world distance
        # Use the V coordinate from the original path to maintain helical structure
        target_u = find_u_for_world_distance(uv_path, world_distances, target_distance)
        
        # Keep original V, use adjusted U for uniform spacing
        uniform_path.append((target_u, orig_v))
    
    return uniform_path


def find_u_for_world_distance(
    uv_path: List[Tuple[float, float]], 
    world_distances: List[float], 
    target_distance: float
) -> float:
    """
    Find the U coordinate that corresponds to a target world distance along the path.
    Uses interpolation for smooth results.
    """
    if not world_distances or len(world_distances) != len(uv_path):
        return uv_path[0][0] if uv_path else 0.0
    
    # Handle edge cases
    if target_distance <= 0:
        return uv_path[0][0]
    if target_distance >= world_distances[-1]:
        return uv_path[-1][0]
    
    # Find the segment that contains our target distance
    for i in range(1, len(world_distances)):
        if world_distances[i] >= target_distance:
            # Interpolate between points i-1 and i
            prev_dist = world_distances[i-1]
            curr_dist = world_distances[i]
            prev_u = uv_path[i-1][0]
            curr_u = uv_path[i][0]
            
            # Linear interpolation
            if curr_dist > prev_dist:
                t = (target_distance - prev_dist) / (curr_dist - prev_dist)
                return prev_u + t * (curr_u - prev_u)
            else:
                return prev_u
    
    return uv_path[-1][0]


def generate_helical_strand_revolved(
    center_u_abs: float, 
    center_v_abs: float, 
    effective_u_bounds: Tuple[float, float],  # Changed from u_bounds to match call
    v_bounds: Tuple[float, float],
    count_v: int,
    rise_factor: float, 
    rotation_degrees: float, 
    u_bias: float,  # Changed from uniformity to match bias terminology
    is_revolved: bool,
    surface_evaluator: Any,
    app: Any
) -> List[Tuple[float, float]]:
    """
    Generate helical strand with proper density normalization for revolved surfaces.
    
    For revolved surfaces (V ≈ 2π), this ensures that:
    1. Density is evenly distributed along the U parameter (height)
    2. V parameter is calculated based on tilt angle and U position
    3. Spiral makes proper helical progression around the surface
    4. Edge margin is applied in world space along U axis
    5. Uniformity uses world-walking for even world-space distribution along U
    """
    # FIXED: Properly unpack the effective bounds
    effective_u_min, effective_u_max = effective_u_bounds
    v_min, v_max = v_bounds
    effective_u_range = effective_u_max - effective_u_min
    v_range = v_max - v_min
    
    # FIXED: Convert u_bias to uniformity for internal calculations
    uniformity = 1.0 - u_bias  # u_bias=1.0 -> uniformity=0.0 (UV-conformant), u_bias=0.0 -> uniformity=1.0 (world-uniform)
    
    log(app, f"Helical Strand (Revolved): Generating {count_v} points with {rotation_degrees}° tilt",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"Helical Strand: Using effective U bounds [{effective_u_min:.6f}, {effective_u_max:.6f}] (range={effective_u_range:.6f})",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    log(app, f"Helical Strand: Parameters - u_bias={u_bias:.3f} -> uniformity={uniformity:.3f}, is_revolved={is_revolved}",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    uv_path = []
    
    if is_revolved:
        # REVOLVED SURFACE LOGIC: V ≈ 2π, normalize density along U (height)
        log(app, f"Helical Strand: Using revolved surface logic (V range = {v_range:.3f} ≈ 2π)",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Calculate spiral parameters for revolved surfaces
        # For tilt angle, determine how many radians of V advance per unit of U
        tilt_rad = math.radians(rotation_degrees)
        
        # Use effective U range with edge margin applied
        effective_u_range = effective_u_max - effective_u_min
        
        log(app, f"DEBUG EDGE MARGIN: CRITICAL - Using effective_u_range={effective_u_range:.6f} (was {effective_u_max-effective_u_min:.6f})",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # V advance per U unit based on tilt: steeper tilt = more V advance per U 
        if abs(tilt_rad) < math.pi/2:
            v_advance_per_u = math.tan(tilt_rad) * (2 * math.pi) / effective_u_range
        else:
            v_advance_per_u = 10.0  # Very steep spiral
            
        log(app, f"Helical Strand: effective_u_range={effective_u_range:.6f}, v_advance_per_u = {v_advance_per_u:.6f} rad/u_unit",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Generate points evenly distributed in U (height), with V calculated from tilt
        for point_idx in range(count_v):
            # Even distribution along U parameter (height normalization)
            if count_v == 1:
                t = 0.5  # Single point at center
            else:
                t = point_idx / (count_v - 1)  # 0 to 1
            
            # U parameter: evenly distributed within effective bounds (edge margin applied)
            u_param = effective_u_min + t * effective_u_range
            
            # DEBUG: Log first few points to verify edge margin is applied
            if point_idx < 3:
                log(app, f"🔴 CRITICAL: STRAND POINT {point_idx}: t={t:.3f}, u_param={u_param:.6f} (range=[{effective_u_min:.6f}, {effective_u_max:.6f}])",
                    level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            
            # V parameter: calculated from U position and tilt angle
            # Start from center_v and advance based on U position relative to center
            u_offset_from_center = u_param - center_u_abs
            v_advance = u_offset_from_center * v_advance_per_u
            v_param = center_v_abs + v_advance
            
            # Allow V to exceed bounds for proper helical wrapping
            uv_path.append((u_param, v_param))
            
        log(app, f"Helical Strand: Generated {len(uv_path)} points with even U distribution (edge margin applied)",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            
    else:
        # GENERIC SURFACE LOGIC: Fall back to original algorithm
        log(app, f"Helical Strand: Using generic surface logic (V range = {v_range:.3f})",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            
        # Use original algorithm for non-revolved surfaces
        return generate_helical_strand_simple(
            center_u_abs, center_v_abs, u_bounds, v_bounds,
            count_v, rise_factor, rotation_degrees, uniformity, surface_evaluator, app
        )
    
    # STAGE 2: Apply spiral-specific uniformity blending
    if uniformity > 0.0 and len(uv_path) > 1:
        log(app, f"DEBUG U_BIAS: Applying spiral-specific uniformity blending (u_bias={u_bias:.3f}, uniformity={uniformity:.3f})",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        
        # Generate world-uniform distribution while preserving spiral structure
        world_uniform_path = generate_spiral_world_uniform_distribution(uv_path, surface_evaluator, app)
        
        if world_uniform_path and len(world_uniform_path) == len(uv_path):
            # Blend between UV-conformant (bias=1) and world-uniform (bias=0)
            final_path = []
            for i in range(len(uv_path)):
                uv_point = uv_path[i]  # UV-conformant (bias=1)
                uniform_point = world_uniform_path[i]  # World-uniform (bias=0)
                
                # CRITICAL: Only blend U coordinates, preserve V structure
                # This maintains the helical flow while adjusting spacing
                blended_u = uv_point[0] * (1 - uniformity) + uniform_point[0] * uniformity
                blended_v = uv_point[1]  # Always use UV-conformant V (preserves helix)
                
                final_path.append((blended_u, blended_v))
                
                # DEBUG: Log first few blended points
                if i < 3:
                    log(app, f"🟡 SPIRAL BLEND: Point {i}: UV_u={uv_point[0]:.6f} + uniform_u={uniform_point[0]:.6f} -> blended_u={blended_u:.6f} (V={blended_v:.6f})",
                        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            
            log(app, f"DEBUG U_BIAS: Applied spiral uniformity blending - {len(final_path)} points with preserved helix",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
            return final_path
        else:
            log(app, f"DEBUG U_BIAS: Could not generate world-uniform distribution, using UV-conformant",
                level=LogLevel.WARNING, module="SURFACE_GRID_GEN")
    else:
        if uniformity <= 0.0:
            log(app, f"DEBUG U_BIAS: u_bias={u_bias:.3f} -> using pure UV-conformant distribution",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
        else:
            log(app, f"DEBUG U_BIAS: Path too short ({len(uv_path)} points), using UV-conformant",
                level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    
    # Return UV path (with or without uniformity compensation)
    log(app, f"DEBUG FINAL: Returning {len(uv_path)} points. First few points:",
        level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    for i in range(min(3, len(uv_path))):
        log(app, f"  Point {i}: U={uv_path[i][0]:.6f}, V={uv_path[i][1]:.6f}",
            level=LogLevel.DEBUG, module="SURFACE_GRID_GEN")
    return uv_path