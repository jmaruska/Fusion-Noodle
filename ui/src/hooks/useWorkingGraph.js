import { useCallback, useEffect, useRef, useState } from 'react';
import FusionBridge from '../bridge/FusionBridge';

/**
 * Tracks whether the graph on the canvas differs from the one last generated,
 * and keeps the add-in's working copy up to date.
 *
 * A document holds two snapshots of its graph: the one Generate last built
 * ("generated"), and the graph as edited since ("working copy"). The add-in
 * keeps the working copy in memory and writes it into the document when the
 * document is saved, so edits survive closing the palette, switching documents,
 * and saving, without a Generate.
 *
 * Whoever loads a graph onto the canvas calls expectLoad('generated' | 'working')
 * first, so this hook knows what the graph that settles next represents.
 */
const SETTLE_MS = 800;           // Wait for edits (and multi-step loads) to settle
const UNKNOWN_BASELINE = '\u0000'; // A working copy was loaded; the generated graph wasn't seen

function signature(nodes, edges) {
  const nodePart = nodes
    .map(n => [n.id, n.data?.nodeType, n.data?.currentInputs || {},
      Math.round(n.position?.x || 0), Math.round(n.position?.y || 0)])
    .sort((a, b) => (a[0] < b[0] ? -1 : 1));
  const edgePart = edges
    .map(e => [e.source, e.sourceHandle, e.target, e.targetHandle])
    .sort((a, b) => (a.join('|') < b.join('|') ? -1 : 1));
  return JSON.stringify([nodePart, edgePart]);
}

export function useWorkingGraph({ nodes, edges, reactFlowInstance, onProblem }) {
  const [isEdited, setIsEdited] = useState(false);
  const baselineRef = useRef(null);
  const pendingKindRef = useRef('generated');
  const lastSentRef = useRef(null);
  const latestRef = useRef({ nodes, edges });
  latestRef.current = { nodes, edges };
  const onProblemRef = useRef(onProblem);
  onProblemRef.current = onProblem;

  // The add-in answers every message. A refusal must not pass silently, or edits
  // look safe when they are not.
  const report = useCallback((what) => (result) => {
    const failed = result instanceof Error || (result && result.success === false);
    if (!failed) return;
    const reason = result instanceof Error ? result.message : (result.error || 'unknown error');
    console.error(`[WorkingGraph] ${what}: ${reason}`);
    lastSentRef.current = null; // Try again on the next change
    if (onProblemRef.current) onProblemRef.current(`${what}: ${reason}`);
  }, []);

  const expectLoad = useCallback((kind) => {
    pendingKindRef.current = kind === 'working' ? 'working' : 'generated';
  }, []);

  // A Generate just succeeded: the canvas is now the generated graph. The add-in
  // dropped its working copy at the same time (graph_handler.py).
  const markGenerated = useCallback(() => {
    const { nodes: currentNodes, edges: currentEdges } = latestRef.current;
    const current = signature(currentNodes, currentEdges);
    baselineRef.current = current;
    lastSentRef.current = current;
    setIsEdited(false);
  }, []);

  const settle = useCallback(() => {
    const { nodes: currentNodes, edges: currentEdges } = latestRef.current;
    const current = signature(currentNodes, currentEdges);

    // A graph was just loaded: record what it represents and send nothing.
    if (pendingKindRef.current) {
      const kind = pendingKindRef.current;
      pendingKindRef.current = null;
      baselineRef.current = kind === 'working' ? UNKNOWN_BASELINE : current;
      lastSentRef.current = current;
      setIsEdited(kind === 'working');
      return;
    }

    const edited = current !== baselineRef.current;
    setIsEdited(edited);
    if (current === lastSentRef.current) return;
    lastSentRef.current = current;

    if (edited && currentNodes.length > 0 && reactFlowInstance) {
      FusionBridge.sendMessage('updateWorkingGraph', { reactFlowState: reactFlowInstance.toObject() })
        .then(report('Your graph edits could not be stored'), report('Your graph edits could not be stored'));
    } else {
      // Back to the generated graph (or an empty canvas): no working copy to keep
      FusionBridge.sendMessage('discardWorkingGraph', {})
        .then(report('The stored graph edits could not be cleared'), report('The stored graph edits could not be cleared'));
    }
  }, [reactFlowInstance, report]);

  // Settle a short while after the last change
  const timerRef = useRef(null);
  useEffect(() => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      settle();
    }, SETTLE_MS);
    return () => clearTimeout(timerRef.current);
  }, [nodes, edges, settle]);

  // The palette page is reloaded when the document changes. Don't lose an edit
  // made in the last moment before that. (Closing the palette only hides the page,
  // so the timer above still fires.)
  useEffect(() => {
    const flush = () => {
      if (timerRef.current && !pendingKindRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
        settle();
      }
    };
    // beforeunload comes before the bridge shuts down on pagehide (FusionBridge.js);
    // pagehide is kept for pages that skip beforeunload. A second call does nothing.
    window.addEventListener('beforeunload', flush);
    window.addEventListener('pagehide', flush);
    return () => {
      window.removeEventListener('beforeunload', flush);
      window.removeEventListener('pagehide', flush);
    };
  }, [settle]);

  return { isEdited, expectLoad, markGenerated };
}
