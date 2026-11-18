import { useCallback } from 'react';
import { currentNodeInfo } from '../utils/nodeSpec.js';

/**
 * Custom hook for managing graph operations
 * 
 * Provides loadGraphFromData, which puts a saved graph on the canvas.
 */
const useGraphOperations = ({ 
  reactFlowInstance, 
  setNodes, 
  setEdges, 
  computeFlow, 
  fixEdgeColors
}) => {
  // Load graph from JSON data with proper node setup
  const loadGraphFromData = useCallback((flowObject) => {
    if (!reactFlowInstance) {
      console.warn('[Load Graph] ReactFlow instance not available');
      return;
    }

    // Delay to allow any pending operations to complete
    setTimeout(() => {
      // Process nodes with proper data handling
      let nodesWithRefreshKey = null;
      if (flowObject.nodes) {
        nodesWithRefreshKey = flowObject.nodes.map(node => {
          const processedNode = {
            ...node,
            data: {
              ...node.data,
              // UI guards for restored nodes
              isPortVisible: node?.data?.isPortVisible || (() => true),
              initiallyVisible: node?.data?.initiallyVisible !== undefined ? node.data.initiallyVisible : true
            }
          };

          // Remove volatile UI-only flags that could freeze inputs
          if (processedNode.data) {
            if (processedNode.data.nodeState) delete processedNode.data.nodeState;
            if (processedNode.data.computedOutputs) delete processedNode.data.computedOutputs;
            if (processedNode.data.visualize) delete processedNode.data.visualize; // Visualizer eyes start off
          }
          // Clear selection/measured to avoid stale layout/selection state
          if (processedNode.selected) delete processedNode.selected;
          if (processedNode.measured) delete processedNode.measured;
          
          // Drop helpers that older versions stored on the node. Nothing reads them.
          for (const stale of ['refreshKey', 'onInputChange', 'refreshMetadata', 'updateNodeData', 'reactFlowInstance']) {
            delete processedNode.data[stale];
          }
          delete processedNode.ref;

          // A saved graph carries the port details from when it was saved. Replace
          // them with the current definition so labels, units, ports and width
          // changed since then show up. Unknown node types keep what they were saved with.
          const freshInfo = currentNodeInfo(processedNode.data?.nodeType);
          if (freshInfo) {
            processedNode.data.nodeInfo = freshInfo;
            processedNode.data.label = freshInfo.name;
            processedNode.data.nodeCategory = freshInfo.category;
            processedNode.data.wide = freshInfo.wide;
          }
          
          return processedNode;
        });
        
        setNodes(nodesWithRefreshKey);
      }
      
      if (flowObject.edges) {
        const fixedEdges = fixEdgeColors(flowObject.edges, nodesWithRefreshKey || flowObject.nodes);
        setEdges(fixedEdges);
      }
      
      // Smart fitView: zoom out for large graphs, but never zoom in beyond 1.0
      const attemptSmartFitView = () => {
        if (reactFlowInstance && (nodesWithRefreshKey?.length > 0 || flowObject.nodes?.length > 0)) {
          // Check if nodes are measured
          const nodes = reactFlowInstance.getNodes();
          const unmeasuredNodes = nodes.filter(node => !node.measured || !node.measured.width || !node.measured.height);

          if (unmeasuredNodes.length === 0) {
            // All nodes measured - fit the graph in view, never zooming in past 1.0
            reactFlowInstance.fitView({ maxZoom: 1.0, padding: 0.1 });
          } else {
            return false; // Retry needed
          }
        }
        return true; // Success or no nodes
      };

      // Try multiple times to ensure nodes are fully measured
      const tryFitView = (attempt = 1) => {
        if (attempt > 3) {
          return;
        }
        
        setTimeout(() => {
          if (!attemptSmartFitView()) {
            tryFitView(attempt + 1);
          }
        }, attempt * 200); // 200ms, 400ms, 600ms
      };
      
      tryFitView();

      // Trigger computation after everything is set
      setTimeout(() => {
        computeFlow();
      }, 200); // Minimal delay after fitView

    }, 100); // Delay for reinitialization
  }, [setNodes, setEdges, reactFlowInstance, computeFlow, fixEdgeColors]);

  return { loadGraphFromData };
};

export { useGraphOperations };
