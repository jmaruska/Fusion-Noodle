"""
Array_Path node — distributes a collection of instances along a 3D curve.

Supported curve types (selected via the CURVE port):
  - BRepEdge  : any model or surface edge in the active design
  - SketchCurve : any sketch entity (line, arc, circle, spline, etc.)

World-space handling
--------------------
Curves in sub-components are evaluated in component-local space and then
transformed to world space via the occurrence's worldTransform at execution
time. This means moved occurrences are always reflected correctly — the
transform is re-resolved on every graph execution, never baked at selection.

For SketchCurves the transform chain is:
    sketch-local → (sketch.transform) → component-local → (occ.worldTransform) → world

Frame convention (Q2 confirmed)
---------------------------------
Local +Z aligns to the curve tangent (forward direction).
Local +X = right = normalize(world-up × tangent)
Local +Y = true-up = normalize(tangent × local-X)
Degenerate case (tangent ≈ world-up): fall back to world-X then world-Z.

Arc-length spacing
------------------
'spacing' mode uses binary-search inversion of getLengthAtParameter to achieve
true equal arc-length distribution, not uniform parameter distribution.
TODO (v2): taper, twist, multi-segment stitched paths, reverse-direction toggle.
"""

import math
import uuid
import traceback
from typing import Dict, Any, List, Optional, Tuple

from ..enforcement import enforce_node_spec
from ..contracts import (
    NodeSpec, PortSpec, PortType,
    NoodleAttributes, CollectionInstanceSpec, CollectionSpec, GeometryEnvelope
)
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel

try:
    import adsk.core   # type: ignore
    import adsk.fusion  # type: ignore
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


@enforce_node_spec
class ArrayPathNode(BaseNode):
    """Distributes collection instances along a selected 3D curve."""

    NODE_TYPE = "Array_Path"
    NODE_CATEGORY = "array"
    NODE_NAME = "Array on Path"
    NODE_DESCRIPTION = "Distribute instances along a curve with tangent-aligned orientation"

    DEFAULT_COUNT = 10
    MAX_INSTANCES = 10000
    DEFAULT_SPACING = 1.0

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True,
                         description="Source collection to distribute along the path."),

                PortSpec("spacer_curve", PortType.SPACER),
                PortSpec("curve", PortType.CURVE, required=True, show_input_handle=False,
                         description="Target curve — pick any BRep edge or sketch curve."),

                PortSpec("spacer_dist", PortType.SPACER),
                PortSpec("mode", PortType.ENUM, default_value="count",
                         enum_options=["count", "spacing"],
                         enum_labels={"count": "Count", "spacing": "Spacing"},
                         show_input_handle=False,
                         description="count: fixed number of instances; spacing: fixed arc-length gap (cm)."),
                PortSpec("value", PortType.FLOAT, default_value=10.0,
                         label_from={'port': 'mode', 'map': {'count': 'Count', 'spacing': 'Spacing (cm)'}},
                         description="Number of instances (count mode) or arc-length gap in cm (spacing mode).",
                         min_value=0.001),

                PortSpec("spacer_margins", PortType.SPACER),
                PortSpec("margin_start", PortType.FLOAT, unit="length", default_value=0.0,
                         description="Arc-length margin from curve start before first instance (cm).",
                         min_value=0.0),
                PortSpec("margin_end", PortType.FLOAT, unit="length", default_value=0.0,
                         description="Arc-length margin from curve end after last instance (cm).",
                         min_value=0.0),

                PortSpec("spacer_orient", PortType.SPACER),
                PortSpec("up", PortType.VECTOR3,
                         default_value={"x": 0.0, "y": 1.0, "z": 0.0},
                         description="World-space up hint for frame orientation (Fusion 360 is Y-up by convention)."),
                PortSpec("align_to_tangent", PortType.BOOLEAN, default_value=True,
                         show_input_handle=False,
                         description="Orient instances so local +Z faces along the curve tangent."),
                
                PortSpec("spacer_sizing", PortType.SPACER),
                PortSpec("scale_start", PortType.FLOAT, default_value=1.0,
                         description="XY scale multiplier at the first instance.",
                         min_value=0.001),
                PortSpec("scale_end", PortType.FLOAT, default_value=1.0,
                         description="XY scale multiplier at the last instance.",
                         min_value=0.001),
                
                PortSpec("spacer_rotations", PortType.SPACER),
                PortSpec("twist", PortType.FLOAT, unit="angle", default_value=0.0,
                         label="Twist",
                         description="Total twist in degrees distributed evenly across all instances."),
                PortSpec("bank", PortType.FLOAT, default_value=0.0,
                         label="Bank Factor",
                         description="Curvature-driven tilt around the tangent axis. Positive = bank into curve, negative = bank away."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION,
                         description="Instances distributed along the path"),
            ],
            description=cls.NODE_DESCRIPTION,
            wide=True
        )

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #

    def validate(self, inputs: Dict[str, Any]):
        # Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)
        errors = []

        if not inputs.get("collection"):
            errors.append("Collection input is required")

        if not inputs.get("curve"):
            errors.append("Curve input is required — select a BRep edge or sketch curve")

        mode = inputs.get("mode", "count")
        if mode not in ("count", "spacing"):
            errors.append("Mode must be 'count' or 'spacing'")

        # The value is a count or a spacing depending on Mode, so its count limits
        # can't be declared on the port
        value = inputs.get("value", self.DEFAULT_COUNT)
        if mode == "count" and isinstance(value, (int, float)) and float(value) < 1:
            errors.append("Count must be at least 1")
        if mode == "count" and isinstance(value, (int, float)) and float(value) > self.MAX_INSTANCES:
            errors.append(f"Count cannot exceed {self.MAX_INSTANCES} (too many instances)")

        return errors

    # ------------------------------------------------------------------ #
    # Execute                                                              #
    # ------------------------------------------------------------------ #

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._execute_internal(inputs, context)
        except Exception as e:
            app = context.get('app')
            log(app, f"Array_Path execute failed: {e}", level=LogLevel.ERROR, module="ARRAY_PATH")
            log(app, traceback.format_exc(), level=LogLevel.ERROR, module="ARRAY_PATH")
            raise

    def _execute_internal(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        app = context.get('app')

        # ── Collection ──────────────────────────────────────────────────
        collection_data = inputs.get("collection")
        if not collection_data:
            log(app, "No collection input", level=LogLevel.WARNING, module="ARRAY_PATH")
            return {"collection": None}

        if isinstance(collection_data, dict):
            collection_spec = CollectionSpec.from_dict(collection_data)
        elif hasattr(collection_data, 'source_geometries'):
            collection_spec = collection_data
        else:
            raise TypeError(f"Unexpected collection type: {type(collection_data)}")

        # ── Curve data ───────────────────────────────────────────────────
        curve_data = inputs.get("curve")
        if not isinstance(curve_data, dict) or not curve_data.get('entity_token'):
            log(app, "No valid curve data", level=LogLevel.WARNING, module="ARRAY_PATH")
            return {"collection": None}

        # ── Parameters ──────────────────────────────────────────────────
        mode = str(inputs.get("mode", "count"))
        raw_value = float(inputs.get("value", self.DEFAULT_COUNT))
        count = max(1, int(raw_value))      # used when mode='count'
        spacing = max(0.001, raw_value)     # used when mode='spacing'
        align_to_tangent = bool(inputs.get("align_to_tangent", True))
        margin_start = max(0.0, float(inputs.get("margin_start", 0.0)))
        margin_end = max(0.0, float(inputs.get("margin_end", 0.0)))
        total_twist = float(inputs.get("twist", 0.0))
        scale_start = max(0.001, float(inputs.get("scale_start", 1.0)))
        scale_end = max(0.001, float(inputs.get("scale_end", 1.0)))
        bank_factor = float(inputs.get("bank", 0.0))

        up_raw = inputs.get("up", {"x": 0.0, "y": 1.0, "z": 0.0})
        up_x, up_y, up_z = self._parse_up_vector(up_raw)

        # ── Resolve curve entity from active design ──────────────────────
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            log(app, "No active Fusion design", level=LogLevel.ERROR, module="ARRAY_PATH")
            return {"collection": None}

        entity, world_xform, sketch_xform, curve_type = self._resolve_curve(curve_data, design, app)
        if entity is None:
            log(app, f"Failed to resolve curve entity: {curve_data.get('entity_token')}",
                level=LogLevel.ERROR, module="ARRAY_PATH")
            return {"collection": None}

        resolved_type = getattr(entity, 'objectType', 'unknown').split('::')[-1]
        log(app, f"Array_Path resolved entity: {resolved_type}  "
                 f"sketch_xform={'yes' if sketch_xform else 'None'}  "
                 f"world_xform={'yes' if world_xform else 'None'}",
            level=LogLevel.DEBUG, module="ARRAY_PATH")

        # ── Get evaluator and parameter extents ──────────────────────────
        evaluator, t_start, t_end = self._get_evaluator_and_extents(entity, curve_type, app)
        if evaluator is None:
            return {"collection": None}

        # ── Validate curve length ────────────────────────────────────────
        ok, total_length = evaluator.getLengthAtParameter(t_start, t_end)
        if not ok or total_length < 1e-6:
            log(app, "Curve is zero-length or degenerate — cannot distribute instances",
                level=LogLevel.ERROR, module="ARRAY_PATH")
            return {"collection": None}

        # Diagnostic: sample first and mid points before/after transforms
        for t_probe, label in [(t_start, 'start'), ((t_start + t_end) * 0.5, 'mid')]:
            ok_p, pt_raw = evaluator.getPointAtParameter(t_probe)
            if ok_p:
                pt_w = self._to_world(pt_raw, sketch_xform, world_xform)
                log(app, f"Array_Path probe [{label}] t={t_probe:.4f}  "
                         f"raw=({pt_raw.x:.3f},{pt_raw.y:.3f},{pt_raw.z:.3f})  "
                         f"world=({pt_w.x:.3f},{pt_w.y:.3f},{pt_w.z:.3f})",
                    level=LogLevel.DEBUG, module="ARRAY_PATH")

        log(app, f"Array_Path: curve length={total_length:.4f}cm, mode={mode}, "
                 f"count={count}, spacing={spacing}, "
                 f"margin_start={margin_start}, margin_end={margin_end}",
            level=LogLevel.DEBUG, module="ARRAY_PATH")

        # ── Compute parameter samples ────────────────────────────────────
        params = self._compute_parameters(
            mode, count, spacing, margin_start, margin_end,
            t_start, t_end, evaluator, total_length, app
        )
        if not params:
            log(app, "No parameters generated — check count/spacing vs curve length",
                level=LogLevel.WARNING, module="ARRAY_PATH")
            return {"collection": None}
        if len(params) > self.MAX_INSTANCES:
            log(app, f"Spacing gives {len(params)} instances along the curve; the limit is "
                     f"{self.MAX_INSTANCES}. Increase the spacing.",
                level=LogLevel.ERROR, module="ARRAY_PATH")
            return {"collection": None}

        log(app, f"Array_Path: generating {len(params)} instances", level=LogLevel.DEBUG, module="ARRAY_PATH")

        # ── Build NoodleAttributes for each sample ───────────────────────
        n_params = len(params)
        noodle_attrs_list = []
        for idx, t in enumerate(params):
            attrs = self._evaluate_frame(
                evaluator, t, t_start, t_end,
                world_xform, sketch_xform,
                up_x, up_y, up_z, align_to_tangent, bank_factor, app
            )
            if attrs:
                t_norm = idx / max(n_params - 1, 1)
                if total_twist != 0.0:
                    attrs = self._apply_twist(attrs, math.radians(total_twist * t_norm))
                if scale_start != 1.0 or scale_end != 1.0:
                    xy_scale = scale_start + (scale_end - scale_start) * t_norm
                    attrs = NoodleAttributes(
                        tx=attrs.tx, ty=attrs.ty, tz=attrs.tz,
                        sx=attrs.sx * xy_scale, sy=attrs.sy * xy_scale, sz=attrs.sz,
                        qx=attrs.qx, qy=attrs.qy, qz=attrs.qz, qw=attrs.qw,
                        use_quaternion=True
                    )
                noodle_attrs_list.append(attrs)

        if not noodle_attrs_list:
            log(app, "Failed to evaluate any frames along curve", level=LogLevel.ERROR, module="ARRAY_PATH")
            return {"collection": None}

        # ── Build output instances ───────────────────────────────────────
        node_id = context.get('node_id', 'unknown')
        source_geometries = list(collection_spec.source_geometries)
        output_instances: List[CollectionInstanceSpec] = []

        for input_inst in collection_spec.instances:
            if isinstance(input_inst, CollectionInstanceSpec):
                inst_spec = input_inst
            else:
                inst_spec = CollectionInstanceSpec.from_dict(input_inst)

            src_sx = inst_spec.transform.sx if hasattr(inst_spec.transform, 'sx') else 1.0
            src_sy = inst_spec.transform.sy if hasattr(inst_spec.transform, 'sy') else 1.0
            src_sz = inst_spec.transform.sz if hasattr(inst_spec.transform, 'sz') else 1.0

            for i, frame_attrs in enumerate(noodle_attrs_list):
                final_attrs = NoodleAttributes(
                    tx=frame_attrs.tx, ty=frame_attrs.ty, tz=frame_attrs.tz,
                    sx=frame_attrs.sx * src_sx,
                    sy=frame_attrs.sy * src_sy,
                    sz=frame_attrs.sz * src_sz,
                    qx=frame_attrs.qx, qy=frame_attrs.qy,
                    qz=frame_attrs.qz, qw=frame_attrs.qw,
                    use_quaternion=True
                )
                output_instances.append(CollectionInstanceSpec(
                    instance_id=str(uuid.uuid4())[:8],
                    source_geometry_id=inst_spec.source_geometry_id,
                    transform=final_attrs,
                    metadata={
                        "source_node": self.NODE_TYPE,
                        "source_node_id": node_id,
                        "array_type": "path_array",
                        "path_index": i,
                        "path_param": params[i] if i < len(params) else 0.0,
                        "curve_token": curve_data.get('entity_token', ''),
                        "source_instance_id": inst_spec.instance_id,
                    }
                ))

        output_collection = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=str(uuid.uuid4())[:8],
            source_geometries=source_geometries,
            instances=output_instances,
            metadata={
                "type": "path_array",
                "mode": mode,
                "count": len(noodle_attrs_list),
                "curve_length": total_length,
                "curve_token": curve_data.get('entity_token', ''),
                "array_node_id": node_id,
            }
        )

        log(app, f"Array_Path: produced {len(output_instances)} instances",
            level=LogLevel.DEBUG, module="ARRAY_PATH")

        return {"collection": output_collection}

    # ------------------------------------------------------------------ #
    # Curve resolution                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_curve(
        self, curve_data: Dict[str, Any], design, app
    ) -> Tuple[Any, Any, Any, str]:
        """
        Re-find the curve entity in the current design state.

        Returns (entity, world_xform, sketch_xform, curve_type) where:
          - world_xform : occurrence.worldTransform (Matrix3D) or None (root component)
          - sketch_xform: sketch.transform (Matrix3D) or None (not a sketch curve)
          - curve_type  : 'brep_edge' or 'sketch_curve'

        Primary lookup uses design.findEntityByToken() — the same mechanism Fusion
        uses internally for parametric references (loft profiles, extrude base, etc.).
        This is session-persistent and survives model edits as long as the entity exists.
        The occurrence / sketch transform is re-resolved at execution time so moved
        components are reflected without re-selecting the curve.
        """
        entity_token = curve_data.get('entity_token', '')
        curve_type = curve_data.get('curve_type', '')

        # ── Primary: token-based lookup (works for both BRepEdge and SketchCurve) ──
        try:
            results = design.findEntityByToken(entity_token)
            if results and results.count > 0:
                entity = results.item(0)
                resolved_ot = getattr(entity, 'objectType', 'unknown').split('::')[-1]
                log(app, f"Array_Path findEntityByToken → {resolved_ot} (token={entity_token[:40]}...)",
                    level=LogLevel.DEBUG, module="ARRAY_PATH")
                world_xform, sketch_xform = self._get_transforms(entity, curve_type, design, app)
                return entity, world_xform, sketch_xform, curve_type
            else:
                log(app, f"Array_Path findEntityByToken returned empty for token={entity_token[:40]}",
                    level=LogLevel.DEBUG, module="ARRAY_PATH")
        except Exception as e:
            log(app, f"findEntityByToken failed for '{entity_token}': {e}",
                level=LogLevel.DEBUG, module="ARRAY_PATH")

        # ── Fallback for synthesized sketch tokens (legacy / no entityToken on curve) ──
        if curve_type == 'sketch_curve':
            sketch_name = curve_data.get('sketch_name', '')
            curve_index = int(curve_data.get('curve_index', 0))
            stored_temp_id = curve_data.get('temp_id')
            # object_type e.g. "adsk::fusion::SketchControlPointSpline"
            stored_object_type = (curve_data.get('object_type', '') or '').split('::')[-1]
            root = design.rootComponent

            def _find_in_sketch(sketch):
                curves = sketch.sketchCurves
                # 1. Match by tempId (same Fusion session)
                if stored_temp_id is not None:
                    for i in range(curves.count):
                        item = curves.item(i)
                        if getattr(item, 'tempId', None) == stored_temp_id:
                            return item
                # 2. Match by objectType subtype + index within that type
                #    (prevents hull SketchLines stealing index 0 from a SketchControlPointSpline)
                if stored_object_type:
                    type_hits = 0
                    for i in range(curves.count):
                        item = curves.item(i)
                        item_subtype = (getattr(item, 'objectType', '') or '').split('::')[-1]
                        if item_subtype == stored_object_type:
                            if type_hits == curve_index:
                                return item
                            type_hits += 1
                # 3. Absolute index fallback
                if curve_index < curves.count:
                    return curves.item(curve_index)
                return None

            for sketch in root.sketches:
                if sketch.name == sketch_name:
                    curve = _find_in_sketch(sketch)
                    if curve is not None:
                        return curve, None, sketch.transform, curve_type

            for occ in root.allOccurrences:
                for sketch in occ.component.sketches:
                    if sketch.name == sketch_name:
                        curve = _find_in_sketch(sketch)
                        if curve is not None:
                            return curve, occ.worldTransform, sketch.transform, curve_type

            log(app, f"SketchCurve not found: sketch='{sketch_name}', type='{stored_object_type}', index={curve_index}",
                level=LogLevel.WARNING, module="ARRAY_PATH")

        log(app, f"Curve not found for token: '{entity_token}'",
            level=LogLevel.WARNING, module="ARRAY_PATH")
        return None, None, None, curve_type

    def _get_transforms(self, entity, curve_type: str, design, app) -> Tuple[Any, Any]:
        """Return (world_xform, sketch_xform) for an entity resolved via findEntityByToken."""
        world_xform = None
        sketch_xform = None
        try:
            if curve_type == 'sketch_curve':
                sketch = entity.parentSketch if hasattr(entity, 'parentSketch') else None
                if sketch:
                    sketch_xform = sketch.transform
                    # Sketch in a sub-component occurrence
                    if hasattr(sketch, 'assemblyContext') and sketch.assemblyContext:
                        world_xform = sketch.assemblyContext.worldTransform
            elif curve_type == 'brep_edge':
                if hasattr(entity, 'assemblyContext') and entity.assemblyContext:
                    world_xform = entity.assemblyContext.worldTransform
        except Exception as e:
            log(app, f"Error resolving transforms: {e}", level=LogLevel.DEBUG, module="ARRAY_PATH")
        return world_xform, sketch_xform

    def _get_evaluator_and_extents(
        self, entity, curve_type: str, app
    ) -> Tuple[Any, float, float]:
        """Return (evaluator, t_start, t_end) for the resolved curve entity."""
        try:
            if curve_type == 'brep_edge':
                ev = entity.evaluator
            elif curve_type == 'sketch_curve':
                ev = entity.geometry.evaluator
            else:
                return None, 0.0, 1.0

            ok, t_start, t_end = ev.getParameterExtents()
            if not ok:
                log(app, "getParameterExtents failed", level=LogLevel.ERROR, module="ARRAY_PATH")
                return None, 0.0, 1.0

            return ev, t_start, t_end

        except Exception as e:
            log(app, f"Error getting evaluator: {e}", level=LogLevel.ERROR, module="ARRAY_PATH")
            return None, 0.0, 1.0

    # ------------------------------------------------------------------ #
    # Parameter distribution                                               #
    # ------------------------------------------------------------------ #

    def _compute_parameters(
        self, mode: str, count: int, spacing: float,
        margin_start: float, margin_end: float,
        t_start: float, t_end: float,
        evaluator, total_length: float, app
    ) -> List[float]:
        """
        Compute the list of curve parameters at which to place instances.

        Margins are in world units (cm) and clip the active region from each end.
        'count' mode : n arc-length-uniform instances across the active region.
        'spacing' mode: arc-length spacing via binary-search inversion of getLengthAtParameter.
        """
        # Clamp margins so they don't consume the whole curve
        usable_total = total_length - margin_start - margin_end
        if usable_total < 1e-4:
            log(app, "Margins exceed curve length — no room for instances",
                level=LogLevel.WARNING, module="ARRAY_PATH")
            return []

        # Binary-search for t_effective_start (arc-length = margin_start from t_start)
        t_effective_start = self._t_at_arc_length(evaluator, t_start, t_end, margin_start)
        # Binary-search for t_effective_end (arc-length = total_length - margin_end from t_start)
        t_effective_end = self._t_at_arc_length(evaluator, t_start, t_end,
                                                  total_length - margin_end)

        if mode == 'count':
            n = max(1, count)
            if n == 1:
                return [t_effective_start]
            params: List[float] = []
            for i in range(n):
                if i == 0:
                    params.append(t_effective_start)
                    continue
                if i == n - 1:
                    params.append(t_effective_end)
                    continue
                target = usable_total * i / (n - 1)
                params.append(self._t_at_arc_length(evaluator, t_effective_start,
                                                     t_effective_end, target))
            return params

        if mode == 'spacing':
            params: List[float] = []
            current_t = t_effective_start
            params.append(current_t)

            while True:
                ok, remaining = evaluator.getLengthAtParameter(current_t, t_effective_end)
                if not ok or remaining < spacing * 0.5:
                    break

                t_lo = current_t
                t_hi = t_effective_end
                for _ in range(50):
                    t_mid = (t_lo + t_hi) * 0.5
                    ok2, seg_len = evaluator.getLengthAtParameter(current_t, t_mid)
                    if not ok2:
                        break
                    if abs(seg_len - spacing) < 1e-5:
                        break
                    if seg_len < spacing:
                        t_lo = t_mid
                    else:
                        t_hi = t_mid

                next_t = (t_lo + t_hi) * 0.5
                if next_t >= t_effective_end - 1e-9 or next_t <= current_t + 1e-9:
                    break

                params.append(next_t)
                current_t = next_t

            return params

        return []

    # ------------------------------------------------------------------ #
    # Frame evaluation                                                     #
    # ------------------------------------------------------------------ #

    def _evaluate_frame(
        self, evaluator, t: float, t_start: float, t_end: float,
        world_xform, sketch_xform,
        up_x: float, up_y: float, up_z: float,
        align_to_tangent: bool, bank_factor: float, app
    ) -> Optional[NoodleAttributes]:
        """
        Compute a NoodleAttributes (position + quaternion rotation) for a single
        curve sample point.

        World-space point: evaluator → sketch_xform (if sketch) → world_xform (if occurrence).
        Tangent: finite-difference of world-space points (avoids manual matrix rotation math).
        Frame: Gram-Schmidt with up-hint → X = normalize(up × Z), Y = normalize(Z × X).
        """
        try:
            # ── Position ────────────────────────────────────────────────
            ok, pt = evaluator.getPointAtParameter(t)
            if not ok:
                return None

            pt_world = self._to_world(pt, sketch_xform, world_xform)
            px, py, pz = pt_world.x, pt_world.y, pt_world.z

            if not align_to_tangent:
                return NoodleAttributes(tx=px, ty=py, tz=pz, use_quaternion=True, qw=1.0)

            # ── Tangent via finite difference ────────────────────────────
            dt = (t_end - t_start) * 0.001
            t_fwd = min(t + dt, t_end)
            t_bwd = max(t - dt, t_start)

            ok_f, pt_f = evaluator.getPointAtParameter(t_fwd)
            ok_b, pt_b = evaluator.getPointAtParameter(t_bwd)

            if not ok_f or not ok_b:
                return NoodleAttributes(tx=px, ty=py, tz=pz, use_quaternion=True, qw=1.0)

            pf = self._to_world(pt_f, sketch_xform, world_xform)
            pb = self._to_world(pt_b, sketch_xform, world_xform)

            fwd_x = pf.x - pb.x
            fwd_y = pf.y - pb.y
            fwd_z = pf.z - pb.z
            fwd_len = math.sqrt(fwd_x * fwd_x + fwd_y * fwd_y + fwd_z * fwd_z)
            if fwd_len < 1e-9:
                return NoodleAttributes(tx=px, ty=py, tz=pz, use_quaternion=True, qw=1.0)

            fwd_x /= fwd_len
            fwd_y /= fwd_len
            fwd_z /= fwd_len

            # ── Gram-Schmidt frame: local Z = forward ────────────────────
            # X = normalize(up × Z)
            rx, ry, rz = self._cross(up_x, up_y, up_z, fwd_x, fwd_y, fwd_z)
            r_len = math.sqrt(rx * rx + ry * ry + rz * rz)

            if r_len < 1e-6:
                # Tangent nearly parallel to up_hint — try world X then world Z
                for fallback in ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)):
                    rx, ry, rz = self._cross(fallback[0], fallback[1], fallback[2],
                                             fwd_x, fwd_y, fwd_z)
                    r_len = math.sqrt(rx * rx + ry * ry + rz * rz)
                    if r_len > 1e-6:
                        break

            if r_len < 1e-6:
                return NoodleAttributes(tx=px, ty=py, tz=pz, use_quaternion=True, qw=1.0)

            rx /= r_len
            ry /= r_len
            rz /= r_len

            # Y = normalize(Z × X)
            tux, tuy, tuz = self._cross(fwd_x, fwd_y, fwd_z, rx, ry, rz)
            tu_len = math.sqrt(tux * tux + tuy * tuy + tuz * tuz)
            if tu_len > 1e-9:
                tux /= tu_len
                tuy /= tu_len
                tuz /= tu_len

            # ── Bank: curvature-driven tilt around local Z (tangent axis) ──
            # Curvature ≈ finite diff of unit tangents (T_fwd − T_bwd).
            # At endpoints one sample is missing; shift the window inward so
            # the endpoint gets the same quality estimate as interior points.
            if bank_factor != 0.0:
                def _unit_tangent(pa, pb_pt):
                    dx = pa.x - pb_pt.x; dy = pa.y - pb_pt.y; dz = pa.z - pb_pt.z
                    ln = math.sqrt(dx*dx + dy*dy + dz*dz)
                    return (dx/ln, dy/ln, dz/ln) if ln > 1e-9 else None

                # Gate on parameter, not vector length: if a full dt step
                # would overshoot the curve boundary, the forward/backward
                # sample is unreliable — shift the whole window inward.
                at_end   = (t + dt >= t_end)
                at_start = (t - dt <= t_start)

                if at_end and not at_start:
                    # Shift window to (t-2dt, t-dt): both samples inside curve
                    t_b2 = max(t - 2 * dt, t_start)
                    ok_b2, raw_b2 = evaluator.getPointAtParameter(t_b2)
                    if ok_b2:
                        pb2 = self._to_world(raw_b2, sketch_xform, world_xform)
                        tf = _unit_tangent(pt_world, pb)   # T from t-dt → t
                        tb = _unit_tangent(pb, pb2)         # T from t-2dt → t-dt
                    else:
                        tf = tb = None
                elif at_start and not at_end:
                    # Shift window to (t+dt, t+2dt)
                    t_f2 = min(t + 2 * dt, t_end)
                    ok_f2, raw_f2 = evaluator.getPointAtParameter(t_f2)
                    if ok_f2:
                        pf2 = self._to_world(raw_f2, sketch_xform, world_xform)
                        tf = _unit_tangent(pf2, pf)         # T from t+dt → t+2dt
                        tb = _unit_tangent(pf, pt_world)    # T from t → t+dt
                    else:
                        tf = tb = None
                else:
                    tf = _unit_tangent(pf, pt_world)
                    tb = _unit_tangent(pt_world, pb)

                if tf is not None and tb is not None:
                    cx = tf[0] - tb[0]; cy = tf[1] - tb[1]; cz = tf[2] - tb[2]
                    bank_x = cx * rx + cy * ry + cz * rz
                    bank_angle = -bank_x * bank_factor
                    cos_b = math.cos(bank_angle)
                    sin_b = math.sin(bank_angle)
                    new_rx  =  rx  * cos_b + tux * sin_b
                    new_ry  =  ry  * cos_b + tuy * sin_b
                    new_rz  =  rz  * cos_b + tuz * sin_b
                    new_tux = -rx  * sin_b + tux * cos_b
                    new_tuy = -ry  * sin_b + tuy * cos_b
                    new_tuz = -rz  * sin_b + tuz * cos_b
                    rx,  ry,  rz  = new_rx,  new_ry,  new_rz
                    tux, tuy, tuz = new_tux, new_tuy, new_tuz

            # ── Rotation matrix → quaternion (Shepperd) ──────────────────
            # Columns: [X=right, Y=true_up, Z=forward]
            m00, m01, m02 = rx,   tux, fwd_x
            m10, m11, m12 = ry,   tuy, fwd_y
            m20, m21, m22 = rz,   tuz, fwd_z

            trace = m00 + m11 + m22
            if trace > 0:
                s = math.sqrt(trace + 1.0) * 2
                qw = 0.25 * s
                qx = (m21 - m12) / s
                qy = (m02 - m20) / s
                qz = (m10 - m01) / s
            elif m00 > m11 and m00 > m22:
                s = math.sqrt(1.0 + m00 - m11 - m22) * 2
                qw = (m21 - m12) / s
                qx = 0.25 * s
                qy = (m01 + m10) / s
                qz = (m02 + m20) / s
            elif m11 > m22:
                s = math.sqrt(1.0 + m11 - m00 - m22) * 2
                qw = (m02 - m20) / s
                qx = (m01 + m10) / s
                qy = 0.25 * s
                qz = (m12 + m21) / s
            else:
                s = math.sqrt(1.0 + m22 - m00 - m11) * 2
                qw = (m10 - m01) / s
                qx = (m02 + m20) / s
                qy = (m12 + m21) / s
                qz = 0.25 * s

            return NoodleAttributes(
                tx=px, ty=py, tz=pz,
                qx=qx, qy=qy, qz=qz, qw=qw,
                use_quaternion=True
            )

        except Exception as e:
            log(app, f"Error evaluating frame at t={t}: {e}", level=LogLevel.ERROR, module="ARRAY_PATH")
            return None

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _apply_twist(attrs: NoodleAttributes, angle_rad: float) -> NoodleAttributes:
        """Post-multiply a rotation around local Z (tangent axis) onto the frame quaternion."""
        s = math.sin(angle_rad * 0.5)
        c = math.cos(angle_rad * 0.5)
        qx, qy, qz, qw = attrs.qx, attrs.qy, attrs.qz, attrs.qw
        # q_final = q_frame * q_twist_z  where q_twist_z = (0, 0, s, c)
        return NoodleAttributes(
            tx=attrs.tx, ty=attrs.ty, tz=attrs.tz,
            sx=attrs.sx, sy=attrs.sy, sz=attrs.sz,
            qx= qx*c + qy*s,
            qy=-qx*s + qy*c,
            qz= qw*s + qz*c,
            qw= qw*c - qz*s,
            use_quaternion=True
        )

    @staticmethod
    def _t_at_arc_length(evaluator, t_start: float, t_end: float,
                          target_length: float) -> float:
        """Binary-search for the parameter where arc-length from t_start equals target_length."""
        target_length = max(0.0, target_length)
        if target_length <= 0.0:
            return t_start
        t_lo, t_hi = t_start, t_end
        for _ in range(50):
            t_mid = (t_lo + t_hi) * 0.5
            ok, seg = evaluator.getLengthAtParameter(t_start, t_mid)
            if not ok:
                break
            if abs(seg - target_length) < 1e-5:
                break
            if seg < target_length:
                t_lo = t_mid
            else:
                t_hi = t_mid
        return (t_lo + t_hi) * 0.5

    @staticmethod
    def _to_world(point3d, sketch_xform, world_xform):
        """
        Transform a Point3D from evaluator space to world space.
        A copy is made so the original is not mutated.
        """
        pt = point3d.copy()
        if sketch_xform is not None:
            pt.transformBy(sketch_xform)
        if world_xform is not None:
            pt.transformBy(world_xform)
        return pt

    @staticmethod
    def _cross(ax, ay, az, bx, by, bz) -> Tuple[float, float, float]:
        """Pure-Python 3D cross product a × b."""
        return (
            ay * bz - az * by,
            az * bx - ax * bz,
            ax * by - ay * bx,
        )

    @staticmethod
    def _parse_up_vector(up_raw) -> Tuple[float, float, float]:
        """Extract and normalize the up-hint vector, falling back to Y-up."""
        if isinstance(up_raw, dict):
            ux = float(up_raw.get('x', 0.0))
            uy = float(up_raw.get('y', 1.0))
            uz = float(up_raw.get('z', 0.0))
        else:
            ux, uy, uz = 0.0, 1.0, 0.0

        length = math.sqrt(ux * ux + uy * uy + uz * uz)
        if length < 1e-6:
            return 0.0, 1.0, 0.0
        return ux / length, uy / length, uz / length

    # ------------------------------------------------------------------ #
    # Cache key                                                            #
    # ------------------------------------------------------------------ #
