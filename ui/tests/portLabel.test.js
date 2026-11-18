import test from 'node:test';
import assert from 'node:assert/strict';
import { portLabel } from '../src/utils/nodeSpec.js';

test("a port's own label wins", () => {
  assert.equal(portLabel('direction', { inputs: { direction: { name: 'direction', label: 'X Axis' } } }), 'X Axis');
});

test('ports given as a list are found too', () => {
  assert.equal(portLabel('rx', { inputs: [{ name: 'rx', label: 'Rotate X' }] }), 'Rotate X');
});

test('a port without a label shows its name in Title Case', () => {
  assert.equal(portLabel('count_x', { inputs: { count_x: { name: 'count_x' } } }), 'Count X');
  assert.equal(portLabel('inner_radius', null), 'Inner Radius');
});
