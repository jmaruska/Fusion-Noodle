import { useEffect, useRef } from 'react';
import { wheelKind, zoomAt, scaleAt, panBy } from '../utils/canvasWheel.js';

/**
 * Mouse wheel and pinch zoom, and trackpad scrolling pans the canvas
 * (utils/canvasWheel.js). React Flow's own wheel handling is off.
 */
export function useCanvasWheel(reactFlowInstance, minZoom, maxZoom) {
  const previousRef = useRef(null);

  useEffect(() => {
    const onWheel = (event) => {
      const pane = event.target.closest?.('.react-flow');
      if (!pane || event.target.closest('.nowheel')) return;
      const kind = wheelKind(event, previousRef.current);
      previousRef.current = { kind, time: event.timeStamp };

      event.preventDefault();
      event.stopPropagation();
      const viewport = reactFlowInstance.getViewport();
      if (kind === 'mouse' || kind === 'pinch') {
        const rect = pane.getBoundingClientRect();
        const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
        reactFlowInstance.setViewport(zoomAt(viewport, point, event.deltaY, event.deltaMode, minZoom, maxZoom, kind === 'pinch'));
      } else {
        reactFlowInstance.setViewport(panBy(viewport, event.deltaX, event.deltaY));
      }
    };
    // WebKit reports a pinch as gesture events with a running scale instead
    let gestureScale = 1;
    const onGesture = (event) => {
      const pane = event.target.closest?.('.react-flow');
      if (!pane) return;
      event.preventDefault();
      if (event.type === 'gesturestart') { gestureScale = 1; return; }
      const factor = event.scale / gestureScale;
      gestureScale = event.scale;
      const rect = pane.getBoundingClientRect();
      const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      reactFlowInstance.setViewport(scaleAt(reactFlowInstance.getViewport(), point, factor, minZoom, maxZoom));
    };

    document.addEventListener('wheel', onWheel, { passive: false, capture: true });
    document.addEventListener('gesturestart', onGesture, { passive: false, capture: true });
    document.addEventListener('gesturechange', onGesture, { passive: false, capture: true });
    return () => {
      document.removeEventListener('wheel', onWheel, { capture: true });
      document.removeEventListener('gesturestart', onGesture, { capture: true });
      document.removeEventListener('gesturechange', onGesture, { capture: true });
    };
  }, [reactFlowInstance, minZoom, maxZoom]);
}
