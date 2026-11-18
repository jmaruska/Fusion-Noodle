"""
The saved-graph format: version stamp and migrations.

A graph is saved in two places: on the Noodle Base Feature inside a Fusion
document, and in .noodle files. Both carry a stamp:

    "noodle": {"format": 1, "version": "0.1.0"}

`format` is the number that matters. It goes up by one whenever a change to the
nodes would stop an older graph from loading correctly. Each such change adds
one entry to MIGRATIONS, and every older graph is brought up to date when it
loads. `version` is the add-in version that wrote the graph, kept for
diagnosis only.

ADDING A MIGRATION
------------------
When you rename a node type, rename a port, or rename a dropdown option:

  1. Add 1 to GRAPH_FORMAT.
  2. Append one entry to MIGRATIONS with "to" set to the new GRAPH_FORMAT.

An entry may contain any of these:

    {
        "to": 2,
        "note": "Box was renamed",                         # shown to the user
        "rename_node_types": {"cube_generator": "box"},
        "rename_inputs":  {"box": {"depth": "length"}},     # keyed by the NEW node type
        "rename_outputs": {"box": {"geometry": "body"}},
        "rename_options": {"box": {"mode": {"old": "new"}}},
        "flag_inputs":    {"box": ["size"]},                # see below
        "convert_inputs": {"box": convert_box},             # see below
        "removed_inputs": {"box": ["depth"]},               # see below
    }

`flag_inputs` changes nothing. Use it when an input keeps its name but its
meaning changes, so the value can't be converted. The step's note is shown
only if some graph sets one of those inputs to something other than 0.

`convert_inputs` maps a node type to a function that rewrites that node's saved
inputs in place, for changes a rename can't express. It returns True when the
result is only an approximation, and only then is the step's note shown.
`removed_inputs` lists ports that no longer exist: their computed values are
cleared and connections into them are dropped, with the note shown.

Within one entry, node types are renamed first, so port and option renames are
keyed by the node type's new name.

Changes that need no migration: adding a port (it takes its default), removing
a port (its saved value is ignored), and changing labels or descriptions.
"""

import copy
import json
from typing import Any, Dict, List, Tuple

GRAPH_FORMAT = 8


_OLD_FALLOFF_PORTS = ('range_start', 'range_end', 'repeat_count', 'fade_repeats', 'edge_smooth')


def _convert_falloff(inputs: Dict[str, Any]) -> bool:
    """Falloff Effector and Falloff modifier, format 2 to 3: the range, repeat, fade and edge
    smoothing inputs became one falloff curve. A plain falloff converts exactly (the Linear
    curve is the old straight fade); repeats and edge smoothing can only be approximated."""
    from .utilities.field_curve import preset_curve

    def number(key, default):
        v = inputs.get(key, default)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default

    start, end = number('range_start', 100.0), number('range_end', 0.0)
    repeats = int(number('repeat_count', 0))
    fade = inputs.get('fade_repeats') is True
    edge_smooth = number('edge_smooth', 0.0)
    if repeats > 0:
        curve = preset_curve('Ripple')
        curve['repeat'] = min(12, repeats + 1)
        curve['decay'] = 1.0 if fade else 0.0
    else:
        curve = preset_curve('Linear')
    curve['output'] = {'start': start / 100.0, 'end': end / 100.0}
    approximate = repeats > 0 or edge_smooth > 0
    for key in _OLD_FALLOFF_PORTS:
        inputs.pop(key, None)
    inputs['curve'] = json.dumps(curve, separators=(',', ':'))
    return approximate


_OLD_GRADIENT_PORTS = ('stops', 'interpolation', 'clamp')


def _convert_gradient(inputs: Dict[str, Any]) -> bool:
    """Gradient modifier, format 3 to 4: the stops became a falloff curve, fitted to the old
    gradient's values. A straight ramp converts exactly; steps and sharp corners can't be
    matched by a smooth curve, so anything more than 1% off is flagged."""
    from .utilities.field_curve import fit_curve
    from .utilities.legacy_gradient import evaluate

    stops = inputs.get('stops')
    clamp = inputs.get('clamp') is True
    curve, error = fit_curve(lambda t: evaluate(stops, t, clamp))
    span = max(1e-9, abs(curve['output']['start'] - curve['output']['end']))
    for key in _OLD_GRADIENT_PORTS:
        inputs.pop(key, None)
    inputs['curve'] = json.dumps(curve, separators=(',', ':'))
    return error / span > 0.01

def _convert_polygon(inputs: Dict[str, Any]) -> bool:
    """Polygon, format 4 to 5: Height was the distance to each side of the plane; it is now the
    total thickness, as on Box. A stored height is doubled, so the shape doesn't change. An unset
    height took the old default of 1, which the new default of 2 matches. Exact, so no note."""
    height = inputs.get('height')
    if isinstance(height, (int, float)) and not isinstance(height, bool):
        inputs['height'] = height * 2
    return False


def _convert_polygon_radius(inputs: Dict[str, Any]) -> bool:
    """Polygon, format 6 to 7: Radius was measured to the corners; it is now measured to the
    middle of each side, so a hexagon is 2 × Radius across its flats. The radius is scaled by
    cos(180°/sides) so the shape doesn't change. An unset radius took the old default of 1 to
    the corners and is written out the same way. Exact, so no note."""
    import math
    sides = inputs.get('sides', 6)
    sides = int(sides) if isinstance(sides, (int, float)) and not isinstance(sides, bool) and sides >= 3 else 6
    radius = inputs.get('radius', 1.0)
    if isinstance(radius, (int, float)) and not isinstance(radius, bool):
        inputs['radius'] = radius * math.cos(math.pi / sides)
    return False


def _convert_polygon_size(inputs: Dict[str, Any]) -> bool:
    """Polygon, format 7 to 8: Radius (to the middle of a side) became Size, measured across
    the flats, so it doubles. Measured defaults to across flats. Exact, so no note."""
    size = inputs.get('size')
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        inputs['size'] = size * 2
    return False


MIGRATIONS: List[Dict[str, Any]] = [
    {
        "to": 2,
        "note": ("Edge Margin on Surface Grid and Surface Hex is now a distance in cm, "
                 "not a percentage or fraction of the surface. Check it before you Generate."),
        "flag_inputs": {"Array_Surface_Grid": ["edge_margin"], "Array_Surface_Hex": ["edge_margin"]},
    },
    {
        "to": 3,
        "note": ("Falloff nodes now use the falloff curve editor. Falloffs with repeats or edge "
                 "smoothing were converted to the nearest curve; open the curve editor to check them."),
        "convert_inputs": {"Falloff_Effector": _convert_falloff, "Modifier_Falloff": _convert_falloff},
        "removed_inputs": {"Falloff_Effector": list(_OLD_FALLOFF_PORTS), "Modifier_Falloff": list(_OLD_FALLOFF_PORTS)},
    },
    {
        "to": 4,
        "note": ("The Gradient node now uses the falloff curve editor. Gradients with steps or sharp "
                 "corners were converted to the nearest smooth curve; open the curve editor to check them."),
        "convert_inputs": {"Modifier_Gradient": _convert_gradient},
        "removed_inputs": {"Modifier_Gradient": list(_OLD_GRADIENT_PORTS)},
    },
    {
        "to": 5,
        "note": "Polygon Height is now the total thickness, like Box. Saved heights were doubled to match.",
        "convert_inputs": {"polygon_generator": _convert_polygon},
    },
    {
        "to": 6,
        "note": ("Surface Grid's Stagger Offset now shifts odd rows by that fraction of a column. "
                 "It used to shift by half a column for any value other than 0; check it before you Generate."),
        "flag_inputs": {"Array_Surface_Grid": ["stagger_offset"]},
    },
    {
        "to": 7,
        "note": "Polygon Radius is now measured to the middle of each side. Saved radii were converted, so shapes are unchanged.",
        "convert_inputs": {"polygon_generator": _convert_polygon_radius},
    },
    {
        "to": 8,
        "note": "Polygon Radius is now Size, measured across the flats by default, with a Measured choice. Saved values were converted, so shapes are unchanged.",
        "rename_inputs": {"polygon_generator": {"radius": "size"}},
        "convert_inputs": {"polygon_generator": _convert_polygon_size},
    },
]

STAMP_KEY = 'noodle'


class GraphFormatError(Exception):
    """The data is not a Noodle graph, or it was written by a newer Noodle."""


def stamp(state: Dict[str, Any], addin_version: str = 'unknown') -> Dict[str, Any]:
    """Mark `state` as written in the current format. Returns the same dict."""
    state[STAMP_KEY] = {'format': GRAPH_FORMAT, 'version': addin_version}
    return state


def format_of(state: Dict[str, Any]) -> int:
    """The format a graph was written in. Graphs from before stamping count as 1."""
    info = state.get(STAMP_KEY)
    if isinstance(info, dict) and isinstance(info.get('format'), int):
        return info['format']
    return 1


def check_is_graph(state: Any) -> None:
    """Raise GraphFormatError unless `state` looks like a saved graph."""
    if not isinstance(state, dict):
        raise GraphFormatError('This is not a Noodle graph.')
    nodes = state.get('nodes')
    if not isinstance(nodes, list):
        raise GraphFormatError('This is not a Noodle graph: it has no node list.')
    for node in nodes:
        data = node.get('data') if isinstance(node, dict) else None
        if not isinstance(data, dict) or not node.get('id') or not data.get('nodeType'):
            raise GraphFormatError('This is not a Noodle graph: a node has no id or type.')
    if not isinstance(state.get('edges', []), list):
        raise GraphFormatError('This is not a Noodle graph: edges must be a list.')


def migrate(state: Dict[str, Any], migrations: List[Dict[str, Any]] = None,
            current_format: int = None) -> Tuple[Dict[str, Any], List[str]]:
    """Bring a saved graph up to the current format.

    Returns (migrated copy, notes for the user). The input is not modified.
    Raises GraphFormatError if the graph is not a graph or is from a newer Noodle.
    """
    migrations = MIGRATIONS if migrations is None else migrations
    current_format = GRAPH_FORMAT if current_format is None else current_format

    check_is_graph(state)
    saved_format = format_of(state)
    if saved_format > current_format:
        raise GraphFormatError(
            f'This graph was saved by a newer version of Noodle (format {saved_format}; '
            f'this version reads up to format {current_format}). Update Noodle to open it.')

    result = copy.deepcopy(state)
    notes: List[str] = []
    for step in sorted(migrations, key=lambda s: s['to']):
        if saved_format < step['to'] <= current_format:
            if _apply_step(result, step) and step.get('note'):
                notes.append(step['note'])

    info = result.get(STAMP_KEY) if isinstance(result.get(STAMP_KEY), dict) else {}
    result[STAMP_KEY] = {**info, 'format': current_format}
    return result, notes


def _apply_step(state: Dict[str, Any], step: Dict[str, Any]) -> bool:
    """Apply one migration entry in place. Returns True if it changed anything."""
    changed = False
    type_renames = step.get('rename_node_types', {})
    input_renames = step.get('rename_inputs', {})
    output_renames = step.get('rename_outputs', {})
    option_renames = step.get('rename_options', {})
    flagged_inputs = step.get('flag_inputs', {})
    converters = step.get('convert_inputs', {})
    removed_inputs = step.get('removed_inputs', {})

    node_types: Dict[str, str] = {}
    for node in state.get('nodes', []):
        data = node['data']
        node_type = data['nodeType']
        if node_type in type_renames:
            node_type = data['nodeType'] = type_renames[node_type]
            changed = True
        node_types[node['id']] = node_type

        for old, new in input_renames.get(node_type, {}).items():
            for bucket in ('currentInputs', 'computedInputs'):
                values = data.get(bucket)
                if isinstance(values, dict) and old in values:
                    values[new] = values.pop(old)
                    changed = True

        for port in flagged_inputs.get(node_type, []):
            value = (data.get('currentInputs') or {}).get(port)
            if isinstance(value, (int, float)) and value != 0:
                changed = True  # Nothing to convert; the note tells the user to check it

        if node_type in converters:
            values = data.setdefault('currentInputs', {})
            if not isinstance(values, dict):
                values = data['currentInputs'] = {}
            if converters[node_type](values):
                changed = True  # Approximated; the note tells the user to check it
            computed = data.get('computedInputs')
            if isinstance(computed, dict):
                for port in removed_inputs.get(node_type, []):
                    computed.pop(port, None)

        for port, mapping in option_renames.get(node_type, {}).items():
            for bucket in ('currentInputs', 'computedInputs'):
                values = data.get(bucket)
                if isinstance(values, dict) and values.get(port) in mapping:
                    values[port] = mapping[values[port]]
                    changed = True

    dropped = {node_id for node_id, t in node_types.items() if t in removed_inputs}
    if dropped:
        kept = []
        for edge in state.get('edges', []):
            handle = edge.get('targetHandle')
            port = handle[len('input-'):] if isinstance(handle, str) and handle.startswith('input-') else None
            if edge.get('target') in dropped and port in removed_inputs[node_types[edge['target']]]:
                changed = True  # A connection into a removed input can't be kept
                continue
            kept.append(edge)
        state['edges'] = kept

    for edge in state.get('edges', []):
        changed |= _rename_handle(edge, 'targetHandle', 'input-', input_renames.get(node_types.get(edge.get('target')), {}))
        changed |= _rename_handle(edge, 'sourceHandle', 'output-', output_renames.get(node_types.get(edge.get('source')), {}))
    return changed


def _rename_handle(edge: Dict[str, Any], key: str, prefix: str, renames: Dict[str, str]) -> bool:
    handle = edge.get(key)
    if not isinstance(handle, str) or not handle.startswith(prefix):
        return False
    port = handle[len(prefix):]
    if port not in renames:
        return False
    edge[key] = prefix + renames[port]
    return True
