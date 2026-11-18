/**
 * Base node shell component - provides common structure for all node types
 */
import React, { useEffect, useState, useRef } from 'react';
import VisibleOnIcon from '../../icons/visible-on.svg';
import VisibleOffIcon from '../../icons/visible-off.svg';
import FusionBridge from '../bridge/FusionBridge';

import { useReactFlow } from '@xyflow/react';
import { onVisibilityEvent, emitVisibilityEvent } from '../utils/visibilityBus.js';
import { handleNodeTab } from '../utils/fieldFocus.js';

// Helper function to determine if node should show visibility toggle
const shouldShowVisibilityToggle = (nodeType, nodeCategory, nodeInfo) => {
  // Transform nodes pass geometry through but don't create it — no toggle
  if (nodeCategory === 'transform') {
    return false;
  }

  // Always show for geometry category nodes
  if (nodeCategory === 'geometry') {
    return true;
  }

  // Show for nodes with geometry output ports
  if (nodeInfo?.outputs) {
    const outputs = Array.isArray(nodeInfo.outputs) ? nodeInfo.outputs : Object.values(nodeInfo.outputs);
    return outputs.some(output =>
      output.type === 'GEOMETRY' ||
      output.type === 'BREP' ||
      output.type === 'geometry' ||
      output.type === 'brep'
    );
  }
  
  // Show for specific geometry-producing node types
  const geometryNodeTypes = [
    'body_instance',
    'cube_generator', 'box_generator',
    'sphere_generator',
    'cylinder_generator', 
    'polygon_generator',
    'extrude_node',
    'revolve_node',
    'materializer',  // Collection materializer creates visible geometry
    'loft_node',
    'materialize', 'materializer'
  ];
  
  return geometryNodeTypes.includes(nodeType);
};

/**
 * The eye on an effector. It doesn't show or hide bodies: it turns on the
 * visualizer, which draws a dot at every instance colored by how strongly the
 * effector acts on it. The state lives on the node as `data.visualize`; the
 * useVisualizer hook watches it and keeps the dots up to date.
 */
const VisualizerToggle = ({ id, on }) => {
  // React Flow's own update, available on every node. A function stored in the
  // node's data is not: nodes reloaded after a Generate don't carry one.
  const { updateNodeData } = useReactFlow();
  const onRef = useRef(on);
  onRef.current = on;

  // Showing bodies again (a body eye turned on) turns every visualizer off
  useEffect(() => onVisibilityEvent('visualizers-off', () => {
    if (onRef.current) updateNodeData(id, { visualize: false });
  }), [id, updateNodeData]);

  // Bodies are hidden once the dots are drawn (useVisualizer), so the click shows at once
  const toggle = (e) => {
    e.stopPropagation();
    updateNodeData(id, { visualize: !on });
  };

  return (
    <button className="node-visibility-toggle nodrag" onClick={toggle}>
      <img
        src={on ? VisibleOnIcon : VisibleOffIcon}
        alt={on ? 'Visualizer on' : 'Visualizer off'}
        className="visibility-icon"
      />
    </button>
  );
};

const VisibilityToggle = ({ id, initialVisible = true, nodeType = '' }) => {
  const [isVisible, setIsVisible] = useState(initialVisible);
  const [isPending, setIsPending] = useState(false);
  const pendingTimeoutRef = useRef(null);
  const lastClickRef = useRef(0);
  const visibleRef = useRef(isVisible);
  visibleRef.current = isVisible;

  // An effector's visualizer was turned on: hide this node's bodies so they
  // don't cover the dots.
  useEffect(() => onVisibilityEvent('hide-bodies', (nodes) => {
    if (!visibleRef.current) return;
    setIsVisible(false);
    nodes.push({ nodeId: id, nodeType });
  }), [id, nodeType]);

  // The curve editor asks which bodies are showing before it hides them, and
  // shows exactly those again when it closes
  useEffect(() => onVisibilityEvent('collect-visible-bodies', (ids) => {
    if (visibleRef.current && Array.isArray(ids)) ids.push(id);
  }), [id]);
  useEffect(() => onVisibilityEvent('show-bodies', ({ ids, nodes }) => {
    if (visibleRef.current || !ids.includes(id)) return;
    setIsVisible(true);
    nodes.push({ nodeId: id, nodeType });
  }), [id, nodeType]);

  const toggleVisibility = (e) => {
    e.stopPropagation();
    
    // Optimistic update for immediate visual feedback
    const newState = !isVisible;
    setIsVisible(newState);
    setIsPending(true);

    // Bringing geometry back turns the visualizers off
    if (newState) emitVisibilityEvent('visualizers-off');
    
    // Debounce rapid clicks
    const now = Date.now();
    lastClickRef.current = now;
    
    // Clear any pending timeout
    if (pendingTimeoutRef.current) {
      clearTimeout(pendingTimeoutRef.current);
    }
    
    // Debounced backend sync
    pendingTimeoutRef.current = setTimeout(async () => {
      // Only proceed if this is still the latest click
      if (lastClickRef.current === now) {
        try {
          await FusionBridge.sendMessage('set_node_visibility', {
            nodeId: id,
            nodeType,
            visible: newState
          });
          
          // On successful backend sync, ensure UI matches backend state
        } catch (error) {
          // Revert on error
          console.error('[VisibilityToggle] Backend sync failed:', error);
          setIsVisible(!newState);
        } finally {
          setIsPending(false);
        }
      }
    }, 200); // 200ms debounce
  };

  // Read the state from the design when the node appears, and again after each
  // Generate, which makes new bodies and hides template bodies itself.
  useEffect(() => {
    let isMounted = true;
    const readState = async () => {
      try {
        if (!FusionBridge.initialized) {
          await FusionBridge.initialize();
        }
        const resp = await FusionBridge.sendMessage('get_node_visibility', { nodeId: id, nodeType });
        if (isMounted && resp && resp.success && typeof resp.visible === 'boolean') {
          setIsVisible(resp.visible);
        }
      } catch (e) {
        // Ignore init errors
      }
    };
    readState();
    const unsubscribe = onVisibilityEvent('bodies-changed', readState);

    return () => {
      isMounted = false;
      unsubscribe();
      if (pendingTimeoutRef.current) {
        clearTimeout(pendingTimeoutRef.current);
      }
    };
  }, [id, nodeType]);

  const IconSrc = isVisible ? VisibleOnIcon : VisibleOffIcon;

  return (
    <button
      className={`node-visibility-toggle nodrag ${isPending ? 'pending' : ''}`}
      onClick={toggleVisibility}
      title={isVisible ? "Hide in viewport" : "Show in viewport"}
    >
      <img 
        src={IconSrc} 
        alt={isVisible ? "Visible" : "Hidden"}
        className="visibility-icon"
      />
    </button>
  );
};

const BaseNode = ({ 
  id, 
  data, 
  children, 
  className = '',
  showVisibilityToggle 
}) => {
  const {
    label = "Node",
    nodeType = "",
    nodeCategory = "",
    nodeInfo = {},
    initiallyVisible = true,
    wide = false,
    visualize = false
  } = data || {};

  // Effectors get the visualizer eye instead of a body eye
  const isEffector = nodeCategory === 'effector';
  
  // Determine if visibility toggle should be shown
  const shouldShow = showVisibilityToggle !== undefined 
    ? showVisibilityToggle 
    : shouldShowVisibilityToggle(nodeType, nodeCategory, nodeInfo);

  // Tab moves between this node's fields only (see utils/fieldFocus.js)
  const onKeyDown = (event) => handleNodeTab(event, event.currentTarget);

  return (
    <div 
      onKeyDown={onKeyDown}
      className={`custom-node node-type-${nodeType} node-category-${nodeCategory || 'general'}${wide ? ' wide-node' : ''} ${className}`}
      data-node-type={nodeType} 
      data-node-category={nodeCategory}
      title=""
    >
      <div className="node-header">
        <span className="node-title" title="">{label}</span>
        {isEffector && (
          <VisualizerToggle id={id} on={Boolean(visualize)} />
        )}
        {shouldShow && !isEffector && (
          <VisibilityToggle 
            id={id} 
            initialVisible={initiallyVisible} 
            nodeType={nodeType}
          />
        )}
      </div>

      <div className="node-body">
        {children}
      </div>
    </div>
  );
};

export default BaseNode;