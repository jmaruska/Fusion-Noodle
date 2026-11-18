/**
 * Lets any component put a message on the status line under the toolbar,
 * without the message having to be passed down through every node and port.
 */
const listeners = new Set();

/** Listen for status messages. Returns a function that stops listening. */
export function onStatus(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

/** Show a message. Level is 'info', 'success', 'warning' or 'error'. */
export function reportStatus(level, text) {
  listeners.forEach(callback => callback({ level, text }));
}
