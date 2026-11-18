/**
 * Selection input port component - handles body, surface, brep selection
 * Now uses foundational SelectionButton and ClearButton components
 */
import React from 'react';
import BasePort from './BasePort';
import SelectionButton from '../SelectionButton';
import ClearButton from '../ClearButton';

const SelectionInputPort = ({ 
  portName, 
  portInfo, 
  currentValue, 
  computedInputs = {},
  onInputChange,
  nodeId,
  isConnected = false,
  validationState = null,
  showHandle = true,
  // Pauses flow computation while the Select button is picking
  setSelectionLock
}) => {
  const isComputed = computedInputs && computedInputs[portName] !== undefined;
  const hasValidationError = validationState && validationState.hasError;
  
  // Get selection type from port info
  const selectionType = portInfo?.selectionType || portInfo?.type?.toLowerCase() || 'body';
  
  // Check for selection data based on type
  const hasSelection = currentValue && (() => {
    switch (selectionType) {
      case 'surface':
        return currentValue.entity_token || currentValue.display_name;
      case 'body':
        return currentValue.entity_token || currentValue.body_name;
      case 'point':
        return currentValue.entity_token || currentValue.point_name || currentValue.display_name;
      case 'curve':
        return currentValue.entity_token || currentValue.display_name;
      default:
        return currentValue.entity_token || currentValue.body_name;
    }
  })();
  
  const handleSelectionComplete = (selectionData) => {
    if (onInputChange) {
      // Call onInputChange - this should update the node's currentInputs
      onInputChange(portName, selectionData);
    } else {
      console.error('❌ SelectionInputPort - onInputChange is missing!');
    }
  };
  
  const handleClear = () => {
    onInputChange(portName, null);
  };
  
  // Selection ports don't show ReactFlow handles (per specification)
  return (
    <BasePort 
      portName={portName} 
      portInfo={portInfo} 
      direction="input"
      isConnected={isConnected}
      className="selection-port"
      showHandle={showHandle} // Allow override, but typically false for selection ports
    >
      {/* Inline status display for selection ports */}
      <div className="entity-status-inline">
        <span className="port-label">
          {portInfo?.label || portName.replace(/_/g, " ")}
          {currentValue ? ` - ${currentValue.display_name || currentValue.point_name || currentValue.body_name || 'Selected'}` : ' - None'}
        </span>
      </div>
      
      {/* Selection UI using foundational components */}
      <div className="entity-inputs">
        <div className="entity-control-line">
          <SelectionButton
            selectionType={selectionType}
            nodeId={nodeId}
            portName={portName}
            hasSelection={hasSelection}
            onSelectionComplete={handleSelectionComplete}
            disabled={isComputed || isConnected}
            setSelectionLock={setSelectionLock}
          />
          {hasSelection && !isConnected && (
            <ClearButton
              onClear={handleClear}
              disabled={isComputed}
            />
          )}
        </div>
      </div>
    </BasePort>
  );
};

export default SelectionInputPort;