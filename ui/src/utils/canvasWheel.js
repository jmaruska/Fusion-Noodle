/**
 * Wheel navigation as in Fusion's viewport.
 *
 * - A mouse wheel zooms toward the cursor.
 * - Two fingers on a trackpad pan.
 * - Pinch zooms. Chromium sends a pinch as a wheel event with ctrlKey; WebKit sends
 *   gesture events. Both are handled here, toward the fingers.
 *
 * The browser can't say which device sent a wheel event, so it's inferred, as
 * drawing apps do: a mouse wheel moves in whole notches (wheelDelta a multiple
 * of 120, or line mode), a trackpad in small smooth steps, often sideways too.
 * A gesture keeps the kind it started with until it pauses, so one scroll never
 * switches between zoom and pan halfway.
 */
const GESTURE_GAP_MS = 200;

export function wheelKind(event, previous) {
  if (event.ctrlKey) return 'pinch';
  if (previous && event.timeStamp - previous.time < GESTURE_GAP_MS) return previous.kind;
  if (event.deltaMode !== 0) return 'mouse';             // Lines or pages: a notched wheel
  if (event.deltaX !== 0) return 'trackpad';             // Sideways: fingers
  const notches = event.wheelDeltaY;
  if (typeof notches === 'number' && notches !== 0) return Math.abs(notches) % 120 === 0 ? 'mouse' : 'trackpad';
  return Number.isInteger(event.deltaY) && Math.abs(event.deltaY) >= 50 ? 'mouse' : 'trackpad';
}

/** The viewport after a wheel zoom that keeps the point under the cursor fixed.
 *  A pinch's deltas are small, so it zooms ten times faster per unit, as d3-zoom does. */
export function zoomAt(viewport, point, deltaY, deltaMode, minZoom, maxZoom, pinch = false) {
  const step = (deltaMode === 1 ? 0.05 : 0.002) * (pinch ? 10 : 1);
  return scaleAt(viewport, point, Math.pow(2, -deltaY * step), minZoom, maxZoom);
}

/** The viewport after scaling by `factor` about `point`, within the zoom limits. */
export function scaleAt(viewport, point, factor, minZoom, maxZoom) {
  const zoom = Math.min(maxZoom, Math.max(minZoom, viewport.zoom * factor));
  const ratio = zoom / viewport.zoom;
  return {
    x: point.x - (point.x - viewport.x) * ratio,
    y: point.y - (point.y - viewport.y) * ratio,
    zoom,
  };
}

/** The viewport after a two-finger pan. */
export function panBy(viewport, deltaX, deltaY) {
  return { x: viewport.x - deltaX, y: viewport.y - deltaY, zoom: viewport.zoom };
}
