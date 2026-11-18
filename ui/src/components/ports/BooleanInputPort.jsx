/**
 * Boolean Input Port - renders a custom checkbox for boolean values
 */
import React from 'react';
import BasePort from './BasePort';

const BooleanInputPort = ({
  portName,
  portInfo,
  currentValue,
  computedInputs,
  onInputChange,
  isConnected,
  validationState = null,
  showHandle = true
}) => {
  const isComputed = computedInputs && computedInputs[portName] !== undefined;
  const isLocked = isConnected || isComputed;
  const value = isComputed ? computedInputs[portName] : currentValue;
  const boolValue = Boolean(value ?? portInfo?.defaultValue ?? false);
  const hasValidationError = validationState && validationState.hasError;

  const handleToggle = () => {
    if (!isLocked && onInputChange) {
      onInputChange(portName, !boolValue);
    }
  };

  return (
    <BasePort
      portName={portName}
      portInfo={portInfo}
      direction="input"
      isConnected={isConnected}
      hasValidationError={hasValidationError}
      showHandle={showHandle}
    >
      <span className="port-label">
        {portInfo?.label || portName.replace(/_/g, ' ')}
      </span>

      <button
        type="button"
        role="checkbox"
        aria-checked={boolValue}
        onClick={handleToggle}
        disabled={isLocked}
        className={`custom-checkbox nodrag${boolValue ? ' checked' : ''}${isLocked ? ' disabled' : ''}${hasValidationError ? ' error' : ''}`}
        title={hasValidationError ? validationState?.errorMessage : ''}
      >
        {boolValue && (
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
            <path d="m4.2 8.6 1.4-1.5 1.7 1.5 3.6-4 1.5 1.3-5 5.5-3.2-2.8z"/>
          </svg>
        )}
      </button>
    </BasePort>
  );
};

export default BooleanInputPort;
