// The polling manager drives Select buttons and 3D Point tracking. These tests
// cover its timer bookkeeping only; they never run a feature handler.
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';

globalThis.document = { hidden: false, addEventListener() {}, removeEventListener() {} };
globalThis.window = { addEventListener() {}, removeEventListener() {} };

const { UnifiedPollingManager } = await import('../src/modules/UnifiedPollingManager.js');

function freshManager() {
  const manager = new UnifiedPollingManager();
  manager._ensureTrackingSetup = () => {};
  return manager;
}

test('polling restarts after the palette is shown again', () => {
  mock.timers.enable({ apis: ['setInterval'] });
  try {
    const manager = freshManager();
    manager.enterSelectionMode();
    manager.registered3DPointNodes.set('point', {});
    manager.enableFeature('pointCoordinateCheck');
    assert.equal(manager.isActive, true);

    // Hidden: everything is suspended, then the selection ends while hidden,
    // which used to stop the timer for good.
    manager.enterHiddenMode();
    manager.exitSelectionMode();
    assert.equal(manager.isActive, false);

    manager.exitHiddenMode();
    assert.equal(manager.isActive, true, 'the timer must run again');
    assert.equal(manager.featureConfigs.get('pointCoordinateCheck').enabled, true);
    manager.stop();
  } finally {
    mock.timers.reset();
  }
});
