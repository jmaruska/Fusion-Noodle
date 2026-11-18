/**
 * Declared bounds on number inputs: `minValue`, `maxValue`, and whole numbers for
 * integer ports. The backend checks the same thing with the same words before a
 * node runs (bounds_problem in backend/contracts.py).
 *
 * Values outside the bounds aren't clamped: the field turns red, the node says
 * why, and Generate waits until it's fixed, as Fusion's own dialogs do.
 */
import { unitSuffix } from './units.js';
import { portLabel, portIsShown } from './nodeSpec.js';

const NUMBER_TYPES = new Set(['float', 'integer']);
const number = v => String(Number(v.toPrecision(6)));
const unitText = portInfo => {
  const suffix = unitSuffix(portInfo);
  return suffix ? (suffix === '°' ? '°' : ` ${suffix}`) : '';
};

/** The range to show beside a field, e.g. "1 – 100" or "≥ 0.001 cm", or null. */
export function boundsText(portInfo) {
  const lo = portInfo?.minValue, hi = portInfo?.maxValue;
  const unit = unitText(portInfo);
  if (lo != null && hi != null) return `${number(lo)} – ${number(hi)}${unit}`;
  if (lo != null) return `≥ ${number(lo)}${unit}`;
  if (hi != null) return `≤ ${number(hi)}${unit}`;
  return null;
}

/** What's wrong with `value` (without the port's label), or null. */
export function boundsProblem(value, portInfo) {
  if (!NUMBER_TYPES.has(String(portInfo?.type).toLowerCase())) return null;
  if (value == null || (typeof value === 'object' && !Array.isArray(value))) return null; // Nothing yet, or a modifier
  if (typeof value !== 'number' || Number.isNaN(value)) return 'must be a number';
  if (String(portInfo.type).toLowerCase() === 'integer' && !Number.isInteger(value)) return 'must be a whole number';
  const lo = portInfo.minValue, hi = portInfo.maxValue;
  const unit = unitText(portInfo);
  if (lo != null && hi != null && (value < lo || value > hi)) return `must be between ${number(lo)} and ${number(hi)}${unit}`;
  if (lo != null && value < lo) return `must be at least ${number(lo)}${unit}`;
  if (hi != null && value > hi) return `must be at most ${number(hi)}${unit}`;
  return null;
}

/**
 * Every bounds problem on a node: {fieldErrors: {port: message}, errors: ['Label message']}.
 * Checks typed values and values arriving through a connection; hidden ports are skipped.
 */
export function nodeBoundsProblems(node) {
  const nodeInfo = node?.data?.nodeInfo;
  const current = node?.data?.currentInputs || {};
  const values = { ...current, ...(node?.data?.computedInputs || {}) };
  const ports = nodeInfo?.inputs || {};
  const list = Array.isArray(ports) ? ports : Object.entries(ports).map(([name, p]) => ({ name, ...p }));
  const fieldErrors = {};
  const errors = [];
  list.forEach(port => {
    if (!portIsShown(port, current)) return;
    const value = values[port.name] ?? port.defaultValue;
    const problem = boundsProblem(value, port);
    if (problem) {
      fieldErrors[port.name] = problem;
      errors.push(`${portLabel(port.name, nodeInfo)} ${problem}`);
    }
  });
  return { fieldErrors, errors };
}
