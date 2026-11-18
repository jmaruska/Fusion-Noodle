/**
 * Planning for adding nodes to the canvas: which helper nodes come along, how
 * they connect, and where the group goes so it doesn't land on existing nodes.
 *
 * Pure functions only: no React, no DOM. That keeps this testable with Node
 * (see ui/tests/) and leaves the wiring to NodeManager.
 *
 * Which helpers a node needs is decided by the backend and arrives on each node
 * spec as `companions` (see backend/nodes/companions.py). Nothing here knows
 * about any particular node type.
 */
export const NODE_WIDTH = 180;
export const WIDE_NODE_WIDTH = 240;
export const COLUMN_GAP = 90;   // Horizontal space between nodes in a group
export const CLEARANCE = 40;    // Minimum space between a new group and existing nodes

const HEADER_HEIGHT = 44;
const ROW_HEIGHT = 34;

/** Size of a node before the browser has measured it. A vector input takes four rows. */
export function estimateNodeSize(spec) {
  const rows = (ports) => (ports || []).reduce((sum, port) => {
    if (port.type === 'spacer') return sum + 0.4;
    if (port.type === 'vector3') return sum + 4;
    return sum + 1;
  }, 0);
  return {
    width: spec && spec.wide ? WIDE_NODE_WIDTH : NODE_WIDTH,
    height: Math.round(HEADER_HEIGHT + ROW_HEIGHT * (rows(spec && spec.inputs) + rows(spec && spec.outputs)) + 16)
  };
}

/** The rectangle a node on the canvas occupies, using its measured size when known. */
export function nodeRect(node, specFor) {
  const estimate = estimateNodeSize(specFor ? specFor(node.data && node.data.nodeType) : null);
  return {
    x: node.position.x,
    y: node.position.y,
    width: (node.measured && node.measured.width) || node.width || estimate.width,
    height: (node.measured && node.measured.height) || node.height || estimate.height
  };
}

export function boundsOf(rects) {
  if (!rects.length) return null;
  const minX = Math.min(...rects.map(r => r.x));
  const minY = Math.min(...rects.map(r => r.y));
  const maxX = Math.max(...rects.map(r => r.x + r.width));
  const maxY = Math.max(...rects.map(r => r.y + r.height));
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export function rectsOverlap(a, b, clearance = 0) {
  return a.x < b.x + b.width + clearance && a.x + a.width + clearance > b.x &&
         a.y < b.y + b.height + clearance && a.y + a.height + clearance > b.y;
}

export function rectContains(outer, inner) {
  return inner.x >= outer.x && inner.y >= outer.y &&
         inner.x + inner.width <= outer.x + outer.width &&
         inner.y + inner.height <= outer.y + outer.height;
}

/**
 * Which nodes to create for `nodeType`, left to right, and how to connect them.
 * A companion is skipped when the graph already has a node of its type.
 *
 * Returns { members: [{ type, role: 'before' | 'main' | 'after' }],
 *           connections: [{ from, sourcePort, to, targetPort }] }   (from/to index members)
 */
export function planGroup(nodeType, specs, existingNodes) {
  const spec = specs.find(s => s.type === nodeType);
  if (!spec) return null;
  const present = new Set(existingNodes.map(n => n.data && n.data.nodeType));
  const wanted = (spec.companions || []).filter(c => !present.has(c.type) && specs.some(s => s.type === c.type));

  const before = wanted.filter(c => c.side === 'before');
  const after = wanted.filter(c => c.side === 'after');
  const members = [
    ...before.map(c => ({ type: c.type, role: 'before' })),
    { type: nodeType, role: 'main' },
    ...after.map(c => ({ type: c.type, role: 'after' }))
  ];
  const mainIndex = before.length;
  const connections = [
    ...before.map((c, i) => ({ from: i, sourcePort: c.sourcePort, to: mainIndex, targetPort: c.targetPort })),
    ...after.map((c, i) => ({ from: mainIndex, sourcePort: c.sourcePort, to: mainIndex + 1 + i, targetPort: c.targetPort }))
  ];
  return { members, connections };
}

/**
 * Positions for a row of nodes, left to right, centered on `center`.
 * If the row would land on existing nodes, it moves below all of them.
 *
 * sizes: [{ width, height }] for each member. existingRects: rectangles in use.
 * Returns { positions: [{ x, y }], bounds, moved }.
 */
export function placeRow(sizes, center, existingRects) {
  const totalWidth = sizes.reduce((sum, s) => sum + s.width, 0) + COLUMN_GAP * (sizes.length - 1);
  const tallest = Math.max(...sizes.map(s => s.height));
  let left = Math.round(center.x - totalWidth / 2);
  let top = Math.round(center.y - tallest / 2);

  const rowRect = () => ({ x: left, y: top, width: totalWidth, height: tallest });
  let moved = false;
  if (existingRects.some(rect => rectsOverlap(rowRect(), rect, CLEARANCE))) {
    const used = boundsOf(existingRects);
    top = Math.round(used.y + used.height + CLEARANCE * 2);
    moved = true;
  }

  const positions = [];
  let x = left;
  for (const size of sizes) {
    positions.push({ x, y: top });
    x += size.width + COLUMN_GAP;
  }
  return { positions, bounds: rowRect(), moved };
}
