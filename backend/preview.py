"""
Running parts of a graph without generating.

Two things need node results before the user clicks Generate:

  Live values      The palette shows the value arriving at a connected input (a
                   Number feeding a Box's Width). Only pure calculations run:
                   nodes marked PREVIEWABLE, which never touch Fusion.

  The visualizer   Dots in the viewport show how strongly effectors act on each
                   instance. Arrays and effectors run for real, reading faces and
                   curves from the design, but nothing that creates bodies,
                   sketches, or features runs.

Both use the same walk over the graph. They differ only in which nodes may run.
The real node always does the work, so a node's logic exists in one place.
"""

from typing import Any, Callable, Dict, Iterable, List, Optional

from .contracts import PortType

# Output types that mean a node adds something to the design when it runs
_CREATED_TYPES = (PortType.GEOMETRY, PortType.CURVE)


def creates_design_objects(node_class: Any) -> bool:
    """True if running this node adds bodies, sketches, or features to the design.

    Derived from the node's outputs: a node that outputs geometry or curves makes
    them. Arrays, effectors, modifiers, transforms, and math nodes only compute.
    """
    return any(port.port_type in _CREATED_TYPES for port in node_class.get_spec().outputs)


def _placeholder_outputs(node_class: Any, node_id: str) -> Dict[str, Any]:
    """Stand-in outputs for a node that isn't run. Geometry gets an empty envelope,
    which is enough for an Atomizer to start a collection. Curves get nothing, so
    anything that needs the real curve is skipped."""
    outputs = {}
    for port in node_class.get_spec().outputs:
        if port.port_type == PortType.GEOMETRY:
            outputs[port.name] = {'kind': 'preview_placeholder', 'id': f'preview_{node_id}',
                                  'geometry': None, 'geometry_name': 'Preview'}
    return outputs


def evaluate_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]],
                   node_class_for: Callable[[str], Any], may_run: Callable[[Any], bool],
                   context: Optional[Dict[str, Any]] = None,
                   targets: Optional[Iterable[str]] = None,
                   placeholders: bool = False) -> Dict[str, Any]:
    """Run every node that `may_run` allows and whose inputs can be resolved.

    nodes:   [{'id', 'type', 'inputs': {...}, 'known': {...}?}]
             `known` carries outputs the palette already has (a selected point's
             coordinates); such a node is not run.
    edges:   [{'source', 'target', 'sourceHandle': 'output-x', 'targetHandle': 'input-y'}]
    targets: node ids to evaluate (with whatever feeds them). Default: all nodes.
    placeholders: give nodes that may not run stand-in geometry outputs instead of
             treating everything downstream of them as unknown.

    Returns {'outputs': {node_id: {port: value}}, 'errors': {node_id: message},
             'inputs': {node_id: {port: value}}} where 'inputs' are the values each node
             that ran was given, connections resolved (the visualizer draws falloff outlines
             from them).
    """
    context = context or {}
    by_id = {node['id']: node for node in nodes if isinstance(node, dict) and node.get('id')}
    incoming: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        if isinstance(edge, dict) and edge.get('target') in by_id:
            incoming.setdefault(edge['target'], []).append(edge)

    outputs: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}
    given: Dict[str, Dict[str, Any]] = {}
    resolved: Dict[str, Optional[Dict[str, Any]]] = {}

    def evaluate(node_id: str, visiting: frozenset) -> Optional[Dict[str, Any]]:
        if node_id in resolved:
            return resolved[node_id]
        if node_id in visiting or node_id not in by_id:
            return None  # A loop, or an edge from a node that isn't there
        node = by_id[node_id]

        known = node.get('known')
        if isinstance(known, dict):
            resolved[node_id] = known
            outputs[node_id] = known
            return known

        node_class = node_class_for(str(node.get('type', '')))
        if node_class is None:
            resolved[node_id] = None
            return None
        if not may_run(node_class):
            resolved[node_id] = _placeholder_outputs(node_class, node_id) if placeholders else None
            return resolved[node_id]

        inputs = dict(node.get('inputs') or {})
        for edge in incoming.get(node_id, []):
            source_outputs = evaluate(edge.get('source'), visiting | {node_id})
            source_port = str(edge.get('sourceHandle') or '').replace('output-', '', 1)
            target_port = str(edge.get('targetHandle') or '').replace('input-', '', 1)
            if source_outputs is None or source_outputs.get(source_port) is None:
                # This input can't be known without generating
                errors.setdefault(node_id, f"needs the result of a node that only runs on Generate")
                resolved[node_id] = None
                return None
            inputs[target_port] = source_outputs[source_port]

        given[node_id] = inputs
        try:
            connected = {str(edge.get('targetHandle') or '').replace('input-', '', 1)
                         for edge in incoming.get(node_id, [])}
            result = node_class(node_id).execute(inputs, {**context, 'node_id': node_id,
                                                          'connected_inputs': connected})
        except Exception as e:
            errors[node_id] = str(e)
            resolved[node_id] = None
            return None
        result = result if isinstance(result, dict) else {}
        resolved[node_id] = result
        outputs[node_id] = result
        return result

    for node_id in (targets if targets is not None else by_id):
        evaluate(node_id, frozenset())
    return {'outputs': outputs, 'errors': errors, 'inputs': given}


def preview_values(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]],
                   node_class_for: Callable[[str], Any], app: Any = None) -> Dict[str, Any]:
    """Live values: run only the pure calculations (nodes marked PREVIEWABLE)."""
    result = evaluate_graph(nodes, edges, node_class_for,
                            may_run=lambda cls: getattr(cls, 'PREVIEWABLE', False),
                            context={'app': app})
    # A node skipped because its input isn't a plain value is not an error here;
    # the palette just shows that input as connected.
    result['errors'] = {node_id: message for node_id, message in result['errors'].items()
                        if not message.startswith('needs the result')}
    return result


def preview_collections(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], targets: Iterable[str],
                        node_class_for: Callable[[str], Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """The visualizer's pass: run everything feeding `targets` except nodes that
    would add something to the design."""
    return evaluate_graph(nodes, edges, node_class_for,
                          may_run=lambda cls: not creates_design_objects(cls),
                          context={**context, 'preview': True},
                          targets=targets, placeholders=True)
