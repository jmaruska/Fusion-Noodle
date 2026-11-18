/**
 * A hexagonal 2D grid has one spacing, seen two ways: Spacing X is the distance
 * between neighbours in a row (across a cell's flats), and rows are √3/2 of that
 * apart. Typed values are kept in step here (linkHexSpacing). When one is fed by a
 * connection it drives, and the other shows the linked value as if connected too
 * (hexLinkedInputs). The backend follows the same rule (hex_column_spacing in
 * array_2d_grid.py).
 *
 * Values are rounded to 0.0001 cm (a micron, Fusion's own precision) so a linked
 * value reads cleanly and editing back and forth doesn't creep.
 */
const ROW = Math.sqrt(3) / 2;
const DEFAULT_SPACING = 5;
const round = v => Math.round(v * 1e4) / 1e4;

/** The inputs to change after `changedPort` was edited, given the node's new inputs. */
export function linkHexSpacing(inputs, changedPort) {
  if (String(inputs.array_type || '').toLowerCase() !== 'hexagonal') return {};
  const x = Number(inputs.spacing_x ?? DEFAULT_SPACING);
  const y = Number(inputs.spacing_y ?? DEFAULT_SPACING);
  if (changedPort === 'spacing_y' && Number.isFinite(y)) return { spacing_x: round(y / ROW) };
  if ((changedPort === 'spacing_x' || changedPort === 'array_type') && Number.isFinite(x)) return { spacing_y: round(x * ROW) };
  return {};
}

/**
 * Values to show as connected on a hexagonal 2D grid: when Spacing X or Spacing Y
 * is fed by a connection (X wins if both are), the other is the linked value.
 * `inputs` are the node's typed values, `computed` the values arriving through
 * connections, `connected` the names of connected inputs. Returns entries to add
 * to the node's computed inputs; empty when nothing is linked or the driving value
 * isn't known before Generate.
 */
export function hexLinkedInputs(inputs, computed, connected) {
  if (String(inputs?.array_type || '').toLowerCase() !== 'hexagonal') return {};
  if (connected.has('spacing_x')) {
    const x = Number(computed?.spacing_x);
    return Number.isFinite(x) ? { spacing_y: round(x * ROW) } : {};
  }
  if (connected.has('spacing_y')) {
    const y = Number(computed?.spacing_y);
    return Number.isFinite(y) ? { spacing_x: round(y / ROW) } : {};
  }
  return {};
}

/**
 * The spacing input that can't take a connection right now: on a hexagonal grid,
 * once one spacing is connected the other is driven by it, so its input dot is
 * hidden and a connection dropped on it is refused. Null when either may connect,
 * including a graph that already has both connected (both stay visible to remove one).
 */
export function hexBlockedInput(inputs, connected) {
  if (String(inputs?.array_type || '').toLowerCase() !== 'hexagonal') return null;
  const x = connected.has('spacing_x');
  const y = connected.has('spacing_y');
  if (x && !y) return 'spacing_y';
  if (y && !x) return 'spacing_x';
  return null;
}
