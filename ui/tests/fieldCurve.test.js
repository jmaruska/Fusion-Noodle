import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildField, normalizeCurve, presetCurve, matchingPreset, DEFAULT_CURVE_NAME } from '../src/utils/fieldCurve.js';

const vectors = JSON.parse(readFileSync(new URL('../../tests/fixtures/field_curve_vectors.json', import.meta.url)));

test('every shared example matches (the Python curve runs the same file)', () => {
  for (const c of vectors.cases) {
    const f = buildField(c.curve, c.start_flat, c.open_ends);
    for (const [t, expected] of c.samples) {
      assert.ok(Math.abs(f.value(t, true) - expected) < 1e-9, `${c.name} at t=${t}`);
    }
    assert.deepEqual(f.continuity().map(r => [r.name, r.grade]), c.continuity, c.name);
  }
});

test('the lookup table stays close to the exact curve', () => {
  for (const c of vectors.cases) {
    const f = buildField(c.curve, c.start_flat, c.open_ends);
    const worst = Math.max(...c.samples.map(([t, v]) => Math.abs(f.value(t) - v)));
    assert.ok(worst < 5e-4, c.name);
  }
});

test('anything unreadable becomes the default curve', () => {
  for (const v of [null, '', 'not json', '{"points": []}', 42]) {
    assert.deepEqual(normalizeCurve(v), presetCurve(DEFAULT_CURVE_NAME));
  }
});

test('a preset is recognised until a point moves', () => {
  const pulse = presetCurve('Pulse');
  assert.equal(matchingPreset(JSON.stringify(pulse)), 'Pulse');
  pulse.points[2][1] = 0.9;
  assert.equal(matchingPreset(pulse), null);
});
