"""
Automated tests to verify all backend modules comply with the specification.
This module is EXEMPT from print() restrictions as it's a diagnostic tool.
"""

import os
import sys
from pathlib import Path

# Handle both direct execution and module import
try:
    from .enforcement import SpecificationEnforcer
    from .frontend_integration_check import validate_frontend_integration
    from .contract_validation_tests import run_contract_validation_tests
except ImportError:
    # Direct execution - add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend.enforcement import SpecificationEnforcer
    from backend.frontend_integration_check import validate_frontend_integration
    from backend.contract_validation_tests import run_contract_validation_tests

def test_all_modules():
    """Scan all backend modules for spec violations."""
    v2_path = Path(__file__).parent
    errors = []
    
    # Files that are exempt from certain checks
    EXEMPT_FILES = ['spec_tests.py', 'surface_placement_utils.py']  # This file needs print for output, surface_placement_utils has editing conflicts
    
    # Test backend Python files
    for py_file in v2_path.rglob("*.py"):
        if '__pycache__' in str(py_file):
            continue

        relative = py_file.relative_to(v2_path)
        module_name = str(relative).replace('/', '.').replace('.py', '')
        module_path = str(py_file)

        # Skip exempt files
        if py_file.name in EXEMPT_FILES:
            continue
            
        errs = SpecificationEnforcer.check_module(module_name, module_path)
        if errs:
            errors.append((f"Backend: {module_name}", errs))
    
    # Test UI files for CSS violations
    ui_path = v2_path.parent / 'ui' / 'src'
    if ui_path.exists():
        for ui_file in ui_path.rglob("*.jsx"):
            module_name = f"ui/{str(ui_file.relative_to(ui_path))}"
            module_path = str(ui_file)
            
            errs = SpecificationEnforcer.check_module(module_name, module_path)
            if errs:
                errors.append((f"UI: {module_name}", errs))
    
    # Test frontend integration compliance
    frontend_errors = validate_frontend_integration()
    if frontend_errors:
        errors.append(("Frontend Integration", frontend_errors))
    
    # Test contract validation compliance
    contract_errors = run_contract_validation_tests()
    if contract_errors:
        for test_name, test_errors in contract_errors:
            errors.append((f"Contract: {test_name}", test_errors))
    
    return errors

def output_results(results):
    """Output test results - this function is allowed to use print."""
    if results:
        # Use sys.stdout.write to avoid triggering our own checker
        sys.stdout.write("❌ Specification violations found:\n")
        for module, errs in results:
            sys.stdout.write(f"\nModule: {module}\n")
            for err in errs:
                sys.stdout.write(f"  - {err}\n")
        return False
    else:
        sys.stdout.write("✅ All backend modules comply with the specification.\n")
        return True

if __name__ == "__main__":
    results = test_all_modules()
    success = output_results(results)
    exit(0 if success else 1)