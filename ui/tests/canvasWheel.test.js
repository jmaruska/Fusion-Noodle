import test from 'node:test';
import assert from 'node:assert/strict';
import { wheelKind, zoomAt, scaleAt, panBy } from '../src/utils/canvasWheel.js';

const ev = (o) => ({ ctrlKey: false, deltaMode: 0, deltaX: 0, deltaY: 0, timeStamp: 1000, ...o });

test('pinch, mouse wheel and trackpad are told apart', () => {
  assert.equal(wheelKind(ev({ ctrlKey: true, deltaY: 3 })), 'pinch');
  assert.equal(wheelKind(ev({ deltaY: 100, wheelDeltaY: -120 })), 'mouse');
  assert.equal(wheelKind(ev({ deltaMode: 1, deltaY: 3 })), 'mouse');
  assert.equal(wheelKind(ev({ deltaY: 4, wheelDeltaY: -12 })), 'trackpad');
  assert.equal(wheelKind(ev({ deltaX: 2, deltaY: 6 })), 'trackpad');
});

test('a gesture keeps its kind until it pauses', () => {
  const previous = { kind: 'trackpad', time: 1000 };
  assert.equal(wheelKind(ev({ deltaY: 40, wheelDeltaY: -120, timeStamp: 1050 }), previous), 'trackpad');
  assert.equal(wheelKind(ev({ deltaY: 100, wheelDeltaY: -120, timeStamp: 1500 }), previous), 'mouse');
});

test('zooming keeps the point under the cursor still', () => {
  const before = { x: 50, y: 20, zoom: 1 };
  const point = { x: 200, y: 150 };
  const after = zoomAt(before, point, -100, 0, 0.1, 4);
  assert.ok(after.zoom > 1);
  // The canvas position under the cursor is the same before and after
  const canvasPoint = v => ({ x: (point.x - v.x) / v.zoom, y: (point.y - v.y) / v.zoom });
  assert.deepEqual(canvasPoint(after).x.toFixed(9), canvasPoint(before).x.toFixed(9));
  assert.deepEqual(canvasPoint(after).y.toFixed(9), canvasPoint(before).y.toFixed(9));
});

test('zoom stays within its limits; two fingers pan', () => {
  assert.equal(zoomAt({ x: 0, y: 0, zoom: 4 }, { x: 0, y: 0 }, -1000, 0, 0.1, 4).zoom, 4);
  assert.deepEqual(panBy({ x: 10, y: 10, zoom: 2 }, 5, -3), { x: 5, y: 13, zoom: 2 });
});

test('a pinch zooms faster per unit than a wheel, and scaleAt keeps the fingers still', () => {
  const v = { x: 0, y: 0, zoom: 1 };
  assert.ok(zoomAt(v, { x: 0, y: 0 }, -10, 0, 0.1, 4, true).zoom > zoomAt(v, { x: 0, y: 0 }, -10, 0, 0.1, 4).zoom);
  const after = scaleAt({ x: 10, y: 20, zoom: 1 }, { x: 100, y: 100 }, 2, 0.1, 4);
  assert.deepEqual(after, { x: -80, y: -60, zoom: 2 });
});
