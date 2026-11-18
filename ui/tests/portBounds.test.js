import test from 'node:test';
import assert from 'node:assert/strict';
import { boundsText, boundsProblem, nodeBoundsProblems } from '../src/utils/portBounds.js';

const count = { type: 'integer', minValue: 1, maxValue: 100 };
const width = { type: 'float', unit: 'length', minValue: 0.001 };

test('messages match the backend (bounds_problem in contracts.py)', () => {
  assert.equal(boundsProblem(50, count), null);
  assert.equal(boundsProblem(500, count), 'must be between 1 and 100');
  assert.equal(boundsProblem(2.5, count), 'must be a whole number');
  assert.equal(boundsProblem(0, width), 'must be at least 0.001 cm');
  assert.equal(boundsProblem(2, { type: 'float', maxValue: 1 }), 'must be at most 1');
});

test('the range beside a field', () => {
  assert.equal(boundsText(count), '1 – 100');
  assert.equal(boundsText(width), '≥ 0.001 cm');
  assert.equal(boundsText({ type: 'float', unit: 'angle', minValue: -90, maxValue: 90 }), '-90 – 90°');
  assert.equal(boundsText({ type: 'float' }), null);
});

test('a node: typed and connected values are checked, hidden ports and modifiers are not', () => {
  const node = {
    data: {
      nodeInfo: {
        inputs: {
          count_x: { name: 'count_x', label: 'Count X', ...count },
          radius: { name: 'radius', label: 'Radius', ...width, visibleWhen: { port: 'shape', values: ['sphere'], default: 'sphere' } },
          strength: { name: 'strength', type: 'float', minValue: 0 },
        },
      },
      currentInputs: { count_x: 3, shape: 'linear', radius: -5 },
      computedInputs: { count_x: 400, strength: { modifier_type: 'noise' } },
    },
  };
  const { errors, fieldErrors } = nodeBoundsProblems(node);
  assert.deepEqual(errors, ['Count X must be between 1 and 100']);
  assert.deepEqual(Object.keys(fieldErrors), ['count_x']);
});

test('every number port must hold a number; nothing yet or a modifier is fine', () => {
  const tilt = { type: 'float' };
  assert.equal(boundsProblem('45', tilt), 'must be a number');
  assert.equal(boundsProblem([1], tilt), 'must be a number');
  assert.equal(boundsProblem(undefined, tilt), null);
  assert.equal(boundsProblem({ modifier_type: 'wave' }, tilt), null);
  assert.equal(boundsProblem(-720, tilt), null);
});

import { formatShown } from '../src/utils/units.js';
test('fields show at most 4 decimals', () => {
  assert.equal(formatShown(28.88623261), '28.8862');
  assert.equal(formatShown(0.1), '0.1');
  assert.equal(formatShown(100), 100);
});
