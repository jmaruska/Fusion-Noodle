"""
Vector and matrix math utilities for v2 nodes.
Consolidates repeated mathematical operations from array nodes.
"""

import math
from typing import Dict, Tuple, List, Optional, Any

try:
    import adsk.core  # type: ignore
    FUSION_AVAILABLE = True
except Exception:
    FUSION_AVAILABLE = False


# ============================================================================
# VECTOR OPERATIONS (Dict format for JSON compatibility)
# ============================================================================

def normalize_vector(vector: Dict[str, float]) -> Dict[str, float]:
    """Normalize a vector to unit length."""
    x, y, z = vector['x'], vector['y'], vector['z']
    magnitude = math.sqrt(x*x + y*y + z*z)
    if magnitude < 1e-10:
        return {'x': 0.0, 'y': 0.0, 'z': 1.0}  # Default to Z-up
    return {
        'x': x / magnitude,
        'y': y / magnitude,
        'z': z / magnitude
    }


def cross_product(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    """Calculate cross product of two vectors."""
    return {
        'x': a['y'] * b['z'] - a['z'] * b['y'],
        'y': a['z'] * b['x'] - a['x'] * b['z'],
        'z': a['x'] * b['y'] - a['y'] * b['x']
    }


def create_coordinate_system_from_normal(normal_vec: 'adsk.core.Vector3D') -> Tuple['adsk.core.Vector3D', 'adsk.core.Vector3D']:
    """
    Creates a stable coordinate system from a normal vector using a deterministic "up" vector.
    This provides stability but can result in arbitrary-feeling rotation.
    Prefer `create_aligned_coordinate_system` for more intuitive results.
    """
    if not FUSION_AVAILABLE:
        raise ImportError("Fusion 360 API is not available.")

    normal_vec.normalize()
    world_x = adsk.core.Vector3D.create(1.0, 0.0, 0.0)

    # Check if the normal is parallel to the world X-axis.
    # If so, the projection will be a zero vector, so we use world Y as the reference instead.
    if abs(normal_vec.dotProduct(world_x)) > 0.9999:
        ref_vec = adsk.core.Vector3D.create(0.0, 1.0, 0.0)
    else:
        ref_vec = world_x

    # Project the reference vector onto the plane to get the new X-axis.
    # projection = ref_vec - (ref_vec . normal) * normal
    dot = ref_vec.dotProduct(normal_vec)
    scaled_normal = normal_vec.copy()
    scaled_normal.scaleBy(dot)
    
    plane_x_axis = ref_vec.copy()
    plane_x_axis.subtract(scaled_normal)
    plane_x_axis.normalize()

    # The new Y-axis is the cross product of the normal and the new X-axis.
    # This ensures it's orthogonal to both.
    plane_y_axis = normal_vec.crossProduct(plane_x_axis)
    plane_y_axis.normalize()

    return plane_x_axis, plane_y_axis


# ============================================================================
# TRANSFORMATION MATRIX UTILITIES
# ============================================================================

def create_transform_matrix_from_coordinate_system(
    origin: Dict[str, float],
    right_vec: Dict[str, float], 
    up_vec: Dict[str, float],
    forward_vec: Dict[str, float]
) -> Optional[Any]:
    """
    Create a Fusion transformation matrix from coordinate system vectors.
    
    Args:
        origin: Position {x, y, z}
        right_vec: X-axis direction {x, y, z} 
        up_vec: Y-axis direction {x, y, z}
        forward_vec: Z-axis direction {x, y, z}
        
    Returns:
        Fusion Matrix3D object or None if Fusion not available
    """
    if not FUSION_AVAILABLE:
        return None
        
    matrix = adsk.core.Matrix3D.create()
    matrix.setWithCoordinateSystem(
        adsk.core.Point3D.create(origin['x'], origin['y'], origin['z']),
        adsk.core.Vector3D.create(right_vec['x'], right_vec['y'], right_vec['z']),
        adsk.core.Vector3D.create(up_vec['x'], up_vec['y'], up_vec['z']),
        adsk.core.Vector3D.create(forward_vec['x'], forward_vec['y'], forward_vec['z'])
    )
    
    return matrix


# ============================================================================
# PATTERN GENERATION UTILITIES  
# ============================================================================

# ============================================================================
# QUATERNION UTILITIES
# ============================================================================

def quaternion_rotate_a_to_b(ax: float, ay: float, az: float,
                              bx: float, by: float, bz: float):
    """
    Return quaternion (qx, qy, qz, qw) that rotates unit vector A to unit vector B.

    Inputs must already be normalised. Returns identity (0,0,0,1) when A == B,
    and a 180-degree rotation around the most perpendicular world axis when A == -B.

    Uses atan2 form to stay numerically stable near θ=0 and θ=π.
    """
    cx = ay * bz - az * by
    cy = az * bx - ax * bz
    cz = ax * by - ay * bx
    cross_mag = math.sqrt(cx * cx + cy * cy + cz * cz)  # sin θ
    dot = ax * bx + ay * by + az * bz                    # cos θ

    if cross_mag < 1e-9:
        if dot > 0:
            return 0.0, 0.0, 0.0, 1.0  # already aligned
        # Anti-parallel: 180° around a perpendicular axis
        if abs(ax) < 0.9:
            px, py, pz = 1.0, 0.0, 0.0
        else:
            px, py, pz = 0.0, 1.0, 0.0
        proj = ax * px + ay * py + az * pz
        rx, ry, rz = px - proj * ax, py - proj * ay, pz - proj * az
        rmag = math.sqrt(rx * rx + ry * ry + rz * rz)
        if rmag < 1e-9:
            return 0.0, 0.0, 0.0, 1.0
        return rx / rmag, ry / rmag, rz / rmag, 0.0

    angle = math.atan2(cross_mag, dot)
    half = angle * 0.5
    s = math.sin(half) / cross_mag  # scale axis from (unnorm cross) to proper quaternion
    return cx * s, cy * s, cz * s, math.cos(half)


def slerp_quaternion(ax: float, ay: float, az: float, aw: float,
                     bx: float, by: float, bz: float, bw: float,
                     t: float):
    """
    Spherical linear interpolation between quaternions A and B.

    t=0 returns A, t=1 returns B. Result is normalised.
    Falls back to normalised linear interpolation (nlerp) near parallel quaternions.
    """
    dot = ax * bx + ay * by + az * bz + aw * bw

    # Ensure shortest arc
    if dot < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
        dot = -dot

    if dot > 0.9995:
        # Nearly identical — nlerp is accurate enough
        rx = ax + t * (bx - ax)
        ry = ay + t * (by - ay)
        rz = az + t * (bz - az)
        rw = aw + t * (bw - aw)
    else:
        theta_0 = math.acos(dot)
        theta = theta_0 * t
        sin_theta = math.sin(theta)
        sin_theta_0 = math.sin(theta_0)
        s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
        s1 = sin_theta / sin_theta_0
        rx = s0 * ax + s1 * bx
        ry = s0 * ay + s1 * by
        rz = s0 * az + s1 * bz
        rw = s0 * aw + s1 * bw

    mag = math.sqrt(rx * rx + ry * ry + rz * rz + rw * rw)
    if mag < 1e-9:
        return 0.0, 0.0, 0.0, 1.0
    return rx / mag, ry / mag, rz / mag, rw / mag


# ============================================================================
# UTILITY EXPORTS
# ============================================================================

__all__ = [
    # Vector operations
    'normalize_vector',
    'cross_product', 
    'create_coordinate_system_from_normal',
    
    # Matrix operations
    'create_transform_matrix_from_coordinate_system',
    
    # Pattern generation

    # Quaternion utilities
    'quaternion_rotate_a_to_b',
    'slerp_quaternion',
]

def aim_rotation(centre, axis, target):
    """The rotation that turns `axis` (as seen from `centre`) to point at `target`.

    Returns (angle in radians, unit rotation axis), or None when the target is at the
    centre or the axis already points at it. When the axis points directly away, it
    turns half a circle about any axis perpendicular to it.
    """
    import math
    d = [t - c for t, c in zip(target, centre)]
    dl = math.sqrt(sum(x * x for x in d))
    al = math.sqrt(sum(x * x for x in axis))
    if dl < 1e-9 or al < 1e-9:
        return None
    d = [x / dl for x in d]
    a = [x / al for x in axis]
    dot = max(-1.0, min(1.0, sum(p * q for p, q in zip(a, d))))
    cross = (a[1] * d[2] - a[2] * d[1], a[2] * d[0] - a[0] * d[2], a[0] * d[1] - a[1] * d[0])
    cl = math.sqrt(sum(x * x for x in cross))
    if cl < 1e-9:
        if dot > 0:
            return None
        helper = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
        cross = (a[1] * helper[2] - a[2] * helper[1], a[2] * helper[0] - a[0] * helper[2],
                 a[0] * helper[1] - a[1] * helper[0])
        cl = math.sqrt(sum(x * x for x in cross))
        return math.pi, tuple(x / cl for x in cross)
    return math.atan2(cl, dot), tuple(x / cl for x in cross)
