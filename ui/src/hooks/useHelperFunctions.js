import { useCallback } from 'react';
import { styleEdges } from '../utils/ports.js';

/**
 * Hook for utility helper functions used across the application
 */
export function useHelperFunctions() {
  // Colour each connection by the type it carries (see utils/ports.js)
  const fixEdgeColors = useCallback((edgesToFix, nodesToCheck) => styleEdges(edgesToFix, nodesToCheck), []);
  return { fixEdgeColors };
}
