/**
 * Lets the eye icons on different nodes react to each other.
 *
 * Body eyes (Box, Materializer, ...) show and hide generated bodies. Effector
 * eyes turn the visualizer's dots on and off. The two are exclusive in one
 * direction each:
 *
 *   'hide-bodies'      An effector eye was turned on. Every body eye turns off,
 *                      so bodies don't cover the dots. Payload: an array each eye
 *                      that turns off adds {nodeId, nodeType} to. Use hideAllBodies().
 *   'visualizers-off'  A body eye was turned on. Every effector eye turns off,
 *                      so the dots go away and the geometry is back.
 *   'bodies-changed'   A Generate made new bodies. Body eyes read their state
 *                      from the design again.
 *
 * Bodies are hidden only once the dots are on screen (useVisualizer emits
 * 'hide-bodies' after a successful draw), so a click shows something at once even
 * when hiding many bodies takes a second or two.
 *
 * The curve editor turns the visualizer on while it is open and puts the view back
 * when it closes, using two more events with a payload:
 *
 *   'collect-visible-bodies'  payload: an array. Each body eye that is showing
 *                             bodies adds its node id.
 *   'show-bodies'             payload: {ids, nodes}. Those body eyes turn on again,
 *                             without turning any visualizer off, and add
 *                             {nodeId, nodeType} to `nodes`. Use showBodies(ids).
 *
 * The eyes only change their icons. The bodies are shown or hidden in one request
 * for all of them, which Noodle applies as one undo step.
 */
const listeners = new Map();

export function onVisibilityEvent(name, callback) {
  if (!listeners.has(name)) listeners.set(name, new Set());
  listeners.get(name).add(callback);
  return () => listeners.get(name).delete(callback);
}

export function emitVisibilityEvent(name, payload) {
  (listeners.get(name) || []).forEach(callback => callback(payload));
}

/** Turn every body eye off. Returns the {nodeId, nodeType} of each one that was on. */
export function hideAllBodies() {
  const nodes = [];
  emitVisibilityEvent('hide-bodies', nodes);
  return nodes;
}

/** Turn the body eyes of `ids` back on. Returns the {nodeId, nodeType} of each one that was off. */
export function showBodies(ids) {
  const nodes = [];
  emitVisibilityEvent('show-bodies', { ids, nodes });
  return nodes;
}
