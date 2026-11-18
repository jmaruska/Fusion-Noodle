"""Body instance geometry node - spec-compliant implementation."""

from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType
from ..utilities.log_utils import log
from ..utilities.selection_port import SelectionMixin, create_selection_port
from ..utilities.geometry_naming import generate_geometry_name
from ..specification import LogLevel
from .base import BaseNode

@enforce_node_spec
class BodyInstanceNode(BaseNode, SelectionMixin):
    """References an existing body in the design for instancing"""
    
    # Required attributes per specification
    NODE_TYPE = "body_instance"
    NODE_CATEGORY = "geometry"
    NODE_NAME = "Body Instance"
    NODE_DESCRIPTION = "Body Instance"
    
    @classmethod
    def get_spec(cls) -> NodeSpec:
        """Return node specification"""
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                # Use reusable selection port utility - hide connection handle
                create_selection_port("body", "body", required=True, show_input_handle=False, description="Pick the body in Fusion to use as source geometry."),
            ],
            outputs=[
                PortSpec("geometry", PortType.GEOMETRY)
            ]
        )
    
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs"""
        errors = []
        
        # Use selection mixin for validation
        body_value = self.resolve_selection_value(inputs, "body", "body")
        if not body_value:
            errors.append("Body selection is required")
        
        return errors
    
    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the body instance node by resolving entity token to actual body"""
        
        # Import Fusion API only in execution layer (allowed per spec)
        import adsk.core # type: ignore
        import adsk.fusion # type: ignore
        
        app = context.get('app') or adsk.core.Application.get()
        
        log(app, "Processing body instance", level=LogLevel.DEBUG, module="INSTANCE_NODE")
        
        # Get the body selection data
        body_data = inputs.get('body')
        
        if not body_data:
            log(app, "No body selected", level=LogLevel.DEBUG, module="INSTANCE_NODE")
            return {"geometry": None}
        
        log(app, f"Processing body data: {body_data}", level=LogLevel.DEBUG, module="INSTANCE_NODE")
        
        # Resolve entity token to actual Fusion body object
        resolved_body = self._resolve_body_from_token(body_data, app)
        
        if not resolved_body:
            log(app, f"The selected body '{body_data.get('body_name', '?')}' was not found. "
                     "It may have been renamed or deleted. Bodies created by Noodle are rebuilt "
                     "on every Generate, so select a body you modeled.",
                level=LogLevel.ERROR, module="INSTANCE_NODE")
            return {"geometry": None}
        
        log(app, f"Resolved to body: {resolved_body.name}", level=LogLevel.DEBUG, module="INSTANCE_NODE")
        
        # Need to copy the body to create new geometry in current BaseFeature context
        try:
            # Get the current BaseFeature being edited from context
            noodle_base_feature = context.get('base_feature') or context.get('noodle_base_feature')
            if not noodle_base_feature:
                log(app, "No BaseFeature context available", level=LogLevel.ERROR, module="INSTANCE_NODE")
                return {"geometry": None}
            
            # Get the design and root component
            fusion_app = adsk.core.Application.get()
            design = fusion_app.activeProduct
            root_comp = design.rootComponent
            
            # Use TemporaryBRepManager to create a proper copy like other nodes
            temp_brep_mgr = adsk.fusion.TemporaryBRepManager.get()
            temp_brep = temp_brep_mgr.copy(resolved_body)
            log(app, f"Created temporary BRep copy of: {resolved_body.name}", level=LogLevel.DEBUG, module="INSTANCE_NODE")

            # Bodies in a sub-component are stored in component space. Move the copy to
            # where the user sees it, using the component's first occurrence.
            try:
                parent_comp = resolved_body.parentComponent
                if parent_comp and parent_comp != root_comp:
                    occurrences = root_comp.allOccurrencesByComponent(parent_comp)
                    if occurrences and occurrences.count > 0:
                        temp_brep_mgr.transform(temp_brep, occurrences.item(0).transform2)
            except Exception as e:
                log(app, f"Could not apply occurrence transform: {e}", level=LogLevel.DEBUG, module="INSTANCE_NODE")
            
            # Create unique source name including component context to avoid conflicts
            source_body_name = body_data.get('body_name', 'Body')
            component_name = body_data.get('component_name', '')
            if component_name and component_name != source_body_name:
                # Include component context if different from body name
                source_name = f"{component_name}_{source_body_name}"
            else:
                source_name = source_body_name
            
            target_name = generate_geometry_name(
                node_type="body_instance",
                node_id=self.id,
                source_name=source_name
            )
            
            # Add the copied body to the BaseFeature (cross-component copying)
            bodies = root_comp.bRepBodies
            
            # Try-catch around the body.add operation as it can fail for cross-component copies
            try:
                final_body = bodies.add(temp_brep, noodle_base_feature)
                log(app, f"Successfully added copied body to BaseFeature: {final_body.name}", 
                    level=LogLevel.DEBUG, module="INSTANCE_NODE")
            except Exception as e:
                log(app, f"Failed to add copied body to BaseFeature: {str(e)}", 
                    level=LogLevel.ERROR, module="INSTANCE_NODE")
                # Try without BaseFeature as fallback
                final_body = bodies.add(temp_brep)
                log(app, f"Added body without BaseFeature as fallback: {final_body.name}", 
                    level=LogLevel.WARNING, module="INSTANCE_NODE")
            
            # Enhanced tracking will handle naming via post-BaseFeature reconciliation
            log(app, f"Body Instance created, will be named '{target_name}' after reconciliation", 
                level=LogLevel.DEBUG, module="INSTANCE_NODE")
            
            # Return in spec-compliant format with target name (actual naming happens post-BaseFeature)
            return {
                "geometry": {
                    "kind": "instance", 
                    "id": f"instance_{self.id}",
                    "geometry": final_body,
                    "geometry_name": target_name  # Enhanced tracking will apply this name
                }
            }
            
        except Exception as copy_error:
            log(app, f"Failed to copy and add body: {str(copy_error)}", level=LogLevel.ERROR, module="INSTANCE_NODE")
            log(app, "Falling back to original body reference", level=LogLevel.WARNING, module="INSTANCE_NODE")
            
            # Return original body with geometry contract format
            return {
                "geometry": {
                    "kind": "instance",
                    "id": f"instance_{self.id}",
                    "geometry": resolved_body,
                    "geometry_name": resolved_body.name
                }
            }
    
    def _resolve_body_from_token(self, body_data: Any, app: Any) -> Any:
        """Resolve body reference to actual Fusion BRepBody object"""
        try:
            # If it's already a body object, return it
            if hasattr(body_data, 'name') and hasattr(body_data, 'faces'):
                return body_data
            
            # If no reference data, return None
            if not isinstance(body_data, dict):
                return None
            
            # Handle name-based identification (preferred approach)
            if 'body_name' in body_data and 'component_name' in body_data:
                body_name = body_data['body_name']
                component_name = body_data['component_name']
                log(app, f"Searching for body by name: '{body_name}' in '{component_name}'", 
                    level=LogLevel.DEBUG, module="INSTANCE_NODE")
                
                # Search for the component and body by name
                design = app.activeProduct
                if not design:
                    log(app, "No active design found", level=LogLevel.ERROR, module="INSTANCE_NODE")
                    return None
                
                # Search through all components
                for comp in design.allComponents:
                    if comp.name == component_name:
                        log(app, f"Found component: '{comp.name}'", level=LogLevel.DEBUG, module="INSTANCE_NODE")
                        
                        # Search for body in this component
                        for body in comp.bRepBodies:
                            if body.name == body_name:
                                log(app, f"Found body: '{body.name}' in '{comp.name}'", 
                                    level=LogLevel.DEBUG, module="INSTANCE_NODE")
                                return body
                        
                        log(app, f"Body '{body_name}' not found in component '{component_name}'", 
                            level=LogLevel.ERROR, module="INSTANCE_NODE")
                        return None
                
                log(app, f"Component '{component_name}' not found", level=LogLevel.ERROR, module="INSTANCE_NODE")
                return None
            else:
                log(app, "No body identification found", level=LogLevel.ERROR, module="INSTANCE_NODE")
                return None
                
        except Exception as e:
            log(app, f"Error resolving body: {str(e)}", level=LogLevel.ERROR, module="INSTANCE_NODE")
            return None

    def _set_body_name_with_retry(self, app: Any, body: Any, target_name: str, max_attempts: int = 3) -> None:
        """Set body name with retry logic to handle Fusion API timing issues."""
        log(app, f"Attempting to set body name to: {target_name}", level=LogLevel.DEBUG, module="INSTANCE_NODE")
        
        for attempt in range(max_attempts):
            try:
                body.name = target_name
                if body.name == target_name:
                    log(app, f"Successfully set body name to: {target_name}", level=LogLevel.DEBUG, module="INSTANCE_NODE")
                    return  # Success
                log(app, f"Name mismatch on attempt {attempt+1}: expected '{target_name}', got '{body.name}'", 
                    level=LogLevel.WARNING, module="INSTANCE_NODE")
            except Exception as e:
                log(app, f"Failed to set body name on attempt {attempt+1}: {str(e)}", 
                    level=LogLevel.WARNING, module="INSTANCE_NODE")
        
        # Final attempt without error handling
        log(app, f"Final attempt to set body name: {target_name}", level=LogLevel.WARNING, module="INSTANCE_NODE")
        try:
            body.name = target_name
            log(app, f"Final result - body name is: {body.name}", level=LogLevel.WARNING, module="INSTANCE_NODE")
        except Exception as e:
            log(app, f"Final attempt failed: {str(e)}", level=LogLevel.ERROR, module="INSTANCE_NODE")
