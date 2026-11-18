import React, { useEffect, useState } from 'react';

/**
 * One line, top right, for results that have nowhere else to go: opening or
 * saving a file, a revert, migration notes, the visualizer, and why a Generate
 * failed. Where the design stands lives on the Generate button. Information and
 * success fade after a few seconds; warnings and errors stay until replaced.
 */
const FADE_MS = 6000;

const StatusPanel = ({ statusMessage }) => {
  const [shown, setShown] = useState(statusMessage);

  useEffect(() => {
    setShown(statusMessage);
    if (!statusMessage || statusMessage.level === 'warning' || statusMessage.level === 'error') return undefined;
    const timer = setTimeout(() => setShown(null), FADE_MS);
    return () => clearTimeout(timer);
  }, [statusMessage]);

  if (!shown || !shown.text) return null;
  return (
    <div className={`noodle-status-panel noodle-status-${shown.level || 'info'}`} role="status">
      {shown.text}
    </div>
  );
};

export default StatusPanel;
