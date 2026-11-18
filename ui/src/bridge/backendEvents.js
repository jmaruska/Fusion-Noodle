/**
 * Messages pushed from the add-in to the palette.
 *
 * Most communication is request/response: the palette calls the add-in and gets
 * an answer back. Some work finishes after the request has already returned (a
 * Generate that runs inside a Fusion command, for example). The add-in then
 * calls palette.sendInfoToHTML(action, json), which Fusion delivers to
 * window.fusionJavaScriptHandler.handle(action, data).
 */
const listeners = new Map(); // action -> Set of callbacks

window.fusionJavaScriptHandler = {
  handle(action, data) {
    let payload = data;
    try {
      payload = typeof data === 'string' && data ? JSON.parse(data) : data;
    } catch (error) {
      console.error(`[BackendEvents] Could not parse data for '${action}':`, error);
    }
    (listeners.get(action) || []).forEach(callback => {
      try {
        callback(payload);
      } catch (error) {
        console.error(`[BackendEvents] Listener for '${action}' failed:`, error);
      }
    });
    return 'OK';
  }
};

/** Subscribe to a pushed message. Returns a function that unsubscribes. */
export function onBackendEvent(action, callback) {
  if (!listeners.has(action)) listeners.set(action, new Set());
  listeners.get(action).add(callback);
  return () => listeners.get(action)?.delete(callback);
}

/** Resolve with the next pushed message for `action`, or reject after `timeoutMs`. */
export function waitForBackendEvent(action, timeoutMs) {
  return new Promise((resolve, reject) => {
    let timer = null;
    const unsubscribe = onBackendEvent(action, payload => {
      clearTimeout(timer);
      unsubscribe();
      resolve(payload);
    });
    timer = setTimeout(() => {
      unsubscribe();
      reject(new Error(`No '${action}' message arrived from Fusion`));
    }, timeoutMs);
  });
}
