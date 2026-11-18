/**
 * The graph as the add-in needs it to run nodes without generating: each node's
 * id, type, and manual inputs, plus the connections. Used for live values and
 * for the effector visualizer.
 */
const POINT_NODE = '3D_POINT';

/**
 * A 3D Point's coordinates come from the entity picked in Fusion, not from a
 * calculation, so the palette supplies them as a known output. The last
 * Generate's result is newest; otherwise use the stored selection.
 */
export function pointPosition(node) {
  const executed = node.data.executionResult?.position;
  if (executed) return executed;
  const point = node.data.currentInputs?.point;
  if (point && typeof point === 'object' && 'x' in point) {
    return { x: point.x, y: point.y, z: point.z };
  }
  return { x: 0.0, y: 0.0, z: 0.0 };
}

export const isPointNode = (node) => node.data?.nodeType === POINT_NODE;

export function buildGraphRequest(nodes, edges) {
  return {
    nodes: nodes.map(n => {
      const entry = { id: n.id, type: n.data.nodeType, inputs: n.data.currentInputs || {} };
      if (isPointNode(n)) entry.known = { position: pointPosition(n) };
      return entry;
    }),
    edges: edges.map(e => ({
      source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle
    }))
  };
}
