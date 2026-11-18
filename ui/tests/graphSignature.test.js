import test from 'node:test';
import assert from 'node:assert/strict';
import { graphSignatures } from '../src/utils/graphSignature.js';

const node = (id, x, inputs, extra = {}) => ({ id, position: { x, y: 0 }, data: { nodeType: 'box', currentInputs: inputs }, ...extra });
const edges = [{ source: 'a', sourceHandle: 'output-geometry', target: 'b', targetHandle: 'input-geometry' }];

test('moving or selecting a node changes the layout but not the result', () => {
  const before = graphSignatures([node('a', 0, { width: 2 }), node('b', 100, {})], edges);
  const moved = graphSignatures([node('a', 250, { width: 2 }, { selected: true }), node('b', 100, {})], edges);
  assert.equal(moved.result, before.result);
  assert.notEqual(moved.full, before.full);
});

test('a value or a connection changes the result', () => {
  const before = graphSignatures([node('a', 0, { width: 2 }), node('b', 100, {})], edges);
  assert.notEqual(graphSignatures([node('a', 0, { width: 3 }), node('b', 100, {})], edges).result, before.result);
  assert.notEqual(graphSignatures([node('a', 0, { width: 2 }), node('b', 100, {})], []).result, before.result);
});
