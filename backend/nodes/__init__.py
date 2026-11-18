"""
Node registry - discovers and manages all available node types
"""

import importlib
import inspect
from pathlib import Path
from typing import Dict, Type, List, Optional, Any
from ..utilities.log_utils import log
from ..specification import LogLevel
from .base import BaseNode

class NodeRegistry:
    """Central registry for all node types"""

    _nodes: Dict[str, Type[BaseNode]] = {}
    _specs: Dict[str, Dict[str, Any]] = {}
    _initialized = False
    _app = None
    _menu_section_map: Dict[str, str] = {}   # normalized_type → section name
    _menu_sections: List[str] = []           # ordered non-hidden section names

    @classmethod
    def initialize(cls, app=None):
        """Initialize the registry by discovering all nodes"""
        cls._nodes.clear()
        cls._specs.clear()
        cls._initialized = False

        cls._app = app

        # Build menu lookup from config (independent of node scanning)
        from .menu_config import MENU_SECTIONS
        cls._menu_section_map = {
            node_type: section
            for section, types in MENU_SECTIONS.items()
            for node_type in types
        }
        cls._menu_sections = [s for s in MENU_SECTIONS.keys() if not s.startswith('_')]

        cls._scan_for_nodes(app)
        cls._initialized = True
    
    @classmethod
    def ensure_initialized(cls, app=None):
        """Scan for nodes once. Node files only change when the add-in is stopped and
        run again, which reloads this module and starts a fresh registry."""
        if not cls._initialized:
            cls.initialize(app)

    @classmethod
    def get_menu_sections(cls) -> List[str]:
        """Return ordered list of visible menu section names (excludes _hidden)."""
        return list(cls._menu_sections)

    @classmethod
    def _scan_for_nodes(cls, app):
        """Scan the nodes directory for all node modules"""
        nodes_dir = Path(__file__).parent
        
        log(app, f"Scanning for nodes in: {nodes_dir}", 
            level=LogLevel.DEBUG, module="NODE_REGISTRY")
        
        modules_found = []
        for py_file in nodes_dir.glob("*.py"):
            if py_file.name.startswith('_') or py_file.name in ('base.py', 'menu_config.py'):
                continue
            
            module_name = py_file.stem
            modules_found.append(module_name)
            
            try:
                # Import the module
                module = importlib.import_module(f'.{module_name}', package=__name__)
                
                # Find all Node classes in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseNode) and 
                        obj is not BaseNode and 
                        hasattr(obj, 'NODE_TYPE') and
                        obj.NODE_TYPE and  # Must have non-empty NODE_TYPE
                        obj.NODE_TYPE.strip()):  # Must have non-whitespace NODE_TYPE
                        
                        node_type = obj.NODE_TYPE
                        cls._nodes[node_type] = obj
                        
                        # Get and cache the spec
                        spec = obj.get_spec()
                        
                        # Convert spec to frontend format
                        normalized_type = node_type.lower().replace(' ', '_')
                        frontend_spec = {
                            'type': normalized_type,
                            'name': obj.NODE_NAME,
                            'category': obj.NODE_CATEGORY,
                            'menu_category': cls._menu_section_map.get(normalized_type, obj.NODE_CATEGORY),
                            'description': obj.NODE_DESCRIPTION,
                            'inputs': [],
                            'outputs': []
                        }
                        
                        # Convert inputs using proper PortSpec.to_dict() method
                        for port in spec.inputs:
                            frontend_spec['inputs'].append(port.to_dict())
                        
                        # Convert outputs using proper PortSpec.to_dict() method
                        for port in spec.outputs:
                            frontend_spec['outputs'].append(port.to_dict())
                        
                        cls._specs[normalized_type] = frontend_spec
                        
                        log(app, f"Registered node: {node_type} ({obj.NODE_NAME})", 
                            level=LogLevel.DEBUG, module="NODE_REGISTRY")
                        
            except Exception as e:
                log(app, f"Failed to load node module {module_name}: {e}", 
                    level=LogLevel.ERROR, module="NODE_REGISTRY")
        
        log(app, f"NodeRegistry initialized with {len(cls._nodes)} node types from {len(modules_found)} classes", 
            level=LogLevel.DEBUG, module="NODE_REGISTRY")
    
    @classmethod
    def get_node_class(cls, node_type: str) -> Optional[Type[BaseNode]]:
        """Get a node class by type with flexible matching"""
        # Try exact match first
        if node_type in cls._nodes:
            return cls._nodes[node_type]
        
        # Try case-insensitive exact match
        for registered_type, node_class in cls._nodes.items():
            if registered_type.lower() == node_type.lower():
                return node_class
        
        # Try normalized formats (lowercase with underscores vs spaces)
        node_type_normalized = node_type.lower().replace(' ', '_')
        for registered_type, node_class in cls._nodes.items():
            registered_normalized = registered_type.lower().replace(' ', '_')
            if registered_normalized == node_type_normalized:
                return node_class
        
        # Try without underscores/spaces altogether
        node_type_clean = node_type.lower().replace('_', '').replace(' ', '')
        for registered_type, node_class in cls._nodes.items():
            registered_clean = registered_type.lower().replace('_', '').replace(' ', '')
            if registered_clean == node_type_clean:
                return node_class
        
        return None
    
    @classmethod  
    def get_all_specs(cls) -> List[Dict[str, Any]]:
        """Get all node specifications in frontend format"""
        from ..utilities.log_utils import log
        from ..specification import LogLevel
        
        specs = []
        for node_type, node_class in cls._nodes.items():
            try:
                node_spec = node_class.get_spec()
                
                # Use the spec's to_dict method and supplement with class attributes
                spec_dict = node_spec.to_dict()
                spec_dict['name'] = node_class.NODE_NAME
                spec_dict['type'] = spec_dict['node_type']
                spec_dict['description'] = spec_dict['description'] or node_class.NODE_DESCRIPTION
                normalized = node_type.lower().replace(' ', '_')
                spec_dict['menu_category'] = cls._menu_section_map.get(normalized, node_class.NODE_CATEGORY)
                # Helpers the palette adds and connects with this node (see companions.py)
                from .companions import companions_for
                spec_dict['companions'] = companions_for(node_class, cls.get_node_class)

                specs.append(spec_dict)
                
                log(cls._app, 
                    f"Added spec for {node_type}: {spec_dict['name']}", 
                    level=LogLevel.DEBUG, module="NODE_REGISTRY")
                    
            except Exception as e:
                log(cls._app, 
                    f"Failed to load node module {node_type}: {str(e)}", 
                    level=LogLevel.ERROR, module="NODE_REGISTRY")
        
        return specs
    
    @classmethod
    def get_spec(cls, node_type: str) -> Optional[Dict[str, Any]]:
        """Get a specific node spec in frontend format"""
        return cls._specs.get(node_type.lower().replace(' ', '_'))