"""
Enforcement mechanisms that ACTUALLY CHECK the specification.
These are not suggestions - they are requirements.
"""

import ast
import inspect
import re
from typing import Any, List, Type, Callable, Dict
from functools import wraps
from .specification import SPECIFICATION
from .utilities.data_integrity_utils import (
    DataIntegrityValidator,
    RuntimeIntegrityChecker,
)

# Files exempt from certain checks (diagnostic tools)
EXEMPT_FROM_PRINT_CHECK = ['spec_tests.py']

# ============================================================================
# DECORATORS THAT ENFORCE SPECS
# ============================================================================

def enforce_node_spec(cls: Type) -> Type:
    """Decorator that enforces node specification at import time"""
    
    spec = SPECIFICATION.node_system
    errors = []
    
    # Check required methods exist
    for method_name in spec.required_methods:
        if not hasattr(cls, method_name):
            errors.append(f"Node {cls.__name__} missing required method: {method_name}")
    
    # Check method signatures (but be flexible about classmethods)
    for method_name, expected_sig in spec.method_signatures.items():
        if hasattr(cls, method_name):
            method = getattr(cls, method_name)
            actual_sig = str(inspect.signature(method))
            
            # Special handling for classmethods
            if method_name == 'get_spec':
                # For classmethod, the signature includes 'cls' which is OK
                if 'NodeSpec' not in actual_sig:
                    errors.append(f"Node {cls.__name__}.{method_name} must return NodeSpec")
            else:
                # For regular methods, do a more flexible check
                # Just check that the key parameters are present
                if method_name == 'execute':
                    if 'inputs' not in actual_sig or 'context' not in actual_sig:
                        errors.append(f"Node {cls.__name__}.{method_name} missing required parameters")
                elif method_name == 'validate':
                    if 'inputs' not in actual_sig:
                        errors.append(f"Node {cls.__name__}.{method_name} missing 'inputs' parameter")
    
    # Check required attributes
    for attr in spec.required_attributes:
        if not hasattr(cls, attr):
            errors.append(f"Node {cls.__name__} missing required attribute: {attr}")
        elif not getattr(cls, attr):
            errors.append(f"Node {cls.__name__} has empty {attr}")
    
    # Check naming convention
    if not re.match(spec.naming_rules['node_class'], cls.__name__):
        errors.append(f"Node class name {cls.__name__} doesn't match pattern")
    
    if errors:
        raise SpecificationError(f"Node {cls.__name__} violates specification:\n" + "\n".join(errors))
    
    # Add runtime validation
    original_execute = cls.execute
    
    @wraps(original_execute)
    def validated_execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        # Get app from context for logging
        app = context.get('app')
        node_type = getattr(self, 'node_type', cls.__name__)
        
        # Create a simple logger function to avoid circular imports
        def simple_logger(msg: str):
            if app and hasattr(app, 'log'):
                try:
                    from .utilities.log_utils import log, LogLevel
                    log(app, msg, level=LogLevel.DEBUG, module="NodeValidation")
                except Exception:
                    pass  # Fallback silently if logging fails
        
        # Enhanced data flow composition validation
        composition_valid, composition_errors = DataIntegrityValidator.validate_data_flow_composition(
            inputs, node_type, simple_logger
        )
        if not composition_valid:
            raise SpecificationError("; ".join(composition_errors))
        
        # Modifier outputs travel on FLOAT ports, so the UI lets them connect to any
        # number input. Only effectors and other modifiers know how to evaluate them.
        if getattr(cls, 'NODE_CATEGORY', '') not in ('effector', 'modifiers'):
            for input_name, value in inputs.items():
                if isinstance(value, dict) and 'modifier_type' in value:
                    raise SpecificationError(
                        f"'{self.port_label(input_name)}' is connected to a modifier. Modifiers can only drive "
                        f"an effector's Strength or another modifier's input.")

        # Declared bounds first (min_value, max_value, whole numbers for INTEGER ports),
        # so every node gets the same check and message as the palette shows
        from .contracts import bounds_problem
        bound_errors = [problem for port in self.get_spec().inputs
                        if port.name in inputs
                        for problem in [bounds_problem(port, inputs[port.name], inputs)] if problem]
        if bound_errors:
            raise SpecificationError("; ".join(bound_errors))

        # The node's own validation
        validation_errors = self.validate(inputs)
        if validation_errors:
            raise SpecificationError("; ".join(str(e) for e in validation_errors))
        
        # Execute with runtime monitoring. Nodes report many failures by logging a
        # reason and returning an empty output, so remember the last logged problem.
        from .utilities.log_utils import reset_last_problem, get_last_problem
        reset_last_problem()
        result = original_execute(self, inputs, context)
        
        # Enhanced runtime integrity validation
        runtime_valid, runtime_errors = RuntimeIntegrityChecker.validate_node_execution(
            node_type, inputs, result, simple_logger
        )
        if not runtime_valid:
            reason = get_last_problem()
            if reason and any("cannot be None" in str(e) for e in runtime_errors):
                raise SpecificationError(reason)
            raise SpecificationError("; ".join(str(e) for e in runtime_errors))
        
        # Wire format policy: COLLECTION ports must carry CollectionSpec objects, never dicts.
        # to_dict() is for serialization boundaries only (frontend responses, file I/O).
        from .contracts import CollectionSpec, PortType
        node_spec = self.get_spec()
        for output in node_spec.outputs:
            if output.port_type == PortType.COLLECTION and output.name in result:
                value = result[output.name]
                if value is not None and not isinstance(value, CollectionSpec):
                    raise SpecificationError(
                        f"Node {cls.__name__} output '{output.name}' is {type(value).__name__}, "
                        f"expected CollectionSpec. Never call .to_dict() on a wire value — "
                        f"to_dict() is for serialization boundaries only."
                    )

        # Enhanced output validation matching specification contracts
        for output in node_spec.outputs:
            if output.name in result:
                value = result[output.name]
                validator = SPECIFICATION.data_contracts.validation_rules.get(
                    output.port_type.name.lower() if hasattr(output.port_type, 'name') else str(output.port_type).lower()
                )
                if validator and not validator(value):
                    raise SpecificationError(
                        f"Output {output.name} failed enhanced validation for type {output.port_type}"
                    )

        return result
    
    cls.execute = validated_execute
    return cls

def enforce_logging(func: Callable) -> Callable:
    """Decorator that enforces logging specification"""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Skip source inspection for the log function itself
        # to avoid recursion issues
        
        # Ensure proper logging parameters
        if 'level' in kwargs:
            # Accept both LogLevel enum and string
            level = kwargs['level']
            if not (hasattr(level, 'value') or isinstance(level, str)):
                raise SpecificationError("Log level must be a LogLevel enum or string")
        
        if 'module' not in kwargs:
            raise SpecificationError("Log calls must include 'module' parameter")
        
        return func(*args, **kwargs)
    
    return wrapper

def _check_inline_css_violations(source: str, module_name: str) -> List[str]:
    """Check for inline CSS violations in UI code"""
    errors = []
    lines = source.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        # Check for React inline styles
        if 'style={{' in line:
            # Allow ReactFlow required inline styles
            if any(pattern in line for pattern in [
                'connectionLineStyle={{',
                'defaultEdgeOptions={{',
                'style: {',  # Inside ReactFlow props
            ]):
                continue  # These are mandatory ReactFlow patterns
            
            # Allow CSS custom properties (--variable: value)
            if '--' in line and ':' in line:
                continue  # CSS custom properties are acceptable
            
            errors.append(f"Inline CSS violation at line {line_num} in {module_name}: style={{}} not allowed")
        
        # Check for inline style attributes
        if 'style="' in line and not line.strip().startswith('//'):
            errors.append(f"Inline style attribute at line {line_num} in {module_name}: style=\"\" not allowed")
        
        # Check for hardcoded colors (basic patterns)
        color_patterns = [
            r'#[0-9a-fA-F]{3,6}',  # Hex colors
            r'rgb\s*\(',           # RGB colors
            r'rgba\s*\(',          # RGBA colors
            r'hsl\s*\(',           # HSL colors
        ]
        
        for pattern in color_patterns:
            if re.search(pattern, line) and not line.strip().startswith('//') and 'var(--' not in line:
                # Allow ReactFlow required colors and CSS custom properties
                if any(reactflow_pattern in line for reactflow_pattern in [
                    'connectionLineStyle',
                    'defaultEdgeOptions', 
                    'stroke:',  # ReactFlow edge styling
                ]):
                    continue  # ReactFlow requires these inline
                
                # Only flag if it's clearly in a style context
                if any(style_indicator in line.lower() for style_indicator in ['style', 'color', 'background']):
                    errors.append(f"Hardcoded color at line {line_num} in {module_name}: {re.search(pattern, line).group()}")
    
    return errors

def _check_porttype_usage(node: ast.AST, module_name: str) -> List[str]:
    """Check that PortType attribute access uses valid enum values"""
    errors = []
    
    # Get valid PortType values
    from .contracts import PortType
    valid_port_types = set(member.name for member in PortType)
    
    if isinstance(node, ast.Attribute):
        # Check for PortType.SOMETHING usage
        if (isinstance(node.value, ast.Name) and 
            node.value.id == 'PortType'):
            
            attr_name = node.attr
            if attr_name not in valid_port_types:
                errors.append(
                    f"Invalid PortType.{attr_name} at line {node.lineno} in {module_name}. "
                    f"Valid values: {sorted(valid_port_types)}"
                )
    
    return errors

# ============================================================================
# IMPORT HOOK TO ENFORCE AT IMPORT TIME
# ============================================================================

class SpecificationEnforcer:
    """Import hook that validates all modules against spec"""
    
    @staticmethod
    def check_module(module_name: str, module_path: str):
        """Check a module file against specifications"""
        
        # Check if this file is exempt from certain checks
        from pathlib import Path
        filename = Path(module_path).name
        
        with open(module_path, 'r') as f:
            source = f.read()
        
        errors = []
        
        # For JSX/TSX files, selectively enforce inline CSS checks for node UI only
        if filename.endswith('.jsx') or filename.endswith('.tsx'):
            # Limit enforcement to node-related components to avoid flagging app-level UI
            try:
                from pathlib import Path
                path_posix = Path(module_path).as_posix()
            except Exception:
                path_posix = module_path

            node_css_targets = [
                '/ui/src/components/BaseNode.jsx',
                '/ui/src/components/ModularCustomNode.jsx',
                '/ui/src/components/ports/',
                '/ui/src/components/SelectionButton.jsx',
                '/ui/src/components/StatusPanel.jsx',
            ]

            enforce_inline_css = any(target in path_posix for target in node_css_targets)

            if enforce_inline_css:
                errors.extend(_check_inline_css_violations(source, module_name))
            # If not enforcing for this file, skip UI inline CSS checks entirely
            return errors
        
        # Parse AST for Python files only
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            errors.append(f"Syntax error in {module_name}: {e}")
            return errors
        
        # Check imports and other violations
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:  # node.module can be None
                    import_stmt = f"from {node.module}"
                    for forbidden in SPECIFICATION.architecture.forbidden_imports:
                        if forbidden in import_stmt:
                            errors.append(
                                f"Forbidden import in {module_name}: {import_stmt}"
                            )
            
            # Check for print statements (unless exempt)
            if filename not in EXEMPT_FROM_PRINT_CHECK:
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == 'print':
                        errors.append(
                            f"Forbidden print() at line {node.lineno} in {module_name}"
                        )
            
            # Check PortType enum usage for validity
            errors.extend(_check_porttype_usage(node, module_name))
        
        # Check document lifecycle compliance for handlers
        if 'handlers' in module_name and 'persistence' in module_name:
            # Load module and check classes
            # This would need dynamic loading for full validation
            pass
        
        return errors

# ============================================================================
# SPECIFICATION EXCEPTIONS
# ============================================================================

class SpecificationError(Exception):
    """Raised when code violates the specification"""
    pass
