"""
Companion nodes: the helpers a node needs around it to do anything.

An array or an effector works on a collection. It needs an Atomizer before it
(to turn geometry into a collection) and a Materializer after it (to turn the
result back into bodies). When the user adds such a node and the graph has no
Atomizer or Materializer yet, the palette adds and connects them.

The rule is derived from a node's ports, so a new array or effector gets it
without any extra work:

  - a node with a collection input gets an Atomizer before it
  - a node that also has a collection output gets a Materializer after it

A node can opt out with AUTO_COMPANIONS = False. Nodes that need an array
upstream, not a bare Atomizer, do this (UV Separator, Interpolize).
"""

from typing import Any, Dict, List, Optional

from ..contracts import PortType

ATOMIZER_TYPE = 'Atomizer'
MATERIALIZER_TYPE = 'Materializer'


def _first_port(ports, port_type: PortType) -> Optional[str]:
    for port in ports:
        if port.port_type == port_type:
            return port.name
    return None


def companions_for(node_class: Any, node_class_for) -> List[Dict[str, str]]:
    """The companions the palette should add with a new node of this class.

    Each entry: {'type', 'side': 'before' | 'after', 'sourcePort', 'targetPort'}.
    For 'before', the companion's sourcePort feeds the new node's targetPort.
    For 'after', the new node's sourcePort feeds the companion's targetPort.
    """
    if not getattr(node_class, 'AUTO_COMPANIONS', True):
        return []
    if node_class.NODE_TYPE in (ATOMIZER_TYPE, MATERIALIZER_TYPE):
        return []

    spec = node_class.get_spec()
    collection_in = _first_port(spec.inputs, PortType.COLLECTION)
    collection_out = _first_port(spec.outputs, PortType.COLLECTION)
    if not collection_in:
        return []

    companions = []
    atomizer = node_class_for(ATOMIZER_TYPE)
    if atomizer:
        source = _first_port(atomizer.get_spec().outputs, PortType.COLLECTION)
        if source:
            companions.append({'type': ATOMIZER_TYPE, 'side': 'before',
                               'sourcePort': source, 'targetPort': collection_in})

    materializer = node_class_for(MATERIALIZER_TYPE)
    if collection_out and materializer:
        target = _first_port(materializer.get_spec().inputs, PortType.COLLECTION)
        if target:
            companions.append({'type': MATERIALIZER_TYPE, 'side': 'after',
                               'sourcePort': collection_out, 'targetPort': target})
    return companions
