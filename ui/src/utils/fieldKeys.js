/**
 * Enter and Escape in a node's number fields, as in Fusion: Enter commits and
 * leaves the field; Escape leaves it and keeps the value it had. Saving happens
 * on blur, and only after typing, so Escape just forgets the typing first.
 */
export function handleFieldKeys(event, forgetTyping) {
  if (event.key === 'Enter') {
    event.preventDefault();
    event.currentTarget.blur();
  } else if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();   // Not a canvas Escape
    forgetTyping();
    event.currentTarget.blur();
  }
}
