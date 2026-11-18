"""
Surface placement utilities for converting 2D patterns to 3D surface instances.

This module provides functions to take abstract 2D patterns (from array generators)
and place them on surfaces with proper alignment and transformation.

Key functions:
- create_surface_instances_with_alignment: Create surface-aligned instances from UV points
"""

from typing import List, Tuple, Any

# Fusion 360 imports
try:
    import adsk.core  # type: ignore
    import adsk.fusion  # type: ignore
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False

# Import surface utilities
from .surface_math_v2 import create_surface_instances_with_uv_alignment

# Logging setup
LOG_MODULE = 'SURFACE_PLACEMENT_UTILS'

from .log_utils import log, LogLevel

if FUSION_AVAILABLE:
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
else:
    app = None
    ui = None

if app:
    log(app, f'Module {LOG_MODULE} imported', level=LogLevel.DEBUG, module=LOG_MODULE)


def create_surface_instances_with_alignment(
    surface_evaluator: Any,
    uv_points: List[Tuple[float, float]],
    rotation_degrees: float = 0.0,
    align_to_normal: bool = True,
    app: Any = None
) -> List[Any]:
    """
    Create surface instances with proper alignment - convenience wrapper.
    
    This is a compatibility function that wraps the surface_math_v2 function
    with a simpler interface for array nodes.
    
    Args:
        surface_evaluator: Fusion surface evaluator
        uv_points: List of (u, v) parameter coordinates  
        rotation_degrees: Additional rotation in degrees
        align_to_normal: Whether to align instances to surface normal
        app: Application reference for logging
        
    Returns:
        List of transformation matrices
    """
    return create_surface_instances_with_uv_alignment(
        surface_evaluator=surface_evaluator,
        uv_points=uv_points,
        rotation_degrees=rotation_degrees,
        align_to_normal=align_to_normal
    )