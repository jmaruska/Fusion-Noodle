import { useCallback } from 'react';
import { nodeBoundsProblems } from '../utils/portBounds.js';

/**
 * Palette-side validation: every number input is checked against the bounds its
 * port declares (utils/portBounds.js). A node with a problem disables Generate.
 */
export const useNodeValidation = () => {

  const validateNodeInputs = useCallback((node) => nodeBoundsProblems(node), []);

  const validateAllNodes = useCallback((nodes) => {
    const allErrors = {};
    const allFieldErrors = {};
    let hasErrors = false;

    nodes.forEach(node => {
      const validation = validateNodeInputs(node);
      if (validation.errors.length > 0) {
        allErrors[node.id] = validation.errors;
        allFieldErrors[node.id] = validation.fieldErrors;
        hasErrors = true;
      }
    });

    return { errors: allErrors, fieldErrors: allFieldErrors, hasErrors };
  }, [validateNodeInputs]);

  const getFieldValidationState = useCallback((nodeId, fieldName, validationResult) => {
    const fieldErrors = validationResult?.fieldErrors?.[nodeId];
    const hasError = Boolean(fieldErrors && fieldErrors[fieldName]);
    
    return {
      hasError,
      errorMessage: fieldErrors?.[fieldName],
      isValid: !hasError
    };
  }, []);

  return {
    validateNodeInputs,
    validateAllNodes,
    getFieldValidationState
  };
};
