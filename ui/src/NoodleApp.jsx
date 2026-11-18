import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { 
  Background,
  ReactFlow,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  Controls,
} from '@xyflow/react';

import { NodeRuntimeContext, NODE_TYPES } from './components/NodeRuntime.jsx';
import Toolbar from './components/Toolbar.jsx';
import StatusPanel from './components/StatusPanel.jsx';

// Import hooks
import { useNodeValidation } from './hooks/useNodeValidation';
import { useWorkingGraph } from './hooks/useWorkingGraph';
import { useVisualizer } from './hooks/useVisualizer';
import { emitVisibilityEvent } from './utils/visibilityBus.js';
import { onStatus } from './utils/statusBus.js';
import { useGraphOperations } from './hooks/useGraphOperations';
import { useNodeInputManagement } from './hooks/useNodeInputManagement';
import { useUIState } from './hooks/useUIState';
import { useTooltipRemoval } from './hooks/useTooltipRemoval';
import { useCanvasWheel } from './hooks/useCanvasWheel';
import { PortTipHost } from './components/PortTip';
import { useHelperFunctions } from './hooks/useHelperFunctions';
import { useFlowComputation } from './hooks/useFlowComputation';
import FusionBridge from './bridge/FusionBridge.js';

// Import new modular managers
import { NodeManager } from './modules/NodeManager';
import { EdgeManager } from './modules/EdgeManager';
import { GenerationManager } from './modules/GenerationManager';
import { unifiedPollingManager } from './modules/UnifiedPollingManager';

// Constants
const FLOW_CONFIG = {
  MIN_ZOOM: 0.1,
  MAX_ZOOM: 4,
  SNAP_GRID: [15, 15]
};

function NoodleAppInner() {
  // ========================================================================
  // CORE STATE
  // ========================================================================
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [reactFlowKey, setReactFlowKey] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null); // { level, text }
  // How the last Generate went: {ok, text}. Shown by the Generate button, not the message line.
  const [lastGenerate, setLastGenerate] = useState(null);
  const [version, setVersion] = useState(null); // From Noodle.manifest via the backend
  const reactFlowInstance = useReactFlow();
  useCanvasWheel(reactFlowInstance, FLOW_CONFIG.MIN_ZOOM, FLOW_CONFIG.MAX_ZOOM);

  // Messages from nodes, such as a selection that could not start
  useEffect(() => onStatus(setStatusMessage), []);

  // Tracks edits since the last Generate and keeps the add-in's working copy current
  const { isEdited, isStale, expectLoad, markGenerated } = useWorkingGraph({
    nodes, edges, reactFlowInstance,
    onProblem: (text) => setStatusMessage({ level: 'warning', text })
  });

  // Effector visualizer: dots in the viewport for effectors whose eye is on
  useVisualizer({ nodes, edges, onStatus: setStatusMessage });

  // Call before putting a loaded graph on the canvas
  const noteGraphLoad = useCallback((isWorkingCopy) => {
    expectLoad(isWorkingCopy ? 'working' : 'generated');
    if (isWorkingCopy) {
      setStatusMessage({ level: 'info', text: 'Restored your unsaved graph edits. The design still shows the last Generate.' });
    }
  }, [expectLoad]);

  // Initialize validation hook
  const { validateAllNodes, getFieldValidationState } = useNodeValidation();

  // ========================================================================
  // HOOKS
  // ========================================================================
  // Order matters below: a hook must come after the hooks whose results it uses
  const {
    nodeMenu,
    setNodeMenu,
    categories,
    setCategories,
    showCascadingMenu,
    setShowCascadingMenu,
    hoveredCategory,
    setHoveredCategory,
    freshNodes,
    setFreshNodes,
    fadingNodes,
    setFadingNodes
  } = useUIState();

  const { fixEdgeColors } = useHelperFunctions();
  
  const { 
    computeFlow, 
    setSelectionLock
  } = useFlowComputation({ 
    nodes, 
    edges, 
    setNodes,
    onProblem: (text) => setStatusMessage({ level: 'warning', text })
  });

  const {
    handleNodeInputChange,
    handleNodesChange,
    handleEdgesChange,
  } = useNodeInputManagement({ 
    setNodes, 
    onNodesChange,
    onEdgesChange,
    computeFlow,
    edges
  });

  useTooltipRemoval();

  // Start the message bridge to the add-in. The saved graph itself arrives with
  // palette_ready (see main.jsx) and is put on the canvas further down.
  useEffect(() => {
    FusionBridge.initialize().catch(error => {
      console.error('[App] Failed to initialize communication:', error);
    });
  }, []);

  // ========================================================================
  // MANAGERS
  // ========================================================================
  const nodeManager = useMemo(() => 
    new NodeManager(reactFlowInstance, nodeMenu, setNodes, setFreshNodes, setEdges), 
    [reactFlowInstance, nodeMenu, setNodes, setFreshNodes, setEdges]
  );
  
  const edgeManager = useMemo(() => 
    new EdgeManager(nodes, edges, setEdges),
    [nodes, edges, setEdges]
  );

  const generationManager = useMemo(() => 
    new GenerationManager(reactFlowInstance),
    [reactFlowInstance]
  );

  // Validate all nodes when nodes or their data change. The same object is kept
  // while the errors are unchanged: every node reads it through context, so a
  // new object on each drag frame would re-render every node on the canvas.
  const lastValidationRef = useRef(null);
  const validationResult = useMemo(() => {
    const result = validateAllNodes(nodes);
    const signature = JSON.stringify(result.fieldErrors);
    if (lastValidationRef.current && lastValidationRef.current.signature === signature) {
      return lastValidationRef.current.result;
    }
    lastValidationRef.current = { signature, result };
    return result;
  }, [nodes, validateAllNodes]);

  // First validation error, for Generate's tip (Generate is disabled while any exist)
  const validationMessage = useMemo(() => {
    if (!validationResult.hasErrors) return null;
    const [nodeId, errors] = Object.entries(validationResult.errors)[0];
    const node = nodes.find(n => n.id === nodeId);
    const name = node?.data?.label || node?.data?.nodeType || 'A node';
    return `${name}: ${errors[0]}`;
  }, [validationResult, nodes]);

  // Where the design stands, shown on the Generate button with a tip
  const generateState = useMemo(() => {
    if (isGenerating) return { state: 'generating', title: 'Generating', body: "Fusion's progress dialog can cancel it." };
    if (nodes.length === 0) return { state: 'empty', title: 'Nothing to generate', body: 'Add nodes to generate.' };
    if (validationMessage) return { state: 'invalid', title: 'Fix before generating', body: validationMessage };
    if (lastGenerate && !lastGenerate.ok) {
      return { state: 'failed', title: lastGenerate.cancelled ? 'Generate was cancelled' : 'The last Generate failed', body: lastGenerate.text };
    }
    if (isStale) return { state: 'stale', title: 'Out of date', body: 'The graph has changed since the last Generate.' };
    return { state: 'current', title: 'Up to date',
             body: lastGenerate?.text || 'The design matches the graph.' };
  }, [isGenerating, nodes.length, validationMessage, lastGenerate, isStale]);

  // ========================================================================
  // UTILITY FUNCTIONS
  // ========================================================================
  const reinitializeReactFlow = useCallback(() => {
    setReactFlowKey(prev => prev + 1);
  }, []);

  const removeFreshHighlight = useCallback((nodeId) => {
    setFadingNodes(prev => new Set([...prev, nodeId]));
    setTimeout(() => {
      setFreshNodes(prev => {
        const newSet = new Set(prev);
        newSet.delete(nodeId);
        return newSet;
      });
      setFadingNodes(prev => {
        const newSet = new Set(prev);
        newSet.delete(nodeId);
        return newSet;
      });
    }, 400);
  }, [setFreshNodes, setFadingNodes]);


  // ========================================================================
  // EVENT HANDLERS
  // ========================================================================
  const handleGenerate = useCallback(async () => {
    if (nodes.length === 0 || isGenerating) {
      return;
    }
    
    setIsGenerating(true);
    setLastGenerate(null);
    // Generate replaces the visualizer: turn every effector eye off
    setNodes(current => (current.some(n => n.data?.visualize)
      ? current.map(n => (n.data?.visualize ? { ...n, data: { ...n.data, visualize: false } } : n))
      : current));
    try {
      const result = await generationManager.generateGeometry(nodes, edges);

      if (!result || !result.success) {
        const text = (result && result.error) || 'Generate failed. See the Text Commands window for details.';
        setLastGenerate({ ok: false, cancelled: Boolean(result && result.cancelled), text });
        setStatusMessage({ level: result && result.cancelled ? 'warning' : 'error', text });
        // Select the node that failed so it's easy to find
        if (result && result.failed_node_id) {
          setNodes(currentNodes => currentNodes.map(n => ({ ...n, selected: n.id === result.failed_node_id })));
        }
        return result;
      }

      const warnings = result.warnings || [];
      setLastGenerate({ ok: true, text: warnings.join(' ') });
      markGenerated();
      setStatusMessage(warnings.length ? { level: 'warning', text: warnings.join(' ') } : null);
      emitVisibilityEvent('bodies-changed'); // Eye icons read their state again
      
      // Process execution results and update node data with any fresh coordinates
      if (result.results) {
        setNodes(currentNodes => {
          return currentNodes.map(node => {
            const nodeResult = result.results[node.id];
            if (nodeResult) {
              return {
                ...node,
                data: {
                  ...node.data,
                  executionResult: nodeResult  // Store the execution result with _fresh_coordinates
                }
              };
            }
            return node;
          });
        });
        
        // Force flow computation AFTER updating node data
        // This ensures UI updates with fresh data from backend
        setTimeout(() => {
          computeFlow();
        }, 150); // Slightly longer delay to ensure state update completes
      }
      
      return result;
    } catch (error) {
      console.error('[Generate] Error during generation:', error);
      setLastGenerate({ ok: false, text: `Generate failed: ${error.message}` });
      setStatusMessage({ level: 'error', text: `Generate failed: ${error.message}` });
      return { success: false, error: error.message };
    } finally {
      setIsGenerating(false);
    }
  }, [nodes, edges, generationManager, computeFlow, setNodes, isGenerating, markGenerated]);

  const clearGraph = useCallback(() => {
    expectLoad('generated'); // The empty canvas is the new starting point, not an edit
    
    // Clear from the add-in first, which deletes the Base Feature
    setStatusMessage(null);
    if (window.adsk && window.adsk.fusionSendData) {
      try {
        Promise.resolve(window.adsk.fusionSendData('clearBaseFeature', JSON.stringify({})))
          .then(response => {
            const result = typeof response === 'string' ? JSON.parse(response) : response;
            if (result && result.success === false) {
              setStatusMessage({ level: 'error', text: `Could not delete the Noodle geometry: ${result.error || 'unknown error'}` });
            }
          })
          .catch(error => console.error('[Clear] Error clearing base feature:', error));
      } catch (error) {
        console.error('[Clear] Error clearing base feature:', error);
      }
    }
    
    setNodes([]);
    setEdges([]);
    
    setTimeout(() => {
      reinitializeReactFlow();
    }, 100);
  }, [setNodes, setEdges, reinitializeReactFlow, expectLoad]);

  const createNode = useCallback(async (nodeType, position = null) => {
    return nodeManager.createNode(nodeType, position);
  }, [nodeManager]);

  const onConnect = useCallback((connection) => {
    return edgeManager.onConnect(connection);
  }, [edgeManager]);

  // Dragging the end of a connection moves it; dropping it on empty canvas removes it
  const movingEdgeRef = useRef(null);
  const reconnectedRef = useRef(false);
  const onReconnectStart = useCallback((_, edge) => {
    movingEdgeRef.current = edge;
    reconnectedRef.current = false;
  }, []);
  const onReconnect = useCallback((oldEdge, connection) => {
    reconnectedRef.current = true;
    edgeManager.onReconnect(oldEdge, connection);
  }, [edgeManager]);
  const onReconnectEnd = useCallback((_, edge) => {
    if (!reconnectedRef.current) edgeManager.removeEdge(edge);
    movingEdgeRef.current = null;
    reconnectedRef.current = false;
  }, [edgeManager]);

  const isValidConnectionHandler = useCallback((connection) => {
    return edgeManager.isValidConnection(connection, movingEdgeRef.current);
  }, [edgeManager]);

  // Dynamic connection line styling
  const onConnectStart = useCallback((_, { nodeId, handleId, handleType }) => {
    if (handleType === 'source') {
      const sourceNode = nodes.find(n => n.id === nodeId);
      if (sourceNode) {
        const portName = handleId?.replace('output-', '');
        const portType = edgeManager.getPortType(sourceNode, 'output', portName);
        
        // Set CSS custom property for dynamic connection line color
        const color = edgeManager.getTypeColor(portType);
        document.documentElement.style.setProperty('--rf-connection-line-color', color);
      }
    }
  }, [nodes, edgeManager]);

  const onConnectEnd = useCallback(() => {
    // Back to the default from theme.css
    document.documentElement.style.removeProperty('--rf-connection-line-color');
  }, []);

  // ========================================================================
  // CUSTOM NODE WRAPPER
  // ========================================================================
  // Shared state for every node. Nodes read it through context, so changing it
  // re-renders nodes without React Flow remounting them (see NodeRuntime.jsx).
  const nodeRuntime = useMemo(() => ({
    freshNodes, fadingNodes, removeFreshHighlight, handleNodeInputChange,
    validationResult, getFieldValidationState, setSelectionLock
  }), [freshNodes, fadingNodes, removeFreshHighlight, handleNodeInputChange,
    validationResult, getFieldValidationState, setSelectionLock]);

  // ========================================================================
  // GRAPH OPERATIONS HOOK
  // ========================================================================
  const { loadGraphFromData } = useGraphOperations({
    reactFlowInstance,
    setNodes,
    setEdges,
    computeFlow,
    fixEdgeColors
  });

  // Ask the add-in to do something that may show a Fusion dialog. FusionBridge's
  // 10 second timeout would fire while a file dialog is still open, so call directly.
  const callAddin = useCallback(async (action, payload = {}) => {
    if (!(window.adsk && window.adsk.fusionSendData)) {
      return { success: false, error: 'Fusion is not available.' };
    }
    const response = await window.adsk.fusionSendData(action, JSON.stringify({ action, ...payload }));
    if (!response) return { success: false, error: 'No response from the add-in.' };
    return typeof response === 'string' ? JSON.parse(response) : response;
  }, []);

  const saveGraphFile = useCallback(async () => {
    if (!reactFlowInstance || nodes.length === 0) return;
    try {
      const result = await callAddin('saveGraphFile', { reactFlowState: reactFlowInstance.toObject() });
      if (result.cancelled) return;
      setStatusMessage(result.success
        ? { level: 'success', text: `Saved ${result.filename}.` }
        : { level: 'error', text: result.error || 'Could not save the graph.' });
    } catch (error) {
      setStatusMessage({ level: 'error', text: `Could not save the graph: ${error.message}` });
    }
  }, [reactFlowInstance, nodes.length, callAddin]);

  const openGraphFile = useCallback(async () => {
    try {
      const result = await callAddin('openGraphFile');
      if (result.cancelled) return;
      if (!result.success || !result.reactFlowState) {
        setStatusMessage({ level: 'error', text: result.error || 'Could not open the graph.' });
        return;
      }

      // Replace the canvas with the opened graph. It differs from what was last
      // generated, so it counts as an edit.
      expectLoad('working');
      reinitializeReactFlow();
      setNodes([]);
      setEdges([]);
      setFreshNodes(new Set());
      setFadingNodes(new Set());
      setTimeout(() => {
        loadGraphFromData(result.reactFlowState);
      }, 100);

      const warnings = result.warnings || [];
      setStatusMessage(warnings.length
        ? { level: 'warning', text: `Opened ${result.filename}. Updated from an older version: ${warnings.join(' ')}` }
        : { level: 'success', text: `Opened ${result.filename}. Click Generate to build it.` });
    } catch (error) {
      setStatusMessage({ level: 'error', text: `Could not open the graph: ${error.message}` });
    }
  }, [callAddin, reinitializeReactFlow, setNodes, setEdges, setFreshNodes, setFadingNodes, loadGraphFromData, expectLoad]);

  // Throw away edits made since the last Generate and show the generated graph again
  const revertGraph = useCallback(async () => {
    try {
      const result = await callAddin('discardWorkingGraph');
      if (!result.success) {
        setStatusMessage({ level: 'error', text: result.error || 'Could not revert the graph.' });
        return;
      }
      const generated = (result.reactFlowStates || [])[0];
      expectLoad('generated');
      reinitializeReactFlow();
      setNodes([]);
      setEdges([]);
      setFreshNodes(new Set());
      setFadingNodes(new Set());
      setTimeout(() => {
        if (generated) loadGraphFromData(generated);
      }, 100);
      setStatusMessage({
        level: 'info',
        text: generated ? 'Reverted to the graph from the last Generate.' : 'Reverted. This design has no generated graph yet.'
      });
    } catch (error) {
      setStatusMessage({ level: 'error', text: `Could not revert the graph: ${error.message}` });
    }
  }, [callAddin, reinitializeReactFlow, setNodes, setEdges, setFreshNodes, setFadingNodes, loadGraphFromData, expectLoad]);

  // ========================================================================
  // EFFECTS
  // ========================================================================

  // Setup unified polling system (selection and tooltips only)
  useEffect(() => {
    // No visibility polling - nodes are master controls, no browser tree sync needed
    
    // Handle document visibility changes for lifecycle compliance
    const handleVisibilityChange = () => {
      if (document.hidden) {
        unifiedPollingManager.enterHiddenMode();
      } else {
        unifiedPollingManager.exitHiddenMode();
      }
    };
    
    const stopPolling = () => unifiedPollingManager.stop();
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('beforeunload', stopPolling);
    window.addEventListener('pagehide', stopPolling);

    return () => {
      unifiedPollingManager.stop();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('beforeunload', stopPolling);
      window.removeEventListener('pagehide', stopPolling);
    };
  }, []);

  // Load node data on startup
  useEffect(() => {
    const nodeData = window.noodleNodeData;

    if (nodeData) {
      const nodes = Array.isArray(nodeData) ? nodeData : nodeData.nodes || [];

      setNodeMenu(nodes);

      // Use backend-ordered sections when available; fall back to deriving from node data
      const sections = !Array.isArray(nodeData) && nodeData.sections
        ? nodeData.sections
        : [...new Set(nodes.map(n => n.menu_category || n.category).filter(c => c !== '_hidden'))];
      setCategories(sections);
      if (!Array.isArray(nodeData) && nodeData.version) setVersion(nodeData.version);
    } else {
      console.error('[Frontend] ❌ No pre-loaded node data available');
    }
  }, [setNodeMenu, setCategories]);

  // Restore ReactFlow state from backend
  useEffect(() => {
    const reactFlowState = window.noodleReactFlowState;

    if (reactFlowState && reactFlowState.nodes && reactFlowState.nodes.length > 0) {
      try {
        noteGraphLoad(Boolean(window.noodleWorkingCopy));
        loadGraphFromData(reactFlowState);
        // An older graph was updated on load and something in it needs checking
        const notes = window.noodleLoadNotes || [];
        if (notes.length) setStatusMessage({ level: 'warning', text: notes.join(' ') });
        window.noodleReactFlowState = null;
        window.noodleWorkingCopy = false;
        window.noodleLoadNotes = [];
      } catch (error) {
        console.error('[Frontend] ❌ Error restoring ReactFlow state:', error);
      }
    }
  }, [nodeMenu, loadGraphFromData, noteGraphLoad]);

  // ========================================================================
  // RENDER
  // ========================================================================
  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Toolbar
        nodeMenu={nodeMenu || []}
        categories={categories || []}
        showCascadingMenu={showCascadingMenu}
        setShowCascadingMenu={setShowCascadingMenu}
        hoveredCategory={hoveredCategory}
        setHoveredCategory={setHoveredCategory}
        createNode={createNode}
        nodes={nodes}
        version={version}
        generateState={generateState}
        openGraphFile={openGraphFile}
        saveGraphFile={saveGraphFile}
        revertGraph={revertGraph}
        isEdited={isEdited}
        clearGraph={clearGraph}
        handleGenerate={handleGenerate}
      />
      
      <PortTipHost />
      <StatusPanel statusMessage={statusMessage} />
      
      <NodeRuntimeContext.Provider value={nodeRuntime}>
      <ReactFlow
        key={reactFlowKey}
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onReconnectStart={onReconnectStart}
        onReconnect={onReconnect}
        onReconnectEnd={onReconnectEnd}
        reconnectRadius={20}
        onConnectStart={onConnectStart}
        onConnectEnd={onConnectEnd}
        isValidConnection={isValidConnectionHandler}
        nodeTypes={NODE_TYPES}
        fitView={false}  // Keep disabled - we'll use smart custom fitView
        minZoom={FLOW_CONFIG.MIN_ZOOM}
        maxZoom={FLOW_CONFIG.MAX_ZOOM}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        deleteKeyCode={['Backspace', 'Delete']}
        multiSelectionKeyCode={['Meta', 'Shift', 'Control']}
        // Navigation as in Fusion's viewport: a mouse wheel and a pinch zoom toward the
        // cursor, two fingers on a trackpad pan (all in useCanvasWheel), and a
        // middle-drag pans. Left- and right-drag on empty canvas pan too.
        zoomOnScroll={false}
        panOnScroll={false}
        zoomOnPinch={false}
        selectionOnDrag={false}  // Disable to prevent interference with input focus
        panOnDrag={[0, 1, 2]}
        nodesFocusable={true}  // Allow nodes to receive focus for accessibility
        elementsSelectable={true}
        connectionLineStyle={{ stroke: 'var(--rf-connection-line-color, #8babdc)', strokeWidth: 2 }}
        connectionLineType="bezier"
        snapToGrid={false}
        snapGrid={FLOW_CONFIG.SNAP_GRID}
        defaultEdgeOptions={{
          type: 'default',
          animated: false,
          style: { stroke: '#8babdc', strokeWidth: 2 }
        }}
      >
        <Background variant="dots" gap={12} size={1} color="#2a2a2a" />
        <Controls 
          fitViewOptions={{ maxZoom: 1.0, padding: 0.1 }}
        />
      </ReactFlow>
      </NodeRuntimeContext.Provider>
    </div>
  );
}

// Main app wrapper with ReactFlowProvider
function NoodleApp() {
  return (
    <ReactFlowProvider>
      <NoodleAppInner />
    </ReactFlowProvider>
  );
}

export default NoodleApp;