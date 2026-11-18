import { useEffect, useRef } from 'react';
import FusionBridge from '../bridge/FusionBridge';
import { buildGraphRequest } from '../utils/graphRequest.js';
import { hideBodiesForVisualizer } from '../utils/bodyVisibility.js';

/**
 * Keeps the effector visualizer's dots in the Fusion viewport up to date.
 *
 * An effector whose eye is on has `data.visualize` set. While any are on, this
 * hook sends the graph to the add-in whenever something that could change the
 * dots changes: an input value, a connection, a moved 3D Point, or which eyes
 * are on. The add-in runs the arrays and effectors (creating nothing in the
 * design) and redraws the dots. When the last eye turns off, the dots are removed.
 *
 * Requests never overlap. A change that arrives while one is running is sent
 * once that one finishes, so the dots always catch up to the latest state.
 *
 * Bodies would cover the dots, so when an effector's visualizer comes on, bodies
 * are hidden, but only after its dots are drawn: hiding many bodies can take a
 * second or two, and the dots show the click did something in the meantime.
 */
const SETTLE_MS = 120;

export function useVisualizer({ nodes, edges, onStatus }) {
  const latestRef = useRef({ nodes, edges });
  latestRef.current = { nodes, edges };
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;

  const inFlightRef = useRef(false);
  const staleRef = useRef(false);
  const activeRef = useRef(false);
  const warnedRef = useRef(false); // A warning is showing in the status line
  const hiddenForRef = useRef(new Set()); // Effectors whose dots have had the bodies hidden for them

  const visualized = nodes.filter(n => n.data?.visualize).map(n => n.id);
  // Everything that can change the dots. Node positions on the canvas cannot.
  const signature = visualized.length === 0 ? '' : JSON.stringify([
    visualized,
    nodes.map(n => [n.id, n.data?.nodeType, n.data?.currentInputs, n.data?.executionResult?.position]),
    edges.map(e => [e.source, e.sourceHandle, e.target, e.targetHandle])
  ]);

  useEffect(() => {
    const report = (level, text) => onStatusRef.current && onStatusRef.current({ level, text });

    const refresh = async () => {
      if (inFlightRef.current) {
        staleRef.current = true;
        return;
      }
      inFlightRef.current = true;
      try {
        const { nodes: currentNodes, edges: currentEdges } = latestRef.current;
        const ids = currentNodes.filter(n => n.data?.visualize).map(n => n.id);
        if (ids.length === 0) return;
        const response = await FusionBridge.sendMessage('updateVisualizer', {
          ...buildGraphRequest(currentNodes, currentEdges), visualized: ids
        });
        if (!response || !response.success) {
          report('warning', `Visualizer: ${(response && response.error) || 'no response from the add-in'}`);
        } else if (response.warnings && response.warnings.length) {
          report('warning', `Visualizer: ${response.warnings.join(' ')}`);
        } else if (warnedRef.current) {
          // The problem is gone: clear the stale warning
          report('info', `Visualizer: showing ${response.points} points.`);
        }
        // The dots are on screen: now hide the bodies covering them, for effectors that are
        // still on (the curve editor may have closed and put the bodies back meanwhile)
        const stillOn = latestRef.current.nodes.filter(n => n.data?.visualize).map(n => n.id);
        hiddenForRef.current = new Set([...hiddenForRef.current].filter(nodeId => stillOn.includes(nodeId)));
        const newlyOn = ids.filter(nodeId => stillOn.includes(nodeId) && !hiddenForRef.current.has(nodeId));
        if (response && response.success && newlyOn.length) {
          newlyOn.forEach(nodeId => hiddenForRef.current.add(nodeId));
          hideBodiesForVisualizer();
        }
        warnedRef.current = !(response && response.success) || Boolean(response.warnings && response.warnings.length);
      } catch (error) {
        report('warning', `Visualizer: ${error.message || error}`);
      } finally {
        inFlightRef.current = false;
        if (staleRef.current) {
          staleRef.current = false;
          refresh();
        }
      }
    };

    if (signature === '') {
      hiddenForRef.current = new Set();
      if (activeRef.current) {
        activeRef.current = false;
        FusionBridge.sendMessage('clearVisualizer', {})
          .catch(error => console.error('[Visualizer] Could not clear the dots:', error));
      }
      return undefined;
    }

    activeRef.current = true;
    const timer = setTimeout(refresh, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [signature]);
}
