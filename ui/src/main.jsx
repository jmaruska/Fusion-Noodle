import React from 'react';
import ReactDOM from 'react-dom/client';
import NoodleApp from './NoodleApp';
import './bridge/backendEvents.js'; // Installs the handler for messages pushed from the add-in

// Import CSS files in order
import '@xyflow/react/dist/style.css'; // React Flow base styles first
import '../styles/reset.css';
import '../styles/theme.css';
import '../styles/ui.css';
import '../styles/flow.css';
import '../styles/falloff-editor.css';
import '../styles/dialog.css';
import '../styles/base-node.css';
import '../styles/handles.css';
import '../styles/edges.css';

// Node-specific styling
import '../styles/nodes/math-node.css';
import '../styles/nodes/geometry-node.css';
import '../styles/nodes/transform-node.css';
import '../styles/nodes/collection-node.css';
import '../styles/nodes/array-node.css';
import '../styles/nodes/effector-node.css';
import '../styles/nodes/sources-node.css';
import '../styles/nodes/curves-node.css';
import '../styles/nodes/modifiers-node.css';
import '../styles/nodes/general-node.css';

function showLoadingScreen(message, subMessage = '') {
  const root = document.getElementById('root');
  root.innerHTML = `
    <div class="loading-screen">
      <div class="loading-content">
        <h2>Noodle Node Editor</h2>
        <div class="loading-spinner"></div>
        <div class="loading-status-container">
          <div class="loading-status-main">${message}</div>
          <div class="loading-status-sub">${subMessage}</div>
        </div>
      </div>
    </div>
  `;
}

function updateLoadingMessage(message, subMessage = '') {
  const mainElement = document.querySelector('.loading-status-main');
  const subElement = document.querySelector('.loading-status-sub');
  if (mainElement) mainElement.textContent = message;
  if (subElement) subElement.textContent = subMessage;
}

function fusionApiReady() {
  return typeof window.adsk !== 'undefined' && typeof window.adsk.fusionSendData === 'function';
}

async function initializeApp() {
  try {
    // returnData now returns a Promise
    const response = await window.returnData(JSON.stringify({ action: 'palette_ready' }));
    
    const data = JSON.parse(response);
    
    if (data.success && data.data) {
      // Store node data globally for NoodleApp to use
      window.noodleNodeData = data.data;
      
      // Store ReactFlow state if provided by backend
      if (data.reactFlowState && data.reactFlowState.nodes && data.reactFlowState.nodes.length > 0) {
        window.noodleReactFlowState = data.reactFlowState;
        window.noodleWorkingCopy = Boolean(data.workingCopy);
        window.noodleLoadNotes = data.notes || [];
      } else {
        window.noodleReactFlowState = null;
      }
      
      // Now render the app
      const root = ReactDOM.createRoot(document.getElementById('root'));
      root.render(
        <React.StrictMode>
          <NoodleApp />
        </React.StrictMode>
      );
    } else {
      console.error('[Frontend] Failed to get node registry:', data);
      throw new Error(data.error || 'Failed to get node registry');
    }
  } catch (error) {
    console.error('[Frontend] Failed to initialize:', error);
    // Render with error state
    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(
      <React.StrictMode>
        <div className="error-container" style={{padding: '20px', color: '#ff0000'}}>
          <h2>Failed to connect to backend</h2>
          <p>{error.message}</p>
          <p style={{fontSize: '12px', color: '#999'}}>
            Make sure the Fusion 360 add-in is running and try reloading the palette.
          </p>
        </div>
      </React.StrictMode>
    );
  }
}

// Start initialization when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp);
} else {
  // Wait a bit for the Fusion API to be injected
  setTimeout(initializeApp, 100);
}
