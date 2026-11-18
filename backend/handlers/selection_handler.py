"""
Selection handler - manages geometry selection workflows.
Spec-compliant implementation with robust selection patterns.

CRITICAL: All response formats MUST comply with SelectionPatternSpec in specification.py
Frontend SelectionButton depends on exact field names and state transitions.
"""

from typing import Dict, Any, Optional
import time
import adsk.core #type: ignore
import adsk.fusion #type: ignore
from ..utilities.log_utils import log
from ..specification import LogLevel

class SelectionHandler:
    """Handles surface and body selection workflows"""

    # Messages this handler accepts, and the method that answers each.
    # The core builds its routing table from these (see Application._build_routes),
    # so adding a message means adding one line here and nowhere else.
    ACTIONS = {
        'selectSurface': '_select_surface',
        'checkSurfaceSelection': '_check_surface_selection',
        'selectBody': '_select_body',
        'checkBodySelection': '_check_body_selection',
        'selectPoint': '_select_point',
        'checkPointSelection': '_check_point_selection',
        'selectCurve': '_select_curve',
        'checkCurveSelection': '_check_curve_selection',
        'cancelSelection': '_cancel_selection',
    }
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.app = context['app']
        self.ui = context['ui']
        
        # Selection state - persistent across calls
        self.active_selections = {}
        
        log(self.app, "SelectionHandler initialized with robust body selection", 
            level=LogLevel.DEBUG, module="SELECTION_HANDLER")
    
    def handle(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Route selection actions"""
        method_name = self.ACTIONS.get(action)
        if not method_name:
            return {'success': False, 'error': f'Unknown selection action: {action}'}
        handler = getattr(self, method_name)

        kind = self._SELECTION_KINDS.get(action)
        if kind and action.startswith('select'):
            # Only one selection can be pending at a time. The check* handlers clear
            # Fusion's active selection when it is the wrong entity type, so two
            # pending selections would steal each other's picks.
            self._clear_pending()
            return handler(data)

        if kind:
            node_id = data.get('nodeId')
            stored = self.active_selections.get(f"{node_id}:{data.get('portName', 'unknown')}")
            if not (stored and not stored.get('consumed', False)):
                pending = self.active_selections.get(f'{kind}_selection_pending')
                if not pending or pending.get('node_id') != node_id:
                    return {'success': False, 'error': 'Selection was cancelled'}
                age_ms = int(time.time() * 1000) - pending.get('timestamp', 0)
                if age_ms > self.SELECTION_TIMEOUT_MS:
                    self._clear_pending()
                    return {'success': False, 'error': 'Selection timed out'}
            result = handler(data)
            if isinstance(result, dict) and result.get('selection_complete'):
                self.active_selections.pop(f'{kind}_selection_pending', None)
            return result

        return handler(data)

    _SELECTION_KINDS = {
        'selectSurface': 'surface', 'checkSurfaceSelection': 'surface',
        'selectBody': 'body', 'checkBodySelection': 'body',
        'selectPoint': 'point', 'checkPointSelection': 'point',
        'selectCurve': 'curve', 'checkCurveSelection': 'curve',
    }
    SELECTION_TIMEOUT_MS = 35000  # Frontend gives up at 30 s

    def _cancel_selection(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Drop the pending selection (cancel click, timeout, or the node was deleted).

        With a nodeId, only that node's pick is dropped. A late cancel from a
        button that was already replaced must not cancel the newer pick.
        """
        node_id = data.get('nodeId')
        pending = [v for k, v in self.active_selections.items() if k.endswith('_selection_pending')]
        if node_id and pending and all(p.get('node_id') != node_id for p in pending):
            return {'success': True, 'message': 'No pending selection for this node'}
        self._clear_pending()
        return {'success': True, 'message': 'Selection cancelled'}

    def _clear_pending(self) -> None:
        for key in [k for k in self.active_selections if k.endswith('_selection_pending')]:
            del self.active_selections[key]
    
    def _select_surface(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Start surface selection with face detection"""
        try:
            node_id = data.get('nodeId')
            port_name = data.get('portName', 'surface')
            
            if not node_id:
                return {
                    'success': False,
                    'error': 'nodeId is required for surface selection'
                }
            
            log(self.app, f"Surface selection requested for node: {node_id}, port: {port_name}", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # Import Fusion API only in execution layer
            import adsk.core # type: ignore
            import adsk.fusion # type: ignore
            
            # Check if we already have a face selected in the current selection set
            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                target_face = None
                
                # Direct face selection
                if hasattr(selected_entity, 'objectType') and 'BRepFace' in selected_entity.objectType:
                    target_face = selected_entity
                    log(self.app, "Direct face selection detected", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                if target_face:
                    # Extract surface information for immediate use
                    surface_info = self._extract_surface_info(target_face)
                    
                    # Clear the selection to avoid confusion
                    self.ui.activeSelections.clear()
                    
                    log(self.app, f"Surface resolved: {surface_info['display_name']}", 
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    return {
                        'success': True,
                        'surface_data': surface_info,
                        'message': f'Selected surface: {surface_info["display_name"]}'
                    }
                else:
                    # Clear invalid selection and continue to polling mode
                    self.ui.activeSelections.clear()
                    log(self.app, "Selection not a face, clearing", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # No valid pre-selection - set up polling state 
            self.active_selections['surface_selection_pending'] = {
                'node_id': node_id,
                'port_name': port_name,
                'timestamp': int(time.time() * 1000),
                'active': True
            }
            
            log(self.app, f"Surface selection polling activated for node: {node_id}, port: {port_name}", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            return {
                'success': True,
                'message': 'Please select a face in the model. The selection will be detected automatically.',
                'selection_active': True
            }
            
        except Exception as e:
            log(self.app, f"Error in _select_surface: {str(e)}", 
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'success': False,
                'error': f'Surface selection failed: {str(e)}'
            }
    
    def _check_surface_selection(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if user has selected a surface since the selection was initiated"""
        try:
            log(self.app, "Checking for surface selection...", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # First check if we already have a stored result for this node
            node_id = data.get('nodeId', 'unknown')
            port_name = data.get('portName', 'unknown') 
            selection_key = f"{node_id}:{port_name}"
            
            if selection_key in self.active_selections:
                stored_selection = self.active_selections[selection_key]
                if not stored_selection.get('consumed', False):
                    # Return the stored result
                    surface_info = stored_selection['surface_data']
                    log(self.app, f"Returning stored surface selection: {surface_info['display_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    # Mark as consumed to prevent repeated returns
                    stored_selection['consumed'] = True
                    
                    return {
                        'success': True,
                        'surface_data': surface_info,
                        'message': f'Selected surface: {surface_info["display_name"]}',
                        'selection_complete': True
                    }
            
            # Check for valid selection
            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                target_face = None
                
                # Direct face selection
                if hasattr(selected_entity, 'objectType') and 'BRepFace' in selected_entity.objectType:
                    target_face = selected_entity
                    log(self.app, "Direct face selection detected in polling", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                if target_face:
                    # Extract surface information and store for return
                    surface_info = self._extract_surface_info(target_face)
                    
                    # Store the result for immediate return and future polling
                    self.active_selections[selection_key] = {
                        'surface_data': surface_info,
                        'timestamp': int(time.time() * 1000),
                        'consumed': False
                    }
                    
                    # Clear the selection
                    self.ui.activeSelections.clear()
                    
                    log(self.app, f"Surface selected in polling: {surface_info['display_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    return {
                        'success': True,
                        'surface_data': surface_info,
                        'message': f'Selected surface: {surface_info["display_name"]}',
                        'selection_complete': True
                    }
                
                else:
                    # Clear invalid selection
                    self.ui.activeSelections.clear()
                    log(self.app, "Invalid selection cleared during polling", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # No selection yet - return polling status (match body selection format)
            return {
                'success': True,
                'selection_pending': True,
                'message': 'Waiting for surface selection...'
            }
            
        except Exception as e:
            log(self.app, f"Error in _check_surface_selection: {str(e)}", 
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'success': False,
                'error': f'Surface selection check failed: {str(e)}'
            }
    
    def _select_body(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Start body selection with persistent state management"""
        try:
            node_id = data.get('nodeId')
            port_name = data.get('portName', 'body')
            
            if not node_id:
                return {
                    'success': False,
                    'error': 'nodeId is required for body selection'
                }
            
            log(self.app, f"Body selection requested for node: {node_id}, port: {port_name}", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # Import Fusion API only in execution layer
            import adsk.core # type: ignore
            import adsk.fusion # type: ignore
            
            # Check if we already have something selected in the current selection set
            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                target_body = None
                
                # Direct body selection
                if hasattr(selected_entity, 'objectType') and 'BRepBody' in selected_entity.objectType:
                    target_body = selected_entity
                    log(self.app, "Direct body selection detected", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                # Face selection - get parent body
                elif hasattr(selected_entity, 'objectType') and 'BRepFace' in selected_entity.objectType:
                    target_body = selected_entity.body
                    log(self.app, "Face selection detected, converting to parent body", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                # Edge selection - get parent body
                elif hasattr(selected_entity, 'objectType') and 'BRepEdge' in selected_entity.objectType:
                    target_body = selected_entity.body
                    log(self.app, "Edge selection detected, converting to parent body", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                # Vertex selection - get parent body
                elif hasattr(selected_entity, 'objectType') and 'BRepVertex' in selected_entity.objectType:
                    target_body = selected_entity.body
                    log(self.app, "Vertex selection detected, converting to parent body", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                if target_body:
                    # Extract body information for immediate use
                    body_info = self._extract_body_info(target_body)
                    
                    # Clear the selection to avoid confusion
                    self.ui.activeSelections.clear()
                    
                    log(self.app, f"Body resolved: {body_info['body_name']}", 
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    return {
                        'success': True,
                        'body_data': body_info,
                        'message': f'Selected body: {body_info["body_name"]}'
                    }
                else:
                    # Clear invalid selection and continue to polling mode
                    self.ui.activeSelections.clear()
                    log(self.app, "Selection not convertible to body, clearing", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # No valid pre-selection - set up polling state 
            self.active_selections['body_selection_pending'] = {
                'node_id': node_id,
                'port_name': port_name,
                'timestamp': int(time.time() * 1000),
                'active': True
            }
            
            log(self.app, f"Body selection polling activated for node: {node_id}, port: {port_name}", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            return {
                'success': True,
                'message': 'Please select a body in the model. The selection will be detected automatically.',
                'selection_active': True
            }
            
        except Exception as e:
            log(self.app, f"Error in _select_body: {str(e)}", 
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'success': False,
                'error': f'Body selection failed: {str(e)}'
            }
    
    def _check_body_selection(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if user has selected a body since the selection was initiated"""
        try:
            log(self.app, "Checking for body selection...", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # First check if we already have a stored result for this node
            node_id = data.get('nodeId', 'unknown')
            port_name = data.get('portName', 'unknown') 
            selection_key = f"{node_id}:{port_name}"
            
            if selection_key in self.active_selections:
                stored_selection = self.active_selections[selection_key]
                if not stored_selection.get('consumed', False):
                    # Return the stored result
                    body_info = stored_selection['body_data']
                    log(self.app, f"Returning stored selection result: {body_info['body_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    # Mark as consumed to prevent repeated returns (optional)
                    stored_selection['consumed'] = True
                    
                    return {
                        'success': True,
                        'body_data': body_info,
                        'message': f'Selected body: {body_info["body_name"]}',
                        'selection_complete': True
                    }
            
            # Check for valid selection
            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                target_body = None
                
                # Direct body selection
                if hasattr(selected_entity, 'objectType') and 'BRepBody' in selected_entity.objectType:
                    target_body = selected_entity
                    log(self.app, "Direct body selection detected in polling", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                # Face selection - get parent body
                elif hasattr(selected_entity, 'objectType') and 'BRepFace' in selected_entity.objectType:
                    target_body = selected_entity.body
                    log(self.app, "Face selection detected in polling, converting to parent body", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                # Edge selection - get parent body
                elif hasattr(selected_entity, 'objectType') and 'BRepEdge' in selected_entity.objectType:
                    target_body = selected_entity.body
                    log(self.app, "Edge selection detected in polling, converting to parent body", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                # Vertex selection - get parent body
                elif hasattr(selected_entity, 'objectType') and 'BRepVertex' in selected_entity.objectType:
                    target_body = selected_entity.body
                    log(self.app, "Vertex selection detected in polling, converting to parent body", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                
                if target_body:
                    # Extract body information
                    body_info = self._extract_body_info(target_body)
                    
                    # Store the selection result for this node - DON'T clear it immediately
                    node_id = data.get('nodeId', 'unknown')
                    port_name = data.get('portName', 'unknown') 
                    selection_key = f"{node_id}:{port_name}"
                    
                    # Store the result so it can be retrieved multiple times if needed
                    self.active_selections[selection_key] = {
                        'body_data': body_info,
                        'timestamp': int(time.time() * 1000),
                        'consumed': False  # Track if frontend has consumed this
                    }
                    
                    # Clear the Fusion selection to avoid confusion for user
                    self.ui.activeSelections.clear()
                    
                    log(self.app, f"Body resolved in polling: {body_info['body_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    return {
                        'success': True,
                        'body_data': body_info,
                        'message': f'Selected body: {body_info["body_name"]}',
                        'selection_complete': True
                    }
                else:
                    # Unknown selection type - clear and continue waiting
                    self.ui.activeSelections.clear()
                    log(self.app, f"Unknown selection type in polling: {selected_entity.objectType if hasattr(selected_entity, 'objectType') else 'No objectType'}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    return {
                        'success': True,
                        'message': 'Please select a body, face, edge, or vertex',
                        'selection_pending': True
                    }
            
            # No selection yet - still waiting
            return {
                'success': True,
                'message': 'Waiting for body selection...',
                'selection_pending': True
            }
            
        except Exception as e:
            log(self.app, f"Error checking body selection: {str(e)}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'success': False,
                'error': f'Selection check failed: {str(e)}'
            }
    
    def _extract_body_info(self, body_entity) -> Dict[str, Any]:
        """Extract body information for frontend display"""
        try:
            # Get parent component name safely
            component_name = "Root"
            if hasattr(body_entity, 'parentComponent') and body_entity.parentComponent:
                component_name = body_entity.parentComponent.name
            
            # Get body name safely
            body_name = "Unnamed Body"
            if hasattr(body_entity, 'name') and body_entity.name:
                body_name = body_entity.name
            
            # Create entity token using component::body pattern (not tempId)
            # Real timeline bodies don't have tempId, so use name-based token
            entity_token = f"{component_name}::{body_name}"
            
            # Get volume safely
            volume = 0.0
            if hasattr(body_entity, 'volume'):
                try:
                    volume = body_entity.volume
                except Exception:
                    volume = 0.0
            
            # Get face count safely
            face_count = 0
            if hasattr(body_entity, 'faces'):
                try:
                    face_count = body_entity.faces.count
                except Exception:
                    face_count = 0
            
            body_info = {
                'entity_token': entity_token,
                'display_name': body_name,
                'body_name': body_name,
                'volume': volume,
                'face_count': face_count,
                'component_name': component_name
            }
            
            log(self.app, f"Extracted body info: {body_info['body_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            return body_info
            
        except Exception as e:
            log(self.app, f"Error extracting body info: {str(e)}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            
            # Return fallback info
            return {
                'entity_token': 'unknown',
                'display_name': 'Unknown Body',
                'body_name': 'Unknown Body',
                'volume': 0.0,
                'face_count': 0,
                'component_name': 'Unknown'
            }
    
    def _extract_surface_info(self, face_entity) -> Dict[str, Any]:
        """Extract surface/face information for frontend display"""
        try:
            # Get parent body name safely
            body_name = "Unknown Body"
            if hasattr(face_entity, 'body') and face_entity.body and hasattr(face_entity.body, 'name'):
                body_name = face_entity.body.name or "Unnamed Body"
            
            # Get parent component name safely
            component_name = "Root"
            if (hasattr(face_entity, 'body') and face_entity.body and 
                hasattr(face_entity.body, 'parentComponent') and face_entity.body.parentComponent):
                component_name = face_entity.body.parentComponent.name
            
            # tempId is only unique within one body and only for this session, so it is
            # kept for display and as a legacy fallback. face_token is the persistent id.
            entity_token = face_entity.tempId if hasattr(face_entity, 'tempId') else "unknown"
            face_token = getattr(face_entity, 'entityToken', None)
            
            # Get surface area safely
            area = 0.0
            if hasattr(face_entity, 'area'):
                try:
                    area = face_entity.area
                except Exception:
                    area = 0.0
            
            # Get surface type safely
            surface_type = "Unknown"
            if hasattr(face_entity, 'geometry') and hasattr(face_entity.geometry, 'objectType'):
                surface_type = face_entity.geometry.objectType.split('::')[-1]
            
            # Create display name (face-specific)
            # Use entity_token to identify the specific face within the body
            display_name = f"face{entity_token}"
            
            surface_info = {
                'entity_token': entity_token,
                'face_token': face_token,
                'display_name': display_name,
                'body_name': body_name,
                'surface_type': surface_type,
                'area': area,
                'component_name': component_name
            }
            
            log(self.app, f"Extracted surface info: {surface_info['display_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            return surface_info
            
        except Exception as e:
            log(self.app, f"Error extracting surface info: {str(e)}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            
            # Return fallback info
            return {
                'entity_token': 'unknown',
                'display_name': 'Unknown Surface',
                'body_name': 'Unknown Body',
                'surface_type': 'Unknown',
                'area': 0.0,
                'component_name': 'Unknown'
            }

    def _select_point(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Start point selection with construction point, sketch point, and vertex detection"""
        try:
            node_id = data.get('nodeId')
            port_name = data.get('portName', 'point')
            
            if not node_id:
                return {
                    'success': False,
                    'error': 'nodeId is required for point selection'
                }
            
            log(self.app, f"Point selection requested for node: {node_id}, port: {port_name}", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # Import Fusion API only in execution layer
            import adsk.core # type: ignore
            import adsk.fusion # type: ignore
            
            # Check if we already have a point-related entity selected
            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                point_info = self._extract_point_info(selected_entity)
                
                if point_info:
                    # Clear the selection to avoid confusion
                    self.ui.activeSelections.clear()
                    
                    log(self.app, f"Point resolved: {point_info['display_name']}", 
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    response = {
                        'success': True,
                        'point_data': point_info,
                        'entity_token': point_info['entity_token'],
                        'display_name': point_info['display_name'],
                        'message': f'Selected point: {point_info["display_name"]} at ({point_info["x"]:.3f}, {point_info["y"]:.3f}, {point_info["z"]:.3f})'
                    }
                    log(self.app, f"=== POINT SELECTION RESPONSE: {response}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    return response
                else:
                    # Clear invalid selection and continue to polling mode
                    self.ui.activeSelections.clear()
                    log(self.app, "Selection not a point, clearing", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # No valid pre-selection - set up polling state 
            self.active_selections['point_selection_pending'] = {
                'node_id': node_id,
                'port_name': port_name,
                'timestamp': int(time.time() * 1000),
                'active': True
            }
            
            log(self.app, f"Point selection polling activated for node: {node_id}, port: {port_name}", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            return {
                'success': True,
                'message': 'Please select a construction point, sketch point, or vertex. The selection will be detected automatically.',
                'selection_active': True
            }
            
        except Exception as e:
            log(self.app, f"Error in _select_point: {str(e)}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'success': False,
                'error': f'Point selection failed: {str(e)}'
            }
    
    def _check_point_selection(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if user has selected a point since the selection was initiated"""
        try:
            log(self.app, "Checking for point selection...", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # First check if we already have a stored result for this node
            node_id = data.get('nodeId', 'unknown')
            port_name = data.get('portName', 'unknown') 
            selection_key = f"{node_id}:{port_name}"
            
            if selection_key in self.active_selections:
                stored_selection = self.active_selections[selection_key]
                if not stored_selection.get('consumed', False):
                    # Return the stored result
                    point_info = stored_selection['point_data']
                    log(self.app, f"Returning stored point selection: {point_info['display_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    # Mark as consumed to prevent repeated returns
                    stored_selection['consumed'] = True
                    
                    return {
                        'success': True,
                        'point_data': point_info,
                        'entity_token': point_info['entity_token'],
                        'display_name': point_info['display_name'],
                        'message': f'Selected point: {point_info["display_name"]} at ({point_info["x"]:.3f}, {point_info["y"]:.3f}, {point_info["z"]:.3f})',
                        'selection_complete': True
                    }
            
            # Check for valid selection
            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                point_info = self._extract_point_info(selected_entity)
                
                if point_info:
                    # Store the selection result for this node
                    self.active_selections[selection_key] = {
                        'point_data': point_info,
                        'timestamp': int(time.time() * 1000),
                        'consumed': False
                    }
                    
                    # Clear the selection
                    self.ui.activeSelections.clear()
                    
                    log(self.app, f"Point selected in polling: {point_info['display_name']}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    response = {
                        'success': True,
                        'point_data': point_info,
                        'entity_token': point_info['entity_token'],
                        'display_name': point_info['display_name'],
                        'message': f'Selected point: {point_info["display_name"]} at ({point_info["x"]:.3f}, {point_info["y"]:.3f}, {point_info["z"]:.3f})',
                        'selection_complete': True
                    }
                    log(self.app, f"=== POINT POLLING RESPONSE: {response}", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    return response
                
                else:
                    # Clear invalid selection
                    self.ui.activeSelections.clear()
                    log(self.app, "Invalid point selection cleared during polling", level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            # No selection yet - return polling status
            return {
                'success': True,
                'selection_pending': True,
                'message': 'Waiting for point selection...'
            }
            
        except Exception as e:
            log(self.app, f"Error in _check_point_selection: {str(e)}", 
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'success': False,
                'error': f'Point selection check failed: {str(e)}'
            }
    
    def _select_curve(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Start curve selection — accepts BRepEdge or any SketchCurve subtype."""
        try:
            node_id = data.get('nodeId')
            port_name = data.get('portName', 'curve')

            if not node_id:
                return {'success': False, 'error': 'nodeId is required for curve selection'}

            log(self.app, f"Curve selection requested for node: {node_id}, port: {port_name}",
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")

            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                curve_info = self._try_extract_curve(selected_entity)

                if curve_info:
                    self.ui.activeSelections.clear()
                    log(self.app, f"Curve resolved immediately: {curve_info['display_name']}",
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    return {
                        'success': True,
                        'curve_data': curve_info,
                        'message': f'Selected curve: {curve_info["display_name"]}'
                    }
                else:
                    self.ui.activeSelections.clear()
                    log(self.app, "Selection not a supported curve type, clearing",
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")

            self.active_selections['curve_selection_pending'] = {
                'node_id': node_id,
                'port_name': port_name,
                'timestamp': int(time.time() * 1000),
                'active': True
            }

            log(self.app, f"Curve selection polling activated for node: {node_id}, port: {port_name}",
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")

            return {
                'success': True,
                'message': 'Please select a sketch curve or model edge. The selection will be detected automatically.',
                'selection_active': True
            }

        except Exception as e:
            log(self.app, f"Error in _select_curve: {str(e)}",
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {'success': False, 'error': f'Curve selection failed: {str(e)}'}

    def _check_curve_selection(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Poll for curve selection completion."""
        try:
            log(self.app, "Checking for curve selection...",
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")

            node_id = data.get('nodeId', 'unknown')
            port_name = data.get('portName', 'unknown')
            selection_key = f"{node_id}:{port_name}"

            if selection_key in self.active_selections:
                stored = self.active_selections[selection_key]
                if not stored.get('consumed', False) and 'curve_data' in stored:
                    curve_info = stored['curve_data']
                    stored['consumed'] = True
                    return {
                        'success': True,
                        'curve_data': curve_info,
                        'message': f'Selected curve: {curve_info["display_name"]}',
                        'selection_complete': True
                    }

            selection = self.ui.activeSelections
            if selection.count > 0:
                selected_entity = selection.item(0).entity
                curve_info = self._try_extract_curve(selected_entity)

                if curve_info:
                    self.active_selections[selection_key] = {
                        'curve_data': curve_info,
                        'timestamp': int(time.time() * 1000),
                        'consumed': False
                    }
                    self.ui.activeSelections.clear()

                    log(self.app, f"Curve selected in polling: {curve_info['display_name']}",
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")

                    return {
                        'success': True,
                        'curve_data': curve_info,
                        'message': f'Selected curve: {curve_info["display_name"]}',
                        'selection_complete': True
                    }
                else:
                    self.ui.activeSelections.clear()
                    log(self.app, "Non-curve selection cleared during curve polling",
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")

            return {
                'success': True,
                'selection_pending': True,
                'message': 'Waiting for curve selection...'
            }

        except Exception as e:
            log(self.app, f"Error in _check_curve_selection: {str(e)}",
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {'success': False, 'error': f'Curve selection check failed: {str(e)}'}

    def _try_extract_curve(self, entity) -> Optional[Dict[str, Any]]:
        """Classify a selected entity as a curve type and extract metadata, or return None."""
        if not entity:
            return None

        object_type = getattr(entity, 'objectType', '') or ''

        # Reject points — not curves
        if 'SketchPoint' in object_type or 'ConstructionPoint' in object_type or 'BRepVertex' in object_type:
            log(self.app, f"Rejected point entity: {object_type}",
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            return None

        if 'BRepEdge' in object_type:
            return self._extract_curve_info_brep_edge(entity)

        # Accept any SketchCurve subtype: SketchLine, SketchArc, SketchCircle,
        # SketchEllipse, SketchFittedSpline, SketchFixedSpline, SketchConicCurve, etc.
        # Construction flag is intentionally NOT used as a filter — construction arcs,
        # lines, and splines are all valid path curves. The entity's objectType is
        # included in the display name so the user can verify exactly what was selected.
        if hasattr(entity, 'parentSketch') and entity.parentSketch is not None:
            return self._extract_curve_info_sketch_curve(entity)

        log(self.app, f"Unrecognised curve entity type: {object_type}",
            level=LogLevel.DEBUG, module="SELECTION_HANDLER")
        return None

    def _extract_curve_info_brep_edge(self, edge) -> Optional[Dict[str, Any]]:
        """Extract curve info from a BRepEdge, including component hierarchy for world-space re-resolution."""
        try:
            entity_token = getattr(edge, 'entityToken', 'unknown')

            body_name = 'Unknown Body'
            component_name = 'Root'
            occurrence_path = ''

            if hasattr(edge, 'body') and edge.body:
                body_name = edge.body.name or 'Unnamed Body'
                if hasattr(edge.body, 'parentComponent') and edge.body.parentComponent:
                    component_name = edge.body.parentComponent.name

            # Capture occurrence path so the node can reconstruct the world transform
            # at execution time (handles moved components correctly).
            if hasattr(edge, 'assemblyContext') and edge.assemblyContext:
                try:
                    occurrence_path = edge.assemblyContext.fullPathName
                except Exception:
                    occurrence_path = ''

            display_name = f"Edge ({component_name}::{body_name})"

            length = 0.0
            if hasattr(edge, 'evaluator'):
                try:
                    ev = edge.evaluator
                    ok, t0, t1 = ev.getParameterExtents()
                    if ok:
                        ok2, length = ev.getLengthAtParameter(t0, t1)
                        if not ok2:
                            length = 0.0
                except Exception:
                    length = 0.0

            return {
                'entity_token': entity_token,
                'curve_type': 'brep_edge',
                'display_name': display_name,
                'body_name': body_name,
                'component_name': component_name,
                'occurrence_path': occurrence_path,
                'sketch_name': '',
                'curve_index': -1,
                'length': round(length, 4)
            }

        except Exception as e:
            log(self.app, f"Error extracting BRepEdge info: {e}",
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return None

    def _extract_curve_info_sketch_curve(self, curve) -> Optional[Dict[str, Any]]:
        """Extract curve info from a SketchCurve subtype."""
        try:
            sketch = curve.parentSketch
            sketch_name = sketch.name if sketch and sketch.name else 'Unknown Sketch'

            component_name = 'Root'
            occurrence_path = ''
            if sketch and hasattr(sketch, 'parentComponent') and sketch.parentComponent:
                component_name = sketch.parentComponent.name

            # Find this curve's index within sketchCurves (for stable re-lookup by index)
            curve_index = 0
            temp_id = getattr(curve, 'tempId', None)
            if sketch and temp_id is not None:
                try:
                    curves_collection = sketch.sketchCurves
                    for i in range(curves_collection.count):
                        if curves_collection.item(i).tempId == temp_id:
                            curve_index = i
                            break
                except Exception:
                    curve_index = 0

            # Capture occurrence path if this sketch lives inside a sub-component occurrence
            if hasattr(sketch, 'assemblyContext') and sketch.assemblyContext:
                try:
                    occurrence_path = sketch.assemblyContext.fullPathName
                except Exception:
                    occurrence_path = ''

            # Prefer the stable entityToken; fall back to a synthesized key only if absent.
            entity_token = getattr(curve, 'entityToken', None) or \
                f"sketch_{sketch_name}_{temp_id if temp_id is not None else curve_index}"

            # Include specific subtype (e.g. SketchFittedSpline vs SketchLine) in the
            # display name so the user can verify they selected the intended entity.
            object_type = getattr(curve, 'objectType', '') or ''
            curve_subtype = object_type.split('::')[-1] if object_type else 'Curve'
            is_construction = getattr(curve, 'isConstruction', False)
            construction_tag = ' [construction]' if is_construction else ''
            display_name = f"{curve_subtype}{construction_tag} ({sketch_name})"

            length = 0.0
            if hasattr(curve, 'geometry') and hasattr(curve.geometry, 'evaluator'):
                try:
                    ev = curve.geometry.evaluator
                    ok, t0, t1 = ev.getParameterExtents()
                    if ok:
                        ok2, length = ev.getLengthAtParameter(t0, t1)
                        if not ok2:
                            length = 0.0
                except Exception:
                    length = 0.0

            return {
                'entity_token': entity_token,
                'curve_type': 'sketch_curve',
                'object_type': object_type,
                'display_name': display_name,
                'body_name': '',
                'component_name': component_name,
                'occurrence_path': occurrence_path,
                'sketch_name': sketch_name,
                'curve_index': curve_index,
                'temp_id': temp_id,
                'length': round(length, 4)
            }

        except Exception as e:
            log(self.app, f"Error extracting SketchCurve info: {e}",
                level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return None

    def _extract_point_info(self, entity) -> Optional[Dict[str, Any]]:
        """Extract point information and world coordinates from any point entity."""
        try:
            if not entity:
                return None
            
            # Get world coordinates directly from Fusion - simple and reliable
            world_coords = self._get_world_coordinates(entity)
            if not world_coords:
                return None
            
            # Get display information
            entity_type = getattr(entity, 'objectType', 'Unknown')
            display_info = self._get_point_display_info(entity, entity_type)
            
            log(self.app, f"🌍 Point selected: {display_info['display_name']} at world ({world_coords[0]:.3f}, {world_coords[1]:.3f}, {world_coords[2]:.3f})", 
                level=LogLevel.DEBUG, module="SELECTION_HANDLER")
            
            return {
                'entity_token': display_info['entity_token'],
                # Fusion's persistent id for exactly this point. The 3D Point node
                # finds the point by it, so moving the point is followed exactly.
                'point_token': getattr(entity, 'entityToken', None),
                'point_name': display_info['point_name'],
                'display_name': display_info['display_name'],
                'x': float(world_coords[0]),
                'y': float(world_coords[1]),
                'z': float(world_coords[2]),
                'point_type': display_info['point_type']
            }
            
        except Exception as e:
            log(self.app, f"Error extracting point info: {str(e)}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return None
    
    def _get_world_coordinates(self, entity) -> Optional[tuple]:
        """Get world coordinates for any point entity - unified approach."""
        try:
            # Strategy 1: Use worldGeometry if available (most reliable)
            if hasattr(entity, 'worldGeometry') and entity.worldGeometry:
                geom = entity.worldGeometry
                if hasattr(geom, 'x') and hasattr(geom, 'y') and hasattr(geom, 'z'):
                    coords = (geom.x, geom.y, geom.z)
                    log(self.app, f"✅ Used worldGeometry: ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})", 
                        level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    return coords
            
            # Strategy 2: Transform geometry using entity's transformation
            if hasattr(entity, 'geometry') and entity.geometry:
                geom = entity.geometry
                if hasattr(geom, 'x') and hasattr(geom, 'y') and hasattr(geom, 'z'):
                    # Create point and transform to world space
                    local_point = adsk.core.Point3D.create(geom.x, geom.y, geom.z)
                    world_point = local_point.copy()
                    
                    # Apply transformations based on entity context
                    if hasattr(entity, 'parentSketch') and entity.parentSketch and entity.parentSketch.transform:
                        world_point.transformBy(entity.parentSketch.transform)
                        log(self.app, f"✅ Transformed sketch point: local({geom.x:.3f}, {geom.y:.3f}, {geom.z:.3f}) → world({world_point.x:.3f}, {world_point.y:.3f}, {world_point.z:.3f})", 
                            level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    elif hasattr(entity, 'assemblyContext') and entity.assemblyContext and entity.assemblyContext.transform:
                        world_point.transformBy(entity.assemblyContext.transform)
                        log(self.app, f"✅ Transformed component point: local({geom.x:.3f}, {geom.y:.3f}, {geom.z:.3f}) → world({world_point.x:.3f}, {world_point.y:.3f}, {world_point.z:.3f})", 
                            level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    else:
                        log(self.app, f"✅ Used geometry directly (assumed world coords): ({geom.x:.3f}, {geom.y:.3f}, {geom.z:.3f})", 
                            level=LogLevel.DEBUG, module="SELECTION_HANDLER")
                    
                    return (world_point.x, world_point.y, world_point.z)
            
            log(self.app, f"❌ Could not extract coordinates from entity: {getattr(entity, 'objectType', 'Unknown')}", 
                level=LogLevel.WARNING, module="SELECTION_HANDLER")
            return None
                    
        except Exception as e:
            log(self.app, f"❌ Error getting world coordinates: {e}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return None
    
    def _get_point_display_info(self, entity, entity_type: str) -> Dict[str, str]:
        """Get display information for a point entity."""
        try:
            # Default values
            display_name = "Point"
            point_name = "Point"
            entity_token = "unknown"
            point_type = "unknown"
            
            if 'ConstructionPoint' in entity_type:
                point_type = 'construction'
                entity_token = getattr(entity, 'entityToken', getattr(entity, 'name', 'unknown'))
                point_name = getattr(entity, 'name', 'Construction Point')
                display_name = point_name
                
            elif 'SketchPoint' in entity_type or 'Point' in entity_type:
                point_type = 'sketch'
                sketch_name = "Unknown Sketch"
                if hasattr(entity, 'parentSketch') and entity.parentSketch:
                    sketch_name = entity.parentSketch.name
                
                entity_token = f"sketch_point_{sketch_name}_{getattr(entity, 'tempId', 'unknown')}"
                point_name = f"Point in {sketch_name}"
                display_name = f"Sketch Point ({sketch_name})"
                
            elif 'BRepVertex' in entity_type:
                point_type = 'vertex'
                body_name = "Unknown Body"
                if hasattr(entity, 'body') and entity.body:
                    body_name = entity.body.name
                
                entity_token = f"vertex_{body_name}_{getattr(entity, 'tempId', 'unknown')}"
                point_name = f"Vertex on {body_name}"
                display_name = f"Vertex ({body_name})"
                
            elif 'Face' in entity_type:
                point_type = 'face_center'
                body_name = entity.body.name if hasattr(entity, 'body') and entity.body else "Unknown Body"
                entity_token = f"face_center_{body_name}_{getattr(entity, 'tempId', 'unknown')}"
                point_name = f"Face Center on {body_name}"
                display_name = f"Face Center ({body_name})"
            
            return {
                'entity_token': entity_token,
                'point_name': point_name,
                'display_name': display_name,
                'point_type': point_type
            }
            
        except Exception as e:
            log(self.app, f"❌ Error getting display info: {e}", level=LogLevel.ERROR, module="SELECTION_HANDLER")
            return {
                'entity_token': 'unknown',
                'point_name': 'Unknown Point',
                'display_name': 'Unknown Point',
                'point_type': 'unknown'
            }
