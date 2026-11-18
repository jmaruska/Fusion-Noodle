import FusionBridge from '../bridge/FusionBridge';
import { hideAllBodies, showBodies } from './visibilityBus.js';

/**
 * Show or hide bodies for the visualizer, in one request for every node, so Fusion
 * makes one undo step of it (see visibilityBus.js and Noodle.py).
 */
function send(nodes, visible) {
  if (!nodes.length) return;
  FusionBridge.sendMessage('set_nodes_visibility', { nodes, visible })
    .catch(error => console.error(`[Visibility] Could not ${visible ? 'show' : 'hide'} bodies:`, error));
}

/** Hide every node's bodies so the visualizer's dots can be seen. */
export function hideBodiesForVisualizer() {
  send(hideAllBodies(), false);
}

/** Show the bodies of `ids` again, as they were before the curve editor opened. */
export function restoreBodies(ids) {
  send(showBodies(ids), true);
}
