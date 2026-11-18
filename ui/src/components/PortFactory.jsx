/**
 * Port factory - automatically creates the appropriate port component based on type
 */
import React from 'react';
import { useEdges } from "@xyflow/react";
import { hexBlockedInput } from "../utils/hexSpacing";
import NumericInputPort from './ports/NumericInputPort';
import Vector3InputPort from './ports/Vector3InputPort';
import SelectionInputPort from './ports/SelectionInputPort';
import EnumInputPort from './ports/EnumInputPort';
import BooleanInputPort from './ports/BooleanInputPort';
import SpacerPort from './ports/SpacerPort';
import OutputPort from './ports/OutputPort';
import BasePort from './ports/BasePort';
import { portIsShown } from '../utils/nodeSpec';

const PortFactory = ({
  portName,
  portInfo,
  direction = 'input',
  currentInputs = {},
  computedInputs = {},
  computedOutputs = {},
  onInputChange,
  nodeId,
  validationState = null,
  isPortVisible = () => true,
  // Pauses flow computation while a Select button is picking
  setSelectionLock,
  // Tab index support
  tabIndexBase = 0,
  portIndex = 0
}) => {
  const edges = useEdges();
  
  // Calculate tab index for this port
  // Only input ports that can actually receive focus should have tab indices
  const isActualInputPort = direction === 'input' && 
    portInfo?.type !== 'spacer' && 
    portInfo?.type !== 'SPACER' &&
    portInfo?.showInputField !== false;
  
  // Use simple tab index: base + port sequence number
  const tabIndex = isActualInputPort ? (tabIndexBase + portIndex) : -1;
  
  // Check if port is connected
  const isConnected = edges.some(edge => {
    if (direction === 'input') {
      return edge.target === nodeId && edge.targetHandle === `input-${portName}`;
    } else {
      return edge.source === nodeId && edge.sourceHandle === `output-${portName}`;
    }
  });
  
  // A hexagonal grid's spacing that the other, connected spacing drives can't take
  // a connection, so its input dot is hidden (utils/hexSpacing.js)
  const connectedHere = new Set(edges.filter(e => e.target === nodeId)
    .map(e => String(e.targetHandle || '').replace('input-', '')));
  const blockedInput = direction === 'input' ? hexBlockedInput(currentInputs, connectedHere) : null;

  // Check if port should be visible
  if (!isPortVisible(portName, direction)) {
    return null;
  }

  // Ports that belong to one choice of a sibling dropdown (e.g. a falloff's Shape) show only for it.
  // A connection into a hidden port is kept, so switching back restores it.
  if (!portIsShown(portInfo, currentInputs)) {
    return null;
  }
  
  // Resolve dynamic label: if portInfo.labelFrom is set, derive label from a sibling port's value.
  // This lets a single port display different labels depending on another port's current setting
  // (e.g. a Count/Spacing port whose label tracks the mode dropdown) without orphaning connections.
  let resolvedPortInfo = portInfo;
  if (portInfo?.labelFrom && currentInputs) {
    const siblingValue = currentInputs[portInfo.labelFrom.port];
    const mappedLabel = portInfo.labelFrom.map?.[siblingValue];
    if (mappedLabel) {
      resolvedPortInfo = { ...portInfo, label: mappedLabel };
    }
  }

  const portType = resolvedPortInfo?.type?.toLowerCase();

  // Handle output ports
  if (direction === 'output') {
    if (portType === 'spacer') {
      return (
        <SpacerPort
          key={portName}
          height={resolvedPortInfo?.height || 12}
        />
      );
    }
    return (
      <OutputPort
        key={portName}
        portName={portName}
        portInfo={resolvedPortInfo}
        isConnected={isConnected}
        computedOutputs={computedOutputs}
      />
    );
  }

  // Handle input ports based on type
  switch (portType) {
    case 'float':
    case 'integer':
      return (
        <NumericInputPort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          currentValue={currentInputs[portName]}
          computedInputs={computedInputs}
          onInputChange={onInputChange}
          isConnected={isConnected}
          validationState={validationState}
          showHandle={resolvedPortInfo?.showInputHandle !== false && portName !== blockedInput}
          tabIndex={tabIndex}
        />
      );

    case 'string':
      return (
        <NumericInputPort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          currentValue={currentInputs[portName]}
          computedInputs={computedInputs}
          onInputChange={onInputChange}
          isConnected={isConnected}
          validationState={validationState}
          inputType="text"
          showHandle={resolvedPortInfo?.showInputHandle !== false && portName !== blockedInput}
          tabIndex={tabIndex}
        />
      );

    case 'vector3':
      return (
        <Vector3InputPort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          currentValue={currentInputs[portName]}
          computedInputs={computedInputs}
          onInputChange={onInputChange}
          isConnected={isConnected}
          validationState={validationState}
          showHandle={resolvedPortInfo?.showInputHandle !== false && portName !== blockedInput}
          tabIndex={tabIndex}
        />
      );

    case 'spacer':
      return (
        <SpacerPort
          key={portName}
          height={resolvedPortInfo?.height || 12}
        />
      );

    case 'boolean':
      return (
        <BooleanInputPort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          currentValue={currentInputs[portName]}
          computedInputs={computedInputs}
          onInputChange={onInputChange}
          isConnected={isConnected}
          validationState={validationState}
          showHandle={resolvedPortInfo?.showInputHandle !== false && portName !== blockedInput}
        />
      );

    case 'enum':
      return (
        <EnumInputPort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          currentValue={currentInputs[portName]}
          computedInputs={computedInputs}
          onInputChange={onInputChange}
          isConnected={isConnected}
          validationState={validationState}
          showHandle={resolvedPortInfo?.showInputHandle !== false && portName !== blockedInput}
        />
      );

    case 'transform':
    case 'geometry':
    case 'collection':
      return (
        <BasePort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          direction={direction}
          isConnected={isConnected}
        >
          <span className="port-label">
            {resolvedPortInfo?.label || portName.replace(/_/g, " ")}
          </span>
        </BasePort>
      );

    case 'body':
    case 'surface':
    case 'point':
    case 'curve':
      return (
        <SelectionInputPort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          currentValue={currentInputs[portName]}
          computedInputs={computedInputs}
          onInputChange={onInputChange}
          nodeId={nodeId}
          isConnected={isConnected}
          validationState={validationState}
          showHandle={resolvedPortInfo?.showInputHandle !== false && portName !== blockedInput}
          setSelectionLock={setSelectionLock}
        />
      );

    default:
      return (
        <BasePort
          key={portName}
          portName={portName}
          portInfo={resolvedPortInfo}
          direction={direction}
          isConnected={isConnected}
        >
          <span className="port-label">
            {resolvedPortInfo?.label || portName.replace(/_/g, " ")}
          </span>
        </BasePort>
      );
  }
};

export default PortFactory;