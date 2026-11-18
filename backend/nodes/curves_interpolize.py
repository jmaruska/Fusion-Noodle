"""
Interpolize Node — type converter: collection → curves.

Takes a UV-structured collection of positioned instances and produces
SketchFittedSplines through their world-space positions.  Source geometry
is ignored entirely — only instance transforms are used.

UV reconstruction
-----------------
Reads count_u / count_v from collection metadata (written by all array nodes).
Assumes row-major flat ordering: col = index % count_u, row = index // count_u.
This matches the iteration order used by every array node in the system.

If len(instances) != count_u * count_v the grid is non-rectangular; falls back
to a single spline through all points in flat order with a warning.

Sketch lifecycle
----------------
The sketch is added to the Noodle BaseFeature with
root_comp.sketches.addToBaseOrFormFeature(), so it is cleared with the
BaseFeature on every Generate. PipeNode captures the spline references before it
temporarily calls BaseFeature.finishEdit() to run pipeFeatures.add().
All U and V splines for this node live in a single sketch.
"""

from typing import Dict, Any, List

from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel

try:
    import adsk.core
    import adsk.fusion
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


@enforce_node_spec
class InterpolizeNode(BaseNode):

    NODE_TYPE = "Interpolize"
    NODE_CATEGORY = "curves"
    NODE_NAME = "Interpolize"
    NODE_DESCRIPTION = "Fit splines through collection positions along U and V directions"
    AUTO_COMPANIONS = False  # Needs an array upstream, not a bare Atomizer

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True,
                         description="UV-structured collection to interpolate through."),
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("connect_u", PortType.BOOLEAN, default_value=True,
                         show_input_handle=False,
                         description="Fit splines along U rows."),
                PortSpec("connect_v", PortType.BOOLEAN, default_value=True,
                         show_input_handle=False,
                         description="Fit splines along V columns."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("curves", PortType.CURVE,
                         description="Fitted splines through instance positions"),
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
        if not isinstance(raw, dict):
            errors.append(f"{self.port_label('collection')} must be a valid collection object")
            return errors

        instances = raw.get("instances", [])
        if not instances:
            errors.append(f"{self.port_label('collection')} has no instances")

        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        app = context.get("app")
        node_id = context.get("node_id", "interpolize")

        collection = inputs.get("collection")
        raw = collection.to_dict() if hasattr(collection, "to_dict") else collection

        instances = raw.get("instances", [])
        metadata = raw.get("metadata", {})
        connect_u = bool(inputs.get("connect_u", True))
        connect_v = bool(inputs.get("connect_v", True))

        if not instances:
            log(app, "Interpolize: no instances, nothing to do", level=LogLevel.WARNING, module="INTERPOLIZE")
            return {"curves": {"kind": "interpolize_curves", "node_id": node_id, "sketch_name": None, "spline_count": 0}}

        # --- Extract world positions and all per-instance routing metadata ---
        positions = []
        strand_groups: dict = {}   # strand_index → [(strand_position, pos)]
        grid_map: dict = {}        # (grid_u, grid_v) → pos
        has_strands = False
        has_grid_indices = False

        for inst in instances:
            t = inst.get("transform", {}) if isinstance(inst, dict) else inst.transform.to_dict()
            pos = (float(t.get("tx", 0.0)), float(t.get("ty", 0.0)), float(t.get("tz", 0.0)))
            positions.append(pos)

            meta = inst.get("metadata", {}) if isinstance(inst, dict) else (inst.metadata or {})

            si = meta.get("strand_index")
            sp = meta.get("strand_position")
            if si is not None and sp is not None:
                si, sp = int(si), int(sp)
                strand_groups.setdefault(si, []).append((sp, pos))
                has_strands = True

            gu = meta.get("grid_u_index")
            gv = meta.get("grid_v_index")
            if gu is not None and gv is not None:
                grid_map[(int(gu), int(gv))] = pos
                has_grid_indices = True

        # --- Resolve UV grid dimensions (needed for grid and flat paths) ---
        count_u = metadata.get("count_u") or metadata.get("count_x")
        count_v = metadata.get("count_v") or metadata.get("count_y")

        if not count_u or not count_v:
            log(app, "Interpolize: no count_u/count_v in metadata, falling back to 1D",
                level=LogLevel.WARNING, module="INTERPOLIZE")
            count_u, count_v = len(instances), 1
        else:
            count_u, count_v = int(count_u), int(count_v)

        if not has_strands and not has_grid_indices and len(instances) != count_u * count_v:
            log(app,
                f"Interpolize: instance count {len(instances)} != {count_u}×{count_v}={count_u*count_v}, "
                f"no routing metadata — falling back to 1D spline",
                level=LogLevel.WARNING, module="INTERPOLIZE")
            count_u, count_v = len(instances), 1

        log(app, f"Interpolize: {len(positions)} positions, grid {count_u}×{count_v}, "
                 f"connect_u={connect_u}, connect_v={connect_v}, "
                 f"has_strands={has_strands}, has_grid_indices={has_grid_indices}",
            level=LogLevel.DEBUG, module="INTERPOLIZE")

        if not FUSION_AVAILABLE:
            log(app, "Interpolize: Fusion not available, skipping sketch creation",
                level=LogLevel.WARNING, module="INTERPOLIZE")
            return {"curves": {"kind": "interpolize_curves", "node_id": node_id, "sketch_name": None, "spline_count": 0}}

        # --- Fusion sketch setup ---
        design = adsk.fusion.Design.cast(app.activeProduct)
        root_comp = design.rootComponent
        sketch_name = f"Noodle_Interpolize_{node_id}"

        # Create the sketch inside the BaseFeature (mirrors what a user does
        # manually when editing a base feature).  This is the same context that
        # extrudeFeatures.add() uses in PolygonNode and is automatically
        # captured when finishEdit() closes the session.  The BaseFeature is
        # recreated on every graph execution so no stale sketch cleanup needed.
        noodle_base_feature = context.get("noodle_base_feature") or context.get("base_feature")
        if noodle_base_feature:
            sketch = root_comp.sketches.addToBaseOrFormFeature(
                root_comp.xYConstructionPlane, noodle_base_feature, True
            )
        else:
            # Fallback: no base feature context (shouldn't happen in normal use)
            for i in range(root_comp.sketches.count):
                if root_comp.sketches.item(i).name == sketch_name:
                    root_comp.sketches.item(i).deleteMe()
                    break
            sketch = root_comp.sketches.add(root_comp.xYConstructionPlane)

        sketch.name = sketch_name
        splines = sketch.sketchCurves.sketchFittedSplines
        spline_count = 0

        def _add_spline(point_group):
            pts = adsk.core.ObjectCollection.create()
            for (x, y, z) in point_group:
                pts.add(adsk.core.Point3D.create(x, y, z))
            try:
                splines.add(pts)
                return True
            except Exception as e:
                log(app, f"Interpolize: sketchFittedSplines.add failed: {e}",
                    level=LogLevel.WARNING, module="INTERPOLIZE")
                return False

        if has_strands:
            # Path 1 — strand_index/strand_position (post-Separator or Weaver).
            # One curve per strand; connect_u/connect_v not applicable — caller chose
            # which strand set to connect to this Interpolize node.
            for si in sorted(strand_groups.keys()):
                pts = [p for _, p in sorted(strand_groups[si], key=lambda x: x[0])]
                if len(pts) >= 2:
                    if _add_spline(pts):
                        spline_count += 1

        elif has_grid_indices:
            # Path 2 — grid_u_index/grid_v_index (post-Array, no separator).
            # Sparse-aware: handles surfaces where edge culling leaves grid holes.
            if connect_u:
                for row in range(count_v):
                    row_pts = [grid_map[(col, row)] for col in range(count_u) if (col, row) in grid_map]
                    if len(row_pts) >= 2:
                        if _add_spline(row_pts):
                            spline_count += 1

            if connect_v:
                for col in range(count_u):
                    col_pts = [grid_map[(col, row)] for row in range(count_v) if (col, row) in grid_map]
                    if len(col_pts) >= 2:
                        if _add_spline(col_pts):
                            spline_count += 1

        else:
            # Path 3 — flat-index reconstruction (legacy, valid when count matches exactly).
            if connect_u:
                for row in range(count_v):
                    row_pts = [positions[row * count_u + col] for col in range(count_u)]
                    if len(row_pts) >= 2:
                        if _add_spline(row_pts):
                            spline_count += 1

            if connect_v:
                for col in range(count_u):
                    col_pts = [positions[row * count_u + col] for row in range(count_v)]
                    if len(col_pts) >= 2:
                        if _add_spline(col_pts):
                            spline_count += 1

        log(app, f"Interpolize: created {spline_count} splines in sketch '{sketch_name}'",
            level=LogLevel.INFO, module="INTERPOLIZE")

        return {
            "curves": {
                "kind": "interpolize_curves",
                "node_id": node_id,
                "sketch_name": sketch_name,
                "spline_count": spline_count,
            }
        }
