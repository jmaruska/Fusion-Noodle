/**
 * Falloff curve: the shape a field uses to turn t (0 at the start, 1 at the end) into strength.
 *
 * backend/utilities/field_curve.py is the same code in Python. Both run the examples in
 * tests/fixtures/field_curve_vectors.json, so a change to one must be made to the other.
 * The design is in docs/dev/falloff-fields.md.
 *
 * The user draws one tile: a clamped, uniform B-spline with x increasing, normally with a level
 * tangent (two points at one height) at each end. The field never uses that tile as drawn. Each
 * tile is derived from what its two ends meet:
 *   center   the sphere's center (Inner 0): nothing, the profile meets its own mirror image
 *   flat     the inner plateau or the outer edge: a third level point, G2 to flat
 *   mirror   a Mirror repeat seam: the level neighbour slides back to the drawn curvature
 *   restart  a Restart repeat seam: the level points either side are linked; the `lead` side
 *            keeps its curvature and the other side slides to match it
 *   open     nothing at all, as with a Gradient's first and last instance: used as drawn
 */

export const HOLD_AT = 0.3;   // The added level point splits the level leg 30% in from the end point
const GAP = 0.004;            // Smallest x spacing between neighbouring points
const TINY = 1e-6;

const p = (x, y) => [x, y];
export const PRESETS = {
  'Smooth':   { points: [p(0, 1), p(.2, 1), p(.65, 0), p(1, 0)] },
  'Gaussian': { points: [p(0, 1), p(.07, 1), p(.32, .3), p(.55, 0), p(1, 0)] },
  'Linear':   { points: [p(0, 1), p(1 / 3, 2 / 3), p(2 / 3, 1 / 3), p(1, 0)] },
  'Ease out': { points: [p(0, 1), p(.06, 1), p(.12, .7), p(.35, .08), p(.75, 0), p(1, 0)] },
  'Plateau':  { points: [p(0, 1), p(.25, 1), p(.55, 1), p(.8, 0), p(1, 0)] },
  'Ring':     { points: [p(0, 0), p(.12, 0), p(.42, 1), p(.58, 1), p(.88, 0), p(1, 0)] },
  'Ripple':   { points: [p(0, 1), p(.2, 1), p(.65, 0), p(1, 0)], repeat: 5, repeat_style: 'mirror', decay: .7 },
  'Pulse':    { points: [p(0, 0), p(.06, 0), p(.2, 1), p(.3, 1), p(.72, 0), p(1, 0)], repeat: 4, repeat_style: 'restart', decay: .4 },
};
export const PRESET_NAMES = Object.keys(PRESETS);

export function presetCurve(name) {
  const pr = PRESETS[name];
  return normalizeCurve({
    points: pr.points.map(q => q.slice()),
    repeat: pr.repeat ?? 1,
    repeat_style: pr.repeat_style ?? 'mirror',
    decay: pr.decay ?? 0,
  });
}

export const DEFAULT_CURVE_NAME = 'Smooth';

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const num = (v, fallback) => (typeof v === 'number' && Number.isFinite(v) ? v : fallback);

/** A complete, valid curve from anything: a JSON string, a partial object, or nothing. */
export function normalizeCurve(value) {
  let c = value;
  if (typeof c === 'string') {
    try { c = JSON.parse(c); } catch { c = null; }
  }
  if (!c || typeof c !== 'object') return presetCurve(DEFAULT_CURVE_NAME);
  const degree = c.degree === 5 ? 5 : 3;
  let pts = Array.isArray(c.points) ? c.points.filter(q => Array.isArray(q) && q.length >= 2)
    .map(q => [num(q[0], 0), clamp(num(q[1], 0), 0, 1)]) : [];
  if (pts.length < 2) pts = PRESETS[DEFAULT_CURVE_NAME].points.map(q => q.slice());
  pts.sort((a, b) => a[0] - b[0]);
  pts[0][0] = 0; pts[pts.length - 1][0] = 1;
  for (let i = 1; i < pts.length - 1; i++) pts[i][0] = clamp(pts[i][0], 0, 1);
  pts = ensureEnoughPoints(pts, degree);
  const out = c.output && typeof c.output === 'object' ? c.output : {};
  return {
    degree,
    points: pts,
    repeat: clamp(Math.round(num(c.repeat, 1)), 1, 12),
    repeat_style: c.repeat_style === 'restart' ? 'restart' : 'mirror',
    decay: clamp(num(c.decay, 0), 0, 1),
    invert: c.invert === true,
    lead: c.lead === 'end' ? 'end' : 'start',
    output: { start: num(out.start, 1), end: num(out.end, 0) },
  };
}

/** Quintic needs at least six points: add midpoints along the widest legs until there are enough. */
export function ensureEnoughPoints(pts, degree) {
  const c = pts.map(q => q.slice());
  while (c.length < degree + 1) {
    let widest = 0;
    for (let i = 1; i < c.length - 1; i++) if (c[i + 1][0] - c[i][0] > c[widest + 1][0] - c[widest][0]) widest = i;
    const a = c[widest], b = c[widest + 1];
    c.splice(widest + 1, 0, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
  }
  return c;
}

export const tileCount = curve => (curve.repeat_style === 'mirror' ? 2 * curve.repeat - 1 : curve.repeat);

// ---------- B-spline ----------
export function knotVector(n, deg) {   // n + 1 control points, clamped and uniform
  const m = n + deg + 1, t = [];
  for (let i = 0; i <= m; i++) t.push(i <= deg ? 0 : i >= m - deg ? 1 : (i - deg) / (n - deg + 1));
  return t;
}
export function deBoor(P, deg, t, u) {
  const n = P.length - 1;
  let k = deg;
  if (u >= t[n + 1]) k = n; else while (k < n && u >= t[k + 1]) k++;
  const d = [];
  for (let j = 0; j <= deg; j++) d.push(P[j + k - deg].slice());
  for (let r = 1; r <= deg; r++) for (let j = deg; j >= r; j--) {
    const den = t[j + 1 + k - r] - t[j + k - deg];
    const a = den === 0 ? 0 : (u - t[j + k - deg]) / den;
    d[j] = [(1 - a) * d[j - 1][0] + a * d[j][0], (1 - a) * d[j - 1][1] + a * d[j][1]];
  }
  return d[deg];
}

/** Value, first and second derivative of f at t0, from one side only (dir +1 or -1). */
export function oneSided(f, t0, h, dir) {
  const v = [0, 1, 2, 3, 4].map(k => f(t0 + dir * k * h));
  const d1 = (-25 * v[0] + 48 * v[1] - 36 * v[2] + 16 * v[3] - 3 * v[4]) / (12 * h) * dir;
  const d2 = (35 * v[0] - 104 * v[1] + 114 * v[2] - 56 * v[3] + 11 * v[4]) / (12 * h * h);
  return [v[0], d1, d2];
}

const isLevel = (a, b) => Math.abs(a.y - b.y) < 1e-9;

// y''(x) at one end. With a level tangent, moving the level neighbour to distance d from the end
// scales this by 1/d^2 and changes nothing else, so a seam can be matched by sliding one point.
function endBend(cvs, atEnd, deg) {
  const P = cvs.map(c => [c.x, c.y]), t = knotVector(P.length - 1, deg);
  const u0 = atEnd ? 1 : 0, dir = atEnd ? -1 : 1, h = 1e-3;
  const X = oneSided(u => deBoor(P, deg, t, u)[0], u0, h, dir);
  const Y = oneSided(u => deBoor(P, deg, t, u)[1], u0, h, dir);
  return Y[2] / (X[1] * X[1]) - Y[1] * X[2] / (X[1] * X[1] * X[1]);
}

function addStartHold(c) {
  if (c.length > 2 && isLevel(c[0], c[1]) && !isLevel(c[0], c[2]))
    c.splice(1, 0, { x: c[0].x + HOLD_AT * (c[1].x - c[0].x), y: c[0].y, src: null });
}
function addEndHold(c) {
  const n = c.length - 1;
  if (n > 1 && isLevel(c[n], c[n - 1]) && !isLevel(c[n], c[n - 2]))
    c.splice(n, 0, { x: c[n].x - HOLD_AT * (c[n].x - c[n - 1].x), y: c[n].y, src: null });
}

function seamPlan(curve) {
  const c = curve.points.map(([x, y]) => ({ x, y })), n = c.length - 1, deg = curve.degree;
  const startLevel = isLevel(c[0], c[1]), endLevel = isLevel(c[n], c[n - 1]);
  const ks = startLevel ? endBend(c, false, deg) : 0, ke = endLevel ? endBend(c, true, deg) : 0;
  const plan = { ks, ke, restart: 'none' };
  if (startLevel && endLevel && isLevel(c[0], c[n]) && !(Math.abs(ks) < TINY && Math.abs(ke) < TINY)) {
    if (ks * ke <= 0 || Math.abs(ks) < TINY || Math.abs(ke) < TINY) plan.restart = 'flat';
    else { plan.restart = 'match'; plan.target = curve.lead === 'end' ? ke : ks; }
  }
  return plan;
}

function slide(c, atEnd, target, deg) {
  const n = c.length - 1, end = atEnd ? c[n] : c[0], nb = atEnd ? c[n - 1] : c[1], far = atEnd ? c[n - 2] : c[2];
  if (!isLevel(end, nb) || isLevel(end, far) || !target) return;
  const k = endBend(c, atEnd, deg);
  if (!(k * target > 0)) return;
  const d = Math.abs(end.x - nb.x) * Math.sqrt(k / target);
  const x = atEnd ? Math.max(far.x + GAP, Math.min(end.x - GAP, end.x - d))
                  : Math.min(far.x - GAP, Math.max(end.x + GAP, end.x + d));
  if (Math.abs(x - nb.x) > 1e-4) nb.x = x;
}

function tileCVs(curve, startMeets, endMeets, plan) {
  const deg = curve.degree;
  const c = curve.points.map(([x, y], i) => ({ x, y, src: i }));
  const flatRestart = plan.restart === 'flat';
  if (startMeets === 'flat' || (startMeets === 'restart' && flatRestart)) addStartHold(c);
  if (endMeets === 'flat' || (endMeets === 'restart' && flatRestart)) addEndHold(c);
  if (startMeets === 'mirror') slide(c, false, plan.ks, deg);
  if (endMeets === 'mirror') slide(c, true, plan.ke, deg);
  if (plan.restart === 'match') {
    if (startMeets === 'restart') slide(c, false, plan.target, deg);
    if (endMeets === 'restart') slide(c, true, plan.target, deg);
    const n = c.length - 1;
    if (startMeets === 'restart' || endMeets === 'restart') {
      if (isLevel(c[0], c[1])) c[1].link = true;
      if (isLevel(c[n], c[n - 1])) c[n - 1].link = true;
    }
  }
  return c;
}

// What each end of tile i meets. Mirror tiles run backwards on odd counts.
function tileEnds(i, n, curve, startFlat, openEnds) {
  const seam = curve.repeat_style === 'mirror' ? 'mirror' : 'restart';
  const left = i === 0 ? (openEnds ? 'open' : startFlat ? 'flat' : 'center') : seam;
  const right = i === n - 1 ? (openEnds ? 'open' : 'flat') : seam;
  const flipped = curve.repeat_style === 'mirror' && i % 2 === 1;
  return flipped ? [right, left, true] : [left, right, false];
}

const TABLE_SIZE = 1024;
function makeTile(cvs, deg) {
  const P = cvs.map(c => [c.x, c.y]), t = knotVector(P.length - 1, deg);
  return { cvs, P, deg, t, xs: null, ys: null };
}
function tileTable(tile) {
  if (!tile.xs) {
    const xs = new Float64Array(TABLE_SIZE + 1), ys = new Float64Array(TABLE_SIZE + 1);
    for (let i = 0; i <= TABLE_SIZE; i++) { const q = deBoor(tile.P, tile.deg, tile.t, i / TABLE_SIZE); xs[i] = q[0]; ys[i] = q[1]; }
    tile.xs = xs; tile.ys = ys;
  }
  return tile;
}
// Exact y(x): the control polygon is monotone in x, so x(u) is too
function tileYExact(tile, x) {
  x = clamp(x, 0, 1);
  let lo = 0, hi = 1;
  for (let i = 0; i < 52; i++) { const mid = (lo + hi) / 2; if (deBoor(tile.P, tile.deg, tile.t, mid)[0] < x) lo = mid; else hi = mid; }
  return deBoor(tile.P, tile.deg, tile.t, (lo + hi) / 2)[1];
}
function tileYFast(tile, x) {
  const { xs, ys } = tileTable(tile);
  x = clamp(x, 0, 1);
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (xs[mid] < x) lo = mid; else hi = mid; }
  const span = xs[hi] - xs[lo];
  return span > 0 ? ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / span : ys[lo];
}

const smootherstep = t => t * t * t * (t * (t * 6 - 15) + 10);  // zero slope and curvature at both ends

/**
 * Build the field shape for a curve. `startFlat` is true when t = 0 meets a flat region (a sphere
 * with an inner radius), false when it is the sphere's center. `openEnds` is true when nothing
 * lies beyond t = 0 and t = 1 (a Gradient along a strand): the ends are used as drawn and not graded.
 * Returns { tiles, first, shape(t, exact), value(t, exact), continuity() }.
 */
export function buildField(curveInput, startFlat = false, openEnds = false) {
  const curve = normalizeCurve(curveInput);
  const plan = seamPlan(curve), n = tileCount(curve), byKey = new Map(), tiles = [];
  for (let i = 0; i < n; i++) {
    const [startMeets, endMeets, flipped] = tileEnds(i, n, curve, startFlat, openEnds), key = startMeets + '|' + endMeets;
    if (!byKey.has(key)) byKey.set(key, makeTile(tileCVs(curve, startMeets, endMeets, plan), curve.degree));
    tiles.push({ tile: byKey.get(key), flipped });
  }
  const shape = (t, exact = false) => {
    t = clamp(t, 0, 1);
    const s = t * n;
    let i = Math.floor(s), f = s - i;
    if (i >= n) { i = n - 1; f = 1; }
    if (tiles[i].flipped) f = 1 - f;
    let v = exact ? tileYExact(tiles[i].tile, f) : tileYFast(tiles[i].tile, f);
    if (curve.invert) v = 1 - v;
    return v * (1 - curve.decay * smootherstep(t));
  };
  const value = (t, exact = false) => curve.output.end + (curve.output.start - curve.output.end) * shape(t, exact);
  return { curve, tiles, first: tiles[0].tile, tileCount: n, shape, value, continuity: () => continuity(shape, n, startFlat, openEnds) };
}

/** Grade value, tangent and curvature from both sides: 'g2', 'g1', 'g0', or 'gx' (a step). */
export function grade(a, b) {
  const close = (p, q, rel) => Math.abs(p - q) <= rel * Math.max(1, Math.abs(p), Math.abs(q));
  if (!close(a[0], b[0], 1e-5)) return 'gx';
  if (!close(a[1], b[1], 0.01)) return 'g0';
  if (!close(a[2], b[2], 0.03)) return 'g1';
  return 'g2';
}

function continuity(shape, n, startFlat, openEnds) {
  // Step well inside the shortest leg: a hold point sits 30% along a level leg, inside one tile
  const h = 2e-4 / n, f = t => shape(t, true), rows = [];
  if (!openEnds) {
    const startR = oneSided(f, 0, h, 1);
    // With no inner radius the start is the sphere's center, where the profile meets its mirror image
    const startL = startFlat ? [startR[0], 0, 0] : [startR[0], -startR[1], startR[2]];
    rows.push({ name: startFlat ? 'Inner edge' : 'Center', grade: grade(startL, startR) });
    const endL = oneSided(f, 1, h, -1);
    rows.push({ name: 'Outer edge', grade: grade(endL, [endL[0], 0, 0]) });
  }
  if (n > 1) {
    const order = ['g2', 'g1', 'g0', 'gx'];
    let worst = 'g2';
    for (let k = 1; k < n; k++) {
      const t0 = k / n, eps = 1e-9;
      const g = grade(oneSided(f, t0 - eps, h, -1), oneSided(f, t0 + eps, h, 1));
      if (order.indexOf(g) > order.indexOf(worst)) worst = g;
    }
    rows.push({ name: 'Repeats', grade: worst });
  }
  return rows;
}

export const GRADE_LABEL = { g2: 'G2', g1: 'G1', g0: 'G0', gx: 'Gap' };
export function gradeReason(name, g) {
  if (name === 'Center' && g === 'g2') return 'Mirrored here, so a level tangent is enough.';
  if (name === 'Center' && g === 'g0') return 'A point. Level the first two points.';
  return {
    g2: 'Curvature carries through.',
    g1: 'Tangent matches, curvature jumps.',
    g0: 'A crease. The slope changes direction here.',
    gx: 'A step in strength.',
  }[g];
}

/** Which preset a curve still matches exactly, or null once the user has changed it. */
export function matchingPreset(curveInput) {
  const c = normalizeCurve(curveInput);
  const same = (a, b) => Math.abs(a - b) < 1e-9;
  for (const name of PRESET_NAMES) {
    const pr = presetCurve(name);
    if (pr.degree === c.degree && pr.repeat === c.repeat && pr.repeat_style === c.repeat_style && same(pr.decay, c.decay)
        && pr.points.length === c.points.length && pr.points.every((q, i) => same(q[0], c.points[i][0]) && same(q[1], c.points[i][1])))
      return name;
  }
  return null;
}
