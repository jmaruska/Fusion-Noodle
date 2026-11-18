import { test } from 'node:test';
import assert from 'node:assert/strict';
import { onVisibilityEvent, hideAllBodies, showBodies } from '../src/utils/visibilityBus.js';

// Two body eyes, as BaseNode's VisibilityToggle listens
function eye(nodeId, visible) {
  const state = { visible };
  const off = [
    onVisibilityEvent('hide-bodies', nodes => {
      if (!state.visible) return;
      state.visible = false;
      nodes.push({ nodeId, nodeType: 'Materializer' });
    }),
    onVisibilityEvent('show-bodies', ({ ids, nodes }) => {
      if (state.visible || !ids.includes(nodeId)) return;
      state.visible = true;
      nodes.push({ nodeId, nodeType: 'Materializer' });
    }),
  ];
  return { state, remove: () => off.forEach(f => f()) };
}

test('hiding collects every eye that was on, for one request', () => {
  const a = eye('a', true), b = eye('b', false), c = eye('c', true);
  assert.deepEqual(hideAllBodies().map(n => n.nodeId), ['a', 'c']);
  assert.deepEqual([a.state.visible, b.state.visible, c.state.visible], [false, false, false]);
  [a, b, c].forEach(e => e.remove());
});

test('showing turns back on only the eyes asked for', () => {
  const a = eye('a', false), b = eye('b', false);
  assert.deepEqual(showBodies(['b']).map(n => n.nodeId), ['b']);
  assert.deepEqual([a.state.visible, b.state.visible], [false, true]);
  [a, b].forEach(e => e.remove());
});
