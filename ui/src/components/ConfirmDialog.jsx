import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

/**
 * A warning dialog like Fusion's "Unsaved changes": amber bar on the left, a
 * warning icon and title, the message, and Cancel beside the action. Escape or
 * the × cancels; Enter confirms (the action has focus).
 */
const ConfirmDialog = ({ title, confirmLabel, onConfirm, onCancel, children }) => {
  const confirmRef = useRef(null);
  useEffect(() => { confirmRef.current?.focus(); }, []);

  return createPortal(
    <div className="weave-dialog-overlay"
         onPointerDown={e => { if (e.target === e.currentTarget) onCancel(); }}
         onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onCancel(); }}>
      <div className="weave-dialog weave-dialog-warning" role="alertdialog" aria-labelledby="weave-dialog-title">
        <div className="weave-dialog-head">
          <svg className="weave-dialog-icon" viewBox="0 0 20 20" aria-hidden="true">
            <path className="weave-dialog-icon-fill" d="M10 1.8l8.8 15.6H1.2z" />
            <path className="weave-dialog-icon-mark" d="M10 7v5M10 14.2v.8" />
          </svg>
          <h2 id="weave-dialog-title">{title}</h2>
          <button type="button" className="weave-dialog-close" aria-label="Cancel" onClick={onCancel}>×</button>
        </div>
        <div className="weave-dialog-body">{children}</div>
        <div className="weave-dialog-foot">
          <button type="button" className="weave-button" onClick={onCancel}>Cancel</button>
          <button type="button" ref={confirmRef} className="weave-button weave-button-primary" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default ConfirmDialog;
