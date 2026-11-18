"""
Master specification for Noodle v2.
This is THE source of truth - all code must conform to these specs.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Protocol, Type, Callable
from enum import Enum
import inspect

# ============================================================================
# LOGGING SPECIFICATION
# ============================================================================

class LogLevel(Enum):
    """The ONLY allowed log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass(frozen=True)
class LoggingSpec:
    """Enforced logging specification"""
    
    # Required format for ALL log messages
    format_template: str = "[{timestamp}] [{module}] [{level}] {message}"
    
    # Required fields in every log call
    required_fields: List[str] = field(default_factory=lambda: ['module', 'level', 'message'])
    
    # Forbidden patterns (will raise error if used)
    forbidden_patterns: List[str] = field(default_factory=lambda: [
        'print(',  # NO print statements
        'console.log',  # NO JavaScript-style logging
        'logging.',  # NO direct logging module usage
    ])
    
    # The ONLY allowed logging function signature
    log_signature: str = "log(app: Any, message: str, *, level: LogLevel, module: str) -> None"

# ============================================================================
# SELECTION PATTERN SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class SelectionPatternSpec:
    """Specification for backend selection patterns and API contracts"""
    
    # Supported selection types and their backend configurations
    selection_types: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        'body': {
            'action_name': 'selectBody',
            'clear_action': 'cancelBodySelection',
            'check_action': 'checkBodySelection',
            'validation_field': 'entity_token',
            'display_field': 'body_name',
            'port_type': 'BODY'
        },
        'surface': {
            'action_name': 'selectSurface',
            'clear_action': 'cancelSurfaceSelection',
            'check_action': 'checkSurfaceSelection',
            'validation_field': 'entity_token',
            'display_field': 'display_name',
            'port_type': 'SURFACE'
        },
        'brep': {
            'action_name': 'selectBRep',
            'clear_action': 'cancelBRepSelection', 
            'check_action': 'checkBRepSelection',
            'validation_field': 'entity_token',
            'display_field': 'display_name',
            'port_type': 'BREP'
        },
        'point': {
            'action_name': 'selectPoint',
            'clear_action': 'cancelPointSelection',
            'check_action': 'checkPointSelection',
            'validation_field': 'entity_token',
            'display_field': 'point_name',
            'port_type': 'POINT'
        },
        'curve': {
            'action_name': 'selectCurve',
            'clear_action': 'cancelCurveSelection',
            'check_action': 'checkCurveSelection',
            'validation_field': 'entity_token',
            'display_field': 'display_name',
            'port_type': 'CURVE'
        }
    })
    
    # CRITICAL: Selection Button Communication Protocol
    # These response formats are REQUIRED for frontend SelectionButton compatibility
    selection_response_formats: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        'initiate_selection': {
            'immediate_success': {
                'success': True,
                '[type]_data': '# Selection data object',
                'message': 'Selected [type]: [name]'
            },
            'polling_mode': {
                'success': True,
                'message': 'Please select a [type] in the model. The selection will be detected automatically.',
                'selection_active': True
            }
        },
        'check_selection_pending': {
            'success': True,
            'selection_pending': True,  # CRITICAL: Must be 'selection_pending' not 'selection_complete: false'
            'message': 'Waiting for [type] selection...'
        },
        'check_selection_complete': {
            'success': True,
            'selection_complete': True,
            '[type]_data': '# Selection data object',
            'message': 'Selected [type]: [name]'
        },
        'cancel_selection': {
            'success': True,
            'message': '[Type] selection cancelled',
            'selection_cancelled': True  # Optional but recommended
        }
    })
    
    # State transition requirements for selection workflows
    selection_state_transitions: Dict[str, str] = field(default_factory=lambda: {
        'initiate': 'MUST return either immediate_success OR polling_mode response',
        'polling': 'MUST return either selection_pending OR selection_complete response', 
        'completion': 'MUST include [type]_data object and set selection_complete: true',
        'cancellation': 'MUST clear all selection state and return selection_cancelled: true'
    })
    
    # Backend validation rules for selections
    validation_rules: Dict[str, Any] = field(default_factory=lambda: {
        'require_entity_token': True,  # All selections must have valid entity_token
        'validate_selection_exists': True,  # Must validate selection still exists
        'support_clear_action': True,  # Backend must support clearing selections
        'timeout_seconds': 30,  # Selection operations timeout after 30 seconds
    })

# ============================================================================
# DATA CONTRACT SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class DataContractSpec:
    """Rules for all data passing through the system"""
    
    # All data MUST be one of these types
    allowed_port_types: List[str] = field(default_factory=lambda: [
        'float', 'integer', 'boolean', 'string', 'enum',
        'vector3', 'transform', 'geometry', 'collection', 'surface', 'body', 'spacer', 'point', 'curve'
    ])
    
    # All geometry MUST have these fields
    geometry_required_fields: List[str] = field(default_factory=lambda: [
        'kind', 'id', 'geometry', 'geometry_name'
    ])
    
    # All vectors MUST have these fields
    vector3_required_fields: List[str] = field(default_factory=lambda: ['x', 'y', 'z'])
    
    # Validation rules
    validation_rules: Dict[str, Callable] = field(default_factory=lambda: {
        'vector3': lambda v: all(k in v for k in ['x', 'y', 'z']),
        'geometry': lambda g: all(k in g for k in ['kind', 'id']),
        'surface': lambda s: isinstance(s, dict) and ('entity_token' in s or 'display_name' in s),
        'body': lambda b: isinstance(b, dict) and ('entity_token' in b or 'body_name' in b),
        'float': lambda f: isinstance(f, (int, float)) or (isinstance(f, dict) and ('number_type' in f or 'modifier_type' in f)),
        'string': lambda s: isinstance(s, str),
        'enum': lambda e: isinstance(e, str),  # Enum values are string selections
        'integer': lambda i: isinstance(i, int),
        'boolean': lambda b: isinstance(b, bool),
        'transform': lambda t: (
            isinstance(t, dict) and (
                # NoodleAttributes format (Maya-style flat attributes for instance transforms)
                all(k in t for k in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']) or
                # Matrix-chained format (for transform nodes output)
                ('transform_type' in t and t.get('transform_type') == 'matrix_chained' and 'transform_matrix' in t) or
                # Aim format (per-instance rotation computed in effector loop)
                ('transform_type' in t and t.get('transform_type') == 'aim' and 'aim_position' in t and 'aim_axis' in t)
            )
        ),
        'collection': lambda c: (
            # CollectionSpec object (runtime/processing format)
            (hasattr(c, 'collection_type') and hasattr(c, 'source_geometries') and hasattr(c, 'instances') and
             isinstance(c.instances, list) and
             all(hasattr(inst, 'transform') and inst.transform is not None for inst in c.instances)) or
            # Dictionary format (serialized/storage format - matches CollectionSpec.to_dict output)
            (isinstance(c, dict) and
             'type' in c and 
             'source_geometries' in c and
             'instances' in c and
             isinstance(c['instances'], list) and
             all(isinstance(inst, dict) and 'transform' in inst and inst['transform'] is not None for inst in c['instances']))
        ),
        'collection_instance': lambda i: (
            isinstance(i, dict) and
            all(k in i for k in ['instance_id', 'source_geometry_id', 'transform']) and
            i['transform'] is not None  # NEVER None - always valid transform
        ),
    })
    
    # Contract enforcement requirements  
    contract_enforcement_requirements: List[str] = field(default_factory=lambda: [
        'Transform fields MUST never be None - use NoodleAttributes.identity() for default transforms',
        'NoodleAttributes MUST have flat tx,ty,tz,rx,ry,rz,sx,sy,sz attributes (Maya-style)',
        'Collection instances MUST have NoodleAttributes transforms, never None', 
        'Vector3 objects MUST have x, y, z numeric fields',
        'All geometry MUST use GeometryEnvelope contract',
        'Collection data MUST use CollectionSpec and CollectionInstanceSpec contracts',
        'Contract constructors MUST validate input types at construction time (__post_init__)',
        'Node inputs MUST be validated as dictionaries, converted to objects for processing',
        'Node outputs MUST be validated as dictionaries, never contract objects',
        'from_dict() methods MUST handle dict-to-object conversion with validation',
        'to_dict() methods MUST handle object-to-dict conversion for transport',
        'Mixed types (dicts + objects in same list) are FORBIDDEN and cause AttributeError',
        'Defensive None checking indicates contract violation - fix at source instead',
        'Transform modification MUST convert to dict before assignment operations',
        'Transform processing MUST handle all three formats consistently via standard utilities',
        'Mixed transform access patterns (direct .get(), attributes, items) are FORBIDDEN',
        'Direct .get() calls on transform parameters indicate specification violation',
    ])
    
    # Data conversion enforcement patterns
    data_conversion_enforcement: Dict[str, List[str]] = field(default_factory=lambda: {
        'node_execute_input_pattern': [
            '# Input validation with clear error messages',
            'collection_data = inputs.get("collection")',
            'if not isinstance(collection_data, dict):',
            '    raise TypeError(f"collection input must be dict, got {type(collection_data)}")',
            '# Convert to objects for processing', 
            'collection = CollectionSpec.from_dict(collection_data)'
        ],
        'node_execute_output_pattern': [
            '# Create result as objects',
            'result_collection = CollectionSpec(...)',
            '# Convert to dict for transport',
            'return {"collection": result_collection.to_dict()}'
        ],
        'collection_construction_pattern': [
            '# Convert all inputs to proper objects before CollectionSpec',
            'source_geometries = []',
            'for geo_data in collection_data.get("source_geometries", []):',
            '    geo_envelope = GeometryEnvelope(**geo_data)', 
            '    source_geometries.append(geo_envelope)',
            'instances = []',
            'for inst_data in collection_data.get("instances", []):',
            '    inst_spec = CollectionInstanceSpec.from_dict(inst_data)',
            '    instances.append(inst_spec)',
            'collection = CollectionSpec(..., source_geometries=source_geometries, instances=instances)'        ],
        'transform_processing_pattern': [
            '# REQUIRED: Import safe_get utility for consistent transform access',
            'from backend.utilities.log_utils import safe_get',
            '# Read from transform using safe_get (handles all three formats)',
            'scale_x = safe_get(transform_data, "sx", 1.0)',
            'translation_x = safe_get(transform_data, "tx", 0.0)', 
            '# For modifications, convert to dict first',
            'transform_dict = transform_data.to_dict() if hasattr(transform_data, "to_dict") else transform_data',
            'transform_dict["sx"] = new_scale_value',
            '# Return as dict for transport',
            'return {"transform": transform_dict}'        ]
    })
    
    # Node output format requirements (CRITICAL - eliminates guessing)
    node_output_format_rules: List[str] = field(default_factory=lambda: [
        'ALL nodes MUST return serialized dictionary format via .to_dict()',
        'NEVER return contract objects (CollectionSpec, GeometryEnvelope, etc.) directly',
        'Node execute() methods return Dict[str, Any] where values are JSON-serializable',
        'Contract objects exist for validation and structure, not for inter-node communication',
        'Frontend receives only serialized data, never contract object instances',
        'This ensures consistent serialization and prevents .to_dict() attribute errors',
    ])

# ============================================================================
# NODE INTEGRATION SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class NodeIntegrationSpec:
    """Rules for backend node integration and registration"""
    
    # Core integration principle
    integration_principle: str = "ALL new nodes MUST be integrated across both frontend and backend systems"
    
    # Backend integration requirements
    backend_integration_requirements: List[str] = field(default_factory=lambda: [
        'Backend node module (backend/nodes/[category]_[type].py)',
        'Node registration (auto-discovery via @enforce_node_spec)',
        'Backend validation rules (validate() method)',
        'Backend execution logic (execute() method)',
        'Backend node specification (get_spec() method)',
    ])
    
    # Backend node requirements
    backend_node_requirements: List[str] = field(default_factory=lambda: [
        'Backend: Create [category]_[name].py with @enforce_node_spec decorator',
        'Backend: Implement NODE_TYPE, NODE_CATEGORY, NODE_NAME attributes',
        'Backend: Implement execute(), validate(), get_spec() methods',
        'Backend: Auto-discovery registers node in NodeRegistry',
        'Backend: Pass spec_tests.py validation',
    ])
    
    # Backend integration checklist
    backend_integration_checklist: List[str] = field(default_factory=lambda: [
        'Create backend/nodes/[category]_[name].py',
        'Use @enforce_node_spec decorator',
        'Implement required NODE_* attributes',
        'Define get_spec() with inputs/outputs',
        'Implement validate() with proper error messages',
        'Implement execute() with computation logic',
        'Test with python3 backend/spec_tests.py',
    ])
    
    # Forgotten integration warnings
    common_integration_gaps: List[str] = field(default_factory=lambda: [
        'Frontend flow computation missing node case',
        'Edge type coloring not defined for new port types',
        'Validation rules inconsistent between frontend/backend',
        'Math result display not showing computed outputs',
        'Node registry auto-discovery not working',
        'Specification tests not covering new node',
    ])
    
    # Integration enforcement tools
    integration_enforcement_tools: List[str] = field(default_factory=lambda: [
        'spec_tests.py validates backend compliance',
        'contract_validation_tests.py validates runtime data contracts',
        'frontend_integration_check.py validates UI integration',
        'Frontend console errors indicate missing flow computation',
        'Build process catches TypeScript/import errors',
        'Runtime validation catches contract violations',
        'End-to-end testing reveals missing integration points',
    ])

# ============================================================================
# GEOMETRY NODE SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class GeometryNodeSpec:
    """Specific rules for geometry-generating nodes"""
    
    # Required validation patterns for geometry nodes
    dimensional_validation: Dict[str, str] = field(default_factory=lambda: {
        'positive_numbers_only': 'All dimensional inputs must be positive (> 0)',
        'integer_constraints': 'Count inputs (sides, segments, etc.) must be integers',
        'minimum_values': 'Geometric constraints (e.g., sides >= 3, segments >= 1)',
        'type_checking': 'All dimensional inputs must be numbers (int or float)'
    })
    
    # Standard dimensional parameter names
    standard_parameters: Dict[str, List[str]] = field(default_factory=lambda: {
        'box': ['width', 'height', 'depth'],
        'sphere': ['radius'],
        'cylinder': ['radius', 'height'],
        'polygon': ['sides', 'radius', 'height'],
        'torus': ['major_radius', 'minor_radius'],
        'cone': ['base_radius', 'top_radius', 'height']
    })
    
    # Required validation code pattern
    validation_pattern_example: str = '''
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        for param in ['width', 'height', 'depth']:  # or relevant params
            if param in inputs:
                value = inputs[param]
                if not isinstance(value, (int, float)):
                    errors.append(f"Input {param} must be a number")
                elif value <= 0:
                    errors.append(f"Input {param} must be positive")
        return errors
    '''

# ============================================================================
# NODE SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class NodeSystemSpec:
    """Rules for all nodes in the system"""
    
    # Required methods for EVERY node
    required_methods: List[str] = field(default_factory=lambda: [
        'get_spec',  # Must return NodeSpec
        'validate',  # Must validate inputs
        'execute',   # Must execute logic
    ])
    
    # Required class attributes
    required_attributes: List[str] = field(default_factory=lambda: [
        'NODE_TYPE',      # Changed from 'node_type'
        'NODE_CATEGORY',  # Changed from 'category'
        'NODE_NAME',      # Added for frontend compatibility
        'NODE_DESCRIPTION', # Added for frontend compatibility
    ])
    
    # Method signatures that MUST match exactly
    method_signatures: Dict[str, str] = field(default_factory=lambda: {
        'execute': '(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]',
        'validate': '(self, inputs: Dict[str, Any]) -> List[str]',
        'get_spec': '(cls) -> NodeSpec',
    })
    
    # Naming conventions (enforced via regex)
    naming_rules: Dict[str, str] = field(default_factory=lambda: {
        'node_class': r'^[A-Z][a-zA-Z0-9]+Node$',  # Must end with 'Node', allow numbers
        'node_type': r'^[A-Z][a-zA-Z0-9]+$',  # PascalCase, allow numbers
        'port_name': r'^[a-z][a-z_]*$',  # snake_case
    })

# ============================================================================
# GEOMETRY NAMING SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class GeometryNamingSpec:
    """Standard naming conventions for all geometry created by nodes"""
    
    # Core naming pattern: {node_type}_{short_id}_{source_name}_{index}
    base_pattern: str = "{node_type}_{short_id}_{source_name}"
    array_pattern: str = "{node_type}_{short_id}_{source_name}_{index:03d}"
    
    # Node type mappings (kebab-case to underscore)
    node_type_mappings: Dict[str, str] = field(default_factory=lambda: {
        'body_instance': 'body_instance',
        'linear_array': 'linear_array', 
        'radial_array': 'radial_array',
        'surface_array': 'surface_array',
        'cube_generator': 'cube',
        'sphere_generator': 'sphere', 
        'cylinder_generator': 'cylinder',
        'polygon_generator': 'polygon',
        'extrude_node': 'extrude',
        'loft_node': 'loft',
        'revolve_node': 'revolve',
    })
    
    # Source name extraction rules
    source_name_rules: Dict[str, str] = field(default_factory=lambda: {
        'body_instance': 'Use selected body name',
        'array_nodes': 'Use source body name', 
        'generator_nodes': 'Use descriptive name (Box, Sphere, etc.)',
        'transform_nodes': 'Use source geometry name',
    })
    
    # Example naming patterns
    naming_examples: Dict[str, List[str]] = field(default_factory=lambda: {
        'single_body': [
            'body_instance_2589_Body1',
            'cube_3245_Box', 
            'sphere_1847_Sphere',
            'extrude_9823_Profile1'
        ],
        'array_bodies': [
            'linear_array_5647_Body1_000',
            'linear_array_5647_Body1_001', 
            'linear_array_5647_Body1_002',
            'radial_array_8392_Cylinder_000',
            'radial_array_8392_Cylinder_001'
        ],
        'generated_bodies': [
            'cube_1234_Box',
            'sphere_5678_Sphere', 
            'cylinder_9012_Cylinder',
            'polygon_3456_Hexagon'
        ],
        'nested_arrays': [
            # Original: Body1
            'linear_array_5647_Body1_000',  # 1st level array
            'linear_array_8392_Body1_L2_000',  # 2nd level array (intelligently pruned)
            'linear_array_9876_Body1_L3_000',  # 3rd level array (further pruned)
            # Instead of: linear_array_9876_linear_array_8392_linear_array_5647_Body1_000_001_002
        ]
    })
    
    # Validation rules
    validation_patterns: Dict[str, str] = field(default_factory=lambda: {
        'valid_name': r'^[a-z_]+_\d+_[A-Za-z0-9_L]+(_\d{3})?$',  # Allow L for level indicators
        'node_type_part': r'^[a-z_]+$',
        'short_id_part': r'^\d+$',  
        'source_name_part': r'^[A-Za-z0-9_L]+$',  # Allow L for level indicators
        'index_part': r'^\d{3}$',  # Always 3 digits for arrays
    })
    
    # Reserved names to avoid
    reserved_names: List[str] = field(default_factory=lambda: [
        'Body', 'Component', 'Feature', 'Sketch', 
        'Construction', 'Origin', 'Timeline'
    ])
    
    # Name length limits
    length_limits: Dict[str, int] = field(default_factory=lambda: {
        'max_total_length': 100,  # Fusion 360 limit
        'max_node_type_length': 20,
        'max_source_name_length': 40,
        'recommended_total_length': 50,  # For readability
    })

# ============================================================================
# SERVICE LIFECYCLE SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class ServiceLifecycleSpec:
    """Rules for service and event lifecycle management"""
    
    # Core non-persistence requirement
    non_persisting_requirement: str = "ALL events and services MUST stop when palette closes/hides"
    
    # Resource cleanup rules
    cleanup_requirements: List[str] = field(default_factory=lambda: [
        'ALL polling, intervals, and background services MUST be cleaned up',
        'No event listeners may persist after palette closure',
        'No network requests may continue after palette inactive',
        'All timers and async operations must be cancelled on shutdown',
        'Memory references must be cleared to prevent leaks',
    ])
    
    # Inert system mandate
    inert_requirement: str = "System MUST be 100% inert when palette is not visible"
    
    # Required cleanup triggers
    required_cleanup_triggers: List[str] = field(default_factory=lambda: [
        'window.beforeunload',
        'document.visibilitychange',  
        'window.pagehide',
        'component_unmount',
        'palette_hide',
        'backend_timeout',
    ])
    
    # Service timeout rules
    timeout_requirements: Dict[str, int] = field(default_factory=lambda: {
        'backend_inactivity_timeout_seconds': 10,
        'cleanup_grace_period_seconds': 3,
    })
    
    # Forbidden persisting patterns
    forbidden_patterns: List[str] = field(default_factory=lambda: [
        'setInterval without cleanup',
        'setTimeout without cleanup',
        'event listeners without removal',
        'polling without stop condition',
        'background processes without kill switch',
        'zombie network requests',
    ])

# ============================================================================
# DOCUMENT LIFECYCLE SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class DocumentLifecycleSpec:
    """Rules for document state management and transitions"""
    
    # Core behavioral rules
    behavioral_rules: Dict[str, str] = field(default_factory=lambda: {
        'generate_storage': 'ONLY Generate button may store graph to BaseFeature',
        'document_switch_method': 'Document switch uses HTML palette reload for complete frontend reset',
        'html_reload_isolation': 'palette.htmlFileURL = palette.htmlFileURL provides clean frontend state',
        'clear_vs_switch': 'Clear button deletes timeline features, document switch preserves timeline',
        'cross_document_isolation': 'Each document maintains independent graph state via object ID tracking',
        'unique_document_tracking': 'Documents tracked by Python id(document) for reliable switching',
    })
    
    # Required document switch sequence (HTML reload approach)
    document_switch_sequence: List[str] = field(default_factory=lambda: [
        'detect_document_change_via_object_id',
        'update_backend_document_references', 
        'trigger_html_palette_reload',
        'frontend_reinitializes_cleanly',
        'scan_active_document_for_base_feature',
        'populate_if_feature_exists',
    ])
    
    # HTML reload implementation requirements
    html_reload_requirements: List[str] = field(default_factory=lambda: [
        'Use palette.htmlFileURL = palette.htmlFileURL for reload',
        'Backend state updates BEFORE HTML reload trigger',
        'Frontend gets fresh React/ReactFlow state automatically',
        'Visual flash acceptable UX feedback for document switches',
    ])
    
    # State management for different operations
    state_clearing_rules: Dict[str, List[str]] = field(default_factory=lambda: {
        'document_switch': [
            'update_design_reference_to_active_document',
            'update_base_feature_reference_to_active_document', 
            'trigger_html_reload_for_frontend_reset',
        ],
        'generate_action': [
            'validate_active_design_reference',
            'store_graph_to_base_feature_in_active_document',
            'update_timeline_in_active_document',
        ],
        'clear_button': [
            'delete_base_features_from_active_document_timeline',
            'clear_frontend_via_clear_action',
        ],
    })
    
    # Cross-document contamination prevention
    isolation_requirements: List[str] = field(default_factory=lambda: [
        'no_shared_base_feature_references',
        'no_cross_document_geometry_leaks',
        'independent_graph_state_per_document',
        'fresh_design_reference_validation',
    ])

# ============================================================================
# API-FIRST DEVELOPMENT SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class APIFirstSpec:
    """Rules for preferring existing APIs over custom implementations"""
    
    # Core API-first principle
    api_first_principle: str = "ALWAYS check existing APIs before implementing custom solutions"
    
    # ReactFlow API preferences
    reactflow_api_rules: List[str] = field(default_factory=lambda: [
        'Use reactFlowInstance.fitView({ maxZoom: 1.0 }) instead of custom zoom logic',
        'Use ReactFlow Controls component with fitViewOptions instead of custom controls',
        'Use built-in node/edge types when possible before creating custom ones',
        'Use ReactFlow hooks (useReactFlow, useNodes, useEdges) for state management',
        'Use ReactFlow validation (isValidConnection) instead of custom validation',
        'Use ReactFlow positioning (screenToFlowPosition) instead of manual calculations',
    ])
    
    # Fusion 360 API preferences  
    fusion_api_rules: List[str] = field(default_factory=lambda: [
        'Use adsk.fusionSendData() for official communication patterns',
        'Use Fusion document events (documentActivated) instead of polling',
        'Use BaseFeature system for persistence instead of external files',
        'Use Fusion timeline API for geometry deletion instead of manual tracking',
        'Use id(document) for reliable document identification',
        'Use palette.htmlFileURL reassignment for clean reloads',
    ])
    
    # Custom implementation criteria
    custom_implementation_allowed: List[str] = field(default_factory=lambda: [
        'No existing API provides the required functionality',
        'Existing API has known limitations that prevent use case',
        'Performance requirements cannot be met with existing API',
        'Security or architecture constraints require custom approach',
    ])
    
    # Required validation before custom code
    api_research_requirements: List[str] = field(default_factory=lambda: [
        'Document the existing API that was considered',
        'Explain why existing API cannot meet requirements', 
        'Show evidence of API research (docs, testing, community)',
        'Prefer API extension/configuration over complete replacement',
    ])

# ============================================================================
# DATA FLOW COMPOSITION SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class DataFlowCompositionSpec:
    """Rules for composing arbitrary data flows and ensuring intelligent data compounding"""
    
    # Core composition principle
    composition_principle: str = "System MUST intelligently compound data from ANY source in ANY order"
    
    # Flow composition validation rules
    flow_validation_rules: Dict[str, List[str]] = field(default_factory=lambda: {
        'cross_type_compatibility': [
            'Transform chains MUST be compatible with any collection type',
            'Collections MUST accept transforms from any transform node chain', 
            'Geometry MUST be convertible to collections via atomizer pattern',
            'Arrays MUST preserve source geometry metadata through duplication',
            'Effects MUST be applicable to any collection regardless of source',
        ],
        'semantic_consistency': [
            'Transform operations MUST accumulate through chaining without data loss',
            'Collection instance counts MUST be preserved through effect chains',
            'Geometry properties MUST be maintained through all transformations',
            'Surface references MUST remain valid through array operations',
            'Selection tokens MUST be preserved through node graph execution',
        ],
        'arbitrary_order_support': [
            'Node execution order MUST NOT affect final result (commutative where appropriate)',
            'Data validated at each node boundary ensures consistent state',
            'Missing optional inputs MUST use sensible identity defaults',
            'Invalid connections MUST be caught at validation time, not runtime',
            'Graph cycles MUST be detected and prevented with clear error messages',
        ]
    })
    
    # Cross-type integration patterns
    cross_type_patterns: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        'geometry_to_collection': {
            'pattern': 'GeometryEnvelope -> Atomizer -> CollectionSpec',
            'validation': 'Geometry must have valid kind, id, and geometry data',
            'result': 'Single-instance collection with identity transform',
        },
        'collection_duplication': {
            'pattern': 'CollectionSpec -> Array -> CollectionSpec',
            'validation': 'Source collection must have valid instances',
            'result': 'Expanded collection with positioned instances',
        },
        'transform_application': {
            'pattern': 'TransformChain + CollectionSpec -> Effector -> CollectionSpec',
            'validation': 'Transform chain must be compatible with collection instances',
            'result': 'Collection with modified instance transforms',
        },
        'surface_guided_arrays': {
            'pattern': 'CollectionSpec + SurfaceSpec -> ArraySurface -> CollectionSpec',
            'validation': 'Surface must be valid and collection must be atomized',
            'result': 'Collection instances distributed across surface',
        }
    })
    
    # Automatic data conversion rules
    automatic_conversion_rules: List[str] = field(default_factory=lambda: [
        'Single geometry inputs auto-convert to collections via atomizer pattern',
        'Transform objects auto-convert between supported formats (matrix, nested, flat)',
        'Collection instances with missing transforms auto-fill with identity transforms',
        'Invalid numeric inputs auto-clamp to sensible ranges with warnings',
        'Missing vector components default to 0.0 for translations, 1.0 for scales',
        'Empty collections pass through chains unchanged (identity behavior)',
    ])
    
    # Intelligent compounding behaviors
    intelligent_compounding: Dict[str, List[str]] = field(default_factory=lambda: {
        'transform_accumulation': [
            'Scale operations multiply cumulatively (scale 2x then 3x = 6x total)',
            'Rotation operations accumulate in local space unless specified otherwise',
            'Translation operations accumulate in current coordinate space',
            'Matrix operations compose through proper matrix multiplication',
        ],
        'collection_merging': [
            'Multiple collection inputs merge instances maintaining unique IDs',
            'Conflicting source geometries prefer most recent when IDs match',
            'Instance transforms preserve during collection merge operations',
            'Metadata merges using last-write-wins for conflicting keys',
        ],
        'effect_combination': [
            'Multiple effects chain sequentially, each receiving previous result',
            'Overlapping effect ranges blend using specified blend modes',
            'Effect parameters interpolate smoothly across affected regions',
            'Effect masks combine using boolean logic (union, intersection, etc.)',
        ]
    })

# ============================================================================
# RUNTIME DATA INTEGRITY SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class RuntimeDataIntegritySpec:
    """Continuous validation and integrity checking during execution"""
    
    # Runtime validation requirements
    continuous_validation_points: List[str] = field(default_factory=lambda: [
        'Node input validation before execute() method',
        'Contract object construction validation (__post_init__)',
        'Node output validation after execute() method', 
        'Data flow boundary validation between nodes',
        'Collection instance consistency validation during processing',
        'Transform chain validation during composition',
        'Geometry envelope validation before materialization',
    ])
    
    # Integrity check patterns
    integrity_check_patterns: Dict[str, List[str]] = field(default_factory=lambda: {
        'data_consistency': [
            'Collection instance count matches expected from inputs',
            'Transform matrices remain invertible throughout processing',
            'Geometry references remain valid after node operations',
            'Source geometry metadata preserved through all transformations',
            'Instance IDs remain unique within collections',
        ],
        'numerical_stability': [
            'Transform values remain within reasonable bounds (no NaN/Inf)',
            'Scale values remain positive and non-zero',
            'Matrix determinants remain non-zero (no degenerate transforms)',
            'Vector magnitudes remain finite and reasonable',
            'Array counts produce reasonable memory requirements',
        ],
        'semantic_validity': [
            'Collection instances reference existing source geometries',
            'Transform chains maintain mathematical validity',
            'Surface references remain valid throughout processing',
            'Selection tokens correspond to existing Fusion entities',
            'Node graph remains acyclic during execution',
        ]
    })
    
    # Error recovery strategies
    error_recovery_strategies: Dict[str, str] = field(default_factory=lambda: {
        'invalid_transforms': 'Replace with identity transform and log warning',
        'missing_geometry': 'Skip instance and continue processing remaining',
        'numerical_overflow': 'Clamp to reasonable bounds and log warning',
        'invalid_collections': 'Return empty collection with error status',
        'surface_failures': 'Fall back to grid array pattern with warning',
        'memory_limits': 'Reduce array counts to safe levels and warn user',
    })
    
    # Performance monitoring
    performance_monitoring: List[str] = field(default_factory=lambda: [
        'Track node execution times for performance regression detection',
        'Monitor memory usage during large array operations',
        'Validate geometry complexity remains within Fusion limits',
        'Check for exponential growth in instance counts',
        'Monitor transform chain depth for reasonable limits',
    ])

# ============================================================================
# SEMANTIC VALIDATION SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class SemanticValidationSpec:
    """Logical consistency validation beyond type checking"""
    
    # Semantic consistency rules
    semantic_rules: Dict[str, List[str]] = field(default_factory=lambda: {
        'geometric_consistency': [
            'Array patterns must not place instances outside surface bounds',
            'Transform chains must preserve geometric feasibility',
            'Collection instances must reference geometries that can be materialized',
            'Surface arrays must respect surface topology and boundaries',
            'Radial arrays must have positive radius and reasonable angle steps',
        ],
        'mathematical_consistency': [
            'Transform operations must preserve geometric relationships',
            'Scale factors must maintain positive definite matrices',
            'Rotation angles must be normalized to reasonable ranges',
            'Array counts must result in reasonable spacing',
            'Effect falloff curves must be monotonic and bounded',
        ],
        'workflow_consistency': [
            'Node chains must follow logical geometry → collection → effect → material flow',
            'Transform chains must precede collection application',
            'Arrays must operate on existing collections, not raw geometry',
            'Effects must have valid collections as input',
            'Materializer must receive fully processed collections',
        ]
    })
    
    # Cross-node relationship validation
    relationship_validation: Dict[str, str] = field(default_factory=lambda: {
        'atomizer_requirements': 'Must receive valid geometry envelope with required fields',
        'array_requirements': 'Must receive collection with at least one valid instance',
        'effector_requirements': 'Must receive both valid collection and transform chain',
        'materializer_requirements': 'Must receive collection with materializable instances',
        'transform_requirements': 'Must receive valid transform data or use identity default',
    })
    
    # User intent preservation
    intent_preservation_rules: List[str] = field(default_factory=lambda: [
        'Array spacing must reflect user-specified parameters accurately',
        'Transform effects must be visually predictable from parameter values',
        'Collection merging must preserve user-defined geometry relationships',
        'Effect falloff must behave intuitively based on distance metrics',
        'Material application must respect original geometry properties',
    ])

# ============================================================================
# ARCHITECTURE SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class ArchitectureSpec:
    """System-wide architecture rules"""
    
    # Module dependencies (what can import what)
    dependency_rules: Dict[str, List[str]] = field(default_factory=lambda: {
        'nodes': ['contracts', 'services'],  # Nodes can only import these
        'services': ['contracts'],  # Services can only import contracts
        'contracts': [],  # Contracts import nothing
        'core': ['contracts', 'services', 'nodes'],  # Core orchestrates
    })
    
    # Forbidden imports (will raise error)
    forbidden_imports: List[str] = field(default_factory=lambda: [
        'from adsk',  # NO direct Fusion imports except in services
    ])
    
    # Singleton classes (only one instance allowed)
    singleton_classes: List[str] = field(default_factory=lambda: [
        'Application',
        'ServiceContainer',
        'NodeRegistry',
    ])

# ============================================================================
# THE MASTER SPECIFICATION
# ============================================================================

@dataclass(frozen=True)
class MasterSpecification:
    """The complete backend specification for Noodle v2"""
    
    logging: LoggingSpec = field(default_factory=LoggingSpec)
    selection_patterns: SelectionPatternSpec = field(default_factory=SelectionPatternSpec)
    data_contracts: DataContractSpec = field(default_factory=DataContractSpec)
    data_flow_composition: DataFlowCompositionSpec = field(default_factory=DataFlowCompositionSpec)
    runtime_data_integrity: RuntimeDataIntegritySpec = field(default_factory=RuntimeDataIntegritySpec)
    semantic_validation: SemanticValidationSpec = field(default_factory=SemanticValidationSpec)
    node_integration: NodeIntegrationSpec = field(default_factory=NodeIntegrationSpec)
    geometry_nodes: GeometryNodeSpec = field(default_factory=GeometryNodeSpec)
    node_system: NodeSystemSpec = field(default_factory=NodeSystemSpec)
    geometry_naming: GeometryNamingSpec = field(default_factory=GeometryNamingSpec)
    service_lifecycle: ServiceLifecycleSpec = field(default_factory=ServiceLifecycleSpec)
    document_lifecycle: DocumentLifecycleSpec = field(default_factory=DocumentLifecycleSpec)
    api_first: APIFirstSpec = field(default_factory=APIFirstSpec)
    architecture: ArchitectureSpec = field(default_factory=ArchitectureSpec)
    
    def validate_all(self) -> List[str]:
        """Validate the entire specification is internally consistent"""
        errors = []
        # Add validation logic
        return errors

# The ONE instance
SPECIFICATION = MasterSpecification()