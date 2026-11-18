/**
 * Tab and Shift+Tab move between the editable fields of one node, wrapping at
 * the ends, instead of wandering across the canvas. Leaving a field commits its
 * value, as clicking away does.
 */

// Text fields a user types into. Locked (connected) fields are disabled and skipped.
export const FIELD_SELECTOR = 'input.node-input:not([disabled])';

/** Index of the field to move to from `current` among `count` fields. */
export function nextFieldIndex(count, current, backwards) {
  if (count <= 0) return -1;
  if (current < 0) return backwards ? count - 1 : 0;
  return (current + (backwards ? -1 : 1) + count) % count;
}

/**
 * Keydown handler for a node's root element. Returns true when it handled Tab.
 * `event` is a React or DOM keyboard event; `root` is the node's element.
 */
export function handleNodeTab(event, root) {
  if (event.key !== 'Tab' || event.altKey || event.ctrlKey || event.metaKey || !root) return false;
  const fields = Array.from(root.querySelectorAll(FIELD_SELECTOR));
  if (fields.length === 0) return false;
  event.preventDefault();
  event.stopPropagation();
  const index = nextFieldIndex(fields.length, fields.indexOf(document.activeElement), event.shiftKey);
  fields[index].focus();
  return true;
}
