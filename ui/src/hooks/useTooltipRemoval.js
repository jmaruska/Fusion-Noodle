import { useEffect } from 'react';
import { unifiedPollingManager } from '../modules/UnifiedPollingManager';

/**
 * Hook for aggressively removing all tooltips from the DOM
 * Handles title attributes and tooltip-like elements that cause UI interference
 */
export function useTooltipRemoval() {
  // Aggressively remove all tooltips
  useEffect(() => {
    const removeTooltips = () => {
      // Remove title attributes from all elements
      document.querySelectorAll('[title]').forEach(el => {
        if (el.title) {
          el.removeAttribute('title');
        }
      });
      
      // Remove any tooltip-like elements
      document.querySelectorAll('[role="tooltip"], .tooltip, [data-tooltip-id]').forEach(el => {
        el.style.display = 'none';
        el.style.visibility = 'hidden';
        el.style.opacity = '0';
      });
    };

    // Run immediately
    removeTooltips();
    
    // Setup unified polling for periodic tooltip cleanup
    unifiedPollingManager.setFeatureHandler('tooltipCleanup', removeTooltips);
    unifiedPollingManager.enableFeature('tooltipCleanup');
    
    // Also run on mouse events to catch phantom tooltips
    const handleMouseMove = () => removeTooltips();
    document.addEventListener('mousemove', handleMouseMove);
    
    return () => {
      // Note: Don't disable tooltipCleanup here as other components may need it
      document.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  // This hook doesn't return anything - it's just a side effect
  return {};
}