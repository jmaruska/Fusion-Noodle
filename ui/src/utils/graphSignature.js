/**
 * Two fingerprints of the graph on the canvas, compared with the last Generate:
 *
 * - `result`: what Generate builds from. Node types, typed input values and
 *   connections. Moving or selecting nodes doesn't change it, so the Generate
 *   button only says "out of date" when the built result would differ.
 * - `full`: the result plus each node's position, so layout edits are kept in the
 *   working copy and Revert can undo them.
 */
export function graphSignatures(nodes, edges) {
  const resultNodes = nodes
    .map(n => [n.id, n.data?.nodeType, n.data?.currentInputs || {}])
    .sort((a, b) => (a[0] < b[0] ? -1 : 1));
  const layout = nodes
    .map(n => [n.id, Math.round(n.position?.x || 0), Math.round(n.position?.y || 0)])
    .sort((a, b) => (a[0] < b[0] ? -1 : 1));
  const edgePart = edges
    .map(e => [e.source, e.sourceHandle, e.target, e.targetHandle])
    .sort((a, b) => (a.join('|') < b.join('|') ? -1 : 1));
  const result = JSON.stringify([resultNodes, edgePart]);
  return { result, full: JSON.stringify([result, layout]) };
}
