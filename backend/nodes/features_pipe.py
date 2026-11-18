"""
Pipe node — type converter: curves → geometry.

Takes the envelope produced by Interpolize (kind="interpolize_curves") and
runs Fusion's native Pipe command once per SketchFittedSpline, accumulating
solid tube bodies inside the active BaseFeature session.

Why the finishEdit/startEdit cycle?
-------------------------------------
pipeFeatures.add() always produces a parametric timeline feature.  When called
*inside* a BaseFeature edit the API accepts the call but flushes the resulting
feature to the main timeline on finishEdit() — bodies never land inside the BF.
extrudes.add() does not have this problem.

The workaround is self-contained in execute():
  1. Look up the Interpolize sketch (visible in root_comp.sketches during edit).
  2. Call noodle_base_feature.finishEdit() to open the timeline temporarily.
  3. Run pipeFeatures.add() → copy each body to a TemporaryBRep → deleteMe().
  4. Call noodle_base_feature.startEdit() to re-enter the edit.
  5. Commit each BRep with bRepBodies.add(brep, noodle_base_feature).

No pre-pass, no double Interpolize, fully self-contained.

Chain selection is always disabled (noChainedCurves) because Interpolize
splines are purpose-built and may not be positionally continuous.
Radius is in cm; section_size = radius * 2 (diameter).
"""

from typing import Dict, Any, List

from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel
from ..utilities.geometry_naming import generate_geometry_name


@enforce_node_spec
class PipeNode(BaseNode):

    NODE_TYPE = "Pipe"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Pipe"
    NODE_DESCRIPTION = "Create solid tube bodies along interpolated curves"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("curves", PortType.CURVE, required=True,
                        label="Paths",
                        description="Curve collection from Interpolize."),
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("section", PortType.ENUM, default_value="circular",
                         enum_options=["circular", "square", "triangular"],
                         enum_labels={
                             "circular": "Circular",
                             "square": "Square",
                             "triangular": "Triangular",
                         },
                         enum_icons={
                             "circular":    "tool_ui/CircularSection_32x32-dark.svg",
                             "square":      "tool_ui/RectanglarSection_32x32-dark.svg",
                             "triangular":  "tool_ui/TrianglarSection_32x32-dark.svg",
                         },
                         show_input_handle=False,
                         description="Cross-section profile."),
                PortSpec("radius", PortType.FLOAT, min_value=0.001, unit="length", label="Section Size", default_value=0.5,
                         show_input_handle=True,
                         description="Tube radius in cm."),
                PortSpec("hollow", PortType.BOOLEAN, default_value=False,
                         show_input_handle=False,
                         description="Hollow tube with default wall thickness."),
                PortSpec("operation", PortType.ENUM, default_value="newBody",
                         enum_options=["newBody", "add", "cut", "intersect"],
                         enum_icons={
                             "newBody":   "tool_ui/BooleanNewBody_32x32-dark.svg",
                             "add":       "tool_ui/BooleanAdd_32x32-dark.svg",
                             "cut":       "tool_ui/BooleanCut_32x32-dark.svg",
                             "intersect": "tool_ui/BooleanIntersect_32x32-dark.svg",
                         },
                         enum_labels={
                             "newBody": "New Body",
                             "add":     "Join",
                             "cut":     "Cut",
                             "intersect": "Intersect",
                         },
                         show_input_handle=False,
                         description="Boolean operation for each pipe body."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("bodies", PortType.GEOMETRY,
                         description="Pipe solid bodies"),
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
            log(app, "Pipe: no curves input, skipping", level=LogLevel.WARNING, module="PIPE")
            return {"bodies": {"kind": "pipe_bodies", "id": self.id, "body_count": 0}}

        noodle_base_feature = context.get("base_feature") or context.get("noodle_base_feature")
        if not noodle_base_feature:
            raise ValueError("No BaseFeature available for Pipe execute()")

        radius_cm = float(inputs.get("radius", 0.5))
        section_size_cm = radius_cm * 2.0
        hollow = bool(inputs.get("hollow", False))
        section = inputs.get("section", "circular")
        operation_key = inputs.get("operation", "newBody")

        # Keys must match the enum_options in get_spec()
        _SECTION_MAP = {
            "circular":   adsk.fusion.PipeSectionTypes.CircularPipeSectionType,
            "square":     adsk.fusion.PipeSectionTypes.SquarePipeSectionType,
            "triangular": adsk.fusion.PipeSectionTypes.TriangularPipeSectionType,
        }
        _OPERATION_MAP = {
            "newBody":   adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
            "add":       adsk.fusion.FeatureOperations.JoinFeatureOperation,
            "cut":       adsk.fusion.FeatureOperations.CutFeatureOperation,
            "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
        }

        section_type = _SECTION_MAP.get(section, adsk.fusion.PipeSectionTypes.CircularPipeSectionType)
        operation_enum = _OPERATION_MAP.get(operation_key, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        design = adsk.fusion.Design.cast(app.activeProduct)
        root_comp = design.rootComponent

        # Sketch is visible in root_comp.sketches during the BaseFeature edit
        # (created by Interpolize via addToBaseOrFormFeature).
        sketch = None
        for i in range(root_comp.sketches.count):
            s = root_comp.sketches.item(i)
            if s.name == sketch_name:
                sketch = s
                break

        if sketch is None:
            log(app, f"Pipe: sketch '{sketch_name}' not found", level=LogLevel.ERROR, module="PIPE")
            return {"bodies": {"kind": "pipe_bodies", "id": self.id, "body_count": 0}}

        splines = sketch.sketchCurves.sketchFittedSplines
        log(app, f"Pipe: processing {splines.count} splines from '{sketch_name}'",
            level=LogLevel.INFO, module="PIPE")

        # Capture spline references before leaving the edit session.
        spline_refs = [splines.item(i) for i in range(splines.count)]

        # ── Phase 1: exit edit, create pipe features on open timeline ──────────
        # pipeFeatures.add() inside a BaseFeature edit flushes to the main
        # timeline on finishEdit instead of landing inside the BF.  We must
        # temporarily close the edit session to run pipeFeatures.add() safely.
        noodle_base_feature.finishEdit()

        pipe_features_col = root_comp.features.pipeFeatures
        temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        temp_breps = []

        try:
            for i, spline in enumerate(spline_refs):
                pipe_feat = None
                try:
                    path = adsk.fusion.Path.create(
                        spline,
                        adsk.fusion.ChainedCurveOptions.noChainedCurves
                    )
                    pipe_input = pipe_features_col.createInput(path, operation_enum)
                    pipe_input.sectionSize = adsk.core.ValueInput.createByReal(section_size_cm)
                    pipe_input.sectionType = section_type
                    pipe_input.isHollow = hollow

                    pipe_feat = pipe_features_col.add(pipe_input)
                    for j in range(pipe_feat.bodies.count):
                        temp_breps.append(temp_brep_mgr.copy(pipe_feat.bodies.item(j)))
                    pipe_feat.deleteMe()
                except Exception as e:
                    log(app, f"Pipe: spline {i} failed: {e}", level=LogLevel.ERROR, module="PIPE")
                    if pipe_feat is not None:
                        try:
                            pipe_feat.deleteMe()
                        except Exception:
                            pass
        finally:
            # ── Phase 2: re-enter edit, commit BReps into BaseFeature ──────────
            noodle_base_feature.startEdit()

        brep_bodies = root_comp.bRepBodies
        body_count = 0
        for brep in temp_breps:
            try:
                body_name = generate_geometry_name("pipe", self.id, "Pipe", index=body_count)
                new_body = brep_bodies.add(brep, noodle_base_feature)
                new_body.name = body_name
                self._register_body_name(context, body_name)
                body_count += 1
            except Exception as e:
                log(app, f"Pipe: failed to commit body {body_count}: {e}",
                    level=LogLevel.ERROR, module="PIPE")

        log(app, f"Pipe: created {body_count} pipe bodies", level=LogLevel.INFO, module="PIPE")
        return {
            "bodies": {
                "kind": "pipe_bodies",
                "id": self.id,
                "body_count": body_count,
            }
        }
