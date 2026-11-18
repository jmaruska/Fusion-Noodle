/**
 * Unit suffixes shown after the label of number inputs.
 *
 * Values are never converted. Lengths are always centimeters (Fusion's internal
 * unit) and angles are always degrees. The suffix only tells the user what the
 * number means. A port declares what it measures with `unit` in its PortSpec.
 */
const UNIT_SUFFIX = {
  length: 'cm',
  angle: '°'
};

export const unitSuffix = (portInfo) => (portInfo && UNIT_SUFFIX[portInfo.unit]) || null;

/**
 * A number as a field shows it when not being edited: at most 4 decimals, no
 * trailing zeros (28.88623261 shows 28.8862). Editing shows the full value, and
 * values are never rounded where they're stored.
 */
export const formatShown = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n) || Number.isInteger(n)) return value;
  return String(Number(n.toFixed(4)));
};
