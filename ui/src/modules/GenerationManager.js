/**
 * GenerationManager - Handles geometry generation and post-generation tasks
 */
import { waitForBackendEvent } from '../bridge/backendEvents.js';

// How long to wait for a Generate that runs inside a Fusion command. Large arrays
// can take minutes, so this only guards against a result that never arrives.
const DEFERRED_GENERATE_TIMEOUT_MS = 30 * 60 * 1000;

export class GenerationManager {
  constructor(reactFlowInstance) {
    this.reactFlowInstance = reactFlowInstance;
  }

  async generateGeometry(nodes, edges) {
    try {
      // Use ReactFlow's native format for persistence
      const reactFlowState = this.reactFlowInstance.toObject();
      
      const generationData = {
        action: 'generateGeometry',  // Correct backend action name
        nodes: nodes.map(node => {
          // Merge computed values with current inputs
          // Priority: computedInputs (from connections) override currentInputs (manual values)
          const finalInputs = {
            ...(node.data.currentInputs || {}),
            ...(node.data.computedInputs || {})
          };
          
          return {
            id: node.id,
            type: node.data.nodeType,
            inputs: finalInputs,  // Use merged inputs instead of just currentInputs
            position: node.position
          };
        }),
        edges: edges.map(edge => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle,
          targetHandle: edge.targetHandle
        })),
        reactFlowState: reactFlowState  // Send basic state without viewport calculation
      };

      // Use Fusion API communication like other actions
      if (window.adsk && window.adsk.fusionSendData) {
        const response = await window.adsk.fusionSendData('generateGeometry', JSON.stringify(generationData));
        
        // Handle Promise response if needed
        const resolvedResponse = response && typeof response.then === 'function' 
          ? await response 
          : response;

        if (!resolvedResponse || resolvedResponse === 'undefined' || resolvedResponse === 'null') {
          console.error('[GenerationManager] ❌ Generation failed: undefined response');
          return { success: false, error: 'No response from backend' };
        }
        
        let result = typeof resolvedResponse === 'string' ? JSON.parse(resolvedResponse) : resolvedResponse;

        // The add-in can run Generate inside a Fusion command so it is one undo
        // step. The request then returns at once and the result is pushed later.
        if (result.success && result.deferred) {
          try {
            result = await waitForBackendEvent('generateResult', DEFERRED_GENERATE_TIMEOUT_MS);
          } catch (error) {
            return { success: false, error: 'Fusion did not report a result for Generate. Check the Text Commands window.' };
          }
          if (!result || typeof result !== 'object') {
            return { success: false, error: 'Fusion reported an unreadable result for Generate.' };
          }
        }

        if (result.success) {
          // The add-in hides template bodies itself as part of Generate, so it is
          // in the same undo step. The eye icons read their state again when
          // the app announces 'bodies-changed'.
          return result;
        } else {
          console.error('[GenerationManager] ❌ Generation failed:', result.error);
          return result;
        }
        
      } else {
        console.error('[GenerationManager] ❌ No Fusion API available');
        return { success: false, error: 'Fusion API not available' };
      }
      
    } catch (error) {
      console.error('[GenerationManager] Error during generation:', error);
      return { success: false, error: error.message };
    }
  }
}
