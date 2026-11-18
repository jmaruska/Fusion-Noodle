import { useCallback, useRef, useEffect } from 'react';
import FusionBridge from '../bridge/FusionBridge';
import { unifiedPollingManager } from '../modules/UnifiedPollingManager';
import { buildGraphRequest, isPointNode } from '../utils/graphRequest.js';
import { hexLinkedInputs } from '../utils/hexSpacing.js';

/**
 * Live values on the canvas.
 *
 * When a Number feeds a Box's Width, the Width field shows the number before
 * anything is generated. Those values come from the add-in: it runs the real
 * nodes that are pure calculations (see backend/preview.py) and returns their
 * outputs. This hook sends the graph, then carries each returned value along
 * its connection to the input it feeds.
 *
 * There is no copy of any node's logic here. A new node needs nothing in this
 * file. An input fed by something that can't be known without generating
 * (geometry, a collection, a modifier) gets no value and is simply shown as
 * connected.
 */
const sameValue = (a, b) => JSON.stringify(a ?? {}) === JSON.stringify(b ?? {});
const portOf = (handle, prefix) => (handle || '').replace(prefix, '');

export function useFlowComputation({ nodes, edges, setNodes, onProblem }) {
  // While the user is picking an entity in Fusion, node data must not be rewritten
  const selectionLockRef = useRef(false);

  // Latest values, so computeFlow never needs recreating
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const setNodesRef = useRef(setNodes);
  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
    setNodesRef.current = setNodes;
  }, [nodes, edges, setNodes]);

  // Only the answer to the most recent request is applied
  const requestRef = useRef(0);

  // Live values failing must be visible, not just logged. Each distinct problem
  // is reported once, and cleared when live values work again.
  const onProblemRef = useRef(onProblem);
  onProblemRef.current = onProblem;
  const lastProblemRef = useRef(null);
  const reportProblem = (reason) => {
    console.error('[Flow] Live values unavailable:', reason);
    if (reason !== lastProblemRef.current && onProblemRef.current) {
      onProblemRef.current(`Live values are unavailable: ${reason}`);
    }
    lastProblemRef.current = reason;
  };
  const computeFlowRef = useRef(null);

  // Stop polling coordinates for 3D Point nodes that were deleted
  useEffect(() => {
    const currentNodeIds = new Set(nodes.map(n => n.id));
    for (const nodeId of unifiedPollingManager.registered3DPointNodes.keys()) {
      if (!currentNodeIds.has(nodeId)) {
        unifiedPollingManager.unregister3DPointNode(nodeId);
      }
    }
  }, [nodes]);

  // A 3D Point with a selection is polled, so moving the picked entity in Fusion
  // updates the coordinates shown on the node.
  const syncPointPolling = (node) => {
    const point = node.data.currentInputs?.point;
    if (!(point && point.entity_token)) {
      unifiedPollingManager.unregister3DPointNode(node.id);
      return;
    }
    const onMoved = async (newCoordinates) => {
      setNodesRef.current(currentNodes => currentNodes.map(n => {
        if (n.id !== node.id || !n.data.currentInputs?.point) return n;
        return {
          ...n,
          data: {
            ...n.data,
            currentInputs: {
              ...n.data.currentInputs,
              point: { ...n.data.currentInputs.point, x: newCoordinates.x, y: newCoordinates.y, z: newCoordinates.z }
            },
            // The polled coordinates are newer than the last Generate's result
            executionResult: undefined
          }
        };
      }));
      setTimeout(() => computeFlowRef.current && computeFlowRef.current(), 100);
    };
    unifiedPollingManager.register3DPointNode(node.id, node, onMoved);
  };

  const computeFlow = useCallback(async () => {
    if (selectionLockRef.current) return;

    const currentNodes = nodesRef.current;
    if (currentNodes.length === 0) return;
    const requestId = ++requestRef.current;

    currentNodes.filter(isPointNode).forEach(syncPointPolling);

    const request = buildGraphRequest(currentNodes, edgesRef.current);

    let response;
    try {
      response = await FusionBridge.sendMessage('previewValues', request);
    } catch (error) {
      reportProblem(error.message || String(error));
      return;
    }
    if (!response || !response.success) {
      reportProblem((response && response.error) || 'no response from the add-in');
      return;
    }
    lastProblemRef.current = null;
    if (requestId !== requestRef.current || selectionLockRef.current) return; // Superseded
    const outputs = response.outputs || {};

    // Carry each value along its connection. Edges are read at apply time, so a
    // connection removed while the request was in flight leaves no value behind.
    setNodesRef.current(current => {
      const incoming = new Map();
      edgesRef.current.forEach(edge => {
        if (!incoming.has(edge.target)) incoming.set(edge.target, []);
        incoming.get(edge.target).push(edge);
      });

      let changed = false;
      const next = current.map(node => {
        const computedInputs = {};
        const connected = new Set();
        (incoming.get(node.id) || []).forEach(edge => {
          connected.add(portOf(edge.targetHandle, 'input-'));
          const value = outputs[edge.source]?.[portOf(edge.sourceHandle, 'output-')];
          if (value !== undefined && value !== null) {
            computedInputs[portOf(edge.targetHandle, 'input-')] = value;
          }
        });
        // A hexagonal grid's spacings are one value: a connected one drives the other
        if (node.data?.nodeType === 'Array_2D_Grid') {
          Object.assign(computedInputs, hexLinkedInputs(node.data.currentInputs, computedInputs, connected));
        }
        const computedOutputs = outputs[node.id] || {};

        // After a Generate, a 3D Point's stored selection takes the fresh coordinates
        let currentInputs = node.data.currentInputs;
        const fresh = node.data.executionResult?._fresh_coordinates;
        const point = currentInputs?.point;
        if (isPointNode(node) && fresh && point &&
            (point.x !== fresh.x || point.y !== fresh.y || point.z !== fresh.z)) {
          currentInputs = { ...currentInputs, point: { ...point, x: fresh.x, y: fresh.y, z: fresh.z } };
        }

        if (currentInputs === node.data.currentInputs &&
            sameValue(node.data.computedInputs, computedInputs) &&
            sameValue(node.data.computedOutputs, computedOutputs)) {
          return node;
        }
        changed = true;
        return { ...node, data: { ...node.data, currentInputs, computedInputs, computedOutputs } };
      });
      return changed ? next : current;
    });
  }, []);
  computeFlowRef.current = computeFlow;

  // Recompute when nodes are added or removed, or any connection changes, including
  // one whose end was moved to another input (the count stays the same). Input
  // edits call computeFlow themselves (see useNodeInputManagement).
  const edgeSignature = edges.map(e => `${e.source}.${e.sourceHandle}>${e.target}.${e.targetHandle}`).sort().join('|');
  useEffect(() => {
    if (nodes.length === 0) return undefined;
    const timeoutId = setTimeout(() => computeFlow(), 50);
    return () => clearTimeout(timeoutId);
  }, [nodes.length, edgeSignature, computeFlow]);

  // Stable, so passing them to nodes doesn't re-render every node on every render
  const setSelectionLock = useCallback((locked) => {
    selectionLockRef.current = locked;
  }, []);
  const isSelectionLocked = useCallback(() => selectionLockRef.current, []);

  return { computeFlow, setSelectionLock, isSelectionLocked };
}
