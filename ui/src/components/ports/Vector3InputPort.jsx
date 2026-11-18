/**
 * Vector3 input port component - handles x, y, z coordinate inputs
 */
import React, { useState, useRef, useEffect } from 'react';
import BasePort from './BasePort';
import { formatShown, unitSuffix } from '../../utils/units';
import { handleFieldKeys } from '../../utils/fieldKeys';

const Vector3InputPort = ({ 
  portName, 
  portInfo, 
  currentValue, 
  computedInputs = {},
  onInputChange,
  isConnected = false,
  validationState = null,
  showHandle = true
}) => {
  const [editingValues, setEditingValues] = useState({ x: '', y: '', z: '' });
  const [editingAxis, setEditingAxis] = useState(null);
  const inputRefs = useRef({ x: null, y: null, z: null });
  
  const isComputed = computedInputs && computedInputs[portName] !== undefined;
  const isLocked = isConnected || isComputed;
  const value = isComputed ? computedInputs[portName] : currentValue;
  // A node that has never stored this input shows (and edits from) the port's default, which is
  // what the add-in uses too. Showing zeros instead would save zeros on the first edit.
  const vectorValue = value || portInfo?.defaultValue || { x: 0, y: 0, z: 0 };
  const hasValidationError = validationState && validationState.hasError;
  
  // Sync editing values when vectorValue changes externally
  useEffect(() => {
    if (!editingAxis) {
      setEditingValues({
        x: String(vectorValue.x || 0),
        y: String(vectorValue.y || 0),
        z: String(vectorValue.z || 0)
      });
    }
  }, [vectorValue, editingAxis]);
  
  // Whether the user has typed since focusing. Only typing is an edit: tabbing
  // through a field never saves it (which would also store defaults it shows).
  const typedRef = useRef(false);

  const handleFocus = (axis, e) => {
    typedRef.current = false;
    setEditingAxis(axis);
    setEditingValues(prev => ({
      ...prev,
      [axis]: String(vectorValue[axis] || 0)
    }));
    // Select all text for easy replacement
    setTimeout(() => e.target.select(), 0);
  };
  
  const handleAxisChange = (axis, inputText) => {
    // Allow typing: digits, decimal point, minus sign, empty string
    const validPattern = /^-?\d*\.?\d*$/;
    if (inputText === '' || validPattern.test(inputText)) {
      typedRef.current = true;
      setEditingValues(prev => ({ ...prev, [axis]: inputText }));
    }
  };
  
  const handleBlur = (axis) => {
    setEditingAxis(null);
    const typed = typedRef.current;
    typedRef.current = false;
    if (!typed) return;   // Tabbed through: nothing to save
    
    // Parse and commit the value
    const inputText = editingValues[axis];
    let finalValue = 0;
    if (inputText === '' || inputText === '-' || inputText === '.') {
      finalValue = 0;
    } else {
      const parsed = parseFloat(inputText);
      finalValue = isNaN(parsed) ? 0 : parsed;
    }
    
    const updatedVector = { ...vectorValue, [axis]: finalValue };
    onInputChange(portName, updatedVector);
  };
  
  return (
    <BasePort 
      portName={portName} 
      portInfo={portInfo} 
      direction="input"
      isConnected={isConnected}
      className="vector3-port vector3-vertical"
      showHandle={showHandle}
    >
      <div className="vector3-content">
        {/* Port label on its own line */}
        <div className="vector3-label-row">
          <span className="port-label">
            {portInfo?.label || portName.replace(/_/g, " ")}
            {unitSuffix(portInfo) && <span className="port-unit">{unitSuffix(portInfo)}</span>}
          </span>
        </div>
        
        {/* Vector3 inputs stacked vertically */}
        <div className="vector3-inputs">
          {["x", "y", "z"].map((axis) => (
            <div key={axis} className="vector3-row">
              <label>{axis.toUpperCase()}:</label>
              <input
                ref={el => inputRefs.current[axis] = el}
                type="text"
                value={editingAxis === axis ? editingValues[axis] : formatShown(vectorValue[axis] || 0)}
                onFocus={(e) => handleFocus(axis, e)}
                onChange={(e) => handleAxisChange(axis, e.target.value)}
                onBlur={() => handleBlur(axis)}
                onKeyDown={e => handleFieldKeys(e, () => { typedRef.current = false; })}
                disabled={isLocked}
                className={`node-input number-input vector3-input ${isLocked ? 'connected-value' : ''} ${hasValidationError ? 'error' : ''}`}
                title={hasValidationError ? validationState.errorMessage : ''}
              />
            </div>
          ))}
        </div>
      </div>
    </BasePort>
  );
};

export default Vector3InputPort;