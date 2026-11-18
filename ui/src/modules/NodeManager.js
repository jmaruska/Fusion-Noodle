/**
 * NodeManager - Handles node creation, positioning, and metadata management
 */
import { addEdge } from '@xyflow/react';
import { convertNodeSpecForFrontend } from '../utils/nodeSpec.js';
import { edgeStyle } from '../utils/ports.js';
import { planGroup, placeRow, estimateNodeSize, nodeRect, rectContains } from '../utils/nodePlacement.js';

export class NodeManager {
  constructor(reactFlowInstance, nodeMenu, setNodes, setFreshNodes, setEdges) {
    this.reactFlowInstance = reactFlowInstance;
    this.nodeMenu = nodeMenu || [];
    this.setNodes = setNodes;
    this.setFreshNodes = setFreshNodes;
    this.setEdges = setEdges;
  }

  /**
   * Add a node to the canvas. If the node needs helpers the graph doesn't have
   * yet (an array needs an Atomizer before it and a Materializer after it), they
   * are added and connected too, placed clear of existing nodes, and selected as
   * a group so they can be moved together.
   *
   * Which helpers a node needs comes from the backend on each node spec; see
   * utils/nodePlacement.js and backend/nodes/companions.py.
   */
  async createNode(nodeType, position = null) {
    const existing = (this.reactFlowInstance && this.reactFlowInstance.getNodes && this.reactFlowInstance.getNodes()) || [];
    const plan = planGroup(nodeType, this.nodeMenu, existing);
    if (!plan) {
      console.error(`[NodeManager] Spec not found for type: ${nodeType}`);
      return null;
    }

    // A node on its own goes where it always has
    if (plan.members.length === 1) {
      const node = this.buildNode(nodeType, position || this.getSmartNodePosition());
      this.setNodes(prev => [...prev, node]);
      this.markFresh([node.id]);
      return node.id;
    }

    const specFor = (type) => this.nodeMenu.find(n => n.type === type);
    const sizes = plan.members.map(member => estimateNodeSize(specFor(member.type)));
    const { positions, bounds } = placeRow(
      sizes,
      position || this.getViewportCenter(),
      existing.map(node => nodeRect(node, specFor))
    );

    const newNodes = plan.members.map((member, i) => ({ ...this.buildNode(member.type, positions[i]), selected: true }));
    const newEdges = plan.connections.map(c =>
      this.buildEdge(newNodes[c.from], c.sourcePort, newNodes[c.to], c.targetPort));

    // Select only the new group
    this.setNodes(prev => [...prev.map(n => (n.selected ? { ...n, selected: false } : n)), ...newNodes]);
    if (this.setEdges) {
      this.setEdges(prev => newEdges.reduce((edges, edge) => addEdge(edge, edges), prev));
    }
    this.markFresh(newNodes.map(n => n.id));
    this.revealArea(bounds);

    return newNodes[plan.members.findIndex(m => m.role === 'main')].id;
  }

  /** Build a node object for `nodeType` at `position`. Does not add it to the canvas. */
  buildNode(nodeType, position) {
    const nodeInfo = convertNodeSpecForFrontend(this.nodeMenu.find(n => n.type === nodeType));

    // Build defaults for inputs from spec
    const defaultInputs = Object.fromEntries(
      Object.entries(nodeInfo.inputs || {}).map(([name, info]) => [name, info.default])
    );

    const id = `node_${nodeType}_${Date.now()}_${Math.floor(Math.random() * 100000)}`;

    return {
      id,
      type: 'custom',
      position,
      data: {
        label: this.getNodeDisplayName(nodeType),
        nodeType,
        nodeCategory: this.getNodeCategory(nodeType),
        nodeInfo,
        wide: nodeInfo.wide || false,
        currentInputs: defaultInputs,
        computedInputs: {},
        computedOutputs: {},
        isPortVisible: () => true,
        initiallyVisible: true
      }
    };
  }

  /** Build a connection from one new node's output to another's input, colored by type. */
  buildEdge(sourceNode, sourcePort, targetNode, targetPort) {
    const portType = sourceNode.data.nodeInfo.outputs?.[sourcePort]?.type;
    return {
      source: sourceNode.id,
      sourceHandle: `output-${sourcePort}`,
      target: targetNode.id,
      targetHandle: `input-${targetPort}`,
      type: 'default',
      style: edgeStyle(portType)
    };
  }

  markFresh(ids) {
    this.setFreshNodes(prev => {
      const next = new Set(prev || []);
      ids.forEach(id => next.add(id));
      return next;
    });
  }

  /** The part of the canvas currently visible, in canvas coordinates. */
  getVisibleArea() {
    try {
      const wrapper = document.querySelector('.react-flow__renderer') || document.querySelector('.react-flow');
      if (wrapper && this.reactFlowInstance?.screenToFlowPosition) {
        const rect = wrapper.getBoundingClientRect();
        const topLeft = this.reactFlowInstance.screenToFlowPosition({ x: rect.left, y: rect.top });
        const bottomRight = this.reactFlowInstance.screenToFlowPosition({ x: rect.right, y: rect.bottom });
        return { x: topLeft.x, y: topLeft.y, width: bottomRight.x - topLeft.x, height: bottomRight.y - topLeft.y };
      }
    } catch (e) {
      // Not measurable yet
    }
    return null;
  }

  getViewportCenter() {
    const area = this.getVisibleArea();
    return area ? { x: area.x + area.width / 2, y: area.y + area.height / 2 } : { x: 400, y: 300 };
  }

  /** If `area` isn't fully in view, zoom out to show the whole graph. Never zooms in past 1.0. */
  revealArea(area) {
    setTimeout(() => {
      const visible = this.getVisibleArea();
      if (visible && !rectContains(visible, area) && this.reactFlowInstance?.fitView) {
        this.reactFlowInstance.fitView({ maxZoom: 1.0, padding: 0.15, duration: 250 });
      }
    }, 150);
  }

  getSmartNodePosition() {
    // Use the same approach as the double-click handler which we know works
    try {
      if (this.reactFlowInstance?.screenToFlowPosition) {
        // Find the ReactFlow wrapper (not just the pane)
        const reactFlowWrapper = document.querySelector('.react-flow__renderer') || 
                                document.querySelector('.react-flow') ||
                                document.querySelector('.react-flow__pane');
        
        if (reactFlowWrapper) {
          const rect = reactFlowWrapper.getBoundingClientRect();
          
          // Get the center in absolute screen coordinates (like a mouse click)
          const centerX = rect.left + rect.width / 2;
          const centerY = rect.top + rect.height / 2;
          
          // Convert to flow coordinates exactly like the double-click handler
          const centerPos = this.reactFlowInstance.screenToFlowPosition({
            x: centerX,
            y: centerY
          });
          
          // Offset left and up to give room for graph building
          const offsetPos = {
            x: centerPos.x - 100, // Left by ~half node width
            y: centerPos.y - 100  // Up to give room to clothesline down
          };

          return offsetPos;
        }
      }
    } catch (e) {
      // screenToFlowPosition can fail before the canvas is measured; use the fallback below
    }
    
    // Fallback: simple center position with offset
    return { x: 300, y: 200 }; // Center minus 100x, 100y
  }

  getNodeDisplayName(nodeType) {
    const nodeSpec = this.nodeMenu.find(n => n.type === nodeType);
    return nodeSpec ? nodeSpec.name : nodeType;
  }

  getNodeCategory(nodeType) {
    const nodeSpec = this.nodeMenu.find(n => n.type === nodeType);
    return nodeSpec ? nodeSpec.category : 'general';
  }
}
