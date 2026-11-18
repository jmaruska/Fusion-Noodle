import test from 'node:test';
import assert from 'node:assert/strict';
import {
  planGroup, placeRow, estimateNodeSize, nodeRect, boundsOf, rectsOverlap, rectContains,
  NODE_WIDTH, COLUMN_GAP, CLEARANCE
} from '../src/utils/nodePlacement.js';

const companions = [
  { type: 'Atomizer', side: 'before', sourcePort: 'collection', targetPort: 'collection' },
  { type: 'Materializer', side: 'after', sourcePort: 'collection', targetPort: 'collection' }
];
const specs = [
  { type: 'Array_2D_Grid', companions, inputs: [{ type: 'collection' }, { type: 'vector3' }], outputs: [{ type: 'collection' }] },
  { type: 'Atomizer', companions: [], inputs: [{ type: 'geometry' }], outputs: [{ type: 'collection' }] },
  { type: 'Materializer', companions: [], inputs: [{ type: 'collection' }], outputs: [{ type: 'geometry' }] },
  { type: 'cube_generator', companions: [], inputs: [], outputs: [] }
];
const existing = (type, x = 0, y = 0) => ({ id: type + x, position: { x, y }, data: { nodeType: type } });

test('an array in an empty graph brings an Atomizer and a Materializer, wired in order', () => {
  const plan = planGroup('Array_2D_Grid', specs, []);
  assert.deepEqual(plan.members.map(m => m.type), ['Atomizer', 'Array_2D_Grid', 'Materializer']);
  assert.deepEqual(plan.members.map(m => m.role), ['before', 'main', 'after']);
  assert.deepEqual(plan.connections, [
    { from: 0, sourcePort: 'collection', to: 1, targetPort: 'collection' },
    { from: 1, sourcePort: 'collection', to: 2, targetPort: 'collection' }
  ]);
});

test('a second array brings nothing when both helpers exist', () => {
  const plan = planGroup('Array_2D_Grid', specs, [existing('Atomizer'), existing('Materializer')]);
  assert.deepEqual(plan.members.map(m => m.type), ['Array_2D_Grid']);
  assert.deepEqual(plan.connections, []);
});

test('only the missing helper is added', () => {
  const plan = planGroup('Array_2D_Grid', specs, [existing('Atomizer')]);
  assert.deepEqual(plan.members.map(m => m.type), ['Array_2D_Grid', 'Materializer']);
  assert.deepEqual(plan.connections, [{ from: 0, sourcePort: 'collection', to: 1, targetPort: 'collection' }]);
});

test('a node with no companions is added alone', () => {
  assert.deepEqual(planGroup('cube_generator', specs, []).members, [{ type: 'cube_generator', role: 'main' }]);
});

test('an unknown node type has no plan', () => {
  assert.equal(planGroup('nope', specs, []), null);
});

test('a row is centered on the requested point and spaced left to right', () => {
  const sizes = [{ width: 180, height: 100 }, { width: 180, height: 300 }, { width: 180, height: 100 }];
  const { positions, moved } = placeRow(sizes, { x: 0, y: 0 }, []);
  assert.equal(moved, false);
  assert.equal(positions[1].x - positions[0].x, 180 + COLUMN_GAP);
  assert.equal(positions[2].x - positions[1].x, 180 + COLUMN_GAP);
  assert.equal(positions[0].x + (positions[2].x + 180 - positions[0].x) / 2, 0);
  assert.ok(positions.every(p => p.y === positions[0].y), 'tops are aligned');
});

test('a row that would land on existing nodes moves below all of them', () => {
  const sizes = [{ width: 180, height: 100 }, { width: 180, height: 100 }];
  const taken = [{ x: -50, y: -50, width: 180, height: 120 }, { x: 400, y: 500, width: 180, height: 200 }];
  const { positions, bounds, moved } = placeRow(sizes, { x: 0, y: 0 }, taken);
  assert.equal(moved, true);
  assert.ok(positions[0].y >= 700 + CLEARANCE, 'below the lowest existing node');
  assert.ok(taken.every(rect => !rectsOverlap(bounds, rect, CLEARANCE)));
});

test('a row placed in clear space stays put', () => {
  const sizes = [{ width: 180, height: 100 }];
  const taken = [{ x: 2000, y: 2000, width: 180, height: 100 }];
  assert.equal(placeRow(sizes, { x: 0, y: 0 }, taken).moved, false);
});

test('node size uses the measured size when the browser has one', () => {
  const measured = { position: { x: 5, y: 6 }, measured: { width: 300, height: 400 }, data: { nodeType: 'Atomizer' } };
  assert.deepEqual(nodeRect(measured, t => specs.find(s => s.type === t)), { x: 5, y: 6, width: 300, height: 400 });
  const unmeasured = { position: { x: 0, y: 0 }, data: { nodeType: 'Array_2D_Grid' } };
  const rect = nodeRect(unmeasured, t => specs.find(s => s.type === t));
  assert.equal(rect.width, NODE_WIDTH);
  assert.ok(rect.height > estimateNodeSize(specs[1]).height, 'a vector input makes a node taller');
});

test('bounds and containment', () => {
  const bounds = boundsOf([{ x: 0, y: 0, width: 10, height: 10 }, { x: 20, y: 30, width: 10, height: 10 }]);
  assert.deepEqual(bounds, { x: 0, y: 0, width: 30, height: 40 });
  assert.equal(rectContains(bounds, { x: 5, y: 5, width: 10, height: 10 }), true);
  assert.equal(rectContains(bounds, { x: 25, y: 5, width: 10, height: 10 }), false);
  assert.equal(boundsOf([]), null);
});
