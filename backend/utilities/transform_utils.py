"""
Transform utility functions for backend.

This module provides shared utilities for applying transforms to geometry instances,
ensuring consistency across all nodes that handle transforms.
"""

import math
try:
    import adsk.core
    import adsk.fusion
    FUSION_AVAILABLE = True
except ImportError:
    adsk = None
    FUSION_AVAILABLE = False

from typing import Any, Optional, Dict, List
from .log_utils import log, LogLevel


def transform_matrix_rows(transform_data: Dict[str, Any]) -> Optional[List[float]]:
    """The 4x4 matrix for an instance transform, row by row, or None for identity.

    Scale is applied first, then rotation, then translation, all about the
    origin, so one matrix does what used to take three kernel transforms.
    Rotation comes from the quaternion when use_quaternion is set, otherwise
    from Euler angles in degrees applied X, then Y, then Z. Pure Python.
    """
    if not transform_data or not any(k in transform_data for k in ("tx", "ty", "tz")):
        return None
    get = transform_data.get
    sx, sy, sz = float(get("sx", 1.0)), float(get("sy", 1.0)), float(get("sz", 1.0))
    tx, ty, tz = float(get("tx", 0.0)), float(get("ty", 0.0)), float(get("tz", 0.0))

    if get("use_quaternion", False):
        qx, qy, qz, qw = float(get("qx", 0.0)), float(get("qy", 0.0)), float(get("qz", 0.0)), float(get("qw", 1.0))
        length = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if length > 0:
            qx, qy, qz, qw = qx / length, qy / length, qz / length, qw / length
        xx, yy, zz = qx * qx, qy * qy, qz * qz
        xy, xz, yz = qx * qy, qx * qz, qy * qz
        wx, wy, wz = qw * qx, qw * qy, qw * qz
        r = [[1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
             [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
             [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)]]
    else:
        ax, ay, az = (math.radians(float(get(k, 0.0))) for k in ("rx", "ry", "rz"))
        cx, sxr, cy, syr, cz, szr = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
        # Rz * Ry * Rx: rotate about X first, then Y, then Z
        r = [[cz * cy, cz * syr * sxr - szr * cx, cz * syr * cx + szr * sxr],
             [szr * cy, szr * syr * sxr + cz * cx, szr * syr * cx - cz * sxr],
             [-syr, cy * sxr, cy * cx]]

    rows = [r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx,
            r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty,
            r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz,
            0.0, 0.0, 0.0, 1.0]
    if all(abs(a - b) < 1e-12 for a, b in zip(rows, _IDENTITY_ROWS)):
        return None
    return rows


_IDENTITY_ROWS = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def apply_complete_transform_to_brep(temp_brep_mgr: Any, brep: Any, transform_data: Dict[str, Any], app=None) -> None:
    """Scale, rotate and move a temporary BRep body with one kernel transform."""
    if not FUSION_AVAILABLE or not temp_brep_mgr:
        return
    rows = transform_matrix_rows(transform_data)
    if rows is None:
        return
    matrix = adsk.core.Matrix3D.create()
    matrix.setWithArray(rows)
    temp_brep_mgr.transform(brep, matrix)


# Matrix Chaining Utilities for Graph-Topology-Respecting Transform Order

def create_identity_matrix_dict() -> Dict[str, float]:
    """Create a 4x4 identity matrix as a dictionary for serialization."""
    return {
        'm00': 1.0, 'm01': 0.0, 'm02': 0.0, 'm03': 0.0,
        'm10': 0.0, 'm11': 1.0, 'm12': 0.0, 'm13': 0.0,
        'm20': 0.0, 'm21': 0.0, 'm22': 1.0, 'm23': 0.0,
        'm30': 0.0, 'm31': 0.0, 'm32': 0.0, 'm33': 1.0
    }

def create_scale_matrix_dict(scale_x: float, scale_y: float, scale_z: float) -> Dict[str, float]:
    """Create a scale transformation matrix as a dictionary."""
    return {
        'm00': scale_x, 'm01': 0.0,     'm02': 0.0,     'm03': 0.0,
        'm10': 0.0,     'm11': scale_y, 'm12': 0.0,     'm13': 0.0,
        'm20': 0.0,     'm21': 0.0,     'm22': scale_z, 'm23': 0.0,
        'm30': 0.0,     'm31': 0.0,     'm32': 0.0,     'm33': 1.0
    }

def create_translation_matrix_dict(tx: float, ty: float, tz: float) -> Dict[str, float]:
    """Create a translation transformation matrix as a dictionary."""
    return {
        'm00': 1.0, 'm01': 0.0, 'm02': 0.0, 'm03': tx,
        'm10': 0.0, 'm11': 1.0, 'm12': 0.0, 'm13': ty,
        'm20': 0.0, 'm21': 0.0, 'm22': 1.0, 'm23': tz,
        'm30': 0.0, 'm31': 0.0, 'm32': 0.0, 'm33': 1.0
    }

def create_rotation_z_matrix_dict(angle_radians: float) -> Dict[str, float]:
    """Create a Z-axis rotation transformation matrix as a dictionary."""
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    return {
        'm00': cos_a,  'm01': -sin_a, 'm02': 0.0, 'm03': 0.0,
        'm10': sin_a,  'm11': cos_a,  'm12': 0.0, 'm13': 0.0,
        'm20': 0.0,    'm21': 0.0,    'm22': 1.0, 'm23': 0.0,
        'm30': 0.0,    'm31': 0.0,    'm32': 0.0, 'm33': 1.0
    }

def create_rotation_x_matrix_dict(angle_radians: float) -> Dict[str, float]:
    """Create an X-axis rotation transformation matrix as a dictionary."""
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    return {
        'm00': 1.0,    'm01': 0.0,    'm02': 0.0,    'm03': 0.0,
        'm10': 0.0,    'm11': cos_a,  'm12': -sin_a, 'm13': 0.0,
        'm20': 0.0,    'm21': sin_a,  'm22': cos_a,  'm23': 0.0,
        'm30': 0.0,    'm31': 0.0,    'm32': 0.0,    'm33': 1.0
    }

def create_rotation_y_matrix_dict(angle_radians: float) -> Dict[str, float]:
    """Create a Y-axis rotation transformation matrix as a dictionary."""
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    return {
        'm00': cos_a,  'm01': 0.0,    'm02': sin_a,  'm03': 0.0,
        'm10': 0.0,    'm11': 1.0,    'm12': 0.0,    'm13': 0.0,
        'm20': -sin_a, 'm21': 0.0,    'm22': cos_a,  'm23': 0.0,
        'm30': 0.0,    'm31': 0.0,    'm32': 0.0,    'm33': 1.0
    }

def create_rotation_xyz_matrix_dict(rx_degrees: float, ry_degrees: float, rz_degrees: float) -> Dict[str, float]:
    """Create a combined XYZ Euler rotation matrix (X, then Y, then Z order)."""
    # Convert to radians
    rx_rad = math.radians(rx_degrees)
    ry_rad = math.radians(ry_degrees)
    rz_rad = math.radians(rz_degrees)
    
    # Create individual rotation matrices
    rot_x = create_rotation_x_matrix_dict(rx_rad)
    rot_y = create_rotation_y_matrix_dict(ry_rad)
    rot_z = create_rotation_z_matrix_dict(rz_rad)
    
    # Combine: RZ * RY * RX (applied in reverse order: X first, then Y, then Z)
    temp = multiply_matrix_dicts(rot_y, rot_x)
    final = multiply_matrix_dicts(rot_z, temp)
    
    return final

def multiply_matrix_dicts(matrix_a: Dict[str, float], matrix_b: Dict[str, float]) -> Dict[str, float]:
    """Multiply two 4x4 transformation matrices (A * B). Result = matrix_a applied first, then matrix_b."""
    result = {}
    
    # 4x4 matrix multiplication: C[i][j] = sum(A[i][k] * B[k][j] for k in 0..3)
    for i in range(4):
        for j in range(4):
            result_key = f'm{i}{j}'
            result[result_key] = 0.0
            for k in range(4):
                a_key = f'm{i}{k}'
                b_key = f'm{k}{j}'
                result[result_key] += matrix_a.get(a_key, 0.0) * matrix_b.get(b_key, 0.0)
    
    return result

def matrix_dict_to_fusion_matrix(matrix_dict: Dict[str, float]):
    """Convert matrix dictionary to Fusion 360 Matrix3D object."""
    if not FUSION_AVAILABLE:
        return None
    
    matrix_3d = adsk.core.Matrix3D.create()
    
    # Set all 16 matrix elements
    for i in range(4):
        for j in range(4):
            key = f'm{i}{j}'
            if key in matrix_dict:
                matrix_3d.setCell(i, j, matrix_dict[key])
    
    return matrix_3d

def apply_matrix_dict_to_brep(temp_brep_mgr: Any, brep: Any, matrix_dict: Dict[str, float], app=None) -> None:
    """Apply a transformation matrix dictionary to a BRep using Fusion's TemporaryBRepManager."""
    if not FUSION_AVAILABLE or not temp_brep_mgr:
        return
    
    # Convert dict to Fusion matrix and apply
    fusion_matrix = matrix_dict_to_fusion_matrix(matrix_dict)
    if fusion_matrix:
        
        temp_brep_mgr.transform(brep, fusion_matrix)
        if app:
            log(app, f"🔧 Applied transformation matrix to geometry", level=LogLevel.DEBUG, module="TRANSFORM_UTILS")


def decompose_matrix_dict(matrix_dict):
    """
    Decompose a 4x4 transformation matrix into scale, rotation (Euler XYZ), and translation components.
    
    Args:
        matrix_dict: Dictionary with keys like 'm00', 'm01', etc.
        
    Returns:
        dict: {
            'scale': {'x': sx, 'y': sy, 'z': sz},
            'rotation_degrees': {'x': rx, 'y': ry, 'z': rz},  # In degrees
            'translation': {'x': tx, 'y': ty, 'z': tz}
        }
    """
    import math
    
    # Extract translation (4th column)
    tx = matrix_dict.get('m03', 0.0)
    ty = matrix_dict.get('m13', 0.0)
    tz = matrix_dict.get('m23', 0.0)
    
    # Extract the 3x3 upper-left matrix for scale and rotation
    m00, m01, m02 = matrix_dict.get('m00', 1.0), matrix_dict.get('m01', 0.0), matrix_dict.get('m02', 0.0)
    m10, m11, m12 = matrix_dict.get('m10', 0.0), matrix_dict.get('m11', 1.0), matrix_dict.get('m12', 0.0)
    m20, m21, m22 = matrix_dict.get('m20', 0.0), matrix_dict.get('m21', 0.0), matrix_dict.get('m22', 1.0)
    
    # Extract scale factors (length of each column vector)
    sx = math.sqrt(m00*m00 + m10*m10 + m20*m20)
    sy = math.sqrt(m01*m01 + m11*m11 + m21*m21) 
    sz = math.sqrt(m02*m02 + m12*m12 + m22*m22)
    
    # Handle negative determinant (reflection)
    det = m00*(m11*m22 - m12*m21) - m01*(m10*m22 - m12*m20) + m02*(m10*m21 - m11*m20)
    if det < 0:
        sx = -sx
    
    # Remove scale to get pure rotation matrix
    if sx != 0.0 and sy != 0.0 and sz != 0.0:
        r00, r01, r02 = m00/sx, m01/sy, m02/sz
        r10, r11, r12 = m10/sx, m11/sy, m12/sz
        r20, r21, r22 = m20/sx, m21/sy, m22/sz
        
        # Extract Euler angles (XYZ order) from rotation matrix
        # Clamp values to handle numerical precision issues
        def clamp(val, min_val=-1.0, max_val=1.0):
            return max(min_val, min(max_val, val))
        
        # XYZ Euler extraction
        if abs(r02) < 0.99999:  # Not at singularity
            ry = math.asin(clamp(r02))
            rx = math.atan2(-r12, r22)
            rz = math.atan2(-r01, r00)
        else:  # Gimbal lock case
            if r02 < 0:  # r02 = -1
                ry = -math.pi / 2
                rx = 0
                rz = math.atan2(r10, r11)
            else:  # r02 = 1
                ry = math.pi / 2
                rx = 0
                rz = -math.atan2(r10, r11)
        
        # Convert to degrees
        rx_deg = math.degrees(rx)
        ry_deg = math.degrees(ry) 
        rz_deg = math.degrees(rz)
    else:
        # Identity rotation if scale is zero
        rx_deg = ry_deg = rz_deg = 0.0
    
    return {
        'scale': {'x': sx, 'y': sy, 'z': sz},
        'rotation_degrees': {'x': rx_deg, 'y': ry_deg, 'z': rz_deg},
        'translation': {'x': tx, 'y': ty, 'z': tz}
    }


__all__ = [
    'transform_matrix_rows',
    'apply_complete_transform_to_brep',
    'create_identity_matrix_dict',
    'create_scale_matrix_dict', 
    'create_translation_matrix_dict',
    'create_rotation_z_matrix_dict',
    'create_rotation_x_matrix_dict',
    'create_rotation_y_matrix_dict',
    'create_rotation_xyz_matrix_dict',
    'multiply_matrix_dicts',
    'matrix_dict_to_fusion_matrix',
    'apply_matrix_dict_to_brep',
    'decompose_matrix_dict'  # Matrix decomposition for composition service
]