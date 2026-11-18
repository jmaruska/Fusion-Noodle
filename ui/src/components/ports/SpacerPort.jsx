/**
 * Spacer Port - renders empty space for visual separation in node layouts
 */
import React from 'react';

const SpacerPort = ({ 
  height = 12 // Default spacer height in pixels
}) => {
  return (
    <div 
      className="spacer-port" 
      style={{ '--spacer-height': `${height}px` }}
    />
  );
};

export default SpacerPort;