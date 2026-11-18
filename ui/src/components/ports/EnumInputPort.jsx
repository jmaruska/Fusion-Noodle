/**
 * Enum input port component - handles dropdown selection for enum types.
 * Always uses the custom CSS-driven dropdown (icon-enum-dropdown) for visual
 * consistency with the native Fusion UI two-column layout.
 */
import React, { useState, useRef, useEffect } from 'react';
import BasePort from './BasePort';

const EnumInputPort = ({ 
  portName, 
  portInfo, 
  currentValue, 
  computedInputs = {},
  onInputChange,
  isConnected = false,
  validationState = null,
  showHandle = true
}) => {
  const isComputed = computedInputs && computedInputs[portName] !== undefined;
  const value = isComputed ? computedInputs[portName] : (currentValue || portInfo?.defaultValue);
  const hasValidationError = validationState && validationState.hasError;
  
  const showInputField = portInfo?.showInputField !== false;
  const enumOptions = portInfo?.enumOptions || [];
  const enumIcons  = portInfo?.enumIcons  || null;
  const enumLabels = portInfo?.enumLabels || null;

  const [open, setOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [open]);

  const handleSelect = (option) => {
    onInputChange(portName, option);
    setOpen(false);
  };

  const getLabel = (option) => enumLabels?.[option] || option;
  const getIcon  = (option) => enumIcons?.[option]  || null;

  return (
    <BasePort 
      portName={portName} 
      portInfo={portInfo} 
      direction="input"
      isConnected={isConnected}
      validationState={validationState}
      showHandle={showHandle}
    >
      <div className="port-content">
        <span className="port-label">
          {portInfo?.label || portName.replace(/_/g, ' ')}
        </span>

        {showInputField && !isConnected && (
          <div
            ref={dropdownRef}
            className={`icon-enum-dropdown nodrag${hasValidationError ? ' error' : ''}${isComputed ? ' computed' : ''}`}
          >
            <button
              className="icon-enum-trigger"
              onClick={() => !isComputed && setOpen(o => !o)}
              disabled={isComputed}
              type="button"
            >
              {getIcon(value) && (
                <img src={`./icons/${getIcon(value)}`} alt="" className="enum-option-icon" />
              )}
              <span>{getLabel(value || '')}</span>
              <svg className="enum-caret" xmlns="http://www.w3.org/2000/svg" width="7" height="4" viewBox="0 0 7 4" fill="currentColor" aria-hidden="true">
                <path d="M0 0h7L3.5 4 0 0z"/>
              </svg>
            </button>

            {open && (
              <ul className="icon-enum-menu">
                {enumOptions.map(option => (
                  <li
                    key={option}
                    className={`icon-enum-item${option === value ? ' selected' : ''}`}
                    onMouseDown={() => handleSelect(option)}
                  >
                    {getIcon(option) && (
                      <img src={`./icons/${getIcon(option)}`} alt="" className="enum-option-icon" />
                    )}
                    <span>{getLabel(option)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {isConnected && (
          <span className="connected-indicator">Connected</span>
        )}

        {isComputed && !isConnected && (
          <span className="computed-value">{value}</span>
        )}
      </div>
    </BasePort>
  );
};

export default EnumInputPort;

