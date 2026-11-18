import test from 'node:test';
import assert from 'node:assert/strict';
import { handleFieldKeys } from '../src/utils/fieldKeys.js';

function press(key) {
  const calls = [];
  const event = {
    key,
    preventDefault: () => calls.push('preventDefault'),
    stopPropagation: () => calls.push('stopPropagation'),
    currentTarget: { blur: () => calls.push('blur') },
  };
  handleFieldKeys(event, () => calls.push('forget'));
  return calls;
}

test('Enter leaves the field, which saves what was typed', () => {
  assert.deepEqual(press('Enter'), ['preventDefault', 'blur']);
});

test('Escape forgets the typing before leaving, so nothing is saved', () => {
  const calls = press('Escape');
  assert.ok(calls.indexOf('forget') < calls.indexOf('blur'));
  assert.ok(calls.includes('stopPropagation'));
});

test('other keys are left alone', () => {
  assert.deepEqual(press('5'), []);
  assert.deepEqual(press('Tab'), []);
});
