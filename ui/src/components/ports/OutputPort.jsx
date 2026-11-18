/**
 * Output port component - handles all output port rendering
 */
import React from 'react';
import BasePort from './BasePort';
import formatSmartNumber from '../../utils/numberFormatter';

const OutputPort = ({ 
  portName, 
  portInfo, 
  isConnected = false,
  computedOutputs = {},
  showComputedValue = true
}) => {
  // Check if this is a geometry-type port
  const isGeometryPort = portInfo?.type && ["GEOMETRY", "geometry", "BREP", "brep", "body", "BODY"].includes(portInfo.type);
  
  // Check if this is a collection-type port
  const isCollectionPort = portInfo?.type && ["COLLECTION", "collection"].includes(portInfo.type);
  
  // Check if this is a transform-type port
  const isTransformPort = portInfo?.type && ["TRANSFORM", "transform"].includes(portInfo.type);
  
  // Check if this is a vector3/position-type port (should show static label)
  const isVector3Port = portInfo?.type && ["VECTOR3", "vector3", "POSITION", "position"].includes(portInfo.type);
  
  // Geometry, collection, transform, and vector3 ports should never show computed values, they always show their type name
  const hasComputedValue = !isGeometryPort && !isCollectionPort && !isTransformPort && !isVector3Port && computedOutputs && computedOutputs[portName] !== undefined;
  const computedValue = computedOutputs[portName];
  
  // Format computed value for display - use smart formatting for numbers
  const formatComputedValue = (value) => {
    // Always display 'Geometry' for geometry output ports
    if (portInfo?.type && ["GEOMETRY", "geometry", "BREP", "brep", "body", "BODY"].includes(portInfo.type)) {
      return "Geometry";
    }
    // Always display 'Collection' for collection output ports
    if (portInfo?.type && ["COLLECTION", "collection"].includes(portInfo.type)) {
      return "Collection";
    }
    // Always display 'Transform' for transform output ports
    if (portInfo?.type && ["TRANSFORM", "transform"].includes(portInfo.type)) {
      return "Transform";
    }
    // Always display port label for vector3/position output ports (no computed values)
    if (portInfo?.type && ["VECTOR3", "vector3", "POSITION", "position"].includes(portInfo.type)) {
      return portInfo?.label || portName.replace(/_/g, " ");
    }
    if (value === null || value === undefined) return '';
    if (typeof value === 'number') {
      return formatSmartNumber(value);
    }
    if (typeof value === 'object') {
      if (value.x !== undefined && value.y !== undefined && value.z !== undefined) {
        return `(${formatSmartNumber(value.x)}, ${formatSmartNumber(value.y)}, ${formatSmartNumber(value.z)})`;
      }
      return '[Object]';
    }
    return String(value);
  };

  // Determine what to display as the port label
  const displayLabel = hasComputedValue && showComputedValue 
    ? formatComputedValue(computedValue)
    : (isGeometryPort
      ? "Geometry"
      : (isCollectionPort 
        ? "Collection"
        : (isTransformPort
          ? "Transform"
          : (isVector3Port
            ? (portInfo?.label || portName.replace(/_/g, " "))
            : (portInfo?.label || portName.replace(/_/g, " "))))));
  
  return (
    <BasePort 
      portName={portName} 
      portInfo={portInfo} 
      direction="output"
      isConnected={isConnected}
    >
      {hasComputedValue && showComputedValue ? (
        // Show computed value aligned with input fields (styled via CSS)
        <span className="port-label computed-output-value">
          {displayLabel}
        </span>
      ) : (
        // Show normal port label
        <span className="port-label">
          {displayLabel}
        </span>
      )}
    </BasePort>
  );
};

export default OutputPort;