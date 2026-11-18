import { useState } from 'react';

/**
 * Hook for managing UI state including modals, menus, and node creation
 * Centralizes state for cascading menu, JSON modal, and node positioning
 */
export function useUIState() {
  // State for node menu data (pre-loaded by main.jsx)
  const [nodeMenu, setNodeMenu] = useState([]);
  const [categories, setCategories] = useState([]);

  const [showCascadingMenu, setShowCascadingMenu] = useState(false);
  const [hoveredCategory, setHoveredCategory] = useState(null);
  const [nextNodePosition, setNextNodePosition] = useState({ x: 100, y: 100 });
  const [freshNodes, setFreshNodes] = useState(new Set()); // Track newly created nodes
  const [fadingNodes, setFadingNodes] = useState(new Set()); // Track nodes that are fading out

  return {
    // Node Menu
    nodeMenu,
    setNodeMenu,
    categories,
    setCategories,

    showCascadingMenu,
    setShowCascadingMenu,
    hoveredCategory,
    setHoveredCategory,
    
    // Node Creation
    nextNodePosition,
    setNextNodePosition,
    freshNodes,
    setFreshNodes,
    fadingNodes,
    setFadingNodes
  };
}