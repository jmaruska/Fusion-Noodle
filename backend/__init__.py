"""
Backend - Specification-driven implementation.

This module ENFORCES specifications at import time.
"""

from typing import Dict, Any
from .core import Application
from .specification import SPECIFICATION, LogLevel
from .contracts import (
    NodeSpec, 
    PortSpec, 
    PortType,
    GeometryEnvelope,
    Vector3Spec
)

def initialize(fusion_context: Dict[str, Any]) -> Application:
    """
    Initialize backend with Fusion context.
    
    Args:
        fusion_context: Dict with 'app' and 'ui' keys
    
    Returns:
        Application instance
    """
    # First, validate our own specification
    errors = SPECIFICATION.validate_all()
    if errors:
        raise RuntimeError(f"Specification self-check failed: {errors}")
    
    # Then initialize application
    app = Application.get_instance()
    app.initialize(fusion_context)
    
    # Log successful initialization
    from .utilities.log_utils import log
    log(fusion_context['app'], "Backend initialized successfully", 
        level=LogLevel.INFO, module="BACKEND")
    
    return app

def shutdown() -> None:
    """Release Fusion event subscriptions and reset the backend. Called from stop()."""
    if Application._instance is not None:
        Application._instance.shutdown()

def palette_closed() -> None:
    """Called when the palette closes. Removes the visualizer's dots."""
    if Application._instance is not None:
        Application._instance.palette_closed()

def handle_message(action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle messages from frontend.
    
    Args:
        action: Action name
        data: Action data
    
    Returns:
        Response dictionary
    """
    app = Application.get_instance()
    if not app.initialized:
        return {'success': False, 'error': 'Backend not initialized'}
    
    return app.handle_message(action, data)

# Export public API - CRITICAL: These must be defined BEFORE the __all__ list
__all__ = [
    'initialize',
    'shutdown',
    'palette_closed',
    'handle_message',
    'Application',
    'SPECIFICATION',
    'LogLevel',
    'NodeSpec',
    'PortSpec', 
    'PortType',
    'GeometryEnvelope',
    'Vector3Spec'
]