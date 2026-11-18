"""
Materializer node for converting collection instances into actual Fusion 360 geometry.
Takes virtual collection data and creates real bodies in the design.
"""

import re
import time
from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel
from ..utilities.geometry_naming import generate_geometry_name, extract_node_info_from_name
from ..utilities.transform_utils import apply_complete_transform_to_brep


@enforce_node_spec
class MaterializerNode(BaseNode):
    """Converts virtual collection instances into actual Fusion 360 geometry."""

    NODE_TYPE = "Materializer"
    NODE_CATEGORY = "collection"
    NODE_NAME = "Materializer"
    NODE_DESCRIPTION = "Convert collection instances into real geometry"
    MAX_BODIES = 10000  # Guard against a typo freezing Fusion

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True, description="The instances to build as real bodies in the design.")
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("geometry", PortType.GEOMETRY, description="Geometry")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []

        collection = inputs.get("collection")
        if not collection:
            errors.append("Collection input is required")
            return errors

        if hasattr(collection, 'to_dict'):
            collection = collection.to_dict()

        if not isinstance(collection, dict):
            errors.append("Collection must be a valid collection object")
            return errors

        if "source_geometries" not in collection:
            errors.append("Collection missing source_geometries")

        if "instances" not in collection:
            errors.append("Collection missing instances")

        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Convert collection into actual Fusion 360 geometry."""
        import adsk.core
        import adsk.fusion

        collection = inputs.get("collection")
        if not collection:
            log(context.get('app'), "No collection provided to materializer",
                level=LogLevel.WARNING, module="MATERIALIZER")
            return {"geometry": None}

        if hasattr(collection, 'to_dict'):
            collection = collection.to_dict()

        source_geometries = collection.get("source_geometries", [])
        instances = collection.get("instances", [])

        if len(instances) > self.MAX_BODIES:
            log(context.get('app'),
                f"The collection has {len(instances)} instances; Materializer creates at most "
                f"{self.MAX_BODIES} bodies. Reduce the array counts.",
                level=LogLevel.ERROR, module="MATERIALIZER")
            return {"geometry": None}

        if not source_geometries:
            log(context.get('app'), "Collection missing or empty source_geometries",
                level=LogLevel.WARNING, module="MATERIALIZER")
            return {"geometry": None}

        # Normalize GeometryEnvelope objects to dict
        normalized_sources = []
        for src in source_geometries:
            if hasattr(src, 'geometry'):
                normalized_sources.append({
                    "kind": getattr(src, 'kind', 'unknown'),
                    "id": getattr(src, 'id', 'unknown'),
                    "geometry": src.geometry,
                    "geometry_name": getattr(src, 'geometry_name', 'Unknown'),
                    "metadata": getattr(src, 'metadata', {})
                })
            else:
                normalized_sources.append(src)
        source_geometries = normalized_sources

        node_id = context.get('node_id', 'materializer')
        primary_source = source_geometries[0]

        log(context.get('app'),
            f"Materializing collection: {len(source_geometries)} source(s), {len(instances)} instance(s)",
            level=LogLevel.DEBUG, module="MATERIALIZER")

        if not isinstance(primary_source, dict) or not primary_source.get("geometry"):
            # Selection-based geometry (entity_token) — no BRep copy needed
            if isinstance(primary_source, dict) and primary_source.get("entity_token"):
                log(context.get('app'), "Materialized collection as identity: using source entity token",
                    level=LogLevel.INFO, module="MATERIALIZER")
                return {
                    "geometry": {
                        "kind": primary_source.get("kind", "materialized"),
                        "id": f"materialized_{node_id}",
                        "entity_token": primary_source["entity_token"],
                        "geometry_name": primary_source.get("geometry_name", "Materialized")
                    }
                }
            log(context.get('app'), "No materializable geometry found in collection",
                level=LogLevel.WARNING, module="MATERIALIZER")
            return {"geometry": {"kind": "empty", "id": f"empty_{node_id}", "geometry_name": "Empty"}}

        source_brep_body = primary_source["geometry"]
        source_name = primary_source.get("geometry_name", "Unknown")

        noodle_base_feature = context.get('base_feature') or context.get('noodle_base_feature')
        if not noodle_base_feature:
            log(context.get('app'), "No BaseFeature available for body operations",
                level=LogLevel.ERROR, module="MATERIALIZER")
            return {"geometry": None}

        design = adsk.fusion.Design.cast(context.get('app').activeProduct)
        root_comp = design.rootComponent
        bodies = root_comp.bRepBodies
        temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()

        node_info = extract_node_info_from_name(source_name)
        base_name = node_info['source_name'] if node_info and 'source_name' in node_info else source_name

        short_id_match = re.search(r'_(\d+)$', node_id)
        short_id = short_id_match.group(1) if short_id_match else node_id

        created_bodies = []
        skipped_zero_scale = 0
        failures = 0
        first_failure = None

        log(context.get('app'), f"Starting body creation for {len(instances)} instances (node: {node_id})",
            level=LogLevel.DEBUG, module="MATERIALIZER")

        progress = context.get('progress')
        app = context.get('app')
        node_body_names = context.get('node_body_names')
        name_bodies_by_index = len(instances) > 1
        # Seconds spent in each step, summed over all bodies, for the timing log
        spent = {'copy': 0.0, 'transform': 0.0, 'add': 0.0, 'name': 0.0, 'progress': 0.0}
        clock = time.perf_counter
        loop_started = clock()

        for instance_index, instance in enumerate(instances):
            if progress is not None:
                tp = clock()
                progress.step(instance_index, len(instances))  # Raises if the user cancelled
                spent['progress'] += clock() - tp
            try:
                instance_metadata = instance.get("metadata", {})
                attrs_data = instance.get("transform", {})

                # Normalize attrs_data to dict
                if attrs_data and not isinstance(attrs_data, dict):
                    attrs_data = attrs_data.to_dict() if hasattr(attrs_data, 'to_dict') else {}

                # Skip instances with zero or negative scale — Fusion cannot represent them
                sx = attrs_data.get('sx', 1.0) if attrs_data else 1.0
                sy = attrs_data.get('sy', 1.0) if attrs_data else 1.0
                sz = attrs_data.get('sz', 1.0) if attrs_data else 1.0
                if sx <= 0 or sy <= 0 or sz <= 0:
                    skipped_zero_scale += 1
                    continue

                t0 = clock()
                copied_brep = temp_brep_mgr.copy(source_brep_body)
                t1 = clock()
                if attrs_data:
                    apply_complete_transform_to_brep(temp_brep_mgr, copied_brep, attrs_data)
                t2 = clock()

                # Bodies are always named after this Materializer, never after the
                # array that placed the instance. Eye icons find a node's bodies by
                # that name in a reopened document, and two Materializers fed by
                # one array would otherwise produce duplicate names.
                if name_bodies_by_index:
                    body_name = generate_geometry_name("materializer", node_id, base_name, index=instance_index)
                else:
                    body_name = generate_geometry_name("materializer", node_id, base_name)

                new_body = bodies.add(copied_brep, noodle_base_feature)
                t3 = clock()
                new_body.name = body_name
                # Register body name under this node's ID so the visibility handler
                # can do a fresh, exact lookup regardless of how the name was derived.
                if node_body_names is not None:
                    node_body_names.setdefault(node_id, []).append(body_name)

                # New bodies are visible, so only hidden instances need a call
                if attrs_data and not attrs_data.get("v", True):
                    new_body.isVisible = False
                t4 = clock()
                spent['copy'] += t1 - t0
                spent['transform'] += t2 - t1
                spent['add'] += t3 - t2
                spent['name'] += t4 - t3


                created_bodies.append(new_body)

            except Exception as e:
                failures += 1
                if first_failure is None:
                    first_failure = f"instance {instance_index}: {e}"

        # One line each, not one per instance: an array can hold thousands
        if skipped_zero_scale:
            log(context.get('app'),
                f"Skipped {skipped_zero_scale} of {len(instances)} instances scaled to zero",
                level=LogLevel.INFO, module="MATERIALIZER")
        if failures:
            if not created_bodies:
                # Nothing was built, so say why instead of reporting success
                raise RuntimeError(f"Could not create any bodies ({first_failure})")
            log(context.get('app'),
                f"Could not create {failures} of {len(instances)} bodies. First failure: {first_failure}",
                level=LogLevel.WARNING, module="MATERIALIZER")

        if created_bodies:
            spent['other'] = max(0.0, clock() - loop_started - sum(spent.values()))
            log(app, "Materializer time per step: " + ", ".join(f"{step} {seconds:.2f} s" for step, seconds in spent.items()),
                level=LogLevel.INFO, module="MATERIALIZER")
            first_body = created_bodies[0]
            return {
                "geometry": {
                    "kind": "materialized",
                    "id": f"materialized_{short_id}",
                    "geometry": first_body,
                    "geometry_name": first_body.name,
                    "instance_count": len(created_bodies)
                }
            }

        log(context.get('app'), "No bodies created from collection",
            level=LogLevel.WARNING, module="MATERIALIZER")
        return {"geometry": {"kind": "empty", "id": f"empty_{node_id}", "geometry_name": "Empty"}}
