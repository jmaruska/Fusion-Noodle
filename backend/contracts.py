"""Data contracts for backend.
All data flowing through the system must use these contracts.
"""

from dataclasses import dataclass, field
# Conditional import for Fusion 360 compatibility
try:
    from typing import Any, List, Optional, Dict
except ImportError:
    from typing import Any, Optional, Dict
    List = list  # Fallback to built-in list
from enum import Enum
import re


def port_label(name: str, label: str = "") -> str:
    """The label a port shows in the palette: its own label, or its name in Title Case.

    Matches titleCase in ui/src/utils/nodeSpec.js: underscores become spaces and the first
    character of each word is uppercased; the rest is left as written. Use it whenever a
    message for the user names a port, so the message says what the node shows.
    """
    if label:
        return label
    return re.sub(r'\b\w', lambda m: m.group().upper(), name.replace('_', ' '), flags=re.ASCII)


_UNIT_SUFFIX = {'length': ' cm', 'angle': '°'}


def _number(value: float) -> str:
    return f"{value:g}"


def bounds_problem(port: "PortSpec", value: Any, inputs: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """What's wrong with `value` for a numeric port with declared bounds, or None.

    The palette shows the same message (boundsProblem in ui/src/utils/portBounds.js).
    A port hidden by `visible_when` isn't checked: its value doesn't count.
    Every number port is checked to hold a number; a missing value or a modifier's
    descriptor (a dict) is left alone.
    """
    if port.port_type not in (PortType.FLOAT, PortType.INTEGER):
        return None
    when = port.visible_when
    if when and (inputs or {}).get(when['port'], when.get('default')) not in when['values']:
        return None
    label = port_label(port.name, port.label)
    # Missing values take the default; a dict is a modifier's descriptor, which the
    # node evaluates per instance. Anything else that isn't a number is a mistake.
    if value is None or isinstance(value, dict):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return f"{label} must be a number"
    if port.port_type == PortType.INTEGER and float(value) != int(value):
        return f"{label} must be a whole number"
    lo, hi, unit = port.min_value, port.max_value, _UNIT_SUFFIX.get(port.unit or '', '')
    if lo is not None and hi is not None and not (lo <= value <= hi):
        return f"{label} must be between {_number(lo)} and {_number(hi)}{unit}"
    if lo is not None and value < lo:
        return f"{label} must be at least {_number(lo)}{unit}"
    if hi is not None and value > hi:
        return f"{label} must be at most {_number(hi)}{unit}"
    return None


class PortType(Enum):
    """All allowed port types in the system"""
    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING = "string"
    ENUM = "enum"
    VECTOR3 = "vector3"
    TRANSFORM = "transform"
    GEOMETRY = "geometry"
    COLLECTION = "collection"
    SURFACE = "surface"  # For individual surface patch selections (BRepFace)
    BODY = "body"  # For body selections (BRepBody)
    POINT = "point"  # For point selections (construction points, sketch points, vertices)
    CURVE = "curve"  # For curve selections (SketchCurve, BRepEdge) used as distribution paths
    SPACER = "spacer"  # For visual spacing in node layouts

    BREP = "geometry"  # Alias for geometry

@dataclass
class PortSpec:
    """Specification for a node port"""
    name: str
    port_type: PortType
    default_value: Any = None
    required: bool = False
    description: str = ""
    label: str = ""  # Display label for the port (if empty, uses formatted name)
    selection_type: Optional[str] = None  # For selection ports (e.g., "body", "surface")
    enum_options: Optional[List[str]] = None  # For ENUM ports - dropdown options
    enum_icons: Optional[Dict[str, str]] = None  # For ENUM ports - icon path per option value
    enum_labels: Optional[Dict[str, str]] = None  # For ENUM ports - display label per option value
    show_input_field: bool = True  # Whether to show input field for this port (text boxes, etc.)
    show_input_handle: bool = True  # Whether to show input connection handle/dot
    min_value: Optional[float] = None  # Minimum allowed value for numeric ports
    max_value: Optional[float] = None  # Maximum allowed value for numeric ports
    label_from: Optional[Dict[str, Any]] = None  # Dynamic label: {'port': 'sibling_name', 'map': {'val': 'Label'}}
    unit: Optional[str] = None  # What the number measures: 'length' (cm) or 'angle' (degrees). Shown as a suffix on the input.
    visible_when: Optional[Dict[str, Any]] = None  # Show only for some values of a sibling: {'port': 'shape', 'values': ['box'], 'default': 'sphere'}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert port spec to dictionary for frontend"""
        data = {
            'name': self.name,
            'type': self.port_type.value,
            'required': self.required,
            'defaultValue': self.default_value,
            'showInputField': self.show_input_field,
            'showInputHandle': self.show_input_handle,
            'description': self.description,
            'label': port_label(self.name, self.label)
        }
        if self.selection_type:
            data['selectionType'] = self.selection_type
        if self.enum_options:
            data['enumOptions'] = self.enum_options
        if self.enum_icons:
            data['enumIcons'] = self.enum_icons
        if self.enum_labels:
            data['enumLabels'] = self.enum_labels
        if self.min_value is not None:
            data['minValue'] = self.min_value
        if self.max_value is not None:
            data['maxValue'] = self.max_value
        if self.label_from is not None:
            data['labelFrom'] = self.label_from
        if self.unit is not None:
            data['unit'] = self.unit
        if self.visible_when is not None:
            data['visibleWhen'] = self.visible_when
        return data

@dataclass
class NodeSpec:
    """Complete specification for a node"""
    node_type: str
    category: str
    inputs: List[PortSpec]
    outputs: List[PortSpec]
    description: str = ""
    version: str = "1.0"
    wide: bool = False  # If true, node should be rendered wide in frontend

    def port_label(self, name: str) -> str:
        """The palette label of the input (or, failing that, output) port called `name`."""
        for port in list(self.inputs) + list(self.outputs):
            if port.name == name:
                return port_label(port.name, port.label)
        return port_label(name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert node spec to dictionary for frontend"""
        return {
            'node_type': self.node_type,
            'category': self.category,
            'inputs': [port.to_dict() for port in self.inputs],
            'outputs': [port.to_dict() for port in self.outputs],
            'description': self.description,
            'version': self.version,
            'wide': self.wide
        }

@dataclass
class Vector3Spec:
    """3D vector contract"""
    x: float
    y: float
    z: float
    
    def to_dict(self) -> dict:
        return {'x': self.x, 'y': self.y, 'z': self.z}

@dataclass
class NoodleAttributes:
    """Maya-inspired attributes - flattened primitives, no nesting"""
    # Core transform (9 primitives - Maya style)
    tx: float = 0.0    # translate X
    ty: float = 0.0    # translate Y  
    tz: float = 0.0    # translate Z
    rx: float = 0.0    # rotate X (degrees) - LEGACY, prefer quaternions for complex rotations
    ry: float = 0.0    # rotate Y (degrees) - LEGACY, prefer quaternions for complex rotations
    rz: float = 0.0    # rotate Z (degrees) - LEGACY, prefer quaternions for complex rotations
    sx: float = 1.0    # scale X
    sy: float = 1.0    # scale Y
    sz: float = 1.0    # scale Z
    
    # Enhanced rotation (quaternion) - mathematically superior for complex orientations
    qx: float = 0.0    # quaternion X component
    qy: float = 0.0    # quaternion Y component  
    qz: float = 0.0    # quaternion Z component
    qw: float = 1.0    # quaternion W component (scalar part)
    use_quaternion: bool = False  # Flag: use quaternion rotation instead of Euler
    
    # Visibility control (Maya-style)
    v: bool = True      # visibility (Maya standard)
    template: bool = False
    
    # Advanced features (optional, for future pivot nodes)
    rotate_order: str = "xyz"  # Avoid gimbal lock
    rp_x: float = 0.0         # Rotation pivot X
    rp_y: float = 0.0         # Rotation pivot Y
    rp_z: float = 0.0         # Rotation pivot Z
    sp_x: float = 0.0         # Scale pivot X
    sp_y: float = 0.0         # Scale pivot Y
    sp_z: float = 0.0         # Scale pivot Z
    
    def __post_init__(self):
        """Spec enforcement: Transform fields MUST never be None"""
        transform_fields = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'qx', 'qy', 'qz', 'qw']
        for field in transform_fields:
            value = getattr(self, field)
            if value is None:
                raise ValueError(f"Spec violation: NoodleAttributes.{field} cannot be None. "
                               f"Transform fields MUST never be None per specification.")
        
        # Normalize quaternion if using quaternion rotation
        if self.use_quaternion:
            quat_length = (self.qx**2 + self.qy**2 + self.qz**2 + self.qw**2) ** 0.5
            if quat_length > 0:
                self.qx /= quat_length
                self.qy /= quat_length 
                self.qz /= quat_length
                self.qw /= quat_length
    
    @classmethod
    def from_matrix(cls, matrix_dict: dict, tx: float = 0.0, ty: float = 0.0, tz: float = 0.0, sx: float = 1.0, sy: float = 1.0, sz: float = 1.0) -> 'NoodleAttributes':
        """Create NoodleAttributes from transformation matrix using quaternions (no gimbal lock)"""
        import math
        
        # Extract rotation matrix (3x3 upper-left)
        m00, m01, m02 = matrix_dict.get('m00', 1.0), matrix_dict.get('m01', 0.0), matrix_dict.get('m02', 0.0)
        m10, m11, m12 = matrix_dict.get('m10', 0.0), matrix_dict.get('m11', 1.0), matrix_dict.get('m12', 0.0)
        m20, m21, m22 = matrix_dict.get('m20', 0.0), matrix_dict.get('m21', 0.0), matrix_dict.get('m22', 1.0)
        
        # Remove scale from rotation matrix to get pure rotation
        scale_x = math.sqrt(m00*m00 + m10*m10 + m20*m20)
        scale_y = math.sqrt(m01*m01 + m11*m11 + m21*m21)
        scale_z = math.sqrt(m02*m02 + m12*m12 + m22*m22)
        
        # Handle negative determinant (reflection)
        det = m00*(m11*m22 - m12*m21) - m01*(m10*m22 - m12*m20) + m02*(m10*m21 - m11*m20)
        if det < 0:
            scale_x = -scale_x
        
        # Extract pure rotation matrix
        if scale_x != 0 and scale_y != 0 and scale_z != 0:
            r00, r01, r02 = m00/scale_x, m01/scale_y, m02/scale_z
            r10, r11, r12 = m10/scale_x, m11/scale_y, m12/scale_z
            r20, r21, r22 = m20/scale_x, m21/scale_y, m22/scale_z
        else:
            # Identity rotation if scale is zero
            r00, r01, r02 = 1.0, 0.0, 0.0
            r10, r11, r12 = 0.0, 1.0, 0.0
            r20, r21, r22 = 0.0, 0.0, 1.0
        
        # Convert rotation matrix to quaternion (Shepperd's method)
        trace = r00 + r11 + r22
        if trace > 0:
            s = math.sqrt(trace + 1.0) * 2  # s=4*qw 
            qw = 0.25 * s
            qx = (r21 - r12) / s
            qy = (r02 - r20) / s
            qz = (r10 - r01) / s
        elif r00 > r11 and r00 > r22:
            s = math.sqrt(1.0 + r00 - r11 - r22) * 2  # s=4*qx
            qw = (r21 - r12) / s
            qx = 0.25 * s
            qy = (r01 + r10) / s
            qz = (r02 + r20) / s
        elif r11 > r22:
            s = math.sqrt(1.0 + r11 - r00 - r22) * 2  # s=4*qy
            qw = (r02 - r20) / s
            qx = (r01 + r10) / s
            qy = 0.25 * s
            qz = (r12 + r21) / s
        else:
            s = math.sqrt(1.0 + r22 - r00 - r11) * 2  # s=4*qz
            qw = (r10 - r01) / s
            qx = (r02 + r20) / s
            qy = (r12 + r21) / s
            qz = 0.25 * s
        
        # Use provided translation/scale or extract from matrix
        final_tx = tx if tx != 0.0 else matrix_dict.get('m03', 0.0)
        final_ty = ty if ty != 0.0 else matrix_dict.get('m13', 0.0)  
        final_tz = tz if tz != 0.0 else matrix_dict.get('m23', 0.0)
        final_sx = sx if sx != 1.0 else scale_x
        final_sy = sy if sy != 1.0 else scale_y
        final_sz = sz if sz != 1.0 else scale_z
        
        return cls(
            tx=final_tx, ty=final_ty, tz=final_tz,
            rx=0.0, ry=0.0, rz=0.0,  # Leave Euler angles at identity when using quaternions
            sx=final_sx, sy=final_sy, sz=final_sz,
            qx=qx, qy=qy, qz=qz, qw=qw,
            use_quaternion=True
        )
    
    def to_dict(self) -> dict:
        """Single-level serialization - no nesting!"""
        from dataclasses import asdict
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'NoodleAttributes':
        """Simple conversion - all primitives, no nested object creation"""
        if isinstance(data, NoodleAttributes):
            return data
        # Filter out None values for transform fields and use class defaults for missing fields
        transform_fields = {'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'}
        kwargs = {}
        
        # Process all dataclass fields
        for field in cls.__dataclass_fields__.values():
            if field.name in data and data[field.name] is not None:
                # Use provided value if present and not None
                kwargs[field.name] = data[field.name]
        # Fields that are missing or None keep the dataclass defaults
        return cls(**kwargs)
    
    @classmethod
    def identity(cls) -> 'NoodleAttributes':
        """Create identity attributes (Maya-style)"""
        return cls()
    
    def copy(self) -> 'NoodleAttributes':
        """Create a copy of these attributes"""
        return NoodleAttributes(**self.to_dict())

@dataclass
class GeometryEnvelope:
    """Envelope for geometry data"""
    kind: str  # 'brep', 'mesh', 'surface', etc.
    id: str
    geometry: Any  # The actual Fusion geometry object
    geometry_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to serializable dict - preserve geometry object for materialization"""
        return {
            'kind': self.kind,
            'id': self.id,
            'geometry': self.geometry,  # Preserve actual geometry object
            'geometry_name': self.geometry_name,
            'metadata': self.metadata
        }

@dataclass
class CollectionInstanceSpec:
    """Single instance in a collection - NoodleAttributes only (v2 simplified)"""
    instance_id: str
    source_geometry_id: str
    transform: Any = None  # NoodleAttributes only
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Ensure transform is NoodleAttributes - simplified v2 contract"""
        if self.transform is None:
            self.transform = NoodleAttributes.identity()
        elif isinstance(self.transform, dict):
            # Only support NoodleAttributes format (Maya-style)
            if any(k in self.transform for k in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']):
                try:
                    self.transform = NoodleAttributes.from_dict(self.transform)
                except (TypeError, KeyError):
                    self.transform = NoodleAttributes.identity()
            else:
                # Unknown format - use identity
                self.transform = NoodleAttributes.identity()
    
    def to_dict(self) -> dict:
        return {
            'instance_id': self.instance_id,
            'source_geometry_id': self.source_geometry_id,
            'transform': self.transform.to_dict(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CollectionInstanceSpec':
        """Create instance from dict - NoodleAttributes only"""
        if isinstance(data, CollectionInstanceSpec):
            return data
        transform_data = data.get('transform')
        if transform_data is None or not isinstance(transform_data, dict):
            # Use identity for missing/invalid transforms
            transform = NoodleAttributes.identity()
        else:
            # Only support NoodleAttributes format
            if any(k in transform_data for k in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']):
                try:
                    transform = NoodleAttributes.from_dict(transform_data)
                except (TypeError, KeyError):
                    transform = NoodleAttributes.identity()
            else:
                # Unknown format - use identity
                transform = NoodleAttributes.identity()
            
        return cls(
            instance_id=data['instance_id'],
            source_geometry_id=data['source_geometry_id'],
            transform=transform,
            metadata=data.get('metadata', {})
        )

@dataclass
class CollectionSpec:
    """Collection contract - virtual geometry instances for processing"""
    collection_type: str  # 'geometry_collection'
    collection_id: str
    source_geometries: List[GeometryEnvelope]
    instances: List[CollectionInstanceSpec]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate data types at construction time."""
        # Validate source_geometries
        for i, geo in enumerate(self.source_geometries):
            if isinstance(geo, dict):
                raise TypeError(
                    f"source_geometries[{i}] is dict, expected GeometryEnvelope. "
                    f"Use GeometryEnvelope(**geo_dict) to convert."
                )
            elif not isinstance(geo, GeometryEnvelope):
                raise TypeError(f"source_geometries[{i}] is {type(geo)}, expected GeometryEnvelope")
        
        # Validate instances
        for i, inst in enumerate(self.instances):
            if isinstance(inst, dict):
                raise TypeError(
                    f"instances[{i}] is dict, expected CollectionInstanceSpec. "
                    f"Use CollectionInstanceSpec.from_dict(inst_dict) to convert."
                )
            elif not isinstance(inst, CollectionInstanceSpec):
                raise TypeError(f"instances[{i}] is {type(inst)}, expected CollectionInstanceSpec")
    
    def to_dict(self) -> dict:
        # SERIALIZATION BOUNDARY ONLY — frontend responses, file I/O, logging.
        # Never call this on a value that stays inside the backend execution graph.
        # Wire policy: COLLECTION ports always carry CollectionSpec objects; enforced by enforce_node_spec.
        return {
            'type': self.collection_type,
            'id': self.collection_id,
            'source_geometries': [geo.to_dict() for geo in self.source_geometries],
            'instances': [inst.to_dict() for inst in self.instances],
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CollectionSpec':
        """Create collection from dict with proper validation"""
        if isinstance(data, CollectionSpec):
            return data
        source_geos = []
        for geo_data in data.get('source_geometries', []):
            if isinstance(geo_data, dict):
                source_geos.append(GeometryEnvelope(**geo_data))
            else:
                source_geos.append(geo_data)  # Assume already converted
        
        instances = []
        for inst_data in data.get('instances', []):
            if isinstance(inst_data, dict):
                instances.append(CollectionInstanceSpec.from_dict(inst_data))
            else:
                instances.append(inst_data)  # Assume already converted
        
        return cls(
            collection_type=data.get('type', 'geometry_collection'),
            collection_id=data.get('id', ''),
            source_geometries=source_geos,
            instances=instances,
            metadata=data.get('metadata', {})
        )

# Export all contracts
__all__ = [
    'PortType',
    'PortSpec', 
    'NodeSpec',
    'Vector3Spec',
    'NoodleAttributes',
    'CollectionInstanceSpec',
    'CollectionSpec',
    'GeometryEnvelope'
]