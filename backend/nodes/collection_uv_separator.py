"""
UV Separator Node — splits a UV-structured collection into U-row and V-column strand collections.

Each output collection has per-instance strand_index and strand_position metadata:
  U output: strand_index = grid_v_index (row),  strand_position = grid_u_index (col)
  V output: strand_index = grid_u_index (col),  strand_position = grid_v_index (row)

This coordinate convention ensures that Weaver's checkerboard formula
  sign = (strand_index + strand_position) % 2
produces a consistent over/under pattern at every crossing, regardless of
how the collection was filtered or effected upstream.
"""

import uuid
from typing import Dict, Any, List

from ..enforcement import enforce_node_spec
from ..contracts import (
    NodeSpec, PortSpec, PortType,
    CollectionSpec, CollectionInstanceSpec, GeometryEnvelope
)
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel


@enforce_node_spec
class UVSeparatorNode(BaseNode):

    NODE_TYPE = "UV_Separator"
    NODE_CATEGORY = "collection"
    NODE_NAME = "UV Separator"
    NODE_DESCRIPTION = "Split a UV-structured collection into U-row and V-column strand collections"
    AUTO_COMPANIONS = False  # Needs an array upstream, not a bare Atomizer

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True,
                         description="Instances from a surface or grid array, to split into rows and columns."),
            ],
            outputs=[
                PortSpec("u_collection", PortType.COLLECTION, label="U Collection",
                         description="U row strands — strand_index=row, strand_position=col"),
                PortSpec("v_collection", PortType.COLLECTION, label="V Collection",
                         description="V column strands — strand_index=col, strand_position=row"),
            ],
            description=cls.NODE_DESCRIPTION
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        collection = inputs.get("collection")
        if not collection:
            errors.append(f"{self.port_label('collection')} input is required")
            return errors

        raw = collection.to_dict() if hasattr(collection, "to_dict") else collection
        instances = raw.get("instances", [])
        if not instances:
            errors.append(f"{self.port_label('collection')} has no instances")
            return errors

        first = instances[0]
        meta = first.get("metadata", {}) if isinstance(first, dict) else (getattr(first, "metadata", None) or {})
        if meta.get("grid_u_index") is None or meta.get("grid_v_index") is None:
            errors.append(
                f"{self.port_label('collection')} instances are missing grid_u_index/grid_v_index — "
                "UV Separator works only with Array 2D Grid or Surface Grid Array output"
            )
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        app = context.get("app")
        node_id = context.get("node_id", "uv_separator")

        collection = inputs.get("collection")
        raw = collection.to_dict() if hasattr(collection, "to_dict") else collection

        instances = raw.get("instances", [])
        collection_metadata = dict(raw.get("metadata", {}) or {})

        # Prefer the live object's source_geometries to avoid dict-vs-object issues
        if hasattr(collection, "source_geometries"):
            source_geometries = collection.source_geometries
        else:
            source_geometries = raw.get("source_geometries", [])

        # CollectionSpec.__post_init__ requires GeometryEnvelope objects, not dicts
        geo_list = []
        for g in source_geometries:
            if isinstance(g, dict):
                geo_list.append(GeometryEnvelope(**g))
            else:
                geo_list.append(g)
        source_geometries = geo_list

        u_instances: List[CollectionInstanceSpec] = []
        v_instances: List[CollectionInstanceSpec] = []
        skipped = 0

        # Strand lengths from array metadata (set by Array nodes as count_u / count_v).
        # Fall back to computing from the actual index range when metadata is absent.
        u_strand_length = int(collection_metadata.get("count_u", 0))
        v_strand_length = int(collection_metadata.get("count_v", 0))
        if not u_strand_length or not v_strand_length:
            all_u = [int(((i.metadata or {}).get("grid_u_index", 0)))
                     for i in [CollectionInstanceSpec.from_dict(x) if isinstance(x, dict) else x
                                for x in instances]]
            all_v = [int(((i.metadata or {}).get("grid_v_index", 0)))
                     for i in [CollectionInstanceSpec.from_dict(x) if isinstance(x, dict) else x
                                for x in instances]]
            if not u_strand_length:
                u_strand_length = (max(all_u) + 1) if all_u else 1
            if not v_strand_length:
                v_strand_length = (max(all_v) + 1) if all_v else 1

        for inst_data in instances:
            inst = (CollectionInstanceSpec.from_dict(inst_data)
                    if isinstance(inst_data, dict) else inst_data)
            meta = inst.metadata or {}

            grid_u = meta.get("grid_u_index")
            grid_v = meta.get("grid_v_index")

            if grid_u is None or grid_v is None:
                skipped += 1
                continue

            grid_u = int(grid_u)
            grid_v = int(grid_v)

            # U strand: which row (grid_v) at which column position (grid_u)
            u_meta = dict(meta)
            u_meta["strand_index"] = grid_v
            u_meta["strand_position"] = grid_u
            u_meta["strand_type"] = "u"
            u_meta["strand_length"] = u_strand_length

            u_instances.append(CollectionInstanceSpec(
                instance_id=inst.instance_id + "_u",
                source_geometry_id=inst.source_geometry_id,
                transform=inst.transform,
                metadata=u_meta,
            ))

            # V strand: which column (grid_u) at which row position (grid_v)
            v_meta = dict(meta)
            v_meta["strand_index"] = grid_u
            v_meta["strand_position"] = grid_v
            v_meta["strand_type"] = "v"
            v_meta["strand_length"] = v_strand_length

            v_instances.append(CollectionInstanceSpec(
                instance_id=inst.instance_id + "_v",
                source_geometry_id=inst.source_geometry_id,
                transform=inst.transform,
                metadata=v_meta,
            ))

        if skipped:
            log(app, f"UV Separator: skipped {skipped} instances without grid indices",
                level=LogLevel.WARNING, module="UV_SEPARATOR")

        log(app, f"UV Separator: {len(u_instances)} U instances across "
                 f"{len(set(i.metadata['strand_index'] for i in u_instances))} strands, "
                 f"{len(v_instances)} V instances across "
                 f"{len(set(i.metadata['strand_index'] for i in v_instances))} strands",
            level=LogLevel.DEBUG, module="UV_SEPARATOR")

        u_collection = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=str(uuid.uuid4())[:8],
            source_geometries=source_geometries,
            instances=u_instances,
            metadata={**collection_metadata, "strand_type": "u", "separator_node_id": node_id},
        )
        v_collection = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=str(uuid.uuid4())[:8],
            source_geometries=source_geometries,
            instances=v_instances,
            metadata={**collection_metadata, "strand_type": "v", "separator_node_id": node_id},
        )

        return {"u_collection": u_collection, "v_collection": v_collection}
