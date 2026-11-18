/**
 * Numeric input port component - handles float, integer, number types
 */
import React, { useState, useRef, useEffect } from 'react';
import BasePort from './BasePort';
import { unitSuffix, formatShown } from '../../utils/units';
import { boundsText } from '../../utils/portBounds';
import { showPortTip, hidePortTip, portTipContent } from '../PortTip';
import { handleFieldKeys } from '../../utils/fieldKeys';

const NumericInputPort = ({ 
  portName, 
  portInfo, 
  currentValue, 
  computedInputs = {},
  onInputChange,
  isConnected = false,
  validationState = null,
  showHandle = true
}) => {
  const [editingValue, setEditingValue] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef(null);
  // Whether the user has typed since focusing. Only typing is an edit: a field
  // tabbed through, or whose value changed underneath it, never saves on blur.
  const typedRef = useRef(false);
  
  const isComputed = computedInputs && computedInputs[portName] !== undefined;
  const isLocked = isConnected || isComputed;
  const value = isComputed ? computedInputs[portName] : currentValue;
  const hasValidationError = validationState && validationState.hasError;
  
  const showInputField = portInfo?.showInputField !== false;
  const suffix = unitSuffix(portInfo);
  const range = boundsText(portInfo);
  
  // Show the current value, also while focused but not yet typed in. Tabbing from
  // a linked field (hexagonal Spacing X to Y) lands here before the new value
  // arrives; it replaces the old one and stays selected, ready to type over.
  useEffect(() => {
    if (isEditing && typedRef.current) return;
    const displayValue = value ?? (portInfo?.defaultValue || portInfo?.default || 0);
    setEditingValue(String(displayValue));
    if (isEditing && document.activeElement === inputRef.current) {
      setTimeout(() => inputRef.current?.select(), 0);
    }
  }, [value, isEditing, portInfo]);
  
  const tip = portTipContent(portInfo, range, Boolean(hasValidationError));

  const handleFocus = (e) => {
    typedRef.current = false;
    setIsEditing(true);
    // Clicking into a bounded field shows its range at once
    if (tip && range) showPortTip({ anchor: e.target.closest('.port'), ...tip });
    setEditingValue(String(value ?? (portInfo?.defaultValue || portInfo?.default || 0)));
    // Select all text for easy replacement
    setTimeout(() => e.target.select(), 0);
  };
  
  const handleChange = (e) => {
    const inputText = e.target.value;
    
    // Allow typing: digits, decimal point, minus sign, empty string
    const validPattern = /^-?\d*\.?\d*$/;
    if (inputText === '' || validPattern.test(inputText)) {
      typedRef.current = true;
      setEditingValue(inputText);
    }
  };
  
  const handleBlur = (e) => {
    setIsEditing(false);
    hidePortTip(e.target.closest('.port'));
    const typed = typedRef.current;
    typedRef.current = false;
    if (!typed) return;   // Tabbed through: nothing to save
    
    // Parse and commit the value
    let finalValue = 0;
    if (editingValue === '' || editingValue === '-' || editingValue === '.') {
      finalValue = 0;
    } else {
      const parsed = parseFloat(editingValue);
      finalValue = isNaN(parsed) ? 0 : parsed;
    }
    
    // Leaving a field without changing it is not an edit. Committing anyway
    // would mark the graph as edited, and on a hexagonal grid it would nudge
    // the linked spacing a little further on every Tab.
    const shownValue = Number(value ?? (portInfo?.defaultValue || portInfo?.default || 0));
    if (finalValue === shownValue) return;

    onInputChange(portName, finalValue);
  };
  
  return (
    <BasePort 
      portName={portName} 
      portInfo={portInfo} 
      direction="input"
      isConnected={isConnected}
      showHandle={showHandle}
      tip={tip}
    >
      <span className="port-label">
        {portInfo?.label || portName.replace(/_/g, " ")}
        {suffix && <span className="port-unit">{suffix}</span>}
      </span>
      
      {showInputField && (
        <input
          ref={inputRef}
          type="text"
          value={isEditing ? editingValue : formatShown(value ?? (portInfo?.defaultValue || portInfo?.default || 0))}
          onFocus={handleFocus}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={e => handleFieldKeys(e, () => { typedRef.current = false; })}
          disabled={isLocked}
          className={`node-input number-input nodrag ${isLocked ? 'connected-value' : ''} ${hasValidationError ? 'error' : ''}`}
          placeholder={`${portInfo?.defaultValue || portInfo?.default || 0}`}
          title={hasValidationError ? validationState.errorMessage : ''}
        />
      )}

    </BasePort>
  );
};

export default NumericInputPort;