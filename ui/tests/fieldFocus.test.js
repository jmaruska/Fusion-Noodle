import test from 'node:test';
import assert from 'node:assert/strict';
import { nextFieldIndex } from '../src/utils/fieldFocus.js';

test('Tab moves to the next field and wraps to the first', () => {
  assert.equal(nextFieldIndex(3, 0, false), 1);
  assert.equal(nextFieldIndex(3, 2, false), 0);
});

test('Shift+Tab moves to the previous field and wraps to the last', () => {
  assert.equal(nextFieldIndex(3, 1, true), 0);
  assert.equal(nextFieldIndex(3, 0, true), 2);
});

test('from outside the fields, Tab starts at the first and Shift+Tab at the last', () => {
  assert.equal(nextFieldIndex(4, -1, false), 0);
  assert.equal(nextFieldIndex(4, -1, true), 3);
});

test('a single field stays put, and no fields means nowhere to go', () => {
  assert.equal(nextFieldIndex(1, 0, false), 0);
  assert.equal(nextFieldIndex(0, -1, false), -1);
});
