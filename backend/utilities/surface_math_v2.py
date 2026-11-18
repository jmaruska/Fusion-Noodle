"""
Surface mathematics utilities - surface evaluation, world-space walking, and alignment.
"""

import math
from typing import List, Tuple, Any, Optional
from .log_utils import log, LogLevel

try:
    import adsk.core  # type: ignore
    import adsk.fusion  # type: ignore
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    FUSION_AVAILABLE = True
except Exception:
    app = None
    ui = None
    FUSION_AVAILABLE = False

LOG_MODULE = 'SURFACE_MATH_V2'


# ============================================================================
# UTILITY FUNCTIONS 
# ============================================================================

def distance(p0, p1):
    """Euclidean distance between two 3D points. Handles Vector3/Vector3D or tuple."""
    def to_tuple(pt):
        if hasattr(pt, 'asArray'):
            return tuple(pt.asArray())
        if hasattr(pt, 'x') and hasattr(pt, 'y') and hasattr(pt, 'z'):
            return (pt.x, pt.y, pt.z)
        return pt
    p0 = to_tuple(p0)
    p1 = to_tuple(p1)
    return ((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2 + (p0[2] - p1[2]) ** 2) ** 0.5


def measure_edge_length(surface_evaluator, start_uv, end_uv, num_samples=20):
    """Measure real-world length of UV edge by sampling points along it"""
    total_length = 0.0
    prev_world = None
    
    for i in range(num_samples + 1):
        t = i / num_samples
        u = start_uv[0] + t * (end_uv[0] - start_uv[0])
        v = start_uv[1] + t * (end_uv[1] - start_uv[1])
        
        world_pt, _ = evaluate_surface_point(surface_evaluator, u, v)
        if world_pt is None:
            continue
            
        if prev_world is not None:
            total_length += distance(prev_world, world_pt)
        prev_world = world_pt
        
    return total_length


# ============================================================================
# VECTOR3 CLASS (from v1)
# ============================================================================

class Vector3:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def translateBy(self, other):
        """Translate this vector in-place by another Vector3 (add x, y, z)."""
        self.x += other.x
        self.y += other.y
        self.z += other.z

    def copy(self):
        """Return a new Vector3 with the same x, y, z values."""
        return Vector3(self.x, self.y, self.z)

    def normalized(self):
        mag = math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)
        if mag > 0.0001:
            return Vector3(self.x / mag, self.y / mag, self.z / mag)
        return Vector3(0, 0, 1)

def vector3_cross_product(a, b):
    """Calculate cross product of two Vector3 objects"""
    return Vector3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    )

# ============================================================================
# SURFACE UTILITIES (from v1)
# ============================================================================

def get_surface_bounds(face):
    """Get the parametric bounds of the surface (U/V ranges)"""
    try:
        if not FUSION_AVAILABLE:
            # Return mock bounds for testing
            return (0.0, 1.0, 0.0, 1.0)  # u_min, u_max, v_min, v_max
        
        # Get parameter extents from the surface geometry
        surface = face.geometry
        evaluator = surface.evaluator
        bounds = evaluator.parametricRange()
        
        u_min = bounds.minPoint.x
        u_max = bounds.maxPoint.x
        v_min = bounds.minPoint.y  
        v_max = bounds.maxPoint.y
        
        log(app, f"Surface bounds U:[{u_min:.3f}, {u_max:.3f}] V:[{v_min:.3f}, {v_max:.3f}]", 
            level=LogLevel.DEBUG, module=LOG_MODULE)
        
        return (u_min, u_max, v_min, v_max)
        
    except Exception as e:
        log(app, f"Failed to get surface bounds: {str(e)}", 
            level=LogLevel.ERROR, module=LOG_MODULE)
        return (0.0, 1.0, 0.0, 1.0)


def evaluate_surface_point(evaluator, u, v):
    """Evaluate surface at parametric coordinates to get 3D point and normal"""
    try:
        if not FUSION_AVAILABLE or not evaluator:
            # Return mock data for testing
            return (u * 10, v * 10, 0), (0, 0, 1)

        # Create parameter point
        param_point = adsk.core.Point2D.create(u, v)

        # Evaluate surface position
        (return_value, position) = evaluator.getPointAtParameter(param_point)
        if not return_value:
            log(app, f"Failed to evaluate surface at U:{u:.3f} V:{v:.3f}", 
                level=LogLevel.ERROR, module=LOG_MODULE)
            return None, None

        # Evaluate surface normal
        (return_value, normal) = evaluator.getNormalAtParameter(param_point)
        if not return_value:
            log(app, f"Failed to get normal at U:{u:.3f} V:{v:.3f}", 
                level=LogLevel.ERROR, module=LOG_MODULE)
            if FUSION_AVAILABLE:
                normal = adsk.core.Vector3D.create(0, 0, 1)
            else:
                normal = (0, 0, 1)

        def to_tuple(obj):
            if hasattr(obj, 'asArray'):
                return tuple(obj.asArray())
            if hasattr(obj, 'x') and hasattr(obj, 'y') and hasattr(obj, 'z'):
                return (obj.x, obj.y, obj.z)
            return obj

        pt_tuple = to_tuple(position)
        normal_tuple = to_tuple(normal)
        return pt_tuple, normal_tuple

    except Exception as e:
        log(app, f"Surface evaluation failed: {str(e)}", 
            level=LogLevel.ERROR, module=LOG_MODULE)
        return None, None


def create_coordinate_system_from_normal(normal, reference_vector=None):
    """Create right/forward vectors from a normal vector"""
    # Find a vector perpendicular to normal for X-axis
    if reference_vector is None:
        if abs(normal.x) < 0.9:
            # Normal is not close to X-axis, use X as reference
            reference_vector = Vector3(1, 0, 0)
        else:
            # Normal is close to X-axis, use Y as reference  
            reference_vector = Vector3(0, 1, 0)
    
    # Calculate actual right vector (cross product)
    right = vector3_cross_product(normal, reference_vector).normalized()
    
    # Calculate forward vector (cross product)
    forward = vector3_cross_product(right, normal)
    
    return right, forward


def create_surface_transform(position, normal, rotation_degrees=0.0, align_to_normal=True, u_tangent=None, v_tangent=None):
    """Create transformation matrix for placing geometry on surface"""
    try:
        if not FUSION_AVAILABLE:
            # Return identity matrix for testing
            return None

        # Convert tuple to Vector3 if needed
        def to_vec3(obj):
            if hasattr(obj, 'x') and hasattr(obj, 'y') and hasattr(obj, 'z'):
                return obj
            if isinstance(obj, (tuple, list)) and len(obj) == 3:
                return Vector3(obj[0], obj[1], obj[2])
            raise ValueError("Position/normal must be Vector3 or tuple/list of length 3")
        
        position = to_vec3(position)
        normal = to_vec3(normal)

        # Create coordinate system from normal
        if align_to_normal and normal:
            # If u_tangent and v_tangent are provided, use them for axes
            if u_tangent is not None and v_tangent is not None:
                right = u_tangent.normalized()
                forward = v_tangent.normalized()
            else:
                right, forward = create_coordinate_system_from_normal(normal)

            # Apply rotation around normal (Z-axis)
            # SOLUTION: Negate rotation to unwind systematic over-rotation
            if rotation_degrees != 0:
                rad = math.radians(rotation_degrees * -1)  # Negate to unwind
                cos_r = math.cos(rad)
                sin_r = math.sin(rad)

                # Rotate right and forward vectors around normal
                new_right = Vector3(
                    right.x * cos_r - forward.x * sin_r,
                    right.y * cos_r - forward.y * sin_r,
                    right.z * cos_r - forward.z * sin_r
                )

                new_forward = Vector3(
                    right.x * sin_r + forward.x * cos_r,
                    right.y * sin_r + forward.y * cos_r,
                    right.z * sin_r + forward.z * cos_r
                )

                right = new_right
                forward = new_forward

            # Create Fusion 360 transformation matrix
            matrix = adsk.core.Matrix3D.create()

            # Set coordinate system (columns are X, Y, Z axes + translation)
            matrix.setWithCoordinateSystem(
                adsk.core.Point3D.create(position.x, position.y, position.z),  # Origin
                adsk.core.Vector3D.create(right.x, right.y, right.z),          # X-axis
                adsk.core.Vector3D.create(forward.x, forward.y, forward.z),    # Y-axis
                adsk.core.Vector3D.create(normal.x, normal.y, normal.z)        # Z-axis (normal)
            )

            return matrix

        else:
            # Simple translation matrix without normal alignment
            matrix = adsk.core.Matrix3D.create()
            matrix.translation = adsk.core.Vector3D.create(position.x, position.y, position.z)
            return matrix

    except Exception as e:
        log(app, f"Transform creation failed: {str(e)}", 
            level=LogLevel.ERROR, module=LOG_MODULE)
        return None


# ============================================================================
# SURFACE INSTANCE CREATION FUNCTIONS (from v1)
# ============================================================================

def create_surface_instances_with_uv_alignment(
    surface_evaluator,
    uv_points,
    rotation_degrees=0.0,
    align_to_normal=True
):
    """
    Create properly oriented surface instances with UV tangent alignment for ALL grid types.
    
    This function ensures consistent UV tangent alignment across all grid types by:
    1. Calculating UV tangents at each point
    2. Using those tangents to create properly oriented transformation matrices
    3. Applying rotation around the surface normal
    
    Args:
        surface_evaluator: The surface evaluator to calculate positions, normals, and tangents.
        uv_points: A list of (u, v) coordinates.
        rotation_degrees: Rotation to apply around the surface normal.
        align_to_normal: Whether to align instances to surface normals.

    Returns:
        A list of transformation matrices with proper UV tangent alignment.
    """
    transformation_matrices = []
    
    for uv in uv_points:
        u, v = uv
        position, normal = evaluate_surface_point(surface_evaluator, u, v)
        if position is None or normal is None:
            continue

        # Calculate UV tangents - THIS IS THE KEY FOR CONSISTENT ALIGNMENT
        u_tangent = None
        v_tangent = None
        
        if FUSION_AVAILABLE and surface_evaluator and hasattr(surface_evaluator, 'getFirstDerivative'):
            try:
                import adsk.core # type: ignore
                param_point = adsk.core.Point2D.create(u, v)
                derivs = surface_evaluator.getFirstDerivative(param_point)
                u_tangent = Vector3(*derivs[1].asArray())
                v_tangent = Vector3(*derivs[2].asArray())
                
                log(app, f"Calculated tangents at U:{u:.3f}, V:{v:.3f}", 
                    level=LogLevel.DEBUG, module=LOG_MODULE)
                    
            except Exception as e:
                log(app, f"Failed to calculate tangents at U:{u:.3f}, V:{v:.3f}: {str(e)}", 
                    level=LogLevel.ERROR, module=LOG_MODULE)
                # Fall back to coordinate system from normal
                u_tangent = None
                v_tangent = None

        # Create transformation matrix with UV tangent alignment
        transform = create_surface_transform(
            position, normal, rotation_degrees, 
            align_to_normal=align_to_normal,
            u_tangent=u_tangent, v_tangent=v_tangent
        )
        
        if transform:
            transformation_matrices.append(transform)

    return transformation_matrices


def create_surface_instances_translation_only(
    surface_evaluator,
    uv_points
):
    """
    Create surface instances with translation only - no rotation/alignment.
    
    This function creates transformation matrices that only position objects
    at surface points without any rotational alignment to normals or tangents.
    Objects maintain their original orientation.
    
    Args:
        surface_evaluator: The surface evaluator to calculate positions.
        uv_points: A list of (u, v) coordinates.

    Returns:
        A list of transformation matrices with translation only.
    """
    transformation_matrices = []
    
    # Debug logging
    log(app, f"Processing {len(uv_points)} UV points for translation-only positioning", 
        level=LogLevel.DEBUG, module=LOG_MODULE)
    
    for i, uv in enumerate(uv_points):
        u, v = uv
        position, normal = evaluate_surface_point(surface_evaluator, u, v)
        if position is None:
            log(app, f"Skipped point {i} at UV({u:.3f}, {v:.3f}) - position is None", 
                level=LogLevel.DEBUG, module=LOG_MODULE)
            continue

        # Create simple translation matrix - no rotation/alignment
        if FUSION_AVAILABLE:
            try:
                matrix = adsk.core.Matrix3D.create()
                # Convert position tuple to Vector3D for translation
                if isinstance(position, tuple) and len(position) >= 3:
                    matrix.translation = adsk.core.Vector3D.create(position[0], position[1], position[2])
                    log(app, f"Created matrix {i} at UV({u:.3f}, {v:.3f}) -> pos({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f})", 
                        level=LogLevel.DEBUG, module=LOG_MODULE)
                else:
                    # Fallback for position objects with .x, .y, .z attributes
                    matrix.translation = adsk.core.Vector3D.create(position.x, position.y, position.z)
                    log(app, f"Created matrix {i} at UV({u:.3f}, {v:.3f}) -> pos({position.x:.3f}, {position.y:.3f}, {position.z:.3f})", 
                        level=LogLevel.DEBUG, module=LOG_MODULE)
                transformation_matrices.append(matrix)
            except Exception as e:
                log(app, f"Translation-only transform failed at UV({u:.3f}, {v:.3f}): {str(e)}", 
                    level=LogLevel.ERROR, module=LOG_MODULE)
                continue

    log(app, f"Created {len(transformation_matrices)} transformation matrices", 
        level=LogLevel.DEBUG, module=LOG_MODULE)
    return transformation_matrices


# ============================================================================
# WORLD WALKING FUNCTIONS (from v1)
# ============================================================================

def step_uv_by_world_distance(evaluator, start_u: float, start_v: float, 
                             direction_u: float, direction_v: float, 
                             world_distance: float, max_iterations: int = 10, 
                             tolerance: float = 0.001) -> Tuple[float, float]:
    """
    Step from (start_u, start_v) in UV space by world_distance in world space.
    Uses Newton-Raphson iteration to find the UV coordinates that achieve the target world distance.
    
    Provides accurate geodesic spacing.
    
    Args:
        evaluator: Surface evaluator for position calculations
        start_u, start_v: Starting UV coordinates
        direction_u, direction_v: Direction vector in UV space (will be normalized)
        world_distance: Target distance in world units
        max_iterations: Maximum iterations for convergence
        tolerance: Distance tolerance for convergence
        
    Returns:
        Tuple of (final_u, final_v) coordinates that achieve target world distance
    """
    try:
        if not FUSION_AVAILABLE or not evaluator:
            # Fallback for testing: simple linear step
            log(app, f"World walking fallback: stepping by {world_distance} units", 
                level=LogLevel.WARNING, module=LOG_MODULE)
            direction_length = math.sqrt(direction_u * direction_u + direction_v * direction_v)
            if direction_length > 0:
                scale = world_distance * 0.01  # Simple parameter scaling
                return start_u + direction_u * scale / direction_length, start_v + direction_v * scale / direction_length
            return start_u, start_v
        
        current_u = start_u
        current_v = start_v
        
        # Normalize direction vector
        direction_length = math.sqrt(direction_u * direction_u + direction_v * direction_v)
        if direction_length == 0:
            log(app, f"World walking: zero direction vector, returning start position", 
                level=LogLevel.WARNING, module=LOG_MODULE)
            return start_u, start_v
        
        direction_u /= direction_length
        direction_v /= direction_length
        
        # Get starting position in world space
        start_point = adsk.core.Point2D.create(start_u, start_v)
        (success, start_pos) = evaluator.getPointAtParameter(start_point)
        if not success:
            log(app, f"World walking: failed to evaluate start position at UV({start_u:.3f}, {start_v:.3f})", 
                level=LogLevel.ERROR, module=LOG_MODULE)
            return start_u, start_v
        
        # Get surface derivatives for better initial step estimation
        try:
            param_point = adsk.core.Point2D.create(start_u, start_v)
            derivs = evaluator.getFirstDerivative(param_point)
            if derivs[0]:  # Success
                # Calculate surface scale factors from derivatives
                du_magnitude = math.sqrt(derivs[1].x**2 + derivs[1].y**2 + derivs[1].z**2)
                dv_magnitude = math.sqrt(derivs[2].x**2 + derivs[2].y**2 + derivs[2].z**2)
                
                # Adaptive initial step based on surface curvature
                u_scale = 1.0 / max(du_magnitude, 0.001) if du_magnitude > 0 else 1.0
                v_scale = 1.0 / max(dv_magnitude, 0.001) if dv_magnitude > 0 else 1.0
                
                # Initial guess with surface-aware scaling
                step_u = direction_u * world_distance * u_scale * 0.1  # Conservative start
                step_v = direction_v * world_distance * v_scale * 0.1
            else:
                # Fallback to simple step
                step_u = direction_u * 0.01
                step_v = direction_v * 0.01
        except Exception:
            # Fallback to simple step
            step_u = direction_u * 0.01
            step_v = direction_v * 0.01
        
        # Improved iterative solver with damping
        damping_factor = 1.0
        previous_error = float('inf')
        
        for i in range(max_iterations):
            # Calculate current test position
            test_u = start_u + step_u
            test_v = start_v + step_v
            
            # Get world position at test coordinates
            test_point = adsk.core.Point2D.create(test_u, test_v)
            (success, test_pos) = evaluator.getPointAtParameter(test_point)
            if not success:
                log(app, f"World walking: failed to evaluate test position at UV({test_u:.3f}, {test_v:.3f})", 
                    level=LogLevel.WARNING, module=LOG_MODULE)
                break
            
            # Calculate actual distance in world space
            actual_distance = start_pos.distanceTo(test_pos)
            
            # Check if we're close enough
            distance_error = abs(actual_distance - world_distance)
            if distance_error < tolerance:
                log(app, f"World walking converged: UV({test_u:.3f}, {test_v:.3f}) distance={actual_distance:.3f} (target={world_distance:.3f})", 
                    level=LogLevel.DEBUG, module=LOG_MODULE)
                return test_u, test_v
            
            # Adaptive damping to prevent oscillation
            if distance_error > previous_error:
                damping_factor *= 0.5  # Reduce step if error increased
            else:
                damping_factor = min(damping_factor * 1.1, 1.0)  # Increase step if improving
            
            previous_error = distance_error
            
            # Improved Newton-Raphson with damping
            if actual_distance > 0:  # Avoid division by zero
                correction_factor = (world_distance / actual_distance) * damping_factor
                step_u *= correction_factor
                step_v *= correction_factor
            else:
                # If distance is zero, increase step size slightly with damping
                step_u *= (1.1 * damping_factor)
                step_v *= (1.1 * damping_factor)
        
        # Return best guess if iteration didn't converge
        final_u = start_u + step_u
        final_v = start_v + step_v
        log(app, f"World walking: max iterations reached, using UV({final_u:.3f}, {final_v:.3f})", 
            level=LogLevel.WARNING, module=LOG_MODULE)
        return final_u, final_v
        
    except Exception as e:
        log(app, f"World walking failed: {str(e)}", 
            level=LogLevel.ERROR, module=LOG_MODULE)
        return start_u, start_v


def create_world_spaced_hex_grid(evaluator, center_u: float, center_v: float,
                                count_u: int, count_v: int, world_spacing: float) -> List[Tuple[float, float]]:
    """
    Create a hexagonal grid with accurate world-space spacing using world walking.
    
    This replaces the simple parameter-space approximation with true geodesic spacing.
    
    Args:
        evaluator: Surface evaluator for world walking
        center_u, center_v: Center position in UV space
        count_u, count_v: Grid dimensions
        world_spacing: Distance between hex centers in world units
        
    Returns:
        List of (u, v) coordinates for hex grid with accurate world spacing
    """
    uv_points = []
    
    try:
        # Hexagonal grid math
        hex_row_offset = world_spacing * 0.866025  # sqrt(3)/2 for proper hex geometry
        hex_col_offset = world_spacing * 0.5       # Half spacing for stagger
        
        log(app, f"Creating world-spaced hex grid: {count_u}x{count_v}, spacing={world_spacing:.3f}", 
            level=LogLevel.DEBUG, module=LOG_MODULE)
        
        for row in range(count_v):
            for col in range(count_u):
                # Calculate offset from center (can be positive or negative)
                row_offset = (row - count_v // 2) * hex_row_offset
                col_offset = (col - count_u // 2) * world_spacing
                
                # Add stagger for hex pattern (every other row)
                if row % 2 == 1:
                    col_offset += hex_col_offset
                
                # Start from center and step using world walking
                # Step in U direction first, handling positive/negative offsets
                if col_offset != 0:
                    u_direction = 1.0 if col_offset > 0 else -1.0
                    target_u, temp_v = step_uv_by_world_distance(
                        evaluator, center_u, center_v, u_direction, 0.0, abs(col_offset)
                    )
                else:
                    target_u, temp_v = center_u, center_v
                
                # Step in V direction, handling positive/negative offsets
                if row_offset != 0:
                    v_direction = 1.0 if row_offset > 0 else -1.0
                    final_u, final_v = step_uv_by_world_distance(
                        evaluator, target_u, temp_v, 0.0, v_direction, abs(row_offset)
                    )
                else:
                    final_u, final_v = target_u, temp_v
                
                uv_points.append((final_u, final_v))
        
        log(app, f"World-spaced hex grid: generated {len(uv_points)} points", 
            level=LogLevel.DEBUG, module=LOG_MODULE)
        return uv_points
        
    except Exception as e:
        log(app, f"World-spaced hex grid failed: {str(e)}", 
            level=LogLevel.ERROR, module=LOG_MODULE)
        return []