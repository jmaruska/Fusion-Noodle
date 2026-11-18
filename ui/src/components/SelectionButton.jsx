/**
 * Foundational SelectionButton component - handles just the button interaction
 * This is the reusable core that can be used in any selection context
 */
import React, { useState, useEffect, useRef } from 'react';
import FusionBridge from '../bridge/FusionBridge';
import { reportStatus } from '../utils/statusBus.js';
import { unifiedPollingManager } from '../modules/UnifiedPollingManager';

// Only one Select button can wait for a pick at a time: the add-in keeps one
// pending selection. This holds a function that disarms the waiting button.
let disarmWaitingButton = null;

const SelectionButton = ({ 
  selectionType = 'body', // 'body', 'surface', 'point', 'curve'
  nodeId, 
  portName, 
  hasSelection = false,
  onSelectionComplete, 
  onSelectionStart,
  disabled = false,
  className = '',
  // Pauses flow computation while this button is selecting
  setSelectionLock
}) => {
  const [selectionInProgress, setSelectionInProgress] = useState(false);
  const [startTime, setStartTime] = useState(null);
  const lastClickTime = useRef(0); // Prevent rapid double-clicks
  const inProgressRef = useRef(false);
  inProgressRef.current = selectionInProgress;
  // Only the button that took the selection lock may release it. Several Select
  // buttons can be on the canvas, and an idle one must not free another's lock.
  const holdsLockRef = useRef(false);
  // The parent hands a new callback on every render. Reading it through a ref
  // keeps the polling below from restarting each time the node re-renders.
  const onCompleteRef = useRef(onSelectionComplete);
  onCompleteRef.current = onSelectionComplete;
  const startTimeRef = useRef(null);
  startTimeRef.current = startTime;
  // Called when another Select button is armed. The lock is released here,
  // at once, so the other button's lock can't be undone by this one later.
  // Made once, so it keeps one identity for comparing with disarmWaitingButton.
  // Everything it uses is a ref, a state setter, or the stable lock setter.
  const disarmRef = useRef(null);
  if (!disarmRef.current) {
    disarmRef.current = () => {
      if (disarmWaitingButton === disarmRef.current) disarmWaitingButton = null;
      if (setSelectionLock && holdsLockRef.current) {
        holdsLockRef.current = false;
        setSelectionLock(false);
      }
      setSelectionInProgress(false);
      setStartTime(null);
    };
  }

  const takeLock = () => {
    if (setSelectionLock && !holdsLockRef.current) {
      holdsLockRef.current = true;
      setSelectionLock(true);
    }
  };
  const releaseLock = () => {
    if (setSelectionLock && holdsLockRef.current) {
      holdsLockRef.current = false;
      setSelectionLock(false);
    }
  };

  // Tell the backend to drop its pending selection (timeout, cancel, or unmount)
  const cancelBackendSelection = () => {
    FusionBridge.sendMessage('cancelSelection', { nodeId, portName }).catch(() => {});
  };

  // If the node is deleted (or the graph cleared/pasted) mid-selection, release the
  // flow-computation lock and the backend's pending selection. Otherwise the lock
  // stays held and connected values stop propagating until the palette reloads.
  useEffect(() => () => {
    releaseLock();
    if (inProgressRef.current) {
      cancelBackendSelection();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  
  // Selection type configuration (matches backend specification)
  const selectionConfig = {
    body: { displayName: 'Body', icon: 'SelectMousePointer.svg' },
    surface: { displayName: 'Surface', icon: 'SelectMousePointer.svg' },
    point: { displayName: 'Point', icon: 'SelectMousePointer.svg' },
    curve: { displayName: 'Curve', icon: 'SelectMousePointer.svg' }
  };
  
  const config = selectionConfig[selectionType] || selectionConfig.body;
  
  // Button text following Fusion UX paradigm
  const buttonText = (() => {
    if (selectionInProgress) {
      return 'Selecting...';
    } else if (hasSelection) {
      // Show quantity-based text for loaded state
      return '1 Selected'; // Could be enhanced for multi-select
    } else {
      // Empty state - show selection action
      return `Select ${config.displayName}`;
    }
  })();
  
  // Polling effect for active selections
  useEffect(() => {
    if (!selectionInProgress) {
      releaseLock();
      if (disarmWaitingButton === disarmRef.current) disarmWaitingButton = null;
      return;
    }

    takeLock();

    const checkSelection = async () => {
      try {
        // Check for timeout (30 seconds)
        const started = startTimeRef.current;
        if (started && Date.now() - started > 30000) {
          cancelBackendSelection();
          setSelectionInProgress(false);
          setStartTime(null);
          return;
        }

        const checkAction = `check${selectionType.charAt(0).toUpperCase() + selectionType.slice(1)}Selection`;
        const response = await FusionBridge.sendMessage(checkAction, {
          nodeId: nodeId,
          portName: portName
        });

        // Determine the data field name based on selection type
        const dataFieldName = `${selectionType}_data`;
        const selectionData = response[dataFieldName];

        if (response.success && selectionData) {
          // Selection completed successfully!
          setSelectionInProgress(false);
          setStartTime(null);
          onCompleteRef.current?.(selectionData);
        } else if (response.selection_complete && !selectionData) {
          // Selection completed but no data (failed)
          setSelectionInProgress(false);
          setStartTime(null);
        } else if (response.selection_pending) {
          // Still waiting for selection - continue polling
        } else if (!response.selection_active && !response.selection_pending && !response.selection_complete) {
          // Selection was cancelled or failed
          setSelectionInProgress(false);
          setStartTime(null);
        }
      } catch (error) {
        console.error('❌ SelectionButton: Selection check error:', error);
        setSelectionInProgress(false);
        setStartTime(null);
      }
    };

    // Setup unified polling for selection
    unifiedPollingManager.setFeatureHandler('selection', checkSelection);
    unifiedPollingManager.enterSelectionMode();
    
    // Start immediately
    checkSelection();
    
    return () => {
      unifiedPollingManager.exitSelectionMode();
    };
  }, [selectionInProgress, selectionType, nodeId, portName]); // eslint-disable-line react-hooks/exhaustive-deps
  
  const handleSelection = async () => {
    const now = Date.now();
    
    // Prevent rapid double-clicks (within 300ms)
    if (now - lastClickTime.current < 300) {
      return;
    }
    lastClickTime.current = now;
    
    if (disabled) {
      return;
    }

    // A second click while selecting cancels the selection
    if (selectionInProgress) {
      cancelBackendSelection();
      setSelectionInProgress(false);
      setStartTime(null);
      return;
    }

    // Arming this button disarms any other one that is waiting. It sends no
    // cancel: the add-in replaces the pending pick when this one starts.
    if (disarmWaitingButton && disarmWaitingButton !== disarmRef.current) disarmWaitingButton();
    disarmWaitingButton = disarmRef.current;

    // Use camelCase action names as per specification
    const actionName = `select${selectionType.charAt(0).toUpperCase() + selectionType.slice(1)}`;
    
    try {
      setSelectionInProgress(true);
      setStartTime(now);
      
      onSelectionStart?.();

      const response = await FusionBridge.sendMessage(actionName, {
        nodeId: nodeId,
        portName: portName
      });

      if (response.success) {
        const immediateData = response[`${selectionType}_data`];
        if (immediateData) {
          // Immediate selection (a matching entity was already selected in Fusion)
          setSelectionInProgress(false);
          setStartTime(null);
          onCompleteRef.current?.(immediateData);
        }
      } else {
        // Say why on the status line. Otherwise the button just flickers.
        reportStatus('warning', response.error || response.message || `Could not start selecting a ${config.displayName.toLowerCase()}.`);
        setSelectionInProgress(false);
        setStartTime(null);
      }
    } catch (error) {
      console.error('❌ SelectionButton: Selection error:', error);
      // Reset state on error
      setSelectionInProgress(false);
      setStartTime(null);
    }
  };
  
  return (
    <button
      className={`entity-select-button nodrag ${hasSelection ? 'loaded' : selectionInProgress ? 'selecting' : 'empty'} ${className}`}
      onClick={(e) => {
        // CRITICAL: Prevent ReactFlow from interfering with this click
        e.stopPropagation();
        e.preventDefault();
        e.target.focus(); // Ensure button gets focus
        handleSelection();
      }}
      onMouseDown={(e) => {
        // Also prevent mouseDown from being intercepted
        e.stopPropagation();
        e.target.focus(); // Force focus on mouseDown too
      }}
      tabIndex={0}  // Make button focusable
      disabled={disabled}
    >
      <div className="select-button-content">
        <div className="select-arrow-box">
          <img 
            alt="Select" 
            className="select-icon" 
            src={`./icons/${config.icon}`}
          />
        </div>
        <div className="select-text-area">
          <span className="select-text">{buttonText}</span>
        </div>
      </div>
    </button>
  );
};

export default SelectionButton;