/**
 * Turns a node spec from the backend into the `nodeInfo` shape nodes render from.
 *
 * Every field the backend sends for a port is passed through, so a new PortSpec
 * field (for example `unit`) reaches the port components without being listed here.
 */
const titleCase = (name) => name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

/**
 * The label a node shows for its input port `name`: the port's own label, or its name in
 * Title Case. Use it whenever a message for the user names a port. The backend's
 * port_label (backend/contracts.py) follows the same rule.
 */
export function portLabel(name, nodeInfo) {
  const inputs = nodeInfo?.inputs;
  const port = Array.isArray(inputs) ? inputs.find(p => p.name === name) : inputs?.[name];
  return port?.label || titleCase(name);
}

export function convertNodeSpecForFrontend(nodeSpec) {
  return {
    type: nodeSpec.type,
    name: nodeSpec.name,
    category: nodeSpec.category,
    menu_category: nodeSpec.menu_category || nodeSpec.category,
    description: nodeSpec.description,
    wide: nodeSpec.wide || false,
    inputs: (nodeSpec.inputs || []).reduce((acc, input) => {
      acc[input.name] = {
        ...input,
        defaultValue: input.defaultValue ?? input.default, // Support both formats
        default: input.defaultValue ?? input.default,      // Legacy compatibility
        label: input.label || titleCase(input.name)
      };
      return acc;
    }, {}),
    outputs: (nodeSpec.outputs || []).reduce((acc, output) => {
      acc[output.name] = {
        ...output,
        label: output.label || titleCase(output.name)
      };
      return acc;
    }, {})
  };
}

/**
 * The current `nodeInfo` for a node type, or null if the type is unknown.
 * A saved graph carries the nodeInfo from when it was saved; loading refreshes it
 * with this so old graphs pick up changed labels, units, and ports.
 */
export function currentNodeInfo(nodeType, nodeMenu) {
  const preloaded = window.noodleNodeData;
  const specs = (nodeMenu && nodeMenu.length)
    ? nodeMenu
    : (Array.isArray(preloaded) ? preloaded : (preloaded && preloaded.nodes) || []);
  const spec = specs.find(n => n.type === nodeType);
  return spec ? convertNodeSpecForFrontend(spec) : null;
}

/**
 * Whether a port shows on the node. A port with `visibleWhen` ({port, values, default}) belongs
 * to some choices of a sibling dropdown, such as a falloff's Shape, and shows only for those.
 * A node saved before the dropdown existed has no value for it, so the default counts.
 */
export function portIsShown(portInfo, currentInputs) {
  const when = portInfo?.visibleWhen;
  if (!when) return true;
  return when.values.includes(currentInputs?.[when.port] ?? when.default);
}
