"""
Base Effector Node - V2 Implementation

Abstract base class for all effector nodes that apply transforms to collections.
Provides shared logic for transform application, with subclasses implementing
different strength calculation strategies (uniform, falloff, etc.).
"""

import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
from ..contracts import (
    NodeSpec, PortSpec, PortType, CollectionSpec, CollectionInstanceSpec, 
    GeometryEnvelope, NoodleAttributes, Vector3Spec
)
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log, LogLevel
from .base import BaseNode


# Instance metadata key: {effector node id: strength applied to this instance}
EFFECTOR_STRENGTHS_KEY = 'effector_strengths'

class BaseEffectorNode(BaseNode, ABC):
    """
    Abstract base class for effector nodes.
    
    Provides shared transform application logic with customizable strength calculation.
    Subclasses must implement calculate_strength() to define how transform strength
    is determined for each instance (uniform, spatial falloff, etc.).
    """    
    # No NODE_TYPE, NODE_CATEGORY, etc. for abstract base class
    @abstractmethod
    def calculate_strength(self, instance: CollectionInstanceSpec, transform_data: Dict[str, Any], 
                          context: Dict[str, Any]) -> float:
        """
        Calculate the strength (0.0 to 1.0) to apply the transform to this instance.
        
        Args:
            instance: The collection instance to transform
            transform_data: The transform to apply
            context: Execution context
            
        Returns:
            Strength value between 0.0 (no effect) and 1.0 (full effect)
        """
        pass

    def _resolve_number(self, value: Any, instance_index: int,
                        instance: Any = None) -> float:
        """Resolve a FLOAT port value to a float for a specific instance.

        Accepts:
          - plain float/int    → same value for all instances
          - random descriptor  → unique value per instance (seed + index)
          - noise descriptor   → value sampled at instance world position
          - modifier descriptor → per-instance pattern value, unbounded (may be negative)
        Nothing is clamped: a negative strength pushes the other way, whatever its source.
        """
        import random as _random

        if not isinstance(value, dict):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 1.0

        # Modifier protocol — per-instance evaluation, no clamping (negatives are intentional).
        if "modifier_type" in value:
            from ..utilities.modifier_utils import evaluate_modifier
            meta = {}
            if instance is not None:
                meta = (instance.metadata
                        if hasattr(instance, "metadata")
                        else instance.get("metadata", {})) or {}
            return evaluate_modifier(value, meta)

        number_type = value.get("number_type")

        if number_type == "random":
            mn   = float(value.get("min",  0.0))
            mx   = float(value.get("max",  1.0))
            seed = int(value.get("seed",   0))
            rng  = _random.Random(seed + instance_index)
            return rng.uniform(mn, mx)

        if number_type == "noise":
            from ..utilities.noise_utils import build_perm_table, noise3_range
            seed        = int(value.get("seed",        0))
            frequency   = float(value.get("frequency", 1.0))
            octaves     = int(value.get("octaves",     1))
            lacunarity  = float(value.get("lacunarity", 2.0))
            persistence = float(value.get("persistence", 0.5))
            mn          = float(value.get("min",        0.0))
            mx          = float(value.get("max",        1.0))

            perm = build_perm_table(seed)

            if instance is not None:
                pos = self._extract_position_from_instance(instance)
                x, y, z = pos.x, pos.y, pos.z
            else:
                x, y, z = float(instance_index), 0.0, 0.0

            return (noise3_range(x, y, z, perm,
                                         octaves=octaves,
                                         frequency=frequency,
                                         lacunarity=lacunarity,
                                         persistence=persistence,
                                         out_min=mn,
                                         out_max=mx))

        # Unknown descriptor — neutral
        return 1.0

    def _extract_position_from_instance(self, instance: CollectionInstanceSpec) -> Vector3Spec:
        """Extract 3D position from an instance's spatial data"""
        try:
            # Handle both dict and CollectionInstanceSpec object formats
            metadata = None
            transform = None
            
            if isinstance(instance, dict):
                metadata = instance.get('metadata', {})
                transform = instance.get('transform', {})
            else:
                # CollectionInstanceSpec object
                metadata = getattr(instance, 'metadata', {})
                transform = getattr(instance, 'transform', {})
            
            # First try to get actual spatial position from array metadata
            if metadata:
                # Check for surface_point (from grid arrays)
                surface_point = metadata.get('surface_point')
                if surface_point and isinstance(surface_point, dict):
                    return Vector3Spec(
                        x=surface_point.get('x', 0.0),
                        y=surface_point.get('y', 0.0),
                        z=surface_point.get('z', 0.0)
                    )
                
            # Fallback to transform position (usually 0,0,0 for array instances)
            if transform:
                if hasattr(transform, 'tx'):
                    # NoodleAttributes format
                    return Vector3Spec(x=transform.tx, y=transform.ty, z=transform.tz)
                elif isinstance(transform, dict):
                    # Dictionary format
                    return Vector3Spec(
                        x=transform.get('tx', 0.0),
                        y=transform.get('ty', 0.0), 
                        z=transform.get('tz', 0.0)
                    )
            
            return Vector3Spec(x=0.0, y=0.0, z=0.0)
                
        except Exception:
            return Vector3Spec(x=0.0, y=0.0, z=0.0)

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute effector transformation with strength-based application"""
        # Get app reference directly - much more reliable than context passing
        import adsk.core
        app = adsk.core.Application.get()
        
        effector_name = self.NODE_TYPE.replace('_', ' ')
        
        # Reset debug counter for new execution
        self._debug_count = 0
        
        log(app, f"*** EXECUTING {effector_name.upper()} NODE *** (inputs keys: {list(inputs.keys())})", 
            level=LogLevel.DEBUG, module="EFFECTOR")
        
        # Get inputs
        input_collection = inputs.get('collection')
        transform_data = inputs.get('transform')
        
        # Log input collection summary
        if input_collection:
            instances = []
            if isinstance(input_collection, dict):
                instances = input_collection.get('instances', [])
            elif hasattr(input_collection, 'instances'):
                instances = input_collection.instances
                
            if instances:
                sample_instance = instances[0]
                if isinstance(sample_instance, dict):
                    sample_transform = sample_instance.get('transform', {})
                    log(app, f"INPUT: {len(instances)} instances, sample sx={sample_transform.get('sx', 'N/A')}, ty={sample_transform.get('ty', 'N/A')}", 
                        level=LogLevel.DEBUG, module="EFFECTOR")
                elif hasattr(sample_instance, 'transform'):
                    # Handle dataclass instance
                    sample_transform = sample_instance.transform
                    sx_val = getattr(sample_transform, 'sx', 'N/A') if hasattr(sample_transform, 'sx') else 'N/A'
                    ty_val = getattr(sample_transform, 'ty', 'N/A') if hasattr(sample_transform, 'ty') else 'N/A'
                    log(app, f"INPUT: {len(instances)} instances, sample sx={sx_val}, ty={ty_val}", 
                        level=LogLevel.DEBUG, module="EFFECTOR")
            else:
                log(app, f"INPUT: empty instances", 
                    level=LogLevel.WARNING, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
        else:
            log(app, f"INPUT COLLECTION: {type(input_collection)}", 
                level=LogLevel.DEBUG, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
        
        log(app, f"{effector_name}: processing with transform type={transform_data.get('transform_type') if transform_data else 'None'}", 
            level=LogLevel.DEBUG, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
        
        # Run validation and log results
        validation_errors = self.validate(inputs)
        if validation_errors:
            log(app, f"{effector_name}: VALIDATION ERRORS: {validation_errors}", 
                level=LogLevel.ERROR, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
            return {"collection": None}
        else:
            log(app, f"{effector_name}: Validation passed", 
                level=LogLevel.DEBUG, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
        
        # Validate inputs
        if not input_collection:
            log(app, f"{effector_name}: Missing collection input", 
                level=LogLevel.WARNING, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
            return {"collection": None}
        
        if not transform_data:
            log(app, f"{effector_name}: No transform input - passing through collection unchanged", 
                level=LogLevel.DEBUG, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
            return {"collection": input_collection}
            
        # Convert MatrixTransformSpec to dict if needed for safe_get compatibility
        if hasattr(transform_data, 'to_dict'):
            transform_data = transform_data.to_dict()
        elif not isinstance(transform_data, dict):
            log(app, f"{effector_name}: Unexpected transform_data type: {type(transform_data)}", 
                level=LogLevel.WARNING, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
            return {"collection": input_collection}
            
        try:
            # Parse input collection - handle both CollectionSpec objects and dicts
            if hasattr(input_collection, 'source_geometries'):
                # It's a CollectionSpec object
                source_geometries_data = input_collection.source_geometries
                input_instances = input_collection.instances
            elif isinstance(input_collection, dict):
                # It's a dictionary (backward compatibility)
                source_geometries_data = input_collection.get("source_geometries", [])
                input_instances = input_collection.get("instances", [])
            else:
                return {"collection": input_collection}
            
            # Now we have source_geometries_data and input_instances
            
            if not source_geometries_data or not input_instances:
                return {"collection": input_collection}
            
            # Convert source geometries to GeometryEnvelope objects
            source_geometries = []
            for i, geo_data in enumerate(source_geometries_data):
                if isinstance(geo_data, dict):
                    try:
                        geo_envelope = GeometryEnvelope(**geo_data)
                        source_geometries.append(geo_envelope)
                    except Exception:
                        return {"collection": input_collection}
                else:
                    source_geometries.append(geo_data)
            
            # Apply transformation to each instance
            transformed_instances = []
            failures = 0
            first_failure = None
            affected_count = 0
            
            for i, instance_data in enumerate(input_instances):
                try:
                    # Convert to CollectionInstanceSpec if needed
                    if isinstance(instance_data, dict):
                        instance = CollectionInstanceSpec.from_dict(instance_data)
                    else:
                        instance = instance_data
                    
                    # Calculate strength using subclass implementation
                    # Add inputs to context for subclass access
                    strength_context = context.copy()
                    strength_context['inputs'] = inputs
                    strength = self.calculate_strength(instance, transform_data, strength_context)

                    # Modulate by the optional strength input (scalar or random descriptor)
                    input_strength = inputs.get('strength', 1.0)
                    strength *= self._resolve_number(input_strength, i, instance)
                    

                    
                    # Count as affected when any meaningful strength is present.
                    # Use abs() so negative modifier values (e.g. Checkerboard -1)
                    # are counted correctly.
                    if abs(strength) > 0.01:
                        affected_count += 1
                    
                    new_metadata = instance.metadata.copy() if instance.metadata else {}
                    new_metadata[f'{self.NODE_TYPE.lower()}_applied'] = True
                    new_metadata[f'{self.NODE_TYPE.lower()}_strength'] = strength

                    # Strength per effector node, kept as instances pass down a chain
                    # of effectors. The visualizer reads this (see backend/visualizer.py).
                    strengths = dict(new_metadata.get(EFFECTOR_STRENGTHS_KEY) or {})
                    strengths[self.id] = strength
                    new_metadata[EFFECTOR_STRENGTHS_KEY] = strengths
                    
                    # Apply transform based on strength and populate materializer metadata
                    new_attributes, materializer_metadata = self._apply_transform_with_strength(
                        instance, transform_data, strength, context
                    )
                    
                    # Merge materializer metadata
                    new_metadata.update(materializer_metadata)
                    
                    # Create new instance with transformed attributes
                    new_instance = CollectionInstanceSpec(
                        instance_id=instance.instance_id,
                        source_geometry_id=instance.source_geometry_id,
                        transform=new_attributes,
                        metadata=new_metadata
                    )
                    
                    transformed_instances.append(new_instance)
                    
                except Exception as e:
                    # Keep going with the untouched instance, and report once below
                    failures += 1
                    if first_failure is None:
                        import traceback
                        first_failure = f"{type(e).__name__}: {e}"
                        log(app, f"Effector failed on instance {i}: {first_failure}\n{traceback.format_exc()}",
                            level=LogLevel.DEBUG, module="EFFECTOR")

                    # Keep original instance on error
                    if isinstance(instance_data, dict):
                        transformed_instances.append(CollectionInstanceSpec.from_dict(instance_data))
                    else:
                        transformed_instances.append(instance_data)
            
            if failures:
                if failures == len(input_instances):
                    # Every instance failed, so the effector did nothing at all
                    raise RuntimeError(f"Effector could not be applied ({first_failure})")
                log(app, f"Effector skipped {failures} of {len(input_instances)} instances. "
                         f"First failure: {first_failure}",
                    level=LogLevel.WARNING, module="EFFECTOR")

            # Create result collection with metadata about the effector operation.
            # Start from upstream collection metadata so structural keys (count_u, count_v,
            # array_type, etc.) survive downstream to nodes like Interpolize.
            collection_id = str(uuid.uuid4())[:8]

            upstream_metadata = {}
            if hasattr(input_collection, 'metadata') and input_collection.metadata:
                upstream_metadata = dict(input_collection.metadata)
            elif isinstance(input_collection, dict):
                upstream_metadata = dict(input_collection.get('metadata', {}))

            effector_metadata = {
                **upstream_metadata,
                'type': self.NODE_TYPE.lower(),
                'transform_type': transform_data.get('transform_type'),
                'affected_instances': affected_count,
                'total_instances': len(transformed_instances),
                'effector_node_id': context.get('node_id', 'unknown')
            }

            result_collection = CollectionSpec(
                collection_type="geometry_collection",
                collection_id=collection_id,
                source_geometries=source_geometries,
                instances=transformed_instances,
                metadata=effector_metadata
            )
            
            log(app, f"{effector_name}: Generated {len(transformed_instances)} instances, {affected_count} affected", 
                level=LogLevel.DEBUG, module="EFFECTOR")
            
            # Log output summary
            if transformed_instances:
                sample_output = transformed_instances[0]
                if hasattr(sample_output, 'transform'):
                    sample_transform = sample_output.transform
                    log(app, f"OUTPUT: sx={getattr(sample_transform, 'sx', 'N/A')}, ty={getattr(sample_transform, 'ty', 'N/A')}", 
                        level=LogLevel.DEBUG, module="EFFECTOR")
            
            return {"collection": result_collection}
                
        except Exception as e:
            import traceback
            log(app, f"Effector failed: {type(e).__name__}: {e}\n{traceback.format_exc()}",
                level=LogLevel.DEBUG, module=f"EFFECTOR_{self.NODE_TYPE.upper()}")
            # Fail the node. Passing the collection through untouched would make
            # a broken effector look like one that simply did nothing.
            raise

    def _apply_aim_with_strength(self, instance: CollectionInstanceSpec,
                                transform_data: Dict[str, Any], strength: float,
                                app) -> Tuple[Any, Dict[str, Any]]:
        """Compute per-instance aim quaternion and blend with strength."""
        import math
        from ..utilities.vector_math import quaternion_rotate_a_to_b, slerp_quaternion

        aim_pos = transform_data.get("aim_position", {"x": 0.0, "y": 0.0, "z": 0.0})
        aim_axis = transform_data.get("aim_axis", {"x": 0.0, "y": 1.0, "z": 0.0})

        ax = float(aim_axis.get("x", 0.0))
        ay = float(aim_axis.get("y", 1.0))
        az = float(aim_axis.get("z", 0.0))

        aim_x = float(aim_pos.get("x", 0.0))
        aim_y = float(aim_pos.get("y", 0.0))
        aim_z = float(aim_pos.get("z", 0.0))

        existing = instance.transform
        if not isinstance(existing, NoodleAttributes):
            existing = NoodleAttributes.identity()

        # Prefer surface_point metadata as the instance world position
        metadata = instance.metadata or {}
        sp = metadata.get("surface_point")
        if sp and isinstance(sp, dict):
            inst_x = float(sp.get("x", 0.0))
            inst_y = float(sp.get("y", 0.0))
            inst_z = float(sp.get("z", 0.0))
        else:
            inst_x, inst_y, inst_z = existing.tx, existing.ty, existing.tz

        dx = aim_x - inst_x
        dy = aim_y - inst_y
        dz = aim_z - inst_z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        if dist < 1e-6:
            # Instance is at the aim point — preserve existing transform unchanged
            return existing, {"aim_skipped": True}

        dx /= dist
        dy /= dist
        dz /= dist

        qx, qy, qz, qw = quaternion_rotate_a_to_b(ax, ay, az, dx, dy, dz)

        if strength < 0.9999:
            # Blend from identity quaternion toward full aim rotation
            qx, qy, qz, qw = slerp_quaternion(0.0, 0.0, 0.0, 1.0, qx, qy, qz, qw, strength)

        new_transform = NoodleAttributes(
            tx=existing.tx, ty=existing.ty, tz=existing.tz,
            rx=0.0, ry=0.0, rz=0.0,
            sx=existing.sx, sy=existing.sy, sz=existing.sz,
            qx=qx, qy=qy, qz=qz, qw=qw,
            use_quaternion=True,
            v=existing.v,
        )

        metadata_out = {
            "aim_applied": True,
            "aim_strength": strength,
        }
        return new_transform, metadata_out

    def _apply_transform_with_strength(self, instance: CollectionInstanceSpec,
                                     transform_data: Dict[str, Any], strength: float,
                                     context: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
        """Apply transform to instance with strength via NoodleAttributes composition."""
        import adsk.core
        app = adsk.core.Application.get()

        # Aim transform is per-instance — handle separately before generic path
        if transform_data.get("transform_type") == "aim":
            return self._apply_aim_with_strength(instance, transform_data, strength, app)

        log(app, f"Effector applying transform with strength={strength}",
            level=LogLevel.DEBUG, module="EFFECTOR")

        effector_attrs = self._convert_transform_to_attributes(transform_data, strength, app)

        if not isinstance(instance.transform, NoodleAttributes):
            instance.transform = NoodleAttributes.identity()

        from ..services.transform_composition_service import TransformCompositionService
        composition_service = TransformCompositionService(app)

        final_attributes = composition_service.compose_noodle_attributes(
            base_attributes=instance.transform,
            new_attributes=effector_attrs
        )

        metadata = {
            'effector_node': self.NODE_TYPE,
            'strength_applied': strength,
            'final_transform_type': 'NoodleAttributes',
        }

        log(app, f"Effector final NoodleAttributes sx={final_attributes.sx:.3f}, "
                 f"tx={final_attributes.tx:.3f}",
            level=LogLevel.DEBUG, module="EFFECTOR")

        return final_attributes, metadata

    def _convert_transform_to_attributes(self, transform_data: Dict[str, Any], strength: float, app) -> NoodleAttributes:
        """Convert transform_data to NoodleAttributes with strength applied"""
        # Start with identity
        attrs = NoodleAttributes.identity()
        
        # Extract values based on transform type
        if transform_data.get('transform_type') == 'matrix_chained':
            # Use composition service to extract from matrix
            from ..services.transform_composition_service import TransformCompositionService
            composition_service = TransformCompositionService(app)
            components = composition_service.extract_transform_components(transform_data)
            
            # Apply strength scaling and set attributes
            attrs.tx = components['translation']['x'] * strength
            attrs.ty = components['translation']['y'] * strength  
            attrs.tz = components['translation']['z'] * strength
            attrs.rx = components['rotation_degrees']['x'] * strength
            attrs.ry = components['rotation_degrees']['y'] * strength
            attrs.rz = components['rotation_degrees']['z'] * strength
            # Scale with strength: 1.0 + (scale_factor - 1.0) * strength
            attrs.sx = 1.0 + (components['scale']['x'] - 1.0) * strength
            attrs.sy = 1.0 + (components['scale']['y'] - 1.0) * strength
            attrs.sz = 1.0 + (components['scale']['z'] - 1.0) * strength
        else:
            # Handle as Maya-style attributes if present
            attrs.tx = transform_data.get('tx', 0.0) * strength
            attrs.ty = transform_data.get('ty', 0.0) * strength
            attrs.tz = transform_data.get('tz', 0.0) * strength
            attrs.rx = transform_data.get('rx', 0.0) * strength
            attrs.ry = transform_data.get('ry', 0.0) * strength
            attrs.rz = transform_data.get('rz', 0.0) * strength
            base_sx = transform_data.get('sx', 1.0)
            base_sy = transform_data.get('sy', 1.0) 
            base_sz = transform_data.get('sz', 1.0)
            attrs.sx = 1.0 + (base_sx - 1.0) * strength
            attrs.sy = 1.0 + (base_sy - 1.0) * strength
            attrs.sz = 1.0 + (base_sz - 1.0) * strength
        
        return attrs
