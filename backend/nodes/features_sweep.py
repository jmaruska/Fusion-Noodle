"""
Sweep node — test if sweepFeatures.add() can create bodies inside a BaseFeature.

This node mimics PipeNode but uses sweepFeatures.add() instead. For this test,
it creates a 1cm circle sketch (profile) and sweeps it along each spline in the
input curves (from Interpolize). The profile is always created in the XY plane
at the origin, not normal to the path (for simplicity).

Goal: See if sweepFeatures.add() respects the BaseFeature edit context, or if
it also flushes to the timeline like pipeFeatures.add().
"""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel
from ..utilities.geometry_naming import generate_geometry_name

@enforce_node_spec
class SweepNode(BaseNode):
    NODE_TYPE = "Sweep"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Sweep"
    NODE_DESCRIPTION = "Sweep a circle profile along input curves"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("curves", PortType.CURVE, required=True,
                         description="Curve collection from Interpolize."),
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("radius", PortType.FLOAT, min_value=0.001, unit="length", default_value=0.5,
                         show_input_handle=False,
                         description="Circle profile radius in cm."),
                PortSpec("operation", PortType.ENUM, default_value="newBody",
                         enum_options=["newBody", "add", "cut", "intersect"],
                         enum_labels={
                             "newBody": "New Body",
                             "add": "Join",
                             "cut": "Cut",
                             "intersect": "Intersect",
                         },
                         enum_icons={
                             "newBody":   "tool_ui/BooleanNewBody_32x32-dark.svg",
                             "add":     "tool_ui/BooleanAdd_32x32-dark.svg",
                             "cut":      "tool_ui/BooleanCut_32x32-dark.svg",
                             "intersect":"tool_ui/BooleanIntersect_32x32-dark.svg",
                         },
                         show_input_handle=False,
                         description="Boolean operation for each sweep body."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("bodies", PortType.GEOMETRY,
                         description="Sweep solid bodies"),
            ],
            description=cls.NODE_DESCRIPTION,
            wide=True
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        curves = inputs.get("curves")
        if not curves:
            errors.append(f"{self.port_label('curves')} input is required")
            return errors
        if not isinstance(curves, dict) or curves.get("kind") != "interpolize_curves":
            errors.append(f"{self.port_label('curves')} must be an interpolize_curves envelope from an Interpolize node")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        import adsk.core
        import adsk.fusion

        app = context.get("app") or adsk.core.Application.get()
        curves_envelope = inputs.get("curves", {})
        sketch_name = curves_envelope.get("sketch_name")
        spline_count = curves_envelope.get("spline_count", 0)

        if not sketch_name or spline_count == 0:
            log(app, "Sweep: no curves input, skipping", level=LogLevel.WARNING, module="SWEEP")
            return {"bodies": {"kind": "sweep_bodies", "id": self.id, "body_count": 0}}

        noodle_base_feature = context.get("base_feature") or context.get("noodle_base_feature")
        if not noodle_base_feature:
            raise ValueError("No BaseFeature available for Sweep execute()")

        radius_cm = float(inputs.get("radius", 0.5))
        operation_key = inputs.get("operation", "newBody")
        _OPERATION_MAP = {
            "newBody":   adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
            "add":       adsk.fusion.FeatureOperations.JoinFeatureOperation,
            "cut":       adsk.fusion.FeatureOperations.CutFeatureOperation,
            "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
        }
        operation_enum = _OPERATION_MAP.get(operation_key, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        design = adsk.fusion.Design.cast(app.activeProduct)
        root_comp = design.rootComponent

        # Find the Interpolize sketch
        sketch = None
        for i in range(root_comp.sketches.count):
            s = root_comp.sketches.item(i)
            if s.name == sketch_name:
                sketch = s
                break
        if sketch is None:
            log(app, f"Sweep: sketch '{sketch_name}' not found", level=LogLevel.ERROR, module="SWEEP")
            return {"bodies": {"kind": "sweep_bodies", "id": self.id, "body_count": 0}}

        splines = sketch.sketchCurves.sketchFittedSplines
        log(app, f"Sweep: processing {splines.count} splines from '{sketch_name}'",
            level=LogLevel.INFO, module="SWEEP")

        # Create a profile sketch (circle at origin, XY plane)
        profile_sketch = root_comp.sketches.addToBaseOrFormFeature(
            root_comp.xYConstructionPlane, noodle_base_feature, True)
        profile_sketch.name = f"Noodle_SweepProfile_{self.id}"
        circles = profile_sketch.sketchCurves.sketchCircles
        circle = circles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), radius_cm)
        profile = profile_sketch.profiles.item(0)

        sweep_features = root_comp.features.sweepFeatures
        body_count = 0
        for i in range(splines.count):
            spline = splines.item(i)
            try:
                path = adsk.fusion.Path.create(
                    spline,
                    adsk.fusion.ChainedCurveOptions.noChainedCurves
                )
                sweep_input = sweep_features.createInput(
                    profile,
                    path,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                sweep_input.operation = operation_enum
                sweep_feat = sweep_features.add(sweep_input)
                for j in range(sweep_feat.bodies.count):
                    body = sweep_feat.bodies.item(j)
                    body_name = generate_geometry_name("sweep", self.id, "Sweep", index=body_count)
                    body.name = body_name
                    self._register_body_name(context, body_name)
                    body_count += 1
            except Exception as e:
                log(app, f"Sweep: spline {i} failed: {e}", level=LogLevel.ERROR, module="SWEEP")

        log(app, f"Sweep: created {body_count} sweep bodies", level=LogLevel.INFO, module="SWEEP")
        return {
            "bodies": {
                "kind": "sweep_bodies",
                "id": self.id,
                "body_count": body_count,
            }
        }
