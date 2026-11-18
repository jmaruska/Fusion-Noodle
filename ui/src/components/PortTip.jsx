/**
 * Fusion-style tips for node inputs: the port's label, its description, and the
 * range it accepts.
 *
 * Rules, as in Fusion: a tip appears after resting on an input for a moment, or at
 * once when a bounded field is clicked into; only one shows at a time; any click,
 * drag, scroll or zoom puts it away. It floats above the canvas, so it never moves
 * the node's layout.
 *
 * Not called "tooltip": useTooltipRemoval hides anything named that.
 */
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

const HOVER_DELAY_MS = 700;
const listeners = new Set();
let current = null;
let timer = null;

function publish(tip) {
  current = tip;
  listeners.forEach(fn => fn(tip));
}

/** Show `tip` ({anchor: element, title, body, range, error, sections: [{title, body}]}) now. */
export function showPortTip(tip) {
  clearTimeout(timer);
  publish(tip);
}

/** Show `tip` after the hover delay, unless something cancels it first. */
export function showPortTipSoon(tip) {
  clearTimeout(timer);
  timer = setTimeout(() => publish(tip), HOVER_DELAY_MS);
}

/** Hide the tip, or only the one anchored on `anchor` if given. */
export function hidePortTip(anchor = null) {
  clearTimeout(timer);
  if (!anchor || current?.anchor === anchor) publish(null);
}

/** What a port's tip says, or null when there's nothing to add to the label. */
export function portTipContent(portInfo, range, error) {
  const body = portInfo?.description || null;
  if (!body && !range) return null;
  return { title: portInfo?.label, body, range, error };
}

/** Rendered once, by NoodleApp. */
export function PortTipHost() {
  const [tip, setTip] = useState(null);

  useEffect(() => {
    listeners.add(setTip);
    const hide = () => hidePortTip();
    const onKey = e => { if (e.key === 'Escape') hide(); };
    // Capture, so React Flow's own handlers can't stop them reaching us
    window.addEventListener('pointerdown', hide, true);
    window.addEventListener('wheel', hide, true);
    window.addEventListener('keydown', onKey, true);
    window.addEventListener('blur', hide);
    return () => {
      listeners.delete(setTip);
      window.removeEventListener('pointerdown', hide, true);
      window.removeEventListener('wheel', hide, true);
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('blur', hide);
    };
  }, []);

  if (!tip || !tip.anchor?.isConnected) return null;
  const rect = tip.anchor.getBoundingClientRect();
  const below = rect.bottom + 120 < window.innerHeight;
  const style = {
    left: Math.max(8, Math.min(rect.left, window.innerWidth - 288)),
    top: below ? rect.bottom + 6 : undefined,
    bottom: below ? undefined : window.innerHeight - rect.top + 6,
  };
  return createPortal(
    <div className="noodle-port-tip" style={style}>
      {tip.title && <div className="noodle-port-tip-title">{tip.title}</div>}
      {tip.body && <div className="noodle-port-tip-body">{tip.body}</div>}
      {(tip.sections || []).map(section => (
        <div key={section.title} className="noodle-port-tip-section">
          <div className="noodle-port-tip-title">{section.title}</div>
          <div className="noodle-port-tip-body">{section.body}</div>
        </div>
      ))}
      {tip.range && (
        <div className={`noodle-port-tip-range${tip.error ? ' error' : ''}`}>Allowed: {tip.range}</div>
      )}
    </div>,
    document.body
  );
}
