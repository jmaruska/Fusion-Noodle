"""
Transform Composition Service - V2 Specification Compliant

Provides standardized transform composition for all effector nodes,
ensuring consistent data contracts and order-independent composition.
"""

from typing import Dict, Any, List
from ..contracts import NoodleAttributes, CollectionInstanceSpec
from ..utilities.log_utils import log, LogLevel
from ..utilities.transform_utils import (
    create_identity_matrix_dict, create_scale_matrix_dict, 
    create_rotation_xyz_matrix_dict, create_translation_matrix_dict,
    multiply_matrix_dicts, decompose_matrix_dict
)


class TransformCompositionService:
    """
    Unified service for composing transforms across effector chains.
    
    Ensures spec compliance:
    - Never returns None transforms
    - Handles all three valid transform formats
    - Provides order-independent composition
    """
    
    def __init__(self, app=None):
        self.app = app

    @staticmethod
    def _quaternion_to_euler_degrees(qx: float, qy: float, qz: float, qw: float):
        """Convert a quaternion to XYZ Euler angles in degrees (for matrix building)."""
        import math
        mag = (qx*qx + qy*qy + qz*qz + qw*qw) ** 0.5
        if mag > 0:
            qx, qy, qz, qw = qx/mag, qy/mag, qz/mag, qw/mag
        xx, yy, zz = qx*qx, qy*qy, qz*qz
        xy, xz, yz = qx*qy, qx*qz, qy*qz
        wx, wy, wz = qw*qx, qw*qy, qw*qz
        r02 = 2*(xz + wy)
        if abs(r02) < 0.99999:
            rx = math.atan2(-2*(yz - wx), 1 - 2*(xx + yy))
            ry = math.asin(max(-1.0, min(1.0, r02)))
            rz = math.atan2(-2*(xy - wz), 1 - 2*(yy + zz))
        else:
            ry = math.copysign(math.pi / 2, r02)
            rx = 0.0
            rz = math.atan2(2*(xy + wz), 1 - 2*(xx + zz))
        return math.degrees(rx), math.degrees(ry), math.degrees(rz)

    def extract_transform_components(self, transform_data: Any) -> Dict[str, Dict[str, float]]:
        """
        Extract scale/rotation/translation from ANY valid transform format.
        
        Returns:
            {
                'scale': {'x': sx, 'y': sy, 'z': sz},
                'rotation_degrees': {'x': rx, 'y': ry, 'z': rz},
                'translation': {'x': tx, 'y': ty, 'z': tz}
            }
        """
        if transform_data is None:
            # Spec compliance: Never None, return identity
            return {
                'scale': {'x': 1.0, 'y': 1.0, 'z': 1.0},
                'rotation_degrees': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                'translation': {'x': 0.0, 'y': 0.0, 'z': 0.0}
            }
            
        try:
            # Handle NoodleAttributes objects (Maya-style)
            if hasattr(transform_data, 'sx') and hasattr(transform_data, 'rx'):
                use_quat = getattr(transform_data, 'use_quaternion', False)
                if use_quat:
                    # Convert quaternion to Euler for component-wise composition.
                    # The final output of compose_noodle_attributes re-extracts a quaternion from the
                    # composed matrix via NoodleAttributes.from_matrix(), so precision is restored.
                    rx_deg, ry_deg, rz_deg = self._quaternion_to_euler_degrees(
                        getattr(transform_data, 'qx', 0.0),
                        getattr(transform_data, 'qy', 0.0),
                        getattr(transform_data, 'qz', 0.0),
                        getattr(transform_data, 'qw', 1.0),
                    )
                else:
                    rx_deg = getattr(transform_data, 'rx', 0.0)
                    ry_deg = getattr(transform_data, 'ry', 0.0)
                    rz_deg = getattr(transform_data, 'rz', 0.0)
                return {
                    'scale': {
                        'x': getattr(transform_data, 'sx', 1.0),
                        'y': getattr(transform_data, 'sy', 1.0),
                        'z': getattr(transform_data, 'sz', 1.0)
                    },
                    'rotation_degrees': {'x': rx_deg, 'y': ry_deg, 'z': rz_deg},
                    'translation': {
                        'x': getattr(transform_data, 'tx', 0.0),
                        'y': getattr(transform_data, 'ty', 0.0),
                        'z': getattr(transform_data, 'tz', 0.0)
                    }
                }

            # Handle dictionary formats
            elif isinstance(transform_data, dict):
                # Maya-style flat format
                if 'sx' in transform_data or 'tx' in transform_data or 'rx' in transform_data:
                    use_quat = transform_data.get('use_quaternion', False)
                    if use_quat:
                        rx_deg, ry_deg, rz_deg = self._quaternion_to_euler_degrees(
                            transform_data.get('qx', 0.0), transform_data.get('qy', 0.0),
                            transform_data.get('qz', 0.0), transform_data.get('qw', 1.0),
                        )
                    else:
                        rx_deg = transform_data.get('rx', 0.0)
                        ry_deg = transform_data.get('ry', 0.0)
                        rz_deg = transform_data.get('rz', 0.0)
                    return {
                        'scale': {
                            'x': transform_data.get('sx', 1.0),
                            'y': transform_data.get('sy', 1.0),
                            'z': transform_data.get('sz', 1.0)
                        },
                        'rotation_degrees': {'x': rx_deg, 'y': ry_deg, 'z': rz_deg},
                        'translation': {
                            'x': transform_data.get('tx', 0.0),
                            'y': transform_data.get('ty', 0.0),
                            'z': transform_data.get('tz', 0.0)
                        }
                    }
                
                # Legacy nested format
                elif all(k in transform_data for k in ['translation', 'rotation', 'scale']):
                    translation = transform_data.get('translation', {})
                    rotation = transform_data.get('rotation', {})
                    scale = transform_data.get('scale', {})
                    
                    return {
                        'scale': {
                            'x': scale.get('x', 1.0),
                            'y': scale.get('y', 1.0),
                            'z': scale.get('z', 1.0)
                        },
                        'rotation_degrees': {
                            'x': rotation.get('x', 0.0),
                            'y': rotation.get('y', 0.0),
                            'z': rotation.get('z', 0.0)
                        },
                        'translation': {
                            'x': translation.get('x', 0.0),
                            'y': translation.get('y', 0.0),
                            'z': translation.get('z', 0.0)
                        }
                    }
                
                # Matrix-based format
                elif (transform_data.get('transform_type') == 'matrix_chained' and 
                      'transform_matrix' in transform_data):
                    matrix_dict = transform_data['transform_matrix']
                    components = decompose_matrix_dict(matrix_dict)
                    return components
                
        except Exception as e:
            log(self.app, f"Transform extraction failed: {e}, using identity", 
                level=LogLevel.WARNING, module="TRANSFORM_COMPOSITION")
        
        # Fallback: identity transform (spec compliance - never None)
        return {
            'scale': {'x': 1.0, 'y': 1.0, 'z': 1.0},
            'rotation_degrees': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'translation': {'x': 0.0, 'y': 0.0, 'z': 0.0}
        }
    
    @staticmethod
    def _rotate_vector_by_quaternion(v, q):
        """Rotate vector v=(x,y,z) by quaternion q=(qx,qy,qz,qw). Used to convert local-space offsets to world space."""
        qx, qy, qz, qw = q
        vx, vy, vz = v
        # Rodrigues' formula via cross products (avoids full quaternion multiplication)
        tx = 2 * (qy*vz - qz*vy)
        ty = 2 * (qz*vx - qx*vz)
        tz = 2 * (qx*vy - qy*vx)
        return (
            vx + qw*tx + qy*tz - qz*ty,
            vy + qw*ty + qz*tx - qx*tz,
            vz + qw*tz + qx*ty - qy*tx,
        )

    @staticmethod
    def _euler_xyz_to_quaternion(rx_rad: float, ry_rad: float, rz_rad: float):
        """Convert XYZ Euler angles (radians) to a quaternion (qx, qy, qz, qw)."""
        import math
        cx, sx = math.cos(rx_rad / 2), math.sin(rx_rad / 2)
        cy, sy = math.cos(ry_rad / 2), math.sin(ry_rad / 2)
        cz, sz = math.cos(rz_rad / 2), math.sin(rz_rad / 2)
        qw = cx*cy*cz + sx*sy*sz
        qx = sx*cy*cz - cx*sy*sz
        qy = cx*sy*cz + sx*cy*sz
        qz = cx*cy*sz - sx*sy*cz
        return qx, qy, qz, qw

    @staticmethod
    def _quaternion_multiply(q1, q2):
        """Multiply two quaternions (qx,qy,qz,qw). Result = q1 * q2 (q2 applied in q1's local frame)."""
        x1, y1, z1, w1 = q1
        x2, y2, z2, w2 = q2
        return (
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2,
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
        )

    def compose_noodle_attributes(self, base_attributes: Any, new_attributes: Any, operation_chain: List[str] = None) -> 'NoodleAttributes':
        """
        Compose two NoodleAttributes component-wise.

        Effector composition semantics:
          - Scale:       multiplicative (applied at local origin, before placement)
          - Translation: additive       (world-space offset on top of surface point)
          - Rotation:    quaternion multiply when base uses quaternion, else additive Euler

        This avoids the matrix-order trap where scale * (surface_translate) explodes
        geometry outward by treating each component independently.
        """
        from ..contracts import NoodleAttributes
        import math

        base_components = self.extract_transform_components(base_attributes)
        new_components  = self.extract_transform_components(new_attributes)

        base_v        = getattr(base_attributes, 'v',        True)  if hasattr(base_attributes, 'v')        else True
        base_template = getattr(base_attributes, 'template', False) if hasattr(base_attributes, 'template') else False

        # Scale: multiply (local, doesn't affect position)
        sx = base_components['scale']['x'] * new_components['scale']['x']
        sy = base_components['scale']['y'] * new_components['scale']['y']
        sz = base_components['scale']['z'] * new_components['scale']['z']

        # Translation: rotate the effector's local-space offset by the base quaternion, then add.
        # When the base uses a quaternion (surface-aligned instance), the effector's translation
        # is in the instance's LOCAL frame (e.g. Z=2 means "2 units along surface normal").
        # We must rotate it into world space before adding to the world-space surface position.
        new_tx = new_components['translation']['x']
        new_ty = new_components['translation']['y']
        new_tz = new_components['translation']['z']

        base_uses_quat_for_translation = (
            isinstance(base_attributes, NoodleAttributes) and
            getattr(base_attributes, 'use_quaternion', False) and
            (new_tx != 0.0 or new_ty != 0.0 or new_tz != 0.0)
        )

        if base_uses_quat_for_translation:
            q = (base_attributes.qx, base_attributes.qy, base_attributes.qz, base_attributes.qw)
            world_offset = self._rotate_vector_by_quaternion((new_tx, new_ty, new_tz), q)
            tx = base_components['translation']['x'] + world_offset[0]
            ty = base_components['translation']['y'] + world_offset[1]
            tz = base_components['translation']['z'] + world_offset[2]
        else:
            tx = base_components['translation']['x'] + new_tx
            ty = base_components['translation']['y'] + new_ty
            tz = base_components['translation']['z'] + new_tz

        # Rotation
        new_rx = new_components['rotation_degrees']['x']
        new_ry = new_components['rotation_degrees']['y']
        new_rz = new_components['rotation_degrees']['z']
        new_has_rotation = (new_rx != 0.0 or new_ry != 0.0 or new_rz != 0.0)

        base_uses_quat = (
            isinstance(base_attributes, NoodleAttributes) and
            getattr(base_attributes, 'use_quaternion', False)
        )

        if base_uses_quat:
            if new_has_rotation:
                q_new = self._euler_xyz_to_quaternion(
                    math.radians(new_rx), math.radians(new_ry), math.radians(new_rz)
                )
                q_base = (base_attributes.qx, base_attributes.qy, base_attributes.qz, base_attributes.qw)
                qx, qy, qz, qw = self._quaternion_multiply(q_base, q_new)
            else:
                qx = base_attributes.qx
                qy = base_attributes.qy
                qz = base_attributes.qz
                qw = base_attributes.qw

            final_attributes = NoodleAttributes(
                tx=tx, ty=ty, tz=tz,
                rx=0.0, ry=0.0, rz=0.0,
                sx=sx, sy=sy, sz=sz,
                qx=qx, qy=qy, qz=qz, qw=qw,
                use_quaternion=True,
                v=base_v, template=base_template,
            )
        else:
            # Euler path: additive rotation
            rx = base_components['rotation_degrees']['x'] + new_rx
            ry = base_components['rotation_degrees']['y'] + new_ry
            rz = base_components['rotation_degrees']['z'] + new_rz
            final_attributes = NoodleAttributes(
                tx=tx, ty=ty, tz=tz,
                rx=rx, ry=ry, rz=rz,
                sx=sx, sy=sy, sz=sz,
                v=base_v, template=base_template,
            )

        if self.app:
            log(self.app,
                f"Composed: tx={final_attributes.tx:.3f}, ty={final_attributes.ty:.3f}, tz={final_attributes.tz:.3f}, "
                f"sx={final_attributes.sx:.3f}, use_quat={base_uses_quat}",
                level=LogLevel.DEBUG, module="TRANSFORM_COMPOSITION")

        return final_attributes
