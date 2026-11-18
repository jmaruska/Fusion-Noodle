"""
3D Point Node - Interactive point selection and position capture.

This node allows users to select points in the scene (construction points, sketch points, 
or points on surfaces) and outputs their 3D position as a Vector3 data type for use 
in other nodes like falloff effectors.

This replaces hardcoded point approaches with flexible point selection. 
user-driven point selection.
"""

from typing import Dict, Any, List, Optional
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType, Vector3Spec
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel

@enforce_node_spec
class Point3DNode(BaseNode):
    """
    3D Point capture node for scene point selection.
    
    Allows users to select any point in the scene (construction points, sketch points,
    surface points) and outputs the 3D position as a Vector3 for use in other nodes
    like falloff effectors or array positioning.
    """
    
    NODE_TYPE = "3D_POINT"
    NODE_CATEGORY = "math"
    NODE_NAME = "3D Point"
    NODE_DESCRIPTION = "Select a point in the scene and output its 3D position"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Define the node specification."""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Point selection input - consistent with surface selection pattern
                PortSpec("point", PortType.POINT, required=True, show_input_handle=False, description="Pick a construction point, sketch point or body vertex in Fusion."),
            ],
            outputs=[
                PortSpec("position", PortType.VECTOR3, description="3D position of the selected point")
            ]
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate point selection inputs."""
        errors = []
        
        point_data = inputs.get('point')
        if not point_data:
            errors.append("Point selection is required")
            
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the 3D point node."""
        app = context.get('app')
        if not app:
            log(app, "No Fusion application context available", level=LogLevel.ERROR, module="3D_POINT")
            return {"position": Vector3Spec(0, 0, 0).to_dict()}
        
        log(app, "=== 3D POINT NODE EXECUTION START ===", level=LogLevel.DEBUG, module="3D_POINT")
        log(app, f"Raw inputs received: {inputs}", level=LogLevel.DEBUG, module="3D_POINT")
        
        point_data = inputs.get('point')
        log(app, f"Point input data type: {type(point_data)}", level=LogLevel.DEBUG, module="3D_POINT")
        log(app, f"Point input data content: {point_data}", level=LogLevel.DEBUG, module="3D_POINT")
        
        if not point_data:
            log(app, "No point selected, using origin", level=LogLevel.WARNING, module="3D_POINT")
            return {"position": Vector3Spec(0, 0, 0).to_dict()}
        
        # Where the picked point is now (it may have moved since it was picked)
        fresh_coordinates = self.current_coordinates(app, point_data)
        
        if fresh_coordinates:
            log(app, f"🔄 FRESH coordinates detected: ({fresh_coordinates[0]:.3f}, {fresh_coordinates[1]:.3f}, {fresh_coordinates[2]:.3f})", 
                level=LogLevel.DEBUG, module="3D_POINT")
            position = Vector3Spec(fresh_coordinates[0], fresh_coordinates[1], fresh_coordinates[2])
            
            # Return both position AND updated coordinates for frontend state update
            result = {
                "position": position.to_dict(),
                "_fresh_coordinates": {  # Signal to frontend that coordinates were refreshed
                    "x": fresh_coordinates[0],
                    "y": fresh_coordinates[1], 
                    "z": fresh_coordinates[2]
                }
            }
        else:
            # Use stored coordinates from node data
            log(app, f"📋 Using stored coordinates from node data", level=LogLevel.DEBUG, module="3D_POINT")
            position = self._extract_point_position(app, point_data)
            result = {"position": position.to_dict()}
        
        log(app, f"Final point position: ({position.x:.3f}, {position.y:.3f}, {position.z:.3f})", 
            level=LogLevel.DEBUG, module="3D_POINT")
        log(app, f"Final output: {result}", level=LogLevel.DEBUG, module="3D_POINT")
        log(app, "=== 3D POINT NODE EXECUTION END ===", level=LogLevel.DEBUG, module="3D_POINT")
        
        return result

    def check_coordinates(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if coordinates have changed without full execution.
        Lightweight method for polling coordinate updates.
        """
        app = context.get('app')
        if not app:
            log(app, "No app context for coordinate check", level=LogLevel.WARNING, module="3D_POINT")
            return {"coordinates": None}
        
        log(app, f"=== 3D POINT COORDINATE CHECK START ===", level=LogLevel.DEBUG, module="3D_POINT") 
        
        point_data = inputs.get('point')
        if not point_data:
            log(app, "No point data for coordinate check", level=LogLevel.DEBUG, module="3D_POINT")
            return {"coordinates": None}
        
        log(app, f"Checking coordinates for point: {point_data.get('entity_token', 'unknown')}", level=LogLevel.DEBUG, module="3D_POINT")
        
        fresh_coordinates = self.current_coordinates(app, point_data)
        stored = tuple(float(point_data.get(axis, 0.0)) for axis in 'xyz') if isinstance(point_data, dict) else None

        # Report a change only when the point really moved. Reporting stale or
        # unchanged coordinates as a change would snap the point back, and makes
        # the palette redo work every poll.
        if fresh_coordinates and (stored is None or any(abs(a - b) > 1e-6 for a, b in zip(fresh_coordinates, stored))):
            log(app, f"🔄 Fresh coordinates detected in check: ({fresh_coordinates[0]:.3f}, {fresh_coordinates[1]:.3f}, {fresh_coordinates[2]:.3f})", 
                level=LogLevel.DEBUG, module="3D_POINT")
            
            result = {
                "coordinates": {
                    "x": fresh_coordinates[0],
                    "y": fresh_coordinates[1], 
                    "z": fresh_coordinates[2]
                },
                "coordinates_changed": True
            }
        else:
            # Return stored coordinates
            position = self._extract_point_position(app, point_data)
            log(app, f"📋 Using stored coordinates: ({position.x:.3f}, {position.y:.3f}, {position.z:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
            
            result = {
                "coordinates": {
                    "x": position.x,
                    "y": position.y,
                    "z": position.z
                },
                "coordinates_changed": False
            }
        
        log(app, f"=== 3D POINT COORDINATE CHECK END: {result} ===", level=LogLevel.DEBUG, module="3D_POINT")
        return result

    def current_coordinates(self, app, point_data: Any) -> Optional[tuple]:
        """Where the picked point is now, in world coordinates, or None if unknown.

        Graphs saved after point_token was added find the exact point by its
        persistent Fusion id. While the user drags that point, Fusion shows the
        drag through the active selection, so the selection is read first, but
        only when it is the same point.

        Older graphs have no point_token and keep the previous guesswork. Pick
        the point again to upgrade them.
        """
        if not isinstance(point_data, dict):
            return None
        token = point_data.get('point_token')
        if token:
            selected = self._selected_point_if(app, token)
            if selected:
                return selected
            return self._resolve_by_point_token(app, token)
        coords = self._get_fresh_coordinates_from_current_selection(app)
        return coords or self._try_resolve_entity_coordinates(app, point_data)

    def _selected_point_if(self, app, token: str) -> Optional[tuple]:
        """Coordinates of the selected entity, only if it is the point with `token`."""
        try:
            selections = app.userInterface.activeSelections
            for i in range(selections.count):
                entity = selections.item(i).entity
                if entity is not None and getattr(entity, 'entityToken', None) == token:
                    return self._extract_world_coordinates_from_entity(app, entity)
        except Exception as e:
            log(app, f"Could not read the selection: {e}", level=LogLevel.DEBUG, module="3D_POINT")
        return None

    def _resolve_by_point_token(self, app, token: str) -> Optional[tuple]:
        """Find the picked point by its persistent Fusion id."""
        try:
            import adsk.fusion  # type: ignore
            design = adsk.fusion.Design.cast(app.activeProduct)
            found = design.findEntityByToken(token) if design else None
            if found and len(found) > 0:
                return self._extract_world_coordinates_from_entity(app, found[0])
            log(app, "The picked point no longer exists; pick it again", level=LogLevel.WARNING, module="3D_POINT")
        except Exception as e:
            log(app, f"Could not find the picked point: {e}", level=LogLevel.DEBUG, module="3D_POINT")
        return None

    def _get_fresh_coordinates_from_current_selection(self, app) -> Optional[tuple]:
        """Fire & Forget approach: Try multiple strategies to get current coordinates."""
        try:
            # Strategy 1: Check if there's a currently selected point
            selected_coords = self._check_current_selection_coordinates(app)
            if selected_coords:
                log(app, f"✅ Fresh coordinates from current selection", level=LogLevel.DEBUG, module="3D_POINT")
                return selected_coords
            
            # Strategy 2: If nothing selected, this method can't help
            # The caller should try entity re-resolution as backup
            log(app, "No current selection for fresh coordinates", level=LogLevel.DEBUG, module="3D_POINT")
            return None
            
        except Exception as e:
            log(app, f"Error getting fresh coordinates from selection: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None
    
    def _try_resolve_entity_coordinates(self, app, point_data: dict) -> Optional[tuple]:
        """Try to resolve current coordinates by finding the entity in the model."""
        try:
            if not isinstance(point_data, dict):
                return None
            
            entity_token = point_data.get('entity_token')
            point_type = point_data.get('point_type')
            
            if not entity_token or not point_type:
                log(app, "Missing entity_token or point_type for resolution", level=LogLevel.DEBUG, module="3D_POINT")
                return None
            
            log(app, f"🔍 Attempting to resolve {point_type} point: {entity_token}", level=LogLevel.DEBUG, module="3D_POINT")
            
            if point_type == 'sketch':
                return self._resolve_sketch_point_by_token(app, entity_token, point_data)
            elif point_type == 'construction': 
                return self._resolve_construction_point_by_token(app, entity_token, point_data)
            else:
                log(app, f"Entity resolution not implemented for point type: {point_type}", level=LogLevel.DEBUG, module="3D_POINT")
                return None
                
        except Exception as e:
            log(app, f"Error resolving entity coordinates: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None
    
    def _resolve_sketch_point_by_token(self, app, entity_token: str, point_data: dict) -> Optional[tuple]:
        """Find a sketch point by entity token and get its current world coordinates."""
        try:
            import adsk.fusion #type: ignore
            
            # Extract sketch name from entity_token (format: sketch_point_{sketch_name}_unknown)
            if 'sketch_point_' not in entity_token:
                log(app, f"Invalid sketch point token format: {entity_token}", level=LogLevel.DEBUG, module="3D_POINT")
                return None
            
            # Parse token to get sketch name
            parts = entity_token.split('_')
            if len(parts) < 3:
                log(app, f"Could not parse sketch name from token: {entity_token}", level=LogLevel.DEBUG, module="3D_POINT")
                return None
                
            sketch_name = parts[2]  # sketch_point_Sketch2_unknown -> "Sketch2"
            log(app, f"Looking for sketch: {sketch_name}", level=LogLevel.DEBUG, module="3D_POINT")
            
            design = app.activeProduct
            if not design:
                return None
                
            root_comp = design.rootComponent
            if not root_comp or not root_comp.sketches:
                return None
            
            # Find the sketch by name
            target_sketch = None
            for i in range(root_comp.sketches.count):
                sketch = root_comp.sketches.item(i)
                if sketch and sketch.name == sketch_name:
                    target_sketch = sketch
                    break
            
            if not target_sketch:
                log(app, f"Could not find sketch: {sketch_name}", level=LogLevel.DEBUG, module="3D_POINT")
                return None
            
            # Get the sketch points and examine them all
            if not target_sketch.sketchPoints or target_sketch.sketchPoints.count == 0:
                log(app, f"No sketch points in {sketch_name}", level=LogLevel.DEBUG, module="3D_POINT")
                return None
            
            log(app, f"Found {target_sketch.sketchPoints.count} points in {sketch_name}", level=LogLevel.DEBUG, module="3D_POINT")
            
            # Examine all points and their coordinates
            best_coords = None
            for j in range(target_sketch.sketchPoints.count):
                sketch_point = target_sketch.sketchPoints.item(j)
                if not sketch_point:
                    continue
                
                # Try multiple coordinate extraction methods
                coords = self._extract_sketch_point_coordinates_robust(app, sketch_point, target_sketch)
                if coords:
                    log(app, f"Point {j}: ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
                    
                    # For now, use the first non-zero coordinates we find
                    # This is better than just taking item(0) which might be at origin
                    if coords != (0.0, 0.0, 0.0) or best_coords is None:
                        best_coords = coords
                        if coords != (0.0, 0.0, 0.0):
                            # Found non-zero coordinates, use these
                            break
                else:
                    log(app, f"Point {j}: could not extract coordinates", level=LogLevel.DEBUG, module="3D_POINT")
            
            if best_coords:
                log(app, f"✅ Re-resolved sketch point in {sketch_name}: ({best_coords[0]:.3f}, {best_coords[1]:.3f}, {best_coords[2]:.3f})", 
                    level=LogLevel.DEBUG, module="3D_POINT")
                return best_coords
            
            log(app, f"❌ No valid coordinates found in sketch {sketch_name}", level=LogLevel.WARNING, module="3D_POINT")
            return None
            
        except Exception as e:
            log(app, f"Error resolving sketch point: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None
    
    def _extract_sketch_point_coordinates_robust(self, app, sketch_point, parent_sketch) -> Optional[tuple]:
        """Extract coordinates from a sketch point using multiple strategies."""
        try:
            log(app, f"Extracting coordinates from sketch point", level=LogLevel.DEBUG, module="3D_POINT")
            
            # Strategy 1: Try worldGeometry first (most reliable when available)
            if hasattr(sketch_point, 'worldGeometry') and sketch_point.worldGeometry:
                geom = sketch_point.worldGeometry
                if hasattr(geom, 'x') and hasattr(geom, 'y') and hasattr(geom, 'z'):
                    coords = (geom.x, geom.y, geom.z)
                    log(app, f"Method 1 (worldGeometry): ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
                    return coords
            
            # Strategy 2: Use geometry and apply sketch transformation
            if hasattr(sketch_point, 'geometry') and sketch_point.geometry:
                geom = sketch_point.geometry
                if hasattr(geom, 'x') and hasattr(geom, 'y') and hasattr(geom, 'z'):
                    import adsk.core #type: ignore
                    
                    # Create 3D point from sketch coordinates
                    local_point = adsk.core.Point3D.create(geom.x, geom.y, 0.0)  # Sketch is 2D, Z=0
                    world_point = local_point.copy()
                    
                    # Apply sketch transformation to get world coordinates
                    if parent_sketch and parent_sketch.transform:
                        world_point.transformBy(parent_sketch.transform)
                        coords = (world_point.x, world_point.y, world_point.z)
                        log(app, f"Method 2 (geometry+transform): ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
                        return coords
                    else:
                        # No transform, use local coordinates
                        coords = (local_point.x, local_point.y, local_point.z)
                        log(app, f"Method 2 (geometry, no transform): ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
                        return coords
            
            # Strategy 3: Try generic extraction method as fallback
            coords = self._extract_world_coordinates_from_entity(app, sketch_point)
            if coords:
                log(app, f"Method 3 (generic): ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
                return coords
            
            log(app, f"❌ All coordinate extraction methods failed", level=LogLevel.WARNING, module="3D_POINT")
            return None
                
        except Exception as e:
            log(app, f"Error in robust coordinate extraction: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None
    
    def _resolve_construction_point_by_token(self, app, entity_token: str, point_data: dict) -> Optional[tuple]:
        """Find a construction point by entity token and get current world coordinates."""
        try:
            import adsk.fusion #type: ignore
            
            design = app.activeProduct
            if not design:
                return None
            
            root_comp = design.rootComponent
            if not root_comp or not root_comp.constructionPoints:
                return None
            
            point_name = point_data.get('point_name', '')
            
            # Search by name (most reliable)
            if point_name:
                for i in range(root_comp.constructionPoints.count):
                    point = root_comp.constructionPoints.item(i)
                    if point and point.isValid and point.name == point_name:
                        coords = self._extract_world_coordinates_from_entity(app, point)
                        if coords:
                            log(app, f"✅ Re-resolved construction point: {point_name}: ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", 
                                level=LogLevel.DEBUG, module="3D_POINT")
                            return coords
            
            return None
            
        except Exception as e:
            log(app, f"Error resolving construction point: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None
    
    def _check_current_selection_coordinates(self, app) -> Optional[tuple]:
        """Check if there's a currently selected point."""
        try:
            import adsk.core #type: ignore
            
            ui = app.userInterface
            if not ui or not ui.activeSelections or ui.activeSelections.count == 0:
                return None
            
            selected_entity = ui.activeSelections.item(0).entity
            if not selected_entity:
                return None
            
            # Check if this is a point-type entity
            entity_type = getattr(selected_entity, 'objectType', 'Unknown')
            if not any(point_type in entity_type for point_type in [
                'ConstructionPoint', 'SketchPoint', 'Vertex', 'BRepVertex'
            ]):
                return None
            
            # Extract coordinates
            coords = self._extract_world_coordinates_from_entity(app, selected_entity)
            return coords
            
        except Exception as e:
            log(app, f"Error checking current selection: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None

    def _extract_point_position(self, app, point_data: Any) -> Vector3Spec:
        """Extract 3D position from a point reference or point data, ALWAYS normalized to world space."""
        try:
            log(app, f"Processing point data: {point_data}", level=LogLevel.DEBUG, module="3D_POINT")
            
            # If point_data is a dict with point data from selection handlers, use it directly
            if isinstance(point_data, dict):
                # Check for direct coordinates (these are already world coordinates from selection handler)
                if all(k in point_data for k in ['x', 'y', 'z']):
                    point_type = point_data.get('point_type', 'unknown')
                    world_coords = (float(point_data['x']), float(point_data['y']), float(point_data['z']))
                    
                    log(app, f"Using world coordinates from selection (already transformed): ({world_coords[0]:.3f}, {world_coords[1]:.3f}, {world_coords[2]:.3f})", level=LogLevel.DEBUG, module="3D_POINT")
                    log(app, f"Point type: '{point_type}' (coordinates are ground truth from selection handler)", level=LogLevel.DEBUG, module="3D_POINT")
                    
                    return Vector3Spec(world_coords[0], world_coords[1], world_coords[2])
                
                # Check for coordinates in point_data sub-dict
                elif 'point_data' in point_data and isinstance(point_data['point_data'], dict):
                    inner_data = point_data['point_data']
                    if all(k in inner_data for k in ['x', 'y', 'z']):
                        log(app, f"Using coordinates from point_data: ({inner_data['x']}, {inner_data['y']}, {inner_data['z']})", level=LogLevel.DEBUG, module="3D_POINT")
                        return Vector3Spec(
                            float(inner_data['x']),
                            float(inner_data['y']),
                            float(inner_data['z'])
                        )
                
                # Check for entity_token for legacy compatibility
                elif 'entity_token' in point_data:
                    log(app, f"Trying to resolve entity_token: {point_data['entity_token']}", level=LogLevel.DEBUG, module="3D_POINT")
                    return self._resolve_entity_token(app, point_data['entity_token'])
            
            # If it's a string, try to resolve from the scene
            elif isinstance(point_data, str):
                log(app, f"Trying to resolve string reference: {point_data}", level=LogLevel.DEBUG, module="3D_POINT")
                return self._resolve_entity_token(app, point_data)
            
            log(app, f"Could not extract coordinates from point data: {point_data}", level=LogLevel.WARNING, module="3D_POINT")
            return Vector3Spec(0, 0, 0)
            
        except Exception as e:
            log(app, f"Error in point position extraction: {e}", level=LogLevel.ERROR, module="3D_POINT")
            return Vector3Spec(0, 0, 0)
    
    def _resolve_entity_token(self, app, entity_token: str) -> Vector3Spec:
        """Resolve entity token to world coordinates."""
        try:
            import adsk.core #type: ignore
            import adsk.fusion #type: ignore
            
            design = app.activeProduct
            if not design:
                log(app, "No active design for token resolution", level=LogLevel.ERROR, module="3D_POINT")
                return Vector3Spec(0, 0, 0)
            
            # Try to resolve construction points
            root_comp = design.rootComponent
            if root_comp and root_comp.constructionPoints:
                for i in range(root_comp.constructionPoints.count):
                    point = root_comp.constructionPoints.item(i)
                    if point and point.isValid:
                        # Check if this matches our reference (by name or entity)
                        if (hasattr(point, 'name') and str(point.name) == str(entity_token)) or \
                           (hasattr(point, 'entityToken') and str(point.entityToken) == str(entity_token)):
                            geometry = point.geometry
                            if geometry:
                                log(app, f"Resolved construction point {entity_token}: ({geometry.x}, {geometry.y}, {geometry.z})", level=LogLevel.DEBUG, module="3D_POINT")
                                return Vector3Spec(
                                    float(geometry.x),
                                    float(geometry.y), 
                                    float(geometry.z)
                                )
            
            # If not found, try to parse as direct coordinates (for debugging/testing)
            if ',' in entity_token:
                try:
                    coords = [float(x.strip()) for x in entity_token.split(',')]
                    if len(coords) >= 3:
                        return Vector3Spec(coords[0], coords[1], coords[2])
                except (ValueError, IndexError):
                    pass
            
            log(app, f"Could not resolve entity token: {entity_token}", level=LogLevel.WARNING, module="3D_POINT")
            return Vector3Spec(0, 0, 0)
            
        except Exception as e:
            log(app, f"Error resolving entity token: {e}", level=LogLevel.ERROR, module="3D_POINT")
            return Vector3Spec(0, 0, 0)
    
            return None

    def _extract_world_coordinates_from_entity(self, app, entity) -> Optional[tuple]:
        """Extract world coordinates from any point entity using Fusion's built-in capabilities."""
        try:
            # Use worldGeometry if available (most reliable)
            if hasattr(entity, 'worldGeometry') and entity.worldGeometry:
                geom = entity.worldGeometry
                if hasattr(geom, 'x') and hasattr(geom, 'y') and hasattr(geom, 'z'):
                    return (geom.x, geom.y, geom.z)
            
            # Fallback: Use geometry with manual transformation  
            if hasattr(entity, 'geometry') and entity.geometry:
                geom = entity.geometry
                if hasattr(geom, 'x') and hasattr(geom, 'y') and hasattr(geom, 'z'):
                    import adsk.core #type: ignore
                    local_point = adsk.core.Point3D.create(geom.x, geom.y, geom.z)
                    world_point = local_point.copy()
                    
                    # Apply parent transformations
                    if hasattr(entity, 'parentSketch') and entity.parentSketch and entity.parentSketch.transform:
                        world_point.transformBy(entity.parentSketch.transform)
                    
                    return (world_point.x, world_point.y, world_point.z)
            
            return None
                    
        except Exception as e:
            log(app, f"Error extracting coordinates from entity: {e}", level=LogLevel.DEBUG, module="3D_POINT")
            return None
