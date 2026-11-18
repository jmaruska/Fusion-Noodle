"""
The Gradient modifier's evaluator before graph format 4, kept only so old graphs can be
converted: graph_format samples it and fits a falloff curve to the samples. Nothing else may
use it. How the old editor worked is in __docs/LEGACY_GRADIENT.md.

Stops are {position, value, interp, tension}. interp is the stop's outgoing transition:
  step / linear  an anchor the curve passes through, no handles (C0)
  flat           an anchor with one horizontal handle per side (G1)
  smooth         an anchor with two horizontal handles per side (G2)
  influence      not an anchor: an interior Bezier control point
tension (0.05 to 0.95) scales the handle offsets.
"""

def _de_casteljau(pts: list, t: float) -> tuple:
    """De Casteljau evaluation of a 2D Bezier at parameter t. Returns (x, y)."""
    p = [[pt[0], pt[1]] for pt in pts]
    while len(p) > 1:
        p = [[p[i][0] + (p[i+1][0]-p[i][0])*t, p[i][1] + (p[i+1][1]-p[i][1])*t]
             for i in range(len(p)-1)]
    return p[0][0], p[0][1]


def _find_bezier_t(pts: list, x: float, iters: int = 42) -> float:
    """Binary search for t such that Bx(t) ≈ x (Bx is monotone for sorted control pts)."""
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = (lo + hi) * 0.5
        if _de_casteljau(pts, mid)[0] < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def _build_segment_bezier(A: dict, B: dict, cvs: list) -> list:
    """
    Build 2D control points for a Bezier segment from anchor A to anchor B.

    Stop interp values and their handle behaviour:
      step / linear  — no handles (C0)
      flat           — one horizontal handle per side (G1, zero slope)
      smooth         — two horizontal handles per side (G2, zero slope + zero curvature)
      influence      — never an anchor; treated as interior CV

    Handle tension ∈ [0.05, 0.95] scales offset from anchor:
      G1 handle at  tension · span / 3
      G2 handle at  tension · span · 2 / 3
    """
    span = float(B["position"]) - float(A["position"])
    pts  = [[float(A["position"]), float(A["value"])]]

    a_interp = A.get("interp") or "linear"
    if a_interp in ("flat", "smooth"):
        s = max(0.05, min(0.95, float(A.get("tension", 0.5))))
        pts.append([float(A["position"]) + s * span / 3,      float(A["value"])])  # G1
        if a_interp == "smooth":
            pts.append([float(A["position"]) + s * span * 2 / 3, float(A["value"])])  # G2

    for cv in cvs:
        pts.append([float(cv["position"]), float(cv["value"])])

    b_interp = B.get("interp") or "linear"
    if b_interp in ("flat", "smooth"):
        s = max(0.05, min(0.95, float(B.get("tension", 0.5))))
        if b_interp == "smooth":
            pts.append([float(B["position"]) - s * span * 2 / 3, float(B["value"])])  # G2
        pts.append([float(B["position"]) - s * span / 3,      float(B["value"])])  # G1

    pts.append([float(B["position"]), float(B["value"])])
    return pts


def _interpolate_gradient_stops(stops, t: float, interpolation: str, clamp: bool = False) -> float:
    """
    Evaluate the gradient at t using the Bezier influence-point model.

    linear / step stop  → anchor (curve passes through; segment boundary)
    smooth edge stop    → anchor with implicit horizontal handle; tension = handle fraction
    smooth interior stop → influence CV (pulls curve without passing through)
    """
    if not stops:
        return 0.0
    ss = sorted(stops, key=lambda s: float(s.get("position", 0.0)))
    n  = len(ss)

    if t <= float(ss[0]["position"]):  return float(ss[0]["value"])
    if t >= float(ss[-1]["position"]): return float(ss[-1]["value"])

    # Collect anchor indices — everything except 'influence' is an anchor
    anchors = [0]
    for i in range(1, n - 1):
        if (ss[i].get("interp") or "linear") != "influence":
            anchors.append(i)
    anchors.append(n - 1)

    # Find containing segment
    ai = 0
    for i in range(len(anchors) - 1):
        if float(ss[anchors[i]]["position"]) <= t <= float(ss[anchors[i+1]]["position"]):
            ai = i; break

    a_idx, b_idx = anchors[ai], anchors[ai + 1]
    A, B = ss[a_idx], ss[b_idx]
    a_interp = A.get("interp") or "linear"

    if a_interp == "step":
        return float(A["value"])

    span = float(B["position"]) - float(A["position"])
    if span < 1e-9:
        return float(A["value"])

    cvs = [ss[i] for i in range(a_idx + 1, b_idx)
           if (ss[i].get("interp") or "linear") == "influence"]

    pts = _build_segment_bezier(A, B, cvs)

    if len(pts) == 2:
        y = float(A["value"]) + (float(B["value"]) - float(A["value"])) * (t - float(A["position"])) / span
    else:
        bt  = _find_bezier_t(pts, t)
        y   = _de_casteljau(pts, bt)[1]

    return max(0.0, min(1.0, y)) if clamp else y


DEFAULT_STOPS = [{"position": 0.0, "value": 1.0}, {"position": 1.0, "value": 0.0}]


def evaluate(stops_value, t: float, clamp: bool = False) -> float:
    """The old Gradient's value at t, from stops stored as JSON or as a list."""
    import json
    stops = stops_value
    if isinstance(stops, str):
        try:
            stops = json.loads(stops)
        except (ValueError, TypeError):
            stops = None
    if not isinstance(stops, list) or not stops:
        stops = DEFAULT_STOPS
    return _interpolate_gradient_stops(stops, t, 'linear', clamp=clamp)
