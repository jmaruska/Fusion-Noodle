"""
Frontend integration validation for PortFactory
This should be part of the spec enforcement system
"""

import os
import sys
import re
from pathlib import Path

# Handle both package import and direct execution
try:
    from .specification import SPECIFICATION
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend.specification import SPECIFICATION

def validate_port_factory_coverage():
    """
    Validate that PortFactory handles all allowed port types from data contracts
    """
    errors = []
    
    # Get allowed port types from spec
    allowed_types = SPECIFICATION.data_contracts.allowed_port_types
    
    # Read PortFactory.jsx
    ui_path = Path(__file__).parent.parent / 'ui' / 'src' / 'components' / 'PortFactory.jsx'
    if not ui_path.exists():
        return [f"PortFactory.jsx not found at {ui_path}"]
    
    with open(ui_path, 'r') as f:
        port_factory_content = f.read()
    
    # Find switch cases in PortFactory
    case_pattern = r"case\s*['\"]([^'\"]+)['\"]:"
    found_cases = re.findall(case_pattern, port_factory_content)
    
    # Check for missing cases
    # Map spec types to expected case names
    type_mappings = {
        'float': ['float'],
        'integer': ['integer'],
        'boolean': ['boolean'],
        'string': ['string'],
        'enum': ['enum'],
        'vector3': ['vector3'],
        'geometry': ['geometry'],
        'collection': ['collection'],
        'surface': ['surface', 'body', 'brep'],
        'body': ['surface', 'body', 'brep'],
    }
    
    for spec_type in allowed_types:
        expected_cases = type_mappings.get(spec_type, [spec_type])
        if not any(case in found_cases for case in expected_cases):
            errors.append(f"PortFactory missing case for port type '{spec_type}' (expected cases: {expected_cases})")
    
    # Check for default case handling
    if 'default:' not in port_factory_content:
        errors.append("PortFactory missing default case for unknown port types")
    
    return errors

def validate_frontend_integration():
    """
    Comprehensive frontend integration validation
    """
    errors = []
    
    # Validate PortFactory coverage
    errors.extend(validate_port_factory_coverage())
    
    # TODO: Add other frontend integration checks
    # - Flow computation coverage for all node types
    # - Edge type definitions for all port types
    # - CSS styling completeness
    
    return errors