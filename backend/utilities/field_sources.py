"""
Field shapes for the falloff nodes: where an instance sits in the field, as t from 0 to 1.

The Shape dropdown on a Falloff node picks one; the ports that place it (points, sizes,
directions) live on the node and show only for their shape. How the field fades with t is
the falloff curve, edited in the curve editor (field_curve.py). See docs/dev/falloff-fields.md.

  sphere   t runs from Inner Radius to Radius, measured from the center
  box      the same, but distance is measured square: the largest of the three distances
           along the box's axes, so every contour of the fade is a box
  linear   t runs from the start point to the end point, along the line between them;
           before the start it stays 0 and past the end it stays 1

Sphere and Box share their controls. Scale stretches the field along its local axes (a sphere
becomes an ellipsoid, a cube a box), measured in that stretched space; the X Axis and
the Y Axis turn it (local Z completes the frame). Scale's x, y and z follow those local
axes, and the defaults are the world axes. With Scale 1, 1, 1 a sphere looks the same however
it is turned.
"""

import math
from typing import Any, Dict, List, Tuple

from ..contracts import PortSpec, PortType, port_label
from .field_curve import curve_problems, default_curve_json, field_curve

SHAPES = ('sphere', 'linear', 'box')
SHAPE_LABELS = {'sphere': 'Sphere', 'linear': 'Linear', 'box': 'Box'}
DEFAULT_SHAPE = 'sphere'

_ORIGIN = {'x': 0.0, 'y': 0.0, 'z': 0.0}


def _when(*shapes: str) -> Dict[str, Any]:
    return {'port': 'shape', 'values': list(shapes), 'default': DEFAULT_SHAPE}


def shape_ports(center_name: str) -> List[PortSpec]:
    """The shape dropdown, the ports that place each shape, and the curve, in node order.
    `center_name` keeps each node's existing name for the center port."""
    round_or_square = _when('sphere', 'box')
    return [
        PortSpec("shape", PortType.ENUM, default_value=DEFAULT_SHAPE, enum_options=list(SHAPES),
                 enum_labels=dict(SHAPE_LABELS), show_input_handle=False, label="Shape", description="How position becomes strength: distance from a center, progress along a line, or distance from a box."),
        PortSpec(center_name, PortType.VECTOR3, unit="length", default_value=dict(_ORIGIN), label="Center",
                 description="The middle of the sphere or box.", visible_when=round_or_square),
        PortSpec("start", PortType.VECTOR3, unit="length", default_value=dict(_ORIGIN), label="Start",
                 visible_when=_when('linear'), description="Where the line begins; instances at or before it get the curve's start value."),
        PortSpec("end", PortType.VECTOR3, unit="length", default_value={'x': 10.0, 'y': 0.0, 'z': 0.0}, label="End",
                 visible_when=_when('linear'), description="Where the line ends; instances at or past it get the curve's end value."),
        PortSpec("radius", PortType.FLOAT, unit="length", default_value=10.0, min_value=0.001, label="Radius",
                 visible_when=round_or_square, description="Distance from the center where the fade reaches the curve's end value."),
        PortSpec("inner_radius", PortType.FLOAT, unit="length", default_value=0.0, min_value=0.0, label="Inner Radius",
                 visible_when=round_or_square, description="Distance from the center where the fade begins; inside it the curve's start value holds."),
        PortSpec("scale", PortType.VECTOR3, default_value={'x': 1.0, 'y': 1.0, 'z': 1.0}, label="Scale",
                 description="Stretches the field along its local axes.", visible_when=round_or_square),
        PortSpec("direction", PortType.VECTOR3, default_value={'x': 1.0, 'y': 0.0, 'z': 0.0}, label="X Axis",
                 description="The field's local X axis; Scale x stretches along it.", visible_when=round_or_square),
        PortSpec("up", PortType.VECTOR3, default_value={'x': 0.0, 'y': 1.0, 'z': 0.0}, label="Y Axis",
                 description="The field's local Y axis, squared up to the X Axis; Scale y stretches along it.",
                 visible_when=round_or_square),
        PortSpec("curve", PortType.STRING, default_value=default_curve_json(),
                 show_input_field=False, show_input_handle=False, label="Curve",
                 description="How strength changes across the field; shape it in the curve editor."),
    ]


def _vec(v: Any, default: Dict[str, float]) -> Tuple[float, float, float]:
    if isinstance(v, dict):
        return (float(v.get('x', default['x'])), float(v.get('y', default['y'])), float(v.get('z', default['z'])))
    if hasattr(v, 'x'):
        return (float(v.x), float(v.y), float(v.z))
    return (default['x'], default['y'], default['z'])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = _dot(a, a) ** 0.5
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else None


_ONE = {'x': 1.0, 'y': 1.0, 'z': 1.0}
MIN_SCALE = 1e-6


def _scale(params: Dict[str, Any]) -> Tuple[float, float, float]:
    return tuple(max(MIN_SCALE, abs(c)) for c in _vec(params.get('scale'), _ONE))


def box_axes(x_axis: Any, y_axis: Any) -> Tuple[Tuple[float, float, float], ...]:
    """Local X, Y, Z of a field: X along the X Axis, Y as close to the Y Axis as X allows,
    Z = X × Y. The defaults give the world axes. A zero X Axis counts as world X; a Y Axis that
    is zero or parallel to X is replaced by the world axis furthest from X."""
    x = _unit(_vec(x_axis, {'x': 1.0, 'y': 0.0, 'z': 0.0})) or (1.0, 0.0, 0.0)

    def squared(v):
        return _unit(_sub(v, tuple(_dot(v, x) * c for c in x)))

    y = squared(_vec(y_axis, {'x': 0.0, 'y': 1.0, 'z': 0.0}))
    if y is None:
        helper = min(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), key=lambda a: abs(_dot(a, x)))
        y = squared(helper)
    z = _cross(x, y)
    return x, y, z


def field_t(shape: str, params: Dict[str, Any], point: Tuple[float, float, float], center_name: str) -> Tuple[float, bool]:
    """(t, start_flat) for a point. start_flat says whether t = 0 meets a flat region."""
    if shape == 'linear':
        a, b = _vec(params.get('start'), _ORIGIN), _vec(params.get('end'), {'x': 10.0, 'y': 0.0, 'z': 0.0})
        ab = _sub(b, a)
        length2 = _dot(ab, ab)
        t = _dot(_sub(point, a), ab) / length2 if length2 > 1e-12 else 0.0
        return min(1.0, max(0.0, t)), True
    center = _vec(params.get(center_name), _ORIGIN)
    radius = float(params.get('radius', 10.0))
    inner = float(params.get('inner_radius', 0.0))
    axes = box_axes(params.get('direction'), params.get('up'))
    scale = _scale(params)
    d = _sub(point, center)
    local = [_dot(d, axis) / s for axis, s in zip(axes, scale)]
    if shape == 'box':
        distance = max(abs(c) for c in local)
    else:
        distance = sum(c * c for c in local) ** 0.5
    span = radius - inner
    if span <= 0:
        return (0.0 if distance <= inner else 1.0), inner > 0
    return min(1.0, max(0.0, (distance - inner) / span)), inner > 0


def field_strength(params: Dict[str, Any], point: Tuple[float, float, float], center_name: str) -> float:
    """Strength at a point for a falloff node's inputs (or a falloff modifier's config)."""
    shape = params.get('shape') if params.get('shape') in SHAPES else DEFAULT_SHAPE
    t, start_flat = field_t(shape, params, point, center_name)
    return field_curve(params.get('curve'), start_flat).value(t)


def _label(name: str) -> str:
    """The palette label of one of the shape ports, for naming it in a message."""
    for port in shape_ports('center'):
        if port.name == name:
            return port_label(port.name, port.label)
    return port_label(name)


def shape_problems(params: Dict[str, Any]) -> List[str]:
    """Reasons a falloff node's shape inputs can't be used, in words. Only the chosen shape is checked."""
    errors: List[str] = []
    shape = params.get('shape', DEFAULT_SHAPE)
    if shape not in SHAPES:
        return [f"{_label('shape')} must be one of: {', '.join(SHAPE_LABELS.values())}"]
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if shape in ('sphere', 'box'):
        radius = params.get('radius', 10.0)
        inner = params.get('inner_radius', 0.0)
        if not num(radius) or radius <= 0:
            errors.append(f"{_label('radius')} must be more than 0")
        if not num(inner) or inner < 0:
            errors.append(f"{_label('inner_radius')} can't be negative")
        elif num(radius) and inner >= radius:
            errors.append(f"{_label('inner_radius')} must be less than {_label('radius')}")
        if any(abs(c) < MIN_SCALE for c in _vec(params.get('scale'), _ONE)):
            errors.append(f"{_label('scale')} can't be 0 along any axis")
        if _unit(_vec(params.get('direction'), {'x': 1.0, 'y': 0.0, 'z': 0.0})) is None:
            errors.append(f"{_label('direction')} can't be zero")
    if shape == 'linear':
        a, b = _vec(params.get('start'), _ORIGIN), _vec(params.get('end'), {'x': 10.0, 'y': 0.0, 'z': 0.0})
        if _dot(_sub(b, a), _sub(b, a)) < 1e-12:
            errors.append(f"{_label('start')} and {_label('end')} are the same point, so the falloff has no direction")
    errors.extend(curve_problems(params.get('curve')))
    return errors


# ───────────────────────────── outlines ─────────────────────────────
# Faint guides for the visualizer: where each shape sits. Pure geometry here; the
# visualizer draws them (backend/visualizer.py). All coordinates in cm.

FALLOFF_NODE_CENTER = {'Falloff_Effector': 'position', 'Modifier_Falloff': 'center'}


def _circle(center, u, v, radius, segments=72):
    """A closed polyline: center + radius (cos a · u + sin a · v)."""
    return [tuple(center[k] + radius * (math.cos(a) * u[k] + math.sin(a) * v[k]) for k in range(3))
            for a in (2 * math.pi * i / segments for i in range(segments + 1))]


def _perpendicular(axis):
    """Two unit vectors at right angles to `axis` and to each other."""
    helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _unit(_cross(axis, helper))
    return u, _cross(axis, u)


def _box_edges(center, axes, half):
    """The 12 edges of a box as 2-point polylines."""
    corners = {}
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                corners[(sx, sy, sz)] = tuple(
                    center[k] + sx * half[0] * axes[0][k] + sy * half[1] * axes[1][k] + sz * half[2] * axes[2][k]
                    for k in range(3))
    edges = []
    for key, a in corners.items():
        for axis in range(3):
            if key[axis] < 0:
                other = list(key)
                other[axis] = 1
                edges.append([a, corners[tuple(other)]])
    return edges


def field_outline(params: Dict[str, Any], center_name: str, points=()) -> Dict[str, Any]:
    """Polylines that show where a falloff sits.

    Returns {'solid': [polyline, ...], 'dashed': [...], 'ellipsoids': [(center, axes, semi_axes, dashed)]}.
    An ellipsoid's outline depends on the view, so it is left for the visualizer to trace from
    the camera (ellipsoid_rim). `points` (instance positions) size the rings on a Linear falloff.
    """
    out: Dict[str, Any] = {'solid': [], 'dashed': [], 'ellipsoids': []}
    shape = params.get('shape') if params.get('shape') in SHAPES else DEFAULT_SHAPE
    if shape in ('sphere', 'box'):
        center = _vec(params.get(center_name), _ORIGIN)
        axes = box_axes(params.get('direction'), params.get('up'))
        scale = _scale(params)
        radius = max(0.0, float(params.get('radius', 10.0) or 0.0))
        inner = max(0.0, float(params.get('inner_radius', 0.0) or 0.0))
        for r, dashed in ((radius, False), (inner, True)):
            if r <= 0 or (dashed and r >= radius):
                continue
            semi = tuple(r * s for s in scale)
            if shape == 'sphere':
                out['ellipsoids'].append((center, axes, semi, dashed))
            else:
                out['dashed' if dashed else 'solid'].extend(_box_edges(center, axes, semi))
        return out

    if shape == 'linear':
        a, b = _vec(params.get('start'), _ORIGIN), _vec(params.get('end'), {'x': 10.0, 'y': 0.0, 'z': 0.0})
        ab = _sub(b, a)
        length = _dot(ab, ab) ** 0.5
        if length < 1e-9:
            return out
        axis = tuple(c / length for c in ab)
        u, v = _perpendicular(axis)
        # Rings wide enough to frame the instances, within reason
        reach = 0.0
        for p in points:
            d = _sub(p, a)
            along = _dot(d, axis)
            reach = max(reach, _dot(d, d) - along * along)
        ring = min(2.0 * length, max(0.1 * length, reach ** 0.5)) if reach > 0 else 0.25 * length
        out['solid'].append([a, b])
        head = 0.06 * length
        back = tuple(b[k] - head * 2 * axis[k] for k in range(3))
        out['solid'].append([tuple(back[k] + head * u[k] for k in range(3)), b,
                             tuple(back[k] - head * u[k] for k in range(3))])
        out['dashed'].append(_circle(a, u, v, ring))
        out['dashed'].append(_circle(b, u, v, ring))
        return out


def ellipsoid_rim(center, axes, semi, eye=None, view=None, segments: int = 96) -> list:
    """The silhouette of an ellipsoid seen from a camera, as a closed polyline.

    Squash the ellipsoid to a unit sphere (q_i = (p - center) · axis_i / semi_i): there the
    outline seen from an eye point e is the circle of points with q · e = 1, and from a
    direction v (orthographic) the great circle with q · v = 0. Stretching that circle back
    gives the exact silhouette, since the stretch keeps tangency. Pass `eye` for a perspective
    camera, `view` (the viewing direction) for an orthographic one. Empty when the eye is inside.
    """
    def to_unit(vector):
        return tuple(_dot(vector, axes[i]) / semi[i] for i in range(3))

    if eye is not None:
        e = to_unit(_sub(eye, center))
        n2 = _dot(e, e)
        if n2 <= 1.0 + 1e-9:
            return []
        n = n2 ** 0.5
        w = tuple(c / n for c in e)
        rim_center, r = tuple(c / n2 for c in e), (1.0 - 1.0 / n2) ** 0.5
    else:
        w = _unit(to_unit(view if view is not None else (0.0, 0.0, 1.0))) or (0.0, 0.0, 1.0)
        rim_center, r = (0.0, 0.0, 0.0), 1.0
    u, v = _perpendicular(w)
    rim = []
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        q = tuple(rim_center[k] + r * (math.cos(a) * u[k] + math.sin(a) * v[k]) for k in range(3))
        rim.append(tuple(center[k] + sum(semi[j] * q[j] * axes[j][k] for j in range(3)) for k in range(3)))
    return rim
