import test from 'node:test';
import assert from 'node:assert/strict';
import { planConnection, connect, reconnect, styleEdges, areTypesCompatible, typeColor } from '../src/utils/ports.js';

const node = (id, inputs, outputs) => ({ id, data: { nodeInfo: { inputs, outputs } } });
const nodes = [
  node('num1', {}, { value: { type: 'float' } }),
  node('num2', {}, { value: { type: 'float' } }),
  node('vec', {}, { vector: { type: 'vector3' } }),
  node('box', { width: { type: 'float' }, height: { type: 'float' } }, { geometry: { type: 'geometry' } }),
];
const link = (source, sourcePort, target, targetPort) => ({
  source, sourceHandle: `output-${sourcePort}`, target, targetHandle: `input-${targetPort}`,
});
const edge = (id, ...args) => ({ id, ...link(...args) });

test('a new connection on a free input is valid and replaces nothing', () => {
  assert.deepEqual(planConnection(link('num1', 'value', 'box', 'width'), nodes, []), { valid: true, replaces: null });
});

test('a new connection on an occupied input replaces the old one', () => {
  const edges = [edge('old', 'num1', 'value', 'box', 'width'), edge('keep', 'num1', 'value', 'box', 'height')];
  const plan = planConnection(link('num2', 'value', 'box', 'width'), nodes, edges);
  assert.deepEqual(plan, { valid: true, replaces: 'old' });
  const after = connect(link('num2', 'value', 'box', 'width'), nodes, edges);
  assert.deepEqual(after.map(e => e.source + '>' + e.targetHandle).sort(), ['num1>input-height', 'num2>input-width']);
});

test('reconnecting the same pair again does nothing', () => {
  const edges = [edge('old', 'num1', 'value', 'box', 'width')];
  assert.equal(planConnection(link('num1', 'value', 'box', 'width'), nodes, edges).valid, false);
});

test('incompatible types and self-connections are refused', () => {
  assert.equal(planConnection(link('vec', 'vector', 'box', 'width'), nodes, []).valid, false);
  assert.equal(planConnection(link('box', 'geometry', 'box', 'width'), nodes, []).valid, false);
});

test('dragging an end to another input moves the connection and takes over that input', () => {
  const moving = edge('m', 'num1', 'value', 'box', 'width');
  const edges = [moving, edge('h', 'num2', 'value', 'box', 'height')];
  const after = reconnect(moving, link('num1', 'value', 'box', 'height'), nodes, edges);
  assert.deepEqual(after.map(e => e.source + '>' + e.targetHandle), ['num1>input-height']);
});

test('loading keeps the last of two connections into one input, as the backend does', () => {
  const edges = [edge('a', 'num1', 'value', 'box', 'width'), edge('b', 'num2', 'value', 'box', 'width')];
  assert.deepEqual(styleEdges(edges, nodes).map(e => e.id), ['b']);
});

test('type families and colours', () => {
  assert.ok(areTypesCompatible('float', 'integer'));
  assert.ok(areTypesCompatible('vector3', 'point'));
  assert.ok(!areTypesCompatible('float', 'vector3'));
  assert.equal(typeColor('collection'), 'var(--noodle-color-collection)');
  assert.equal(typeColor('mystery'), 'var(--node-category-general)');
});

test('a hexagonal grid takes a connection into one spacing only', () => {
  const grid = {
    id: 'grid',
    data: {
      currentInputs: { array_type: 'hexagonal' },
      nodeInfo: { inputs: { spacing_x: { type: 'float' }, spacing_y: { type: 'float' } }, outputs: {} },
    },
  };
  const all = [...nodes, grid];
  const intoX = edge('x', 'num1', 'value', 'grid', 'spacing_x');
  // Y is driven by the connected X: refused
  assert.equal(planConnection(link('num2', 'value', 'grid', 'spacing_y'), all, [intoX]).valid, false);
  // Moving X's connection to Y is fine: X is then free
  assert.deepEqual(reconnect(intoX, link('num1', 'value', 'grid', 'spacing_y'), all, [intoX]).map(e => e.targetHandle),
                   ['input-spacing_y']);
  // A plain grid takes both
  const plain = { ...grid, data: { ...grid.data, currentInputs: { array_type: 'grid' } } };
  assert.equal(planConnection(link('num2', 'value', 'grid', 'spacing_y'), [...nodes, plain], [intoX]).valid, true);
});
