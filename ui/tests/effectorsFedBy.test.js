import test from 'node:test';
import assert from 'node:assert/strict';
import { effectorsFedBy } from '../src/utils/effectorsFedBy.js';

const node = (id, category = 'math') => ({ id, data: { nodeCategory: category } });
const edge = (source, target) => ({ source, target });

test('an effector shows its own effect', () => {
  assert.deepEqual(effectorsFedBy('f', [node('f', 'effector')], []), ['f']);
});

test('a modifier shows through every effector it feeds, through Math nodes', () => {
  const nodes = [node('mod', 'modifiers'), node('mul'), node('e1', 'effector'), node('e2', 'effector'), node('e3', 'effector')];
  const edges = [edge('mod', 'mul'), edge('mul', 'e1'), edge('mod', 'e2'), edge('e2', 'e3')];
  assert.deepEqual(effectorsFedBy('mod', nodes, edges).sort(), ['e1', 'e2']);   // stops at e2
});

test('a modifier that feeds nothing has no effectors', () => {
  assert.deepEqual(effectorsFedBy('mod', [node('mod', 'modifiers')], []), []);
});
