/**
 * Foundational ClearButton component - handles clearing selections
 * Reusable across any selection context
 */
import React from 'react';

const ClearButton = ({ 
  onClear, 
  disabled = false,
  title = "Clear selection",
  className = ''
}) => {
  const handleClear = (e) => {
    e.stopPropagation();
    if (!disabled) {
      onClear?.();
    }
  };
  
  return (
    <button
      className={`entity-clear-button nodrag ${className}`}
      onClick={handleClear}
      disabled={disabled}
      title={title}
    >
      <img 
        alt="Clear" 
        className="clear-icon" 
        src="./icons/close-s-ui.svg"
      />
    </button>
  );
};

export default ClearButton;