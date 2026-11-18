/**
 * Base port component - shared functionality for all port types
 */
import React, { useRef } from 'react';
import { Handle, Position } from "@xyflow/react";
import { showPortTipSoon, hidePortTip, portTipContent } from '../PortTip';

const BasePort = ({ 
  portName, 
  portInfo, 
  direction = 'input', // 'input' or 'output'
  isConnected = false,
  children,
  className = '',
  showHandle = true,
  tip            // Tip content for an input; defaults to the port's description
}) => {
  const rowRef = useRef(null);
  const isInput = direction === 'input';
  const position = isInput ? Position.Left : Position.Right;
  const handleType = isInput ? 'target' : 'source';
  const handleId = `${direction}-${portName}`;
  
  const portTypeClass = `port-type-${portInfo?.type?.toLowerCase() || 'unknown'}`;
  const handleClass = `handle-${portInfo?.type?.toLowerCase() || 'unknown'}`;
  const connectedClass = isConnected ? 'connected' : '';
  
  // Resting on an input shows its tip after a moment (PortTip.jsx)
  const tipContent = isInput ? (tip !== undefined ? tip : portTipContent(portInfo, null, false)) : null;
  const onMouseEnter = tipContent
    ? () => showPortTipSoon({ anchor: rowRef.current, ...tipContent })
    : undefined;
  // A tip shown because a field here has focus stays while it's being typed in
  const onMouseLeave = tipContent
    ? () => { if (!rowRef.current?.contains(document.activeElement)) hidePortTip(rowRef.current); }
    : undefined;

  return (
    <div ref={rowRef} className={`port ${direction}-port ${className}`}
         onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      {isInput && showHandle && (
        <Handle
          type={handleType}
          position={position}
          id={handleId}
          className={`${portTypeClass} ${handleClass} ${connectedClass}`}
        />
      )}
      
      {children}
      
      {!isInput && (
        <Handle
          type={handleType}
          position={position}
          id={handleId}
          className={`${portTypeClass} ${handleClass} ${connectedClass}`}
        />
      )}
    </div>
  );
};

export default BasePort;