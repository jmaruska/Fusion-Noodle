import { hexBlockedInput } from './hexSpacing.js';

/**
 * Rules for connecting ports: which types fit together, what colour a connection
 * is, and what happens when a connection is dropped on an input.
 *
 * Every input takes one connection. The backend resolves one value per input
 * (graph_handler._resolve_inputs), so a second connection would silently replace
 * the first. Dropping a new connection on an input that already has one replaces
 * it instead.
 *
 * Colours are the data-type tokens in ui/styles/theme.css, so they are defined
 * once, in CSS.
 */

// Types that can feed each other. Anything not listed only connects to itself.
const FAMILIES = [
  ['FLOAT', 'INTEGER', 'NUMBER'],
  ['GEOMETRY', 'BREP', 'BODY', 'SURFACE'],
  ['COLLECTION', 'ARRAY'],
  ['VECTOR3', 'POINT'],
];

const TYPE_COLOR = {
  FLOAT: '--noodle-color-numbers',
  INTEGER: '--noodle-color-numbers',
  NUMBER: '--noodle-color-numbers',
  GEOMETRY: '--noodle-color-geometry',
  BREP: '--noodle-color-geometry',
  BODY: '--noodle-color-geometry',
  SURFACE: '--noodle-color-geometry',
  COLLECTION: '--noodle-color-collection',
  ARRAY: '--noodle-color-array',
  VECTOR3: '--noodle-color-vector3',
  POINT: '--noodle-color-vector3',
  TRANSFORM: '--noodle-color-transform',
  CURVE: '--noodle-color-curve',
};
const DEFAULT_COLOR = '--node-category-general';

/** A port's type, from the node's spec: `direction` is 'input' or 'output'. */
export function portType(node, direction, portName) {
  const ports = direction === 'input' ? node?.data?.nodeInfo?.inputs : node?.data?.nodeInfo?.outputs;
  if (!ports) return null;
  const port = Array.isArray(ports) ? ports.find(p => p.name === portName) : ports[portName];
  return port?.type ?? null;
}

export function areTypesCompatible(sourceType, targetType) {
  if (!sourceType || !targetType) return false;
  const source = sourceType.toUpperCase();
  const target = targetType.toUpperCase();
  return source === target || FAMILIES.some(f => f.includes(source) && f.includes(target));
}

/** The CSS colour for a connection carrying `type`, e.g. 'var(--noodle-color-collection)'. */
export function typeColor(type) {
  return `var(${TYPE_COLOR[type?.toUpperCase()] || DEFAULT_COLOR})`;
}

export function edgeStyle(type) {
  return { stroke: typeColor(type), strokeWidth: 2 };
}

const portName = handle => handle?.replace(/^(output|input)-/, '');

/**
 * What dropping `connection` would do, given the current graph.
 * Returns {valid: false, reason} or {valid: true, replaces: edge id or null}.
 */
export function planConnection(connection, nodes, edges) {
  const source = nodes.find(n => n.id === connection.source);
  const target = nodes.find(n => n.id === connection.target);
  if (!source || !target) return { valid: false, reason: 'missing node' };
  if (source.id === target.id) return { valid: false, reason: 'same node' };

  const sourceType = portType(source, 'output', portName(connection.sourceHandle));
  const targetType = portType(target, 'input', portName(connection.targetHandle));
  if (!sourceType || !targetType) return { valid: false, reason: 'unknown port' };
  if (!areTypesCompatible(sourceType, targetType)) return { valid: false, reason: 'incompatible types' };

  const targetPort = portName(connection.targetHandle);
  const connectedHere = new Set(edges.filter(e => e.target === target.id && e.targetHandle !== connection.targetHandle)
    .map(e => portName(e.targetHandle)));
  if (hexBlockedInput(target.data?.currentInputs, connectedHere) === targetPort) {
    return { valid: false, reason: 'driven by the other spacing' };
  }

  const existing = edges.find(e => e.target === connection.target && e.targetHandle === connection.targetHandle);
  if (existing && existing.source === connection.source && existing.sourceHandle === connection.sourceHandle) {
    return { valid: false, reason: 'already connected' };
  }
  return { valid: true, replaces: existing ? existing.id : null };
}

/**
 * The edges after dropping `connection`: the input's old connection, if any, is
 * replaced. Returns null when the connection isn't valid.
 */
export function connect(connection, nodes, edges) {
  const plan = planConnection(connection, nodes, edges);
  if (!plan.valid) return null;
  const source = nodes.find(n => n.id === connection.source);
  const type = portType(source, 'output', portName(connection.sourceHandle));
  const id = `xy-edge__${connection.source}${connection.sourceHandle || ''}-${connection.target}${connection.targetHandle || ''}`;
  const edge = { ...connection, id, type: 'default', style: edgeStyle(type) };
  return [...edges.filter(e => e.id !== plan.replaces), edge];
}

/**
 * Keep one connection per input. A graph saved before replacement existed may hold
 * two; the backend uses the last one, so that one is kept.
 */
export function oneConnectionPerInput(edges) {
  const last = new Map();
  edges.forEach((e, i) => last.set(`${e.target}|${e.targetHandle}`, i));
  return edges.filter((e, i) => last.get(`${e.target}|${e.targetHandle}`) === i);
}

/** Restyle every edge from its source port's type; an edge between incompatible ports is drawn as an error. */
export function styleEdges(edges, nodes) {
  return oneConnectionPerInput(edges).map(edge => {
    const source = nodes.find(n => n.id === edge.source);
    const target = nodes.find(n => n.id === edge.target);
    if (!source || !target) return edge;
    const sourceType = portType(source, 'output', portName(edge.sourceHandle));
    const targetType = portType(target, 'input', portName(edge.targetHandle));
    if (!sourceType || !targetType) return edge;
    if (!areTypesCompatible(sourceType, targetType)) {
      return { ...edge, style: { stroke: 'var(--adsk-status-error)', strokeWidth: 2, strokeDasharray: '5,5' } };
    }
    return { ...edge, style: { ...edge.style, ...edgeStyle(sourceType) } };
  });
}

/**
 * The edges after dragging an end of `oldEdge` to make `connection`. The input it
 * lands on loses its old connection, as with a new one. Returns null when the
 * connection isn't valid.
 */
export function reconnect(oldEdge, connection, nodes, edges) {
  const others = edges.filter(e => e.id !== oldEdge.id);
  return connect(connection, nodes, others);
}
