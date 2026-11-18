/**
 * Smart number formatting utility - removes unnecessary trailing zeros
 */

export const formatSmartNumber = (value) => {
  if (value === null || value === undefined) return '';
  
  if (typeof value !== 'number') {
    const parsed = parseFloat(value);
    if (isNaN(parsed)) return String(value);
    value = parsed;
  }
  
  // Handle integers - no decimal places needed
  if (Number.isInteger(value)) {
    return String(value);
  }
  
  // For decimals, use up to 3 decimal places but remove trailing zeros
  const formatted = value.toFixed(3);
  
  // Remove trailing zeros and unnecessary decimal point
  return formatted.replace(/\.?0+$/, '');
};

export default formatSmartNumber;