import test from 'node:test';
import assert from 'node:assert/strict';
import { linkHexSpacing } from '../src/utils/hexSpacing.js';

test('only a hexagonal grid links its spacings', () => {
  assert.deepEqual(linkHexSpacing({ array_type: 'grid', spacing_x: 4 }, 'spacing_x'), {});
});

test('Spacing X sets the rows; Spacing Y sets the columns', () => {
  assert.deepEqual(linkHexSpacing({ array_type: 'hexagonal', spacing_x: 2 }, 'spacing_x'), { spacing_y: 1.7321 });
  assert.deepEqual(linkHexSpacing({ array_type: 'hexagonal', spacing_y: 1.5 }, 'spacing_y'), { spacing_x: 1.7321 });
});

test('choosing Hexagonal brings Spacing Y in line', () => {
  assert.deepEqual(linkHexSpacing({ array_type: 'hexagonal', spacing_x: 5, spacing_y: 5 }, 'array_type'), { spacing_y: 4.3301 });
});

test('editing back and forth does not creep', () => {
  let inputs = { array_type: 'hexagonal', spacing_x: 3 };
  for (let i = 0; i < 20; i++) {
    inputs = { ...inputs, ...linkHexSpacing(inputs, 'spacing_x') };
    inputs = { ...inputs, ...linkHexSpacing(inputs, 'spacing_y') };
  }
  assert.equal(inputs.spacing_x, 3);
});

import { hexLinkedInputs } from '../src/utils/hexSpacing.js';

test('a connected Spacing X drives Spacing Y, shown as connected', () => {
  const linked = hexLinkedInputs({ array_type: 'hexagonal', spacing_y: 2.5981 }, { spacing_x: 4 }, new Set(['spacing_x']));
  assert.deepEqual(linked, { spacing_y: 3.4641 });
});

test('a connected Spacing Y drives Spacing X', () => {
  const linked = hexLinkedInputs({ array_type: 'hexagonal', spacing_x: 3 }, { spacing_y: 4 }, new Set(['spacing_y']));
  assert.deepEqual(linked, { spacing_x: 4.6188 });
});

test('X wins when both are connected; nothing is linked outside Hexagonal, or before the value is known', () => {
  assert.deepEqual(hexLinkedInputs({ array_type: 'hexagonal' }, { spacing_x: 2, spacing_y: 9 }, new Set(['spacing_x', 'spacing_y'])),
                   { spacing_y: 1.7321 });
  assert.deepEqual(hexLinkedInputs({ array_type: 'grid' }, { spacing_x: 4 }, new Set(['spacing_x'])), {});
  assert.deepEqual(hexLinkedInputs({ array_type: 'hexagonal' }, {}, new Set(['spacing_x'])), {});
});

import { hexBlockedInput } from '../src/utils/hexSpacing.js';
test('the driven spacing is blocked; both connected leaves both open to remove one', () => {
  const hex = { array_type: 'hexagonal' };
  assert.equal(hexBlockedInput(hex, new Set(['spacing_x'])), 'spacing_y');
  assert.equal(hexBlockedInput(hex, new Set(['spacing_y'])), 'spacing_x');
  assert.equal(hexBlockedInput(hex, new Set(['spacing_x', 'spacing_y'])), null);
  assert.equal(hexBlockedInput({ array_type: 'grid' }, new Set(['spacing_x'])), null);
});
