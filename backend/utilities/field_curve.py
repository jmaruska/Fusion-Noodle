"""
Falloff curve: the shape a field uses to turn t (0 at the start, 1 at the end) into strength.

ui/src/utils/fieldCurve.js is the same code in JavaScript, used by the curve editor. Both run
the examples in tests/fixtures/field_curve_vectors.json, so a change to one must be made to the
other. The design is in docs/dev/falloff-fields.md.

The user draws one tile: a clamped, uniform B-spline with x increasing, normally with a level
tangent (two points at one height) at each end. The field never uses that tile as drawn. Each
tile is derived from what its two ends meet:
  center   the sphere's center (Inner 0): nothing, the profile meets its own mirror image
  flat     the inner plateau or the outer edge: a third level point, G2 to flat
  mirror   a Mirror repeat seam: the level neighbour slides back to the drawn curvature
  restart  a Restart repeat seam: the level points either side are linked; the `lead` side
           keeps its curvature and the other side slides to match it
  open     nothing at all, as with a Gradient's first and last instance: used as drawn

A curve is stored on a node as a JSON string:

    {"degree": 3, "points": [[0, 1], [0.2, 1], [0.65, 0], [1, 0]],
     "repeat": 1, "repeat_style": "mirror", "decay": 0, "invert": false,
     "lead": "start", "output": {"start": 1, "end": 0}}
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple

HOLD_AT = 0.3     # The added level point splits the level leg 30% in from the end point
GAP = 0.004       # Smallest x spacing between neighbouring points
TINY = 1e-6
TABLE_SIZE = 1024

PRESETS: Dict[str, Dict[str, Any]] = {
    'Smooth':   {'points': [[0, 1], [.2, 1], [.65, 0], [1, 0]]},
    'Gaussian': {'points': [[0, 1], [.07, 1], [.32, .3], [.55, 0], [1, 0]]},
    'Linear':   {'points': [[0, 1], [1 / 3, 2 / 3], [2 / 3, 1 / 3], [1, 0]]},
    'Ease out': {'points': [[0, 1], [.06, 1], [.12, .7], [.35, .08], [.75, 0], [1, 0]]},
    'Plateau':  {'points': [[0, 1], [.25, 1], [.55, 1], [.8, 0], [1, 0]]},
    'Ring':     {'points': [[0, 0], [.12, 0], [.42, 1], [.58, 1], [.88, 0], [1, 0]]},
    'Ripple':   {'points': [[0, 1], [.2, 1], [.65, 0], [1, 0]], 'repeat': 5, 'repeat_style': 'mirror', 'decay': .7},
    'Pulse':    {'points': [[0, 0], [.06, 0], [.2, 1], [.3, 1], [.72, 0], [1, 0]], 'repeat': 4, 'repeat_style': 'restart', 'decay': .4},
}
DEFAULT_CURVE_NAME = 'Smooth'


def preset_curve(name: str) -> Dict[str, Any]:
    pr = PRESETS[name]
    return normalize_curve({
        'points': [list(q) for q in pr['points']],
        'repeat': pr.get('repeat', 1),
        'repeat_style': pr.get('repeat_style', 'mirror'),
        'decay': pr.get('decay', 0),
    })


def default_curve_json(name: str = DEFAULT_CURVE_NAME) -> str:
    return json.dumps(preset_curve(name), separators=(',', ':'))


def _num(v: Any, fallback: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return fallback
    return float(v)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def normalize_curve(value: Any) -> Dict[str, Any]:
    """A complete, valid curve from anything: a JSON string, a partial dict, or nothing."""
    c = value
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except (ValueError, TypeError):
            c = None
    if not isinstance(c, dict):
        return preset_curve(DEFAULT_CURVE_NAME)
    degree = 5 if c.get('degree') == 5 else 3
    raw = c.get('points') if isinstance(c.get('points'), list) else []
    pts = [[_num(q[0], 0.0), _clamp(_num(q[1], 0.0), 0.0, 1.0)]
           for q in raw if isinstance(q, (list, tuple)) and len(q) >= 2]
    if len(pts) < 2:
        pts = [list(q) for q in PRESETS[DEFAULT_CURVE_NAME]['points']]
    pts.sort(key=lambda q: q[0])
    pts[0][0] = 0.0
    pts[-1][0] = 1.0
    for q in pts[1:-1]:
        q[0] = _clamp(q[0], 0.0, 1.0)
    pts = ensure_enough_points(pts, degree)
    out = c.get('output') if isinstance(c.get('output'), dict) else {}
    return {
        'degree': degree,
        'points': pts,
        'repeat': int(_clamp(math.floor(_num(c.get('repeat'), 1) + 0.5), 1, 12)),  # rounds like JS Math.round
        'repeat_style': 'restart' if c.get('repeat_style') == 'restart' else 'mirror',
        'decay': _clamp(_num(c.get('decay'), 0.0), 0.0, 1.0),
        'invert': c.get('invert') is True,
        'lead': 'end' if c.get('lead') == 'end' else 'start',
        'output': {'start': _num(out.get('start'), 1.0), 'end': _num(out.get('end'), 0.0)},
    }


def curve_problems(value: Any) -> List[str]:
    """Reasons a stored curve can't be used as it is. Empty when it is fine."""
    c = value
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except (ValueError, TypeError):
            return ['The falloff curve is not readable. Open the curve editor and pick a preset.']
    if c is None:
        return []
    if not isinstance(c, dict) or not isinstance(c.get('points'), list) or len(c['points']) < 2:
        return ['The falloff curve has no points. Open the curve editor and pick a preset.']
    xs = [q[0] for q in c['points'] if isinstance(q, (list, tuple)) and len(q) >= 2]
    if any(b <= a for a, b in zip(xs, xs[1:])):
        return ['The falloff curve doubles back on itself. Open the curve editor and move the points apart.']
    return []


def ensure_enough_points(pts: List[List[float]], degree: int) -> List[List[float]]:
    """Quintic needs at least six points: add midpoints along the widest legs until there are enough."""
    c = [list(q) for q in pts]
    while len(c) < degree + 1:
        widest = 0
        for i in range(1, len(c) - 1):
            if c[i + 1][0] - c[i][0] > c[widest + 1][0] - c[widest][0]:
                widest = i
        a, b = c[widest], c[widest + 1]
        c.insert(widest + 1, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
    return c


def tile_count(curve: Dict[str, Any]) -> int:
    return 2 * curve['repeat'] - 1 if curve['repeat_style'] == 'mirror' else curve['repeat']


# ---------- B-spline ----------

def knot_vector(n: int, deg: int) -> List[float]:
    """Clamped, uniform knots for n + 1 control points."""
    m = n + deg + 1
    return [0.0 if i <= deg else 1.0 if i >= m - deg else (i - deg) / (n - deg + 1) for i in range(m + 1)]


def de_boor(P: List[Tuple[float, float]], deg: int, t: List[float], u: float) -> Tuple[float, float]:
    n = len(P) - 1
    k = deg
    if u >= t[n + 1]:
        k = n
    else:
        while k < n and u >= t[k + 1]:
            k += 1
    d = [list(P[j + k - deg]) for j in range(deg + 1)]
    for r in range(1, deg + 1):
        for j in range(deg, r - 1, -1):
            den = t[j + 1 + k - r] - t[j + k - deg]
            a = 0.0 if den == 0 else (u - t[j + k - deg]) / den
            d[j] = [(1 - a) * d[j - 1][0] + a * d[j][0], (1 - a) * d[j - 1][1] + a * d[j][1]]
    return d[deg][0], d[deg][1]


def one_sided(f, t0: float, h: float, direction: int) -> Tuple[float, float, float]:
    """Value, first and second derivative of f at t0, from one side only."""
    v = [f(t0 + direction * k * h) for k in range(5)]
    d1 = (-25 * v[0] + 48 * v[1] - 36 * v[2] + 16 * v[3] - 3 * v[4]) / (12 * h) * direction
    d2 = (35 * v[0] - 104 * v[1] + 114 * v[2] - 56 * v[3] + 11 * v[4]) / (12 * h * h)
    return v[0], d1, d2


def _level(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return abs(a['y'] - b['y']) < 1e-9


def _end_bend(cvs: List[Dict[str, Any]], at_end: bool, deg: int) -> float:
    """y''(x) at one end. With a level tangent, moving the level neighbour to distance d from the
    end scales this by 1/d^2 and changes nothing else, so a seam is matched by sliding one point."""
    P = [(c['x'], c['y']) for c in cvs]
    t = knot_vector(len(P) - 1, deg)
    u0, direction, h = (1.0, -1, 1e-3) if at_end else (0.0, 1, 1e-3)
    X = one_sided(lambda u: de_boor(P, deg, t, u)[0], u0, h, direction)
    Y = one_sided(lambda u: de_boor(P, deg, t, u)[1], u0, h, direction)
    return Y[2] / (X[1] * X[1]) - Y[1] * X[2] / (X[1] * X[1] * X[1])


def _add_start_hold(c: List[Dict[str, Any]]) -> None:
    if len(c) > 2 and _level(c[0], c[1]) and not _level(c[0], c[2]):
        c.insert(1, {'x': c[0]['x'] + HOLD_AT * (c[1]['x'] - c[0]['x']), 'y': c[0]['y'], 'src': None})


def _add_end_hold(c: List[Dict[str, Any]]) -> None:
    n = len(c) - 1
    if n > 1 and _level(c[n], c[n - 1]) and not _level(c[n], c[n - 2]):
        c.insert(n, {'x': c[n]['x'] - HOLD_AT * (c[n]['x'] - c[n - 1]['x']), 'y': c[n]['y'], 'src': None})


def _seam_plan(curve: Dict[str, Any]) -> Dict[str, Any]:
    c = [{'x': x, 'y': y} for x, y in curve['points']]
    n, deg = len(c) - 1, curve['degree']
    start_level, end_level = _level(c[0], c[1]), _level(c[n], c[n - 1])
    ks = _end_bend(c, False, deg) if start_level else 0.0
    ke = _end_bend(c, True, deg) if end_level else 0.0
    plan = {'ks': ks, 'ke': ke, 'restart': 'none', 'target': 0.0}
    if start_level and end_level and _level(c[0], c[n]) and not (abs(ks) < TINY and abs(ke) < TINY):
        if ks * ke <= 0 or abs(ks) < TINY or abs(ke) < TINY:
            plan['restart'] = 'flat'
        else:
            plan['restart'] = 'match'
            plan['target'] = ke if curve['lead'] == 'end' else ks
    return plan


def _slide(c: List[Dict[str, Any]], at_end: bool, target: float, deg: int) -> None:
    n = len(c) - 1
    end, nb, far = (c[n], c[n - 1], c[n - 2]) if at_end else (c[0], c[1], c[2])
    if not _level(end, nb) or _level(end, far) or not target:
        return
    k = _end_bend(c, at_end, deg)
    if not k * target > 0:
        return
    d = abs(end['x'] - nb['x']) * math.sqrt(k / target)
    if at_end:
        x = max(far['x'] + GAP, min(end['x'] - GAP, end['x'] - d))
    else:
        x = min(far['x'] - GAP, max(end['x'] + GAP, end['x'] + d))
    if abs(x - nb['x']) > 1e-4:
        nb['x'] = x


def _tile_cvs(curve: Dict[str, Any], start_meets: str, end_meets: str, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    deg = curve['degree']
    c = [{'x': x, 'y': y, 'src': i} for i, (x, y) in enumerate(curve['points'])]
    flat_restart = plan['restart'] == 'flat'
    if start_meets == 'flat' or (start_meets == 'restart' and flat_restart):
        _add_start_hold(c)
    if end_meets == 'flat' or (end_meets == 'restart' and flat_restart):
        _add_end_hold(c)
    if start_meets == 'mirror':
        _slide(c, False, plan['ks'], deg)
    if end_meets == 'mirror':
        _slide(c, True, plan['ke'], deg)
    if plan['restart'] == 'match':
        if start_meets == 'restart':
            _slide(c, False, plan['target'], deg)
        if end_meets == 'restart':
            _slide(c, True, plan['target'], deg)
    return c


def _tile_ends(i: int, n: int, curve: Dict[str, Any], start_flat: bool,
               open_ends: bool) -> Tuple[str, str, bool]:
    """What each end of tile i meets. Mirror tiles run backwards on odd counts."""
    seam = 'mirror' if curve['repeat_style'] == 'mirror' else 'restart'
    left = ('open' if open_ends else 'flat' if start_flat else 'center') if i == 0 else seam
    right = ('open' if open_ends else 'flat') if i == n - 1 else seam
    flipped = curve['repeat_style'] == 'mirror' and i % 2 == 1
    return (right, left, True) if flipped else (left, right, False)


class _Tile:
    def __init__(self, cvs: List[Dict[str, Any]], deg: int):
        self.P = [(c['x'], c['y']) for c in cvs]
        self.deg = deg
        self.t = knot_vector(len(self.P) - 1, deg)
        self._xs: Optional[List[float]] = None
        self._ys: Optional[List[float]] = None

    def y_exact(self, x: float) -> float:
        x = _clamp(x, 0.0, 1.0)
        lo, hi = 0.0, 1.0
        for _ in range(52):
            mid = (lo + hi) / 2
            if de_boor(self.P, self.deg, self.t, mid)[0] < x:
                lo = mid
            else:
                hi = mid
        return de_boor(self.P, self.deg, self.t, (lo + hi) / 2)[1]

    def y_fast(self, x: float) -> float:
        if self._xs is None:
            pts = [de_boor(self.P, self.deg, self.t, i / TABLE_SIZE) for i in range(TABLE_SIZE + 1)]
            self._xs = [q[0] for q in pts]
            self._ys = [q[1] for q in pts]
        xs, ys = self._xs, self._ys
        x = _clamp(x, 0.0, 1.0)
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) >> 1
            if xs[mid] < x:
                lo = mid
            else:
                hi = mid
        span = xs[hi] - xs[lo]
        return ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / span if span > 0 else ys[lo]


def _smootherstep(t: float) -> float:
    """Zero slope and curvature at both ends, so decay never adds a crease."""
    return t * t * t * (t * (t * 6 - 15) + 10)


class FieldCurve:
    """A curve ready to evaluate. `start_flat` is True when t = 0 meets a flat region (a sphere
    with an inner radius) and False when it is the sphere's center. `open_ends` is True when
    nothing lies beyond t = 0 and t = 1 (a Gradient along a strand): the ends are used as drawn."""

    def __init__(self, curve: Any, start_flat: bool = False, open_ends: bool = False):
        self.curve = normalize_curve(curve)
        plan = _seam_plan(self.curve)
        self.n = tile_count(self.curve)
        by_key: Dict[str, _Tile] = {}
        self.tiles: List[Tuple[_Tile, bool]] = []
        for i in range(self.n):
            start_meets, end_meets, flipped = _tile_ends(i, self.n, self.curve, start_flat, open_ends)
            key = start_meets + '|' + end_meets
            if key not in by_key:
                by_key[key] = _Tile(_tile_cvs(self.curve, start_meets, end_meets, plan), self.curve['degree'])
            self.tiles.append((by_key[key], flipped))

    def shape(self, t: float, exact: bool = False) -> float:
        """0..1 from the curve, after repeats, invert and decay; before the output range."""
        t = _clamp(t, 0.0, 1.0)
        s = t * self.n
        i = int(math.floor(s))
        f = s - i
        if i >= self.n:
            i, f = self.n - 1, 1.0
        tile, flipped = self.tiles[i]
        if flipped:
            f = 1.0 - f
        v = tile.y_exact(f) if exact else tile.y_fast(f)
        if self.curve['invert']:
            v = 1.0 - v
        return v * (1.0 - self.curve['decay'] * _smootherstep(t))

    def value(self, t: float, exact: bool = False) -> float:
        """Strength at t: the shape mapped from 0..1 onto the output range."""
        out = self.curve['output']
        return out['end'] + (out['start'] - out['end']) * self.shape(t, exact)


def fit_curve(f, open_ends: bool = True, tolerance: float = 0.005, max_points: int = 12,
              samples: int = 201) -> Tuple[Dict[str, Any], float]:
    """The simplest cubic curve that follows f(t) for t in 0..1, and its largest error.

    For converting older shapes. Control points sit at the Greville abscissae of their knots,
    which makes the curve's x equal t exactly, so fitting the heights is linear least squares.
    Point counts from 4 to max_points are tried and the first within `tolerance` wins.
    Values are mapped onto 0..1 with the output range, so f may run outside 0..1.
    """
    ts = [i / (samples - 1) for i in range(samples)]
    vs = [float(f(t)) for t in ts]
    lo, hi = min(vs), max(vs)
    if hi - lo < 1e-9:
        curve = normalize_curve({'points': [[0, 1], [1 / 3, 1], [2 / 3, 1], [1, 1]],
                                 'output': {'start': lo, 'end': lo}})
        return curve, 0.0
    in_unit = lo >= 0.0 and hi <= 1.0
    out_lo, out_hi = (0.0, 1.0) if in_unit else (lo, hi)
    ys = [(v - out_lo) / (out_hi - out_lo) for v in vs]

    best = None
    for count in range(4, max_points + 1):
        deg, n = 3, count - 1
        knots = knot_vector(n, deg)
        xs = [sum(knots[i + 1:i + deg + 1]) / deg for i in range(count)]
        # Basis functions at every sample: the curve with one control point raised to 1
        basis = []
        for i in range(count):
            P = [(xs[j], 1.0 if j == i else 0.0) for j in range(count)]
            basis.append([de_boor(P, deg, knots, t)[1] for t in ts])
        heights = _least_squares(basis, ys)
        curve = normalize_curve({'degree': 3, 'points': [[x, _clamp(h, 0.0, 1.0)] for x, h in zip(xs, heights)],
                                 'output': {'start': out_hi, 'end': out_lo}})
        fitted = FieldCurve(curve, open_ends=open_ends)
        error = max(abs(fitted.value(t, exact=True) - v) for t, v in zip(ts[::4], vs[::4]))
        if best is None or error < best[1]:
            best = (curve, error)
        if error <= tolerance:
            break
    return best


def _least_squares(basis: List[List[float]], ys: List[float]) -> List[float]:
    """Solve the normal equations (B Bᵀ) c = B y by Gaussian elimination with pivoting."""
    m = len(basis)
    A = [[sum(a * b for a, b in zip(basis[i], basis[j])) for j in range(m)] for i in range(m)]
    rhs = [sum(a * y for a, y in zip(basis[i], ys)) for i in range(m)]
    for col in range(m):
        piv = max(range(col, m), key=lambda r: abs(A[r][col]))
        A[col], A[piv] = A[piv], A[col]
        rhs[col], rhs[piv] = rhs[piv], rhs[col]
        if abs(A[col][col]) < 1e-15:
            continue
        for r in range(col + 1, m):
            k = A[r][col] / A[col][col]
            for c in range(col, m):
                A[r][c] -= k * A[col][c]
            rhs[r] -= k * rhs[col]
    out = [0.0] * m
    for r in range(m - 1, -1, -1):
        s = rhs[r] - sum(A[r][c] * out[c] for c in range(r + 1, m))
        out[r] = s / A[r][r] if abs(A[r][r]) > 1e-15 else 0.0
    return out


_cache: Dict[Tuple[str, bool, bool], FieldCurve] = {}


def field_curve(value: Any, start_flat: bool = False, open_ends: bool = False) -> FieldCurve:
    """FieldCurve for a stored curve, built once and reused: an effector evaluates the same curve
    for every instance, and the visualizer re-runs the graph on every edit."""
    key = (value if isinstance(value, str) else json.dumps(value, sort_keys=True), bool(start_flat), bool(open_ends))
    fc = _cache.get(key)
    if fc is None:
        if len(_cache) > 64:
            _cache.clear()
        fc = _cache[key] = FieldCurve(value, start_flat, open_ends)
    return fc


def sphere_strength(distance: float, radius: float, inner_radius: float, curve: Any) -> float:
    """Strength of a sphere field at a distance from its center, in the same units as the radii."""
    span = radius - inner_radius
    if span <= 0:
        t = 0.0 if distance <= inner_radius else 1.0
    else:
        t = _clamp((distance - inner_radius) / span, 0.0, 1.0)
    return field_curve(curve, inner_radius > 0).value(t)
