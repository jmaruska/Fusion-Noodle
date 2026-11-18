import test from 'node:test';
import assert from 'node:assert/strict';
import { portIsShown } from '../src/utils/nodeSpec.js';

const boxOnly = { visibleWhen: { port: 'shape', values: ['box'], default: 'sphere' } };
const sphereOrBox = { visibleWhen: { port: 'shape', values: ['sphere', 'box'], default: 'sphere' } };

test('a port without visibleWhen always shows', () => {
  assert.equal(portIsShown({}, { shape: 'linear' }), true);
});

test('a port shows only for the choices it belongs to', () => {
  assert.equal(portIsShown(boxOnly, { shape: 'box' }), true);
  assert.equal(portIsShown(boxOnly, { shape: 'linear' }), false);
  assert.equal(portIsShown(sphereOrBox, { shape: 'sphere' }), true);
});

test('a node saved before the dropdown existed counts as the default choice', () => {
  assert.equal(portIsShown(sphereOrBox, {}), true);
  assert.equal(portIsShown(boxOnly, {}), false);
});
