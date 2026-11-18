/**
 * EdgeManager - connects ports on the canvas. The rules live in utils/ports.js.
 */
import { planConnection, connect, reconnect, portType, typeColor } from '../utils/ports.js';

export class EdgeManager {
  constructor(nodes, edges, setEdges) {
    this.nodes = nodes;
    this.edges = edges;
    this.setEdges = setEdges;
  }

  // A connection dropped on an input that already has one replaces it
  onConnect(connection) {
    this.setEdges(prev => connect(connection, this.nodes, prev) ?? prev);
  }

  // Dragging the end of an existing connection: the edge being moved doesn't count
  isValidConnection(connection, movingEdge = null) {
    const edges = movingEdge ? this.edges.filter(e => e.id !== movingEdge.id) : this.edges;
    return planConnection(connection, this.nodes, edges).valid;
  }

  // An end of `oldEdge` was dropped on a port
  onReconnect(oldEdge, connection) {
    this.setEdges(prev => reconnect(oldEdge, connection, this.nodes, prev) ?? prev);
  }

  // An end of `edge` was dropped on empty canvas: the connection is removed
  removeEdge(edge) {
    this.setEdges(prev => prev.filter(e => e.id !== edge.id));
  }

  getPortType(node, direction, portName) {
    return portType(node, direction, portName);
  }

  getTypeColor(type) {
    return typeColor(type);
  }
}
