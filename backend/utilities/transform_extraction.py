"""Transform utilities for v2 - Maya-style flattened attributes generation.
Creates NoodleAttributes objects directly, avoiding nested serialization issues.
"""

from typing import Dict, List
from .log_utils import log, LogLevel
from ..contracts import NoodleAttributes

try:
    import adsk.core  # type: ignore
    import adsk.fusion  # type: ignore
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


def extract_noodle_attributes_from_matrix(transform_matrix, source_scale_dict: Dict[str, float], app=None) -> NoodleAttributes:
    """
    Extract NoodleAttributes from a Fusion 360 Matrix3D using quaternion rotation.

    Quaternions avoid gimbal lock and round-trip precisely through composition.
    Source scale (from the input geometry) is preserved via source_scale_dict,
    since surface-placement matrices always have unit scale.
    """
    try:
        if not hasattr(transform_matrix, 'getCell'):
            return NoodleAttributes.identity()

        # Build the standard matrix_dict expected by NoodleAttributes.from_matrix()
        matrix_dict = {
            'm00': transform_matrix.getCell(0, 0), 'm01': transform_matrix.getCell(0, 1),
            'm02': transform_matrix.getCell(0, 2), 'm03': transform_matrix.getCell(0, 3),
            'm10': transform_matrix.getCell(1, 0), 'm11': transform_matrix.getCell(1, 1),
            'm12': transform_matrix.getCell(1, 2), 'm13': transform_matrix.getCell(1, 3),
            'm20': transform_matrix.getCell(2, 0), 'm21': transform_matrix.getCell(2, 1),
            'm22': transform_matrix.getCell(2, 2), 'm23': transform_matrix.getCell(2, 3),
            'm30': 0.0, 'm31': 0.0, 'm32': 0.0, 'm33': 1.0,
        }

        # Extract position + quaternion rotation from the matrix
        attrs = NoodleAttributes.from_matrix(matrix_dict)

        # Surface-placement matrices have unit scale; use the source geometry's scale instead
        sx = source_scale_dict.get('x', 1.0) or 1.0
        sy = source_scale_dict.get('y', 1.0) or 1.0
        sz = source_scale_dict.get('z', 1.0) or 1.0

        log(app, f"Transform extraction: quaternion rotation, scale=({sx},{sy},{sz})",
            level=LogLevel.DEBUG, module="TRANSFORM_UTILS")

        return NoodleAttributes(
            tx=attrs.tx, ty=attrs.ty, tz=attrs.tz,
            rx=0.0, ry=0.0, rz=0.0,
            sx=sx, sy=sy, sz=sz,
            qx=attrs.qx, qy=attrs.qy, qz=attrs.qz, qw=attrs.qw,
            use_quaternion=True,
        )

    except Exception as e:
        log(app, f"Error extracting attributes: {e}",
            level=LogLevel.WARNING, module="TRANSFORM_UTILS")
        return NoodleAttributes.identity()


def batch_extract_noodle_attributes(transformation_matrices, source_scale_dict: Dict[str, float], app=None) -> List[NoodleAttributes]:
    """
    Extract Maya-style attributes from multiple matrices efficiently.
    
    Args:
        transformation_matrices: List of Fusion 360 Matrix3D objects
        source_scale_dict: Scale dictionary from source geometry
        app: Application reference for logging
        
    Returns:
        List of NoodleAttributes objects (no nested serialization issues!)
    """
    attributes_list = []
    
    for i, matrix in enumerate(transformation_matrices):
        noodle_attrs = extract_noodle_attributes_from_matrix(matrix, source_scale_dict, app)
        attributes_list.append(noodle_attrs)
    
    log(app, f"Extracted {len(attributes_list)} Maya-style NoodleAttributes objects",
        level=LogLevel.DEBUG, module="TRANSFORM_UTILS")
    
    return attributes_list

