/**
 * FalloffCurveEditor: the falloff curve on a node's face, and the modal that edits it.
 * Used by the Falloff nodes (Sphere, Linear or Box, picked with the Shape dropdown on the node)
 * and the Gradient node (along each strand). Where the field sits is set on the node; how it
 * fades is set here.
 *
 * The curve is stored on the node's `curve` input as JSON. While the modal is open, edits are
 * written back a few times a second, so the effector visualizer in the viewport follows along.
 * The curve maths lives in ../utils/fieldCurve.js; the design is in docs/dev/falloff-fields.md.
 *
 * Opening the editor turns on the visualizer for the effector this curve drives (the node itself,
 * or the effectors a modifier feeds) and closing it puts the view back as it was: visualizers
 * that were off go off again and bodies that were showing come back. The dots and the field's
 * outline appear first; bodies are hidden once they are drawn (see hooks/useVisualizer.js).
 *
 * Points: squares are the user's; filled circles are linked across a Restart seam (drag either
 * side and the other follows). Points the curve adds to meet flat ground are not shown.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useEdges, useReactFlow } from '@xyflow/react';
import { effectorsFedBy } from '../utils/effectorsFedBy';
import { emitVisibilityEvent } from '../utils/visibilityBus';
import { restoreBodies } from '../utils/bodyVisibility.js';
import { showPortTipSoon, hidePortTip } from './PortTip';
import {
  buildField, normalizeCurve, presetCurve, matchingPreset, ensureEnoughPoints, deBoor,
  PRESET_NAMES, GRADE_LABEL, gradeReason,
} from '../utils/fieldCurve';

const COMMIT_MS = 120;      // How often edits are written back to the node while editing
const RESTORE_MS = 250;     // On close, let the dots clear before bodies come back
const GAP = 0.004;          // Smallest x spacing between neighbouring points while dragging

// What t measures for each kind of node. `startFlat`: does t = 0 meet flat ground?
// `openEnds`: is there nothing beyond t = 0 and t = 1, so the ends are used as drawn?
const SOURCES = {
  sphere: {
    kind: 'Falloff', label: 'Sphere',
    startFlat: inner => inner > 0,
    axis: inner => [inner > 0 ? 'inner' : 'center', 'radius'],
    openEnds: false,
  },
  linear: {
    kind: 'Falloff', label: 'Linear',
    startFlat: () => true,
    axis: () => ['start', 'end'],
    edgeNames: { 'Inner edge': 'Start', 'Outer edge': 'End' },
    openEnds: false,
  },
  box: {   // Measured like the sphere, but square: every contour of the fade is a box
    kind: 'Falloff', label: 'Box',
    startFlat: inner => inner > 0,
    axis: inner => [inner > 0 ? 'inner' : 'center', 'radius'],
    openEnds: false,
  },
  along: {
    kind: 'Gradient', label: 'Along collection',
    startFlat: () => false,
    axis: () => ['first', 'last'],
    openEnds: true,   // Nothing lies beyond a strand's first and last instance
  },
};

// What the curve editor doesn't edit, by shape: told in the info tip
const SET_ON_NODE = {
  sphere: 'Center, Scale and axes are set on the node.',
  box: 'Center, Scale and axes are set on the node.',
  linear: 'Start and End are set on the node.',
};

// The larger modal only when the palette has room for it with a margin
const roomForLarge = () => window.innerWidth >= 980 && window.innerHeight >= 720;

const cssVar = (el, name, fallback) => {
  const v = el ? getComputedStyle(el).getPropertyValue(name).trim() : '';
  return v || fallback;
};

// Grid, labels and outlines for a canvas. Inside the modal these come from the
// Weave tokens it sets (falloff-editor.css); on the node they fall back to the
// node's own colours.
const canvasTheme = (canvas) => ({
  line: cssVar(canvas, '--falloff-canvas-grid', cssVar(canvas, '--adsk-surface-darkBlue-200', '#3b4453')),
  muted: cssVar(canvas, '--falloff-canvas-label', cssVar(canvas, '--adsk-text-tertiary', '#8babdc')),
  font: cssVar(canvas, '--falloff-canvas-font', '10px ui-monospace, Menlo, monospace'),
  outline: cssVar(canvas, '--falloff-canvas-outline', '#12161d'),
  selected: cssVar(canvas, '--falloff-canvas-selected', '#ffffff'),
});

function fitCanvas(canvas) {
  const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: r.width, h: r.height };
}

// Strength through the field, from -span to +span around the center
function drawProfile(canvas, field, radius, inner, { axis = true } = {}) {
  const { ctx, w, h } = fitCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const pl = axis ? 30 : 4, pr = axis ? 10 : 4, pt = axis ? 8 : 4, pb = axis ? 18 : 4;
  const span = Math.max(radius, 1e-6) * 1.3;
  const X = d => pl + (d + span) / (2 * span) * (w - pl - pr), Y = v => pt + (1 - v) * (h - pt - pb);
  const { line, muted, font } = canvasTheme(canvas);
  ctx.lineWidth = 1;
  if (axis) {
    ctx.strokeStyle = line; ctx.fillStyle = muted; ctx.font = font;
    [0, 0.5, 1].forEach(v => { ctx.beginPath(); ctx.moveTo(pl, Y(v) + .5); ctx.lineTo(w - pr, Y(v) + .5); ctx.stroke(); ctx.fillText(String(v), 4, Y(v) + 3); });
  }
  const mark = (d, label) => {
    ctx.strokeStyle = muted; ctx.globalAlpha = .5; ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(X(d) + .5, pt); ctx.lineTo(X(d) + .5, h - pb); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    if (label && axis) { ctx.fillStyle = muted; ctx.textAlign = 'center'; ctx.fillText(label, X(d), h - 5); ctx.textAlign = 'left'; }
  };
  const fmt = v => `${Math.round(v * 100) / 100} cm`;
  mark(-radius, axis ? `-${fmt(radius)}` : null); mark(radius, axis ? fmt(radius) : null); mark(0, axis ? 'center' : null);
  if (inner > 0) { mark(-inner); mark(inner); }
  const at = d => {
    const a = Math.abs(d), sp = radius - inner;
    const t = sp > 0 ? Math.min(1, Math.max(0, (a - inner) / sp)) : (a <= inner ? 0 : 1);
    return field.value(t);
  };
  ctx.strokeStyle = cssVar(canvas, '--noodle-color-curve', '#32bcad'); ctx.lineWidth = axis ? 2 : 1.5;
  ctx.beginPath();
  const N = Math.max(120, Math.round(w * 1.5));
  for (let i = 0; i <= N; i++) {
    const d = -span + 2 * span * i / N, x = X(d), y = Y(Math.min(1, Math.max(0, at(d))));
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.stroke();
}

// A falloff that holds before t = 0 and after t = 1 (Linear, Box): a little of each side shown
function drawRamp(canvas, field, { axis = true, labels = ['start', 'end'] } = {}) {
  const { ctx, w, h } = fitCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const pl = axis ? 30 : 4, pr = axis ? 10 : 4, pt = axis ? 8 : 4, pb = axis ? 18 : 4;
  const u0 = -0.25, u1 = 1.25;
  const X = u => pl + (u - u0) / (u1 - u0) * (w - pl - pr), Y = v => pt + (1 - v) * (h - pt - pb);
  const { line, muted, font } = canvasTheme(canvas);
  ctx.lineWidth = 1;
  if (axis) {
    ctx.strokeStyle = line; ctx.fillStyle = muted; ctx.font = font;
    [0, 0.5, 1].forEach(v => { ctx.beginPath(); ctx.moveTo(pl, Y(v) + .5); ctx.lineTo(w - pr, Y(v) + .5); ctx.stroke(); ctx.fillText(String(v), 4, Y(v) + 3); });
  }
  [0, 1].forEach((u, i) => {
    ctx.strokeStyle = muted; ctx.globalAlpha = .5; ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(X(u) + .5, pt); ctx.lineTo(X(u) + .5, h - pb); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    if (axis) { ctx.fillStyle = muted; ctx.textAlign = 'center'; ctx.fillText(labels[i], X(u), h - 5); ctx.textAlign = 'left'; }
  });
  ctx.strokeStyle = cssVar(canvas, '--noodle-color-curve', '#32bcad'); ctx.lineWidth = axis ? 2 : 1.5;
  ctx.beginPath();
  const N = Math.max(120, Math.round(w * 1.5));
  for (let i = 0; i <= N; i++) {
    const u = u0 + (u1 - u0) * i / N, x = X(u), y = Y(Math.min(1, Math.max(0, field.value(Math.min(1, Math.max(0, u))))));
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.stroke();
}

// Draw the strength profile that suits the source: mirrored about the center for Sphere and
// Box, held beyond both ends for Linear, or first-to-last along a strand
function drawSourceProfile(canvas, source, field, radius, inner, lengthText, opts = {}) {
  if (source === 'along') drawAlong(canvas, field, opts);
  else if (source === 'linear') drawRamp(canvas, field, { ...opts, labels: ['start', lengthText ? `end · ${lengthText}` : 'end'] });
  else drawProfile(canvas, field, radius, inner, opts);
}

// Value from the first instance of a strand (left) to the last (right)
function drawAlong(canvas, field, { axis = true } = {}) {
  const { ctx, w, h } = fitCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const pl = axis ? 30 : 4, pr = axis ? 10 : 4, pt = axis ? 8 : 4, pb = axis ? 18 : 4;
  const out = field.curve.output, lo = Math.min(0, out.start, out.end), hi = Math.max(1, out.start, out.end);
  const X = t => pl + t * (w - pl - pr), Y = v => pt + (hi - v) / (hi - lo) * (h - pt - pb);
  const { line, muted, font } = canvasTheme(canvas);
  ctx.lineWidth = 1;
  if (axis) {
    ctx.strokeStyle = line; ctx.fillStyle = muted; ctx.font = font;
    [0, 0.5, 1].forEach(v => { ctx.beginPath(); ctx.moveTo(pl, Y(v) + .5); ctx.lineTo(w - pr, Y(v) + .5); ctx.stroke(); ctx.fillText(String(v), 4, Y(v) + 3); });
    ctx.fillText('first', pl, h - 5); ctx.textAlign = 'right'; ctx.fillText('last', w - pr, h - 5); ctx.textAlign = 'left';
  }
  ctx.strokeStyle = cssVar(canvas, '--noodle-color-curve', '#32bcad'); ctx.lineWidth = axis ? 2 : 1.5;
  ctx.beginPath();
  const N = Math.max(120, Math.round(w * 1.5));
  for (let i = 0; i <= N; i++) { const t = i / N, x = X(t), y = Y(field.value(t)); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.stroke();
}

// ───────────────────────────── node face ─────────────────────────────

const FalloffCurveEditor = ({ nodeId, nodeLabel, source = 'sphere', currentInputs = {}, computedInputs = {}, onInputChange }) => {
  const src = SOURCES[source] || SOURCES.sphere;
  const [open, setOpen] = useState(false);
  const previewRef = useRef(null);
  const edges = useEdges();
  const { getNodes, getEdges, updateNodeData } = useReactFlow();
  const savedViewRef = useRef(null);

  // Show this curve's effect while editing, and remember the view to put back afterwards
  const openEditor = () => {
    const nodes = getNodes();
    const wasOn = new Set(nodes.filter(n => n.data?.visualize).map(n => n.id));
    const visibleBodies = [];
    emitVisibilityEvent('collect-visible-bodies', visibleBodies);
    const turnedOn = effectorsFedBy(nodeId, nodes, getEdges()).filter(id => !wasOn.has(id));
    turnedOn.forEach(id => updateNodeData(id, { visualize: true }));
    savedViewRef.current = { turnedOn, visibleBodies };
    setOpen(true);
  };
  const closeEditor = () => {
    setOpen(false);
    const saved = savedViewRef.current;
    savedViewRef.current = null;
    if (!saved) return;
    saved.turnedOn.forEach(id => updateNodeData(id, { visualize: false }));
    if (saved.visibleBodies.length) {
      setTimeout(() => restoreBodies(saved.visibleBodies), RESTORE_MS);
    }
  };
  const connected = port => edges.some(e => e.target === nodeId && e.targetHandle === `input-${port}`);
  const numberOf = (port, fallback) => {
    const v = connected(port) && computedInputs[port] !== undefined ? computedInputs[port] : currentInputs[port];
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
  };
  const roundOrSquare = source === 'sphere' || source === 'box';
  const radius = numberOf('radius', 10), inner = roundOrSquare ? numberOf('inner_radius', 0) : 0;
  const pointOf = (port, fallback) => {
    const v = connected(port) && computedInputs[port] !== undefined ? computedInputs[port] : currentInputs[port];
    return v && typeof v === 'object' ? [Number(v.x) || 0, Number(v.y) || 0, Number(v.z) || 0] : fallback;
  };
  const [sx, sy, sz] = pointOf('start', [0, 0, 0]), [ex, ey, ez] = pointOf('end', [10, 0, 0]);
  const lengthText = `${Math.round(Math.hypot(ex - sx, ey - sy, ez - sz) * 100) / 100} cm`;
  const curve = useMemo(() => normalizeCurve(currentInputs.curve), [currentInputs.curve]);
  const startFlat = src.startFlat(inner);
  const field = useMemo(() => buildField(curve, startFlat, src.openEnds), [curve, startFlat, src]);
  const preset = useMemo(() => matchingPreset(curve), [curve]);

  useEffect(() => {
    const c = previewRef.current;
    if (!c) return undefined;
    const draw = () => drawSourceProfile(c, source, field, radius, Math.min(inner, radius), lengthText, { axis: false });
    draw();
    const ro = new ResizeObserver(draw); ro.observe(c);
    return () => ro.disconnect();
  }, [field, radius, inner, source, lengthText]);

  const summary = [preset || 'Custom', curve.repeat > 1 ? `× ${curve.repeat}` : null].filter(Boolean).join(' ');

  return (
    <>
      <button type="button" className="falloff-curve-preview nodrag nopan" onClick={openEditor}
              title={`Edit the ${src.kind.toLowerCase()} curve`}>
        <canvas ref={previewRef} className="falloff-curve-preview-canvas" />
        <span className="falloff-curve-preview-label">{summary}</span>
      </button>
      {open && createPortal(
        <FalloffCurveModal
          title={nodeLabel || src.kind}
          source={source}
          curve={curve}
          radius={radius} inner={inner} lengthText={lengthText}
          radiusLocked={connected('radius')} innerLocked={connected('inner_radius')}
          onCurve={json => onInputChange('curve', json)}
          onNumber={(port, v) => onInputChange(port, v)}
          onClose={closeEditor}
        />,
        document.body,
      )}
    </>
  );
};

// ───────────────────────────── modal ─────────────────────────────

function NumberField({ id, value, locked, onCommit, min = 0 }) {
  const [text, setText] = useState(String(value));
  useEffect(() => { setText(String(value)); }, [value]);
  const commit = () => {
    const v = parseFloat(text);
    if (Number.isFinite(v) && v >= min) onCommit(v); else setText(String(value));
  };
  if (locked) return <span className="falloff-modal-connected">Connected</span>;
  return (
    <input id={id} className="falloff-modal-number" type="text" inputMode="decimal" value={text}
           onChange={e => setText(e.target.value)} onBlur={commit}
           onKeyDown={e => { if (e.key === 'Enter') { commit(); e.currentTarget.blur(); } if (e.key === 'Escape') setText(String(value)); }} />
  );
}

function FalloffCurveModal({ title, source, curve: initialCurve, radius, inner, lengthText, radiusLocked, innerLocked, onCurve, onNumber, onClose }) {
  const src = SOURCES[source] || SOURCES.sphere;
  const [curve, setCurve] = useState(initialCurve);
  const [comb, setComb] = useState(true);
  const [large, setLarge] = useState(roomForLarge);
  const [dragIndex, setDragIndex] = useState(-1);
  const editorRef = useRef(null), profileRef = useRef(null), modalRef = useRef(null);
  const viewRef = useRef({ w: 1, h: 1 });

  const innerClamped = Math.min(inner, radius);
  const startFlat = src.startFlat(innerClamped);
  const field = useMemo(() => buildField(curve, startFlat, src.openEnds), [curve, startFlat, src]);
  const [axisStart, axisEnd] = src.axis(innerClamped);
  // Continuity rows, named for this shape's edges
  const rows = useMemo(() => field.continuity().map(r => ({ ...r, name: src.edgeNames?.[r.name] ?? r.name })), [field, src]);
  const preset = useMemo(() => matchingPreset(curve), [curve]);

  // Write edits back while editing, at most every COMMIT_MS, and once more on close
  const pending = useRef(null), timer = useRef(null);
  const flush = useCallback(() => {
    clearTimeout(timer.current); timer.current = null;
    if (pending.current !== null) { onCurve(pending.current); pending.current = null; }
  }, [onCurve]);
  const update = useCallback(next => {
    setCurve(next);
    pending.current = JSON.stringify(next);
    if (!timer.current) timer.current = setTimeout(flush, COMMIT_MS);
  }, [flush]);
  const close = useCallback(() => { flush(); onClose(); }, [flush, onClose]);

  useEffect(() => {
    const onResize = () => setLarge(roomForLarge());
    const onKey = e => { if (e.key === 'Escape') close(); };
    window.addEventListener('resize', onResize); window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('resize', onResize); window.removeEventListener('keydown', onKey); };
  }, [close]);
  useEffect(() => () => clearTimeout(timer.current), []);

  // ── drawing ──
  const PAD = { l: 34, r: 14, t: 16, b: 22 };
  const toPx = (x, y) => { const { w, h } = viewRef.current; return [PAD.l + x * (w - PAD.l - PAD.r), PAD.t + (1 - y) * (h - PAD.t - PAD.b)]; };
  const fromPx = (px, py) => { const { w, h } = viewRef.current; return [(px - PAD.l) / (w - PAD.l - PAD.r), 1 - (py - PAD.t) / (h - PAD.t - PAD.b)]; };
  // Points shown and draggable: the user's points as the first tile uses them
  const shown = field.first.cvs.filter(c => c.src !== null);

  const drawEditor = useCallback(() => {
    const canvas = editorRef.current;
    if (!canvas) return;
    const { ctx, w, h } = fitCanvas(canvas);
    viewRef.current = { w, h };
    ctx.clearRect(0, 0, w, h);
    const { line, muted, font, outline, selected } = canvasTheme(canvas);
    const curveColor = cssVar(canvas, '--noodle-color-curve', '#32bcad');
    const cvColor = cssVar(canvas, '--noodle-color-numbers', '#faa21b');
    const combColor = cssVar(canvas, '--adsk-primary-autodeskBlue-400', '#3198eb');
    ctx.font = font; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const [x0, y0] = toPx(0, i / 4), [x1] = toPx(1, i / 4), [gx, gy0] = toPx(i / 4, 0), [, gy1] = toPx(i / 4, 1);
      ctx.strokeStyle = line;
      ctx.beginPath(); ctx.moveTo(x0, y0 + .5); ctx.lineTo(x1, y0 + .5); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(gx + .5, gy0); ctx.lineTo(gx + .5, gy1); ctx.stroke();
      ctx.fillStyle = muted; ctx.fillText((i / 4).toFixed(2).replace(/0$/, ''), 3, y0 + 3);
    }
    ctx.fillStyle = muted;
    ctx.fillText(axisStart, PAD.l, h - 6);
    ctx.textAlign = 'right'; ctx.fillText(axisEnd, w - PAD.r, h - 6); ctx.textAlign = 'left';

    // control polygon through the points the user can see
    ctx.setLineDash([4, 4]); ctx.strokeStyle = cvColor; ctx.globalAlpha = .45;
    ctx.beginPath(); shown.forEach((c, i) => { const [x, y] = toPx(c.x, c.y); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha = 1;

    const { P, deg, t } = field.first, N = 400, pts = [];
    for (let i = 0; i <= N; i++) { const q = deBoor(P, deg, t, i / N); pts.push(toPx(q[0], q[1])); }

    if (comb) {
      const teeth = [];
      for (let i = 1; i < N; i++) {
        const [ax, ay] = pts[i - 1], [bx, by] = pts[i], [cx, cy] = pts[i + 1];
        const abx = bx - ax, aby = by - ay, bcx = cx - bx, bcy = cy - by, acx = cx - ax, acy = cy - ay;
        const la = Math.hypot(abx, aby), lb = Math.hypot(bcx, bcy), lc = Math.hypot(acx, acy);
        const k = la * lb * lc > 1e-9 ? 2 * (abx * bcy - aby * bcx) / (la * lb * lc) : 0;
        teeth.push([bx, by, acy / (lc || 1), -acx / (lc || 1), k]);
      }
      // Longest tooth is 18% of the canvas height: never runs off, always readable
      const kMax = Math.max(1e-9, ...teeth.map(q => Math.abs(q[4]))), scale = 0.18 * h / kMax;
      const tips = teeth.map(([bx, by, nx, ny, k]) => [bx, by, bx + nx * k * scale, by + ny * k * scale]);
      ctx.strokeStyle = combColor; ctx.globalAlpha = .35;
      ctx.beginPath(); tips.forEach(([bx, by, ex, ey], i) => { if (i % 4 === 0) { ctx.moveTo(bx, by); ctx.lineTo(ex, ey); } }); ctx.stroke();
      ctx.globalAlpha = .9;
      ctx.beginPath(); tips.forEach(([, , ex, ey], i) => (i ? ctx.lineTo(ex, ey) : ctx.moveTo(ex, ey))); ctx.stroke();
      ctx.globalAlpha = 1;
    }

    ctx.strokeStyle = curveColor; ctx.lineWidth = 2.5;
    ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();

    ctx.lineWidth = 1.5; ctx.strokeStyle = outline;
    shown.forEach(c => {
      const [x, y] = toPx(c.x, c.y);
      ctx.fillStyle = c.src === dragIndex ? selected : cvColor;
      ctx.beginPath();
      if (c.link) ctx.arc(x, y, 6, 0, Math.PI * 2); else ctx.rect(x - 5, y - 5, 10, 10);
      ctx.fill(); ctx.stroke();
    });
  }, [field, comb, dragIndex, axisStart, axisEnd]); // eslint-disable-line react-hooks/exhaustive-deps

  const drawFieldProfile = useCallback(() => {
    const c = profileRef.current;
    if (!c) return;
    drawSourceProfile(c, source, field, radius, innerClamped, lengthText);
  }, [source, field, radius, innerClamped, lengthText]);

  useEffect(() => {
    drawEditor();
    drawFieldProfile();
  }, [drawEditor, drawFieldProfile, large]);
  useEffect(() => {
    const ro = new ResizeObserver(() => {
      drawEditor();
      drawFieldProfile();
    });
    if (editorRef.current) ro.observe(editorRef.current);
    return () => ro.disconnect();
  }, [drawEditor, drawFieldProfile]);

  // ── editing points ──
  const pointerPos = e => { const r = editorRef.current.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const hit = (px, py) => {
    let best = -1, bestD = 14;
    shown.forEach(c => { const [x, y] = toPx(c.x, c.y), d = Math.hypot(x - px, y - py); if (d < bestD) { bestD = d; best = c.src; } });
    return best;
  };
  const onPointerDown = e => {
    const [px, py] = pointerPos(e), i = hit(px, py);
    if (i < 0) return;
    const pts = curve.points.map(q => q.slice());
    const s = shown.find(c => c.src === i);
    let lead = curve.lead;
    // Grabbing one side of a Restart link makes it lead; start it from where it is drawn
    if (s && s.link) { lead = i === 1 ? 'start' : 'end'; pts[i][0] = s.x; }
    editorRef.current.setPointerCapture(e.pointerId);
    setDragIndex(i);
    update({ ...curve, points: pts, lead });
  };
  const onPointerMove = e => {
    const [px, py] = pointerPos(e);
    if (dragIndex < 0) { editorRef.current.style.cursor = hit(px, py) >= 0 ? 'grab' : 'crosshair'; return; }
    let [x, y] = fromPx(px, py);
    const pts = curve.points.map(q => q.slice()), last = pts.length - 1;
    if (dragIndex === 0) x = 0; else if (dragIndex === last) x = 1;
    else x = Math.min(pts[dragIndex + 1][0] - GAP, Math.max(pts[dragIndex - 1][0] + GAP, x));
    pts[dragIndex] = [x, Math.min(1, Math.max(0, y))];
    update({ ...curve, points: pts });
  };
  const endDrag = () => { if (dragIndex >= 0) { setDragIndex(-1); flush(); } };
  const onDoubleClick = e => {
    const [px, py] = pointerPos(e), i = hit(px, py), pts = curve.points.map(q => q.slice());
    if (i > 0 && i < pts.length - 1) {
      if (pts.length > curve.degree + 1) pts.splice(i, 1); else return;
    } else if (i < 0) {
      const [x, y] = fromPx(px, py);
      if (x <= 0 || x >= 1) return;
      pts.splice(pts.findIndex(q => q[0] > x), 0, [x, Math.min(1, Math.max(0, y))]);
    } else return;
    update({ ...curve, points: pts });
  };

  const set = patch => update({ ...curve, ...patch });
  // A preset replaces the shape and repeats; the output range and degree stay as they are
  const applyPreset = name => {
    if (!name) return;
    const pr = presetCurve(name);
    update({ ...pr, output: curve.output, degree: curve.degree, points: ensureEnoughPoints(pr.points, curve.degree) });
  };
  const pct = v => `${Math.round(v * 100)}%`;

  return (
    <div className="falloff-modal-overlay" onPointerDown={e => { if (e.target === e.currentTarget) close(); }}
         onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') close(); }}>
      <div ref={modalRef} className={`falloff-modal${large ? ' large' : ''}`} role="dialog" aria-label="Falloff curve editor">
        <div className="falloff-modal-head">
          <div className="falloff-modal-title">{src.kind} <span>· {title}</span></div>
          <span className="falloff-modal-field" title="Set on the node">Shape <b>{src.label}</b></span>
          <label className="falloff-modal-field">Preset
            <select value={preset || ''} aria-label="Preset"
                    onChange={e => applyPreset(e.target.value)}>
              <option value="" disabled>Custom</option>
              {PRESET_NAMES.map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button type="button" className="falloff-modal-x" aria-label="Close" onClick={close}>×</button>
        </div>

        <div className="falloff-modal-body">
          <div className="falloff-modal-view">
            <canvas ref={editorRef} className="falloff-modal-editor"
                    aria-label="Falloff curve. Drag the points to shape the fade."
                    onPointerDown={onPointerDown} onPointerMove={onPointerMove}
                    onPointerUp={endDrag} onPointerCancel={endDrag} onDoubleClick={onDoubleClick} />
            <div className="falloff-modal-strip">
              <span className="falloff-modal-chips">
                {rows.map(r => (
                  // Just the grade; its tip names the join and says why, so the strip
                  // stays one short line that never changes height
                  <b key={r.name} className={`falloff-chip grade-${r.grade}`} aria-label={`${r.name}: ${GRADE_LABEL[r.grade]}`}
                     onMouseEnter={e => showPortTipSoon({ anchor: e.currentTarget,
                       title: `${r.name}: ${GRADE_LABEL[r.grade]}`, body: gradeReason(r.name, r.grade) })}
                     onMouseLeave={e => hidePortTip(e.currentTarget)}>
                    {GRADE_LABEL[r.grade]}
                  </b>
                ))}
              </span>
              <span className="falloff-modal-tools">
                <span className="falloff-seg" role="group" aria-label="Degree">
                  <button type="button" aria-pressed={curve.degree === 3}
                          onClick={() => set({ degree: 3 })}>Cubic</button>
                  <button type="button" aria-pressed={curve.degree === 5}
                          onClick={() => set({ degree: 5, points: ensureEnoughPoints(curve.points, 5) })}>Quintic</button>
                </span>
                <button type="button" aria-pressed={comb} onClick={() => setComb(v => !v)}>Comb</button>
              </span>
            </div>
            <canvas ref={profileRef} className="falloff-modal-profile" aria-label="Strength across the field, through the center" />
          </div>

          <div className="falloff-modal-controls">
            <div className="falloff-group">
              <h4>Shape</h4>
              <div className="falloff-row">
                <label htmlFor="fc-repeat">Repeat</label>
                <input id="fc-repeat" type="range" min="1" max="12" step="1" value={curve.repeat} style={{ '--fill': `${((curve.repeat) - (1)) / ((12) - (1)) * 100}%` }}
                       onChange={e => set({ repeat: parseInt(e.target.value, 10) })} />
                <output>{curve.repeat}</output>
              </div>
              <span className="falloff-seg" role="group" aria-label="Repeat style">
                <button type="button" aria-pressed={curve.repeat_style === 'mirror'} onClick={() => set({ repeat_style: 'mirror' })}>Mirror</button>
                <button type="button" aria-pressed={curve.repeat_style === 'restart'} onClick={() => set({ repeat_style: 'restart' })}>Restart</button>
              </span>
              <div className="falloff-row">
                <label htmlFor="fc-decay">Decay</label>
                <input id="fc-decay" type="range" min="0" max="1" step="0.01" value={curve.decay} style={{ '--fill': `${((curve.decay) - (0)) / ((1) - (0)) * 100}%` }}
                       onChange={e => set({ decay: parseFloat(e.target.value) })} />
                <output>{pct(curve.decay)}</output>
              </div>
              <label className="falloff-check">
                <input type="checkbox" checked={curve.invert} onChange={e => set({ invert: e.target.checked })} /> Invert
              </label>
            </div>
            <div className="falloff-group">
              <h4>Output</h4>
              <div className="falloff-row">
                <label htmlFor="fc-start">At start</label>
                <input id="fc-start" type="range" min={Math.min(0, curve.output.start)} max={Math.max(1, curve.output.start)} step="0.01" value={curve.output.start} style={{ '--fill': `${((curve.output.start) - (Math.min(0, curve.output.start))) / ((Math.max(1, curve.output.start)) - (Math.min(0, curve.output.start))) * 100}%` }}
                       onChange={e => set({ output: { ...curve.output, start: parseFloat(e.target.value) } })} />
                <output>{pct(curve.output.start)}</output>
              </div>
              <div className="falloff-row">
                <label htmlFor="fc-end">At end</label>
                <input id="fc-end" type="range" min={Math.min(0, curve.output.end)} max={Math.max(1, curve.output.end)} step="0.01" value={curve.output.end} style={{ '--fill': `${((curve.output.end) - (Math.min(0, curve.output.end))) / ((Math.max(1, curve.output.end)) - (Math.min(0, curve.output.end))) * 100}%` }}
                       onChange={e => set({ output: { ...curve.output, end: parseFloat(e.target.value) } })} />
                <output>{pct(curve.output.end)}</output>
              </div>
            </div>
            {source === 'linear' && (
              <div className="falloff-group">
                <h4>Linear</h4>
                <div className="falloff-row numeric">
                  <span>Length</span><span className="falloff-modal-readout">{lengthText}</span>
                </div>
              </div>
            )}
            {(source === 'sphere' || source === 'box') && (
              <div className="falloff-group">
                <h4>{src.label}</h4>
                <div className="falloff-row numeric">
                  <label htmlFor="fc-radius">Radius <span className="falloff-unit">cm</span></label>
                  <NumberField id="fc-radius" value={radius} locked={radiusLocked} min={0.001}
                               onCommit={v => onNumber('radius', v)} />
                </div>
                <div className="falloff-row numeric">
                  <label htmlFor="fc-inner">Inner <span className="falloff-unit">cm</span></label>
                  <NumberField id="fc-inner" value={inner} locked={innerLocked}
                               onCommit={v => onNumber('inner_radius', v)} />
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="falloff-modal-foot">
          <span className="falloff-modal-info" tabIndex={0} aria-label="How to edit the curve"
                onMouseEnter={e => showPortTipSoon({ anchor: e.currentTarget, sections: [
                  { title: 'Editing the curve', body: 'Drag points. Double-click to add or remove one. Circles are linked across a seam.' },
                  ...(SET_ON_NODE[source] ? [{ title: 'Positioning attributes', body: SET_ON_NODE[source] }] : []),
                ] })}
                onMouseLeave={e => hidePortTip(e.currentTarget)}>i</span>
          <span className="falloff-modal-foot-gap" />
          <button type="button" className="falloff-modal-done" onClick={close}>Done</button>
        </div>
      </div>
    </div>
  );
}

export default FalloffCurveEditor;
