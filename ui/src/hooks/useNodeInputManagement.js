import { linkHexSpacing } from '../utils/hexSpacing.js';
import { useCallback } from 'react';

/**
 * Hook for node input changes: stores typed values, keeps a hexagonal 2D grid's
 * two spacings linked (utils/hexSpacing.js), and refreshes live values.
 */
// Values that make sense as a manual input once a connection is removed.
// Collections, geometry, and modifier descriptors are not kept.
const isPersistableValue = (value) => {
  if (value === null || value === undefined) return false;
  if (['number', 'boolean', 'string'].includes(typeof value)) return true;
  return typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).every(k => ['x', 'y', 'z'].includes(k));
};

export function useNodeInputManagement({ setNodes, onNodesChange, onEdgesChange, computeFlow, edges }) {
  // Helper function to send backend messages
  const sendBackendMessage = useCallback(async (action, data) => {
    try {
      if (window.returnData) {
        const messageData = { action, ...data };
        const response = await window.returnData(JSON.stringify(messageData));
        return JSON.parse(response);
      } else {
        console.warn(`❌ No returnData function available for ${action}`);
        return { success: false, error: 'No returnData function available' };
      }
    } catch (error) {
      console.error(`❌ Error sending ${action}:`, error);
      return { success: false, error: error.message };
    }
  }, []);
  
  // Handle input value changes from nodes
  const handleNodeInputChange = useCallback((nodeId, portName, value) => {
    setNodes(prev => {
      const updatedNodes = prev.map(node => {
        if (node.id === nodeId) {
          const actualType = node.data?.nodeType || node.type || 'unknown';
          
          let newCurrentInputs = {
            ...node.data.currentInputs,
            [portName]: value
          };
          
          // Hexagonal 2D grid: rows are √3/2 of the column spacing apart, so the two
          // spacings are one value. Editing either sets the other, and choosing
          // Hexagonal brings Spacing Y in line with Spacing X (hexSpacing.js).
          if (actualType === 'Array_2D_Grid') {
            Object.assign(newCurrentInputs, linkHexSpacing(newCurrentInputs, portName));
          }

          const newNode = {
            ...node,
            data: {
              ...node.data,
              currentInputs: newCurrentInputs
            }
          };

          return newNode;
        }
        return node;
      });
      
      return updatedNodes;
    });
    
    // Trigger flow computation after input changes
    // This ensures values propagate through connected nodes immediately
    setTimeout(() => {
      if (typeof computeFlow === 'function') {
        computeFlow();
      }
    }, 0);
  }, [setNodes, computeFlow]);

  // Custom nodes change handler that detects deletions and selection changes
  const handleNodesChange = useCallback((changes) => {
    // Find any remove changes (node deletions)
    const removedNodes = changes.filter(change => change.type === 'remove');
    
    // Notify backend about deleted nodes for cleanup
    removedNodes.forEach(async (change) => {
      const nodeId = change.id;
      
      try {
        await sendBackendMessage('deleteNode', { nodeId });
      } catch (error) {
        console.error('❌ Error notifying backend of node deletion:', error);
      }
    });
    
    // Apply the changes using the original handler
    onNodesChange(changes);
  }, [onNodesChange, sendBackendMessage]);

  // Wrapper for onEdgesChange to track user activity and handle value persistence
  const handleEdgesChange = useCallback((changes) => {
    // Keep the last flowed value when a connection is removed. xyflow's remove
    // change only carries the edge id, so look the edge up to find its target.
    const removedIds = new Set(changes.filter(change => change.type === 'remove').map(change => change.id));
    const removedEdges = (edges || []).filter(edge => removedIds.has(edge.id));
    
    if (removedEdges.length > 0) {
      setNodes(prev => prev.map(node => {
        // Find edges targeting this node that are being removed
        const affectedInputs = removedEdges
          .filter(edge => edge.target === node.id)
          .map(edge => {
            // Extract input port name from targetHandle
            const portName = edge.targetHandle?.replace('input-', '');
            return { portName, value: node.data.computedInputs?.[portName] };
          })
          .filter(({ portName, value }) => portName && isPersistableValue(value));
        
        if (affectedInputs.length > 0) {
          // Copy computed values to currentInputs for persistence
          const newCurrentInputs = { ...node.data.currentInputs };
          affectedInputs.forEach(({ portName, value }) => {
            newCurrentInputs[portName] = value;
          });
          
          return {
            ...node,
            data: {
              ...node.data,
              currentInputs: newCurrentInputs
            }
          };
        }
        
        return node;
      }));
    }
    
    // Apply the changes using the original handler
    onEdgesChange(changes);
    
    // Trigger flow computation to update UI after edge changes
    setTimeout(() => {
      if (typeof computeFlow === 'function') {
        computeFlow();
      }
    }, 0);
  }, [onEdgesChange, setNodes, computeFlow, edges]);

  return {
    handleNodeInputChange,
    handleNodesChange,
    handleEdgesChange,
  };
}