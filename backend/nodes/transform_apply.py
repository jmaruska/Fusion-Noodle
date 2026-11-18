"""
Apply Transform Node - V2 Implementation

Bakes a transform directly into seed geometry, redefining that geometry's
relationship to the world origin.

Pipeline position:  Geometry node → Apply Transform → Atomizer → Arrays/Effectors

Key behaviour:
  The transform is applied to the geometry's BRep body BEFORE it enters a
  collection.  When the materializer later copies the body for each instance,
  every copy already starts from the baked-in reference frame.  Scale/rotate
  operations in downstream effectors therefore operate relative to the NEW
  origin rather than the original geometry center.

Typical use case:
  A box node draws from its center.  Apply Transform can offset the box by
  half its length along +Z so the back face sits at the origin.  Surface-array
  instances then place each box with its back face kissing the surface rather
  than penetrating it.
"""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode


@enforce_node_spec
class ApplyTransformNode(BaseNode):
    """
    Bakes a transform matrix into the seed geometry BRep, redefining its origin.

    The input geometry body is copied, the transform is applied to the copy,
    and the modified copy is returned as the output geometry.  The original
    BRep is never mutated.
    """

    NODE_TYPE = "Apply_Transform"
    NODE_CATEGORY = "transform"
    NODE_NAME = "Apply Transform"
    NODE_DESCRIPTION = "Bake a transform into seed geometry, redefining its origin relationship"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("geometry", PortType.GEOMETRY, required=True, label="Geometry", description="The body to bake the transform into."),
                PortSpec("transform", PortType.TRANSFORM, required=True, label="Transform", description="The move, rotate, scale or aim to bake in; an aim turns the body about its centre toward the target."),
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("geometry", PortType.GEOMETRY, label="Geometry"),
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        if not inputs.get("geometry"):
            errors.append("Geometry input is required")
        if not inputs.get("transform"):
            errors.append("Transform input is required")
        return errors

    @staticmethod
    def _aim_matrix(brep, aim: Dict[str, Any]):
        """The rotation about the body's bounding-box centre that turns its aim axis toward
        the aim position, or None when there's nothing to turn (target at the centre)."""
        import adsk.core
        from ..utilities.vector_math import aim_rotation
        box = brep.boundingBox
        centre = ((box.minPoint.x + box.maxPoint.x) / 2, (box.minPoint.y + box.maxPoint.y) / 2,
                  (box.minPoint.z + box.maxPoint.z) / 2)
        axis = aim.get("aim_axis") or {}
        target = aim.get("aim_position") or {}
        turn = aim_rotation(centre, (axis.get("x", 0.0), axis.get("y", 1.0), axis.get("z", 0.0)),
                            (target.get("x", 0.0), target.get("y", 0.0), target.get("z", 0.0)))
        if turn is None:
            return None
        angle, (rx, ry, rz) = turn
        matrix = adsk.core.Matrix3D.create()
        matrix.setToRotation(angle, adsk.core.Vector3D.create(rx, ry, rz),
                             adsk.core.Point3D.create(*centre))
        return matrix

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        import adsk.core
        import adsk.fusion

        app = adsk.core.Application.get()
        log(app, "*** EXECUTING APPLY TRANSFORM NODE ***",
            level=LogLevel.DEBUG, module="APPLY_TRANSFORM")

        geometry_data = inputs.get("geometry")
        transform_data = inputs.get("transform")

        if not geometry_data or not transform_data:
            log(app, "Apply Transform: missing geometry or transform input — passing through unchanged",
                level=LogLevel.WARNING, module="APPLY_TRANSFORM")
            return {"geometry": geometry_data}

        # Unpack geometry envelope (always arrives as a dict from upstream nodes)
        if isinstance(geometry_data, dict):
            source_brep = geometry_data.get("geometry")
            geo_kind = geometry_data.get("kind", "brep")
            geo_id = geometry_data.get("id", "unknown")
            geo_name = geometry_data.get("geometry_name", "Unknown")
            geo_meta = geometry_data.get("metadata", {})
        elif hasattr(geometry_data, "geometry"):
            source_brep = geometry_data.geometry
            geo_kind = getattr(geometry_data, "kind", "brep")
            geo_id = getattr(geometry_data, "id", "unknown")
            geo_name = getattr(geometry_data, "geometry_name", "Unknown")
            geo_meta = getattr(geometry_data, "metadata", {})
        else:
            log(app, "Apply Transform: unrecognised geometry format — passing through unchanged",
                level=LogLevel.WARNING, module="APPLY_TRANSFORM")
            return {"geometry": geometry_data}

        if source_brep is None:
            log(app, "Apply Transform: geometry envelope contains no BRep body",
                level=LogLevel.WARNING, module="APPLY_TRANSFORM")
            return {"geometry": geometry_data}

        # Extract the 4×4 matrix from the transform dict
        if isinstance(transform_data, dict):
            transform_matrix = transform_data.get("transform_matrix")
        else:
            transform_matrix = None

        # An Aim carries a target, not a matrix: turn the body about its own centre so
        # its aim axis points at the target, as the Aim effector does per instance
        aim_matrix = None
        if not transform_matrix and isinstance(transform_data, dict) and transform_data.get("transform_type") == "aim":
            aim_matrix = self._aim_matrix(source_brep, transform_data)

        if not transform_matrix and aim_matrix is None:
            log(app, "Apply Transform: transform contains no matrix — passing through unchanged",
                level=LogLevel.WARNING, module="APPLY_TRANSFORM")
            return {"geometry": geometry_data}

        try:
            temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()

            # Copy the source body so we never mutate upstream geometry
            modified_brep = temp_brep_mgr.copy(source_brep)

            # Apply the full 4×4 matrix to the copy
            if aim_matrix is not None:
                temp_brep_mgr.transform(modified_brep, aim_matrix)
            else:
                from ..utilities.transform_utils import apply_matrix_dict_to_brep
                apply_matrix_dict_to_brep(temp_brep_mgr, modified_brep, transform_matrix, app)

            operation_chain = transform_data.get("operation_chain", [])
            log(app, f"Apply Transform: baked transform ({' → '.join(operation_chain) or 'identity'}) "
                     f"into geometry '{geo_name}'",
                level=LogLevel.DEBUG, module="APPLY_TRANSFORM")

            baked_meta = dict(geo_meta)
            baked_meta.update({
                "transform_baked": True,
                "baked_operation_chain": operation_chain,
                "source_geometry_id": geo_id,
            })

            # If the source is a persistent document body (not already a temp brep),
            # update it in-place via BaseFeature so it's visible in the document
            # even when Apply Transform is a terminal node (no Atomizer downstream).
            base_feature = context.get('base_feature') or context.get('noodle_base_feature')
            output_body = modified_brep
            if base_feature and not geo_id.startswith("baked_"):
                try:
                    base_feature.updateBody(source_brep, modified_brep)
                    output_body = source_brep  # persistent body now has the new shape
                    log(app, f"Apply Transform: updated persistent body '{geo_name}' via BaseFeature",
                        level=LogLevel.DEBUG, module="APPLY_TRANSFORM")
                except Exception as ub_e:
                    log(app, f"Apply Transform: updateBody unavailable ({ub_e}), returning temp brep for pipeline use",
                        level=LogLevel.DEBUG, module="APPLY_TRANSFORM")

            return {
                "geometry": {
                    "kind": geo_kind,
                    "id": f"baked_{geo_id}",
                    "geometry": output_body,
                    "geometry_name": geo_name,
                    "metadata": baked_meta,
                }
            }

        except Exception as e:
            import traceback
            log(app, f"Apply Transform: error — {e}\n{traceback.format_exc()}",
                level=LogLevel.ERROR, module="APPLY_TRANSFORM")
            return {"geometry": geometry_data}
