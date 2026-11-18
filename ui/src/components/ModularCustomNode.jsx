/**
 * New modular CustomNode - uses composition instead of monolithic approach
 */
import React, { useEffect, useMemo } from 'react';
import { useEdges, useUpdateNodeInternals } from '@xyflow/react';
import { portIsShown } from '../utils/nodeSpec';
import { hexBlockedInput } from '../utils/hexSpacing';
import BaseNode from './BaseNode';
import PortFactory from './PortFactory';
import FalloffCurveEditor from './FalloffCurveEditor';

const ModularCustomNode = ({ 
  data, 
  id, 
  onInputChange, 
  validationResult, 
  getFieldValidationState,
  // Pauses flow computation while a Select button is picking
  setSelectionLock
}) => {
  const {
    nodeInfo,
    currentInputs = {},
    computedInputs = {},
    computedOutputs = {},
    isPortVisible = () => true,
  } = data || {};

  // Convert inputs array to object if needed (legacy support)
  // React Flow measures a node's connection dots when it first renders. When ports
  // appear or vanish (a falloff's Shape, a hexagonal grid's driven spacing), it must
  // measure again, or connections into the node can't be drawn until a reload.
  const updateNodeInternals = useUpdateNodeInternals();
  const edges = useEdges();
  const connectedHere = edges.filter(e => e.target === id).map(e => String(e.targetHandle || '').replace('input-', ''));
  const blockedInput = hexBlockedInput(currentInputs, new Set(connectedHere));
  const handleLayout = Object.values(nodeInfo?.inputs || {})
    .filter(port => portIsShown(port, currentInputs) && port.showInputHandle !== false && port.name !== blockedInput)
    .map(port => port.name).join(',');
  useEffect(() => { updateNodeInternals(id); }, [id, handleLayout, updateNodeInternals]);

  const inputs = useMemo(() => {
    if (!nodeInfo?.inputs) return {};
    
    if (!Array.isArray(nodeInfo.inputs)) {
      return nodeInfo.inputs;
    }
    
    const inputsObj = {};
    nodeInfo.inputs.forEach(input => {
      inputsObj[input.name] = {
        type: input.type,
        label: input.label || input.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
        ...input
      };
    });
    return inputsObj;
  }, [nodeInfo?.inputs]);

  // Convert outputs array to object if needed (legacy support)  
  const outputs = useMemo(() => {
    if (!nodeInfo?.outputs) return {};
    
    if (!Array.isArray(nodeInfo.outputs)) {
      return nodeInfo.outputs;
    }
    
    const outputsObj = {};
    nodeInfo.outputs.forEach(output => {
      outputsObj[output.name] = {
        type: output.type,
        label: output.label || output.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
        ...output
      };
    });
    return outputsObj;
  }, [nodeInfo?.outputs]);

  // Wrapper for onInputChange to ensure proper parameters
  const handleInputChange = (portName, value) => {
    if (onInputChange) {
      onInputChange(id, portName, value);
    } else {
      console.error(`❌ [MODULAR NODE] onInputChange is missing for ${id}!`);
    }
  };

  // Determine if visibility toggle should be shown
  const nodeCategory = data?.nodeCategory || '';
  const hasGeometryOutput = Object.values(outputs).some(o => {
    const t = (o?.type || '').toString().toLowerCase();
    return ['geometry', 'brep', 'body'].includes(t);
  });
  // Transform nodes pass geometry through but don't create it — no toggle
  const showVisibilityToggle = (hasGeometryOutput || nodeCategory === 'geometry') && nodeCategory !== 'transform';

  // Identify node type for special rendering
  const nodeType = nodeInfo?.nodeType || data?.nodeType;
  
  // Falloff and Gradient nodes: the `curve` input has no field of its own; the curve editor
  // stands in its place. Falloffs measure distance from a point; a Gradient runs along each strand.
  const renderCurveInputs = (source) => Object.entries(inputs).map(([portName, portInfo]) => (
    portName === 'curve' ? (
      <FalloffCurveEditor
        key="curve-editor"
        nodeId={id}
        nodeLabel={data?.label}
        source={source}
        currentInputs={currentInputs}
        computedInputs={computedInputs}
        onInputChange={handleInputChange}
      />
    ) : (
      <PortFactory
        key={`input-${portName}`}
        portName={portName}
        portInfo={portInfo}
        direction="input"
        currentInputs={currentInputs}
        computedInputs={computedInputs}
        onInputChange={handleInputChange}
        nodeId={id}
        validationState={getFieldValidationState ? getFieldValidationState(id, portName, validationResult) : null}
        isPortVisible={isPortVisible}
        setSelectionLock={setSelectionLock}
      />
    )
  ));

  return (
    <BaseNode id={id} data={data} showVisibilityToggle={showVisibilityToggle}>
      {/* Render Input Ports; falloff and gradient nodes put the curve editor in line */}
      {(nodeType === 'Falloff_Effector' || nodeType === 'Modifier_Falloff') ? (
        renderCurveInputs(['linear', 'box'].includes(currentInputs.shape) ? currentInputs.shape : 'sphere')
      ) : nodeType === 'Modifier_Gradient' ? (
        renderCurveInputs('along')
      ) : (
        Object.entries(inputs).map(([portName, portInfo]) => (
          <PortFactory
            key={`input-${portName}`}
            portName={portName}
            portInfo={portInfo}
            direction="input"
            currentInputs={currentInputs}
            computedInputs={computedInputs}
            onInputChange={handleInputChange}
            nodeId={id}
            validationState={getFieldValidationState ? getFieldValidationState(id, portName, validationResult) : null}
            isPortVisible={isPortVisible}
            setSelectionLock={setSelectionLock}
          />
        ))
      )}

      {/* Render Output Ports */}
      {Object.entries(outputs).map(([portName, portInfo]) => (
        <PortFactory
          key={`output-${portName}`}
          portName={portName}
          portInfo={portInfo}
          direction="output"
          computedOutputs={computedOutputs}
          nodeId={id}
          isPortVisible={isPortVisible}
        />
      ))}
    </BaseNode>
  );
};

export default ModularCustomNode;