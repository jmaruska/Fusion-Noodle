"""
Surface utilities for nodes - surface evaluation, bounds, and UV operations.
"""

from typing import List, Tuple, Optional, Any
import math
from .log_utils import log, LogLevel

try:
    import adsk.core
    import adsk.fusion
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


def get_surface_bounds(surface_face: Any) -> Tuple[float, float, float, float]:
    """Get UV parameter bounds for a surface face."""
    if not FUSION_AVAILABLE or not surface_face:
        return (0.0, 1.0, 0.0, 1.0)
    
    try:
        evaluator = surface_face.evaluator
        u_min, u_max = evaluator.parametricRange().minPoint.x, evaluator.parametricRange().maxPoint.x
        v_min, v_max = evaluator.parametricRange().minPoint.y, evaluator.parametricRange().maxPoint.y
        return (u_min, u_max, v_min, v_max)
    except Exception:
        return (0.0, 1.0, 0.0, 1.0)


def resolve_surface_face(surface_data: Any, app: Any = None) -> Optional[Any]:
    """Resolve surface face from various surface data formats."""
    if not FUSION_AVAILABLE:
        return None
        
    try:
        # Direct surface face object
        if hasattr(surface_data, 'geometry') or hasattr(surface_data, 'evaluator'):
            return surface_data
            
        # None case
        if surface_data is None:
            return None
            
        # Dictionary with entity_token (selection-based)
        if isinstance(surface_data, dict) and 'entity_token' in surface_data:
            try:
                if not app:
                    app = adsk.core.Application.get()
                design = adsk.fusion.Design.cast(app.activeProduct)
                if not design:
                    return None
                    
                # Preferred: persistent entityToken captured at selection time
                face_token = surface_data.get('face_token')
                if face_token:
                    try:
                        found = design.findEntityByToken(face_token)
                        if found and len(found) > 0:
                            face = adsk.fusion.BRepFace.cast(found[0])
                            if face:
                                return face
                    except Exception:
                        pass  # Fall through to the tempId lookup

                # Legacy graphs: tempId is only unique within a body, so restrict the
                # search to the selected body when its name was captured.
                entity_token = surface_data['entity_token']
                body_name = surface_data.get('body_name')
                component_name = surface_data.get('component_name')
                fallback = None
                for comp in design.allComponents:
                    for body in comp.bRepBodies:
                        for face in body.faces:
                            if face.tempId == entity_token:
                                if body_name and body.name == body_name and \
                                        (not component_name or comp.name == component_name):
                                    return face
                                if fallback is None:
                                    fallback = face
                return fallback
            except Exception as e:
                if app:
                    log(app, f"Failed to resolve surface by entity_token: {e}", 
                        level=LogLevel.ERROR, module="SURFACE_UTILS")
                return None
                
        return None
        
    except Exception as e:
        if app:
            log(app, f"Error resolving surface face: {e}", 
                level=LogLevel.ERROR, module="SURFACE_UTILS")
        return None


def resolve_surface_entity(surface_data: Any, app: Any = None) -> Optional[Any]:
    """
    Resolve surface entity from surface data - alias for resolve_surface_face.
    
    This provides compatibility with the node interface naming.
    """
    return resolve_surface_face(surface_data, app)


def evaluate_surface_point(surface_evaluator: Any, u: float, v: float) -> Tuple[Optional[Any], Optional[Any]]:
    """Evaluate surface at UV coordinates to get point and normal."""
    if not FUSION_AVAILABLE or not surface_evaluator:
        return (None, None)
    
    try:
        point2d = adsk.core.Point2D.create(u, v)
        result = surface_evaluator.getPointAtParameter(point2d)
        
        if result[0]:  # success
            point3d = result[1]
            # Get normal at this point
            normal_result = surface_evaluator.getNormalAtParameter(point2d)
            normal = normal_result[1] if normal_result[0] else None
            return (point3d, normal)
        else:
            return (None, None)
    except Exception:
        return (None, None)

def margin_in_parameters(margin_cm: float, point_at, u_bounds: Tuple[float, float],
                         v_bounds: Tuple[float, float], samples: int = 24) -> Tuple[float, float]:
    """How far a margin of `margin_cm` reaches in U and in V parameter units.

    `point_at(u, v)` returns the world point (x, y, z) at those parameters, or
    None. The surface's real length is measured along three lines in each
    direction and averaged, so a surface that is stretched in its parameters
    still gets a margin of the right size in cm. Pure Python, so it can be
    tested outside Fusion.
    """
    if margin_cm <= 0:
        return 0.0, 0.0
    u_min, u_max = u_bounds
    v_min, v_max = v_bounds

    def length_along(fixed_values, along_u):
        lengths = []
        for fixed in fixed_values:
            previous, total, ok = None, 0.0, True
            for k in range(samples + 1):
                t = k / samples
                if along_u:
                    point = point_at(u_min + t * (u_max - u_min), fixed)
                else:
                    point = point_at(fixed, v_min + t * (v_max - v_min))
                if point is None:
                    ok = False
                    break
                if previous is not None:
                    total += math.dist(previous, point)
                previous = point
            if ok and total > 1e-9:
                lengths.append(total)
        return sum(lengths) / len(lengths) if lengths else None

    thirds = (0.25, 0.5, 0.75)
    u_length = length_along([v_min + f * (v_max - v_min) for f in thirds], along_u=True)
    v_length = length_along([u_min + f * (u_max - u_min) for f in thirds], along_u=False)
    du = margin_cm * (u_max - u_min) / u_length if u_length else 0.0
    dv = margin_cm * (v_max - v_min) / v_length if v_length else 0.0
    return du, dv


def inset_bounds_by_margin(surface_evaluator: Any, u_min: float, u_max: float,
                           v_min: float, v_max: float, margin_cm: float,
                           app: Any = None) -> Tuple[float, float, float, float]:
    """Surface bounds shrunk by an Edge Margin given in cm.

    A margin too large for the surface is limited so a sliver of the surface
    in the middle remains, and a warning says so.
    """
    if margin_cm <= 0 or not surface_evaluator:
        return u_min, u_max, v_min, v_max

    def point_at(u, v):
        point, _ = evaluate_surface_point(surface_evaluator, u, v)
        return (point.x, point.y, point.z) if point else None

    du, dv = margin_in_parameters(margin_cm, point_at, (u_min, u_max), (v_min, v_max))
    limit_u, limit_v = 0.45 * (u_max - u_min), 0.45 * (v_max - v_min)
    if du > limit_u or dv > limit_v:
        log(app, f"Edge Margin of {margin_cm:g} cm is larger than the surface allows; using the largest margin that fits",
            level=LogLevel.WARNING, module="SURFACE_UTILS")
        du, dv = min(du, limit_u), min(dv, limit_v)
    return u_min + du, u_max - du, v_min + dv, v_max - dv

