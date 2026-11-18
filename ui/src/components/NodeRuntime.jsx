import React, { createContext, useContext } from 'react';
import ModularCustomNode from './ModularCustomNode';

/**
 * The node component React Flow renders for every node, and the shared
 * state it needs (input handlers, validation, the fresh-node highlight).
 *
 * React Flow treats a new component as a new node type and remounts every node
 * when the type changes. So the component here is defined once, at module
 * level, and everything that changes reaches it through context. A remount on
 * every edit would drop keyboard focus mid-typing and reset each node's state.
 */
export const NodeRuntimeContext = createContext(null);

export function CustomNode(props) {
  const runtime = useContext(NodeRuntimeContext);
  const {
    freshNodes, fadingNodes, removeFreshHighlight, handleNodeInputChange,
    validationResult, getFieldValidationState, setSelectionLock
  } = runtime;
  const isFresh = freshNodes.has(props.id);
  const isFading = fadingNodes.has(props.id);

  return (
    <div
      className={`custom-node-wrapper ${isFresh ? 'fresh-node' : ''} ${isFading ? 'fading-node' : ''}`}
      onMouseEnter={() => {
        if (isFresh && !isFading) removeFreshHighlight(props.id);
      }}
      onClick={() => {
        if (isFresh && !isFading) removeFreshHighlight(props.id);
      }}
    >
      <ModularCustomNode
        {...props}
        isFresh={isFresh}
        onRemoveFresh={() => removeFreshHighlight(props.id)}
        onInputChange={handleNodeInputChange}
        validationResult={validationResult}
        getFieldValidationState={getFieldValidationState}
        setSelectionLock={setSelectionLock}
      />
    </div>
  );
}

// One object for the life of the app: React Flow must never see a new node type
export const NODE_TYPES = { custom: CustomNode };
