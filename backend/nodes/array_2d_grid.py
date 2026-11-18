"""
Array_2D_Grid node for creating 2D grid arrays of geometry.
Creates collection instances positioned in a grid pattern.
"""

import math
from typing import Dict, Any, List
from ..enforcement import enforce_node_spec
from ..contracts import NodeSpec, PortSpec, PortType, CollectionInstanceSpec, CollectionSpec, NoodleAttributes
from .base import BaseNode
from ..utilities.log_utils import log, LogLevel


HEX_ROW = math.sqrt(3) / 2  # Rows of a hexagonal grid are this fraction of the column spacing apart


def hex_column_spacing(array_type: str, spacing_x: float, spacing_y: float, connected) -> float:
    """The column spacing a grid uses. A hexagonal grid has one spacing, seen two ways:
    Spacing X between columns and Spacing Y = X × √3/2 between rows. Whichever is
    connected drives (X if both are); typed values are kept in step by the palette
    (ui/src/utils/hexSpacing.js), so X is used."""
    if str(array_type).lower() == "hexagonal" and "spacing_y" in connected and "spacing_x" not in connected:
        return spacing_y / HEX_ROW
    return spacing_x


@enforce_node_spec
class Array2DGridNode(BaseNode):
    """Creates 2D grid arrays of geometry as collection instances."""
    
    NODE_TYPE = "Array_2D_Grid"
    NODE_CATEGORY = "array"
    NODE_NAME = "Array 2D Grid"
    NODE_DESCRIPTION = "Create 2D grid array"
    
    # Default values
    DEFAULT_COUNT_X = 3
    DEFAULT_COUNT_Y = 3
    DEFAULT_SPACING_X = 5.0
    DEFAULT_SPACING_Y = 5.0

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            inputs=[
                PortSpec("collection", PortType.COLLECTION, required=True, description="The instances to repeat at every grid point."),
                PortSpec("spacer_0", PortType.SPACER),
                PortSpec("array_type", PortType.ENUM, 
                        default_value="grid", 
                        description="Grid lines rows up, Staggered shifts every other row by half, Hexagonal packs rows tighter.", 
                        label="Type",
                        enum_options=["grid", "stagger", "hexagonal"],
                        enum_labels={"grid": "Grid", "stagger": "Staggered", "hexagonal": "Hexagonal"},
                        show_input_handle=False),
                PortSpec("spacer_1", PortType.SPACER),
                PortSpec("count_x", PortType.INTEGER, default_value=3, min_value=1, max_value=100, description="Number of instances along the grid's first axis."),
                PortSpec("count_y", PortType.INTEGER, default_value=3, min_value=1, max_value=100, description="Number of rows along the grid's second axis."),
                PortSpec("spacing_x", PortType.FLOAT, min_value=0.001, unit="length", default_value=5.0, description="Distance between instances along the first axis; in Hexagonal, the distance across a cell's flats."),
                PortSpec("spacing_y", PortType.FLOAT, min_value=0.001, unit="length", default_value=5.0, description="Distance between rows. In Hexagonal it is linked to Spacing X (rows are √3/2 of it apart)."),
                PortSpec("spacer_2", PortType.SPACER),
                PortSpec("normal", PortType.VECTOR3, 
                        default_value={"x": 0.0, "y": 0.0, "z": 1.0}, 
                        description="The direction the grid's plane faces.")
            ],
            outputs=[
                PortSpec("output_spacer", PortType.SPACER),
                PortSpec("collection", PortType.COLLECTION, description="Collection")
            ],
            description=cls.NODE_DESCRIPTION,
            wide=True
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate array inputs."""
        # Numbers and declared bounds are checked before this runs (bounds_problem in contracts.py)
        errors = []
        
        # Check collection input
        collection = inputs.get("collection")
        if not collection:
            errors.append("Collection input is required")
        elif not (isinstance(collection, (dict, CollectionSpec))):
            errors.append("Collection must be a valid collection object")
        elif isinstance(collection, dict) and 'type' not in collection and 'collection_type' not in collection:
            errors.append("Collection dictionary missing type field")
        
        # Validate array_type parameter
        array_type = inputs.get("array_type", "grid")
        valid_types = ["grid", "stagger", "hexagonal"]
        if array_type not in valid_types:
            errors.append(f"Array type must be one of: {', '.join(valid_types)}")
        
        # Hexagonal: one spacing seen two ways (see hex_column_spacing); rows are
        # √3/2 of the column spacing apart, for equilateral triangles
        
        # Validate normal vector parameter
        normal = inputs.get("normal", {"x": 0.0, "y": 0.0, "z": 1.0})
        if isinstance(normal, dict):
            if not all(coord in normal for coord in ['x', 'y', 'z']):
                errors.append("Normal vector must have x, y, z coordinates")
            else:
                # Check if vector is zero (invalid for normal)
                magnitude = (normal['x']**2 + normal['y']**2 + normal['z']**2)**0.5
                if magnitude < 1e-6:
                    errors.append("Normal vector cannot be zero vector")
        else:
            errors.append("Normal vector must be a valid vector3 object")
        
        return errors

    def _generate_pattern_positions(self, array_type: str, count_x: int, count_y: int, spacing_x: float, spacing_y: float) -> List[tuple]:
        """Generate grid positions based on array pattern type"""
        positions = []
        
        if array_type == "grid":
            # Standard grid pattern - centered around origin
            start_x = -(count_x - 1) * spacing_x / 2.0
            start_y = -(count_y - 1) * spacing_y / 2.0
            
            for j in range(count_y):
                for i in range(count_x):
                    x_pos = start_x + i * spacing_x
                    y_pos = start_y + j * spacing_y
                    positions.append((x_pos, y_pos))
                    
        elif array_type == "stagger":
            # Staggered/brick pattern - alternate rows offset by half spacing
            start_x = -(count_x - 1) * spacing_x / 2.0
            start_y = -(count_y - 1) * spacing_y / 2.0
            
            for j in range(count_y):
                for i in range(count_x):
                    x_pos = start_x + i * spacing_x
                    # Offset every other row
                    if j % 2 == 1:
                        x_pos += spacing_x * 0.5
                    y_pos = start_y + j * spacing_y
                    positions.append((x_pos, y_pos))
                    
        elif array_type == "hexagonal":
            # Hexagonal pattern - triangular grid with equilateral triangles
            # Only uses spacing_x to ensure proper hexagonal geometry
            hex_spacing_y = spacing_x * HEX_ROW  # Rows of equilateral triangles; the palette links Spacing Y to this
            start_x = -(count_x - 1) * spacing_x / 2.0
            start_y = -(count_y - 1) * hex_spacing_y / 2.0
            
            for j in range(count_y):
                for i in range(count_x):
                    x_pos = start_x + i * spacing_x
                    # Offset every other row by half spacing for hexagonal pattern
                    if j % 2 == 1:
                        x_pos += spacing_x * 0.5
                    y_pos = start_y + j * hex_spacing_y  # Use calculated hex spacing
                    positions.append((x_pos, y_pos))
                    
        else:
            # Fallback to grid if unknown type
            start_x = -(count_x - 1) * spacing_x / 2.0
            start_y = -(count_y - 1) * spacing_y / 2.0
            
            for j in range(count_y):
                for i in range(count_x):
                    x_pos = start_x + i * spacing_x
                    y_pos = start_y + j * spacing_y
                    positions.append((x_pos, y_pos))
                    
        return positions
    

    
    @staticmethod
    def _grid_axes(normal):
        """Unit X, Y and Z axes of the grid plane, with Z along the normal."""
        nx, ny, nz = float(normal.get('x', 0.0)), float(normal.get('y', 0.0)), float(normal.get('z', 1.0))
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        z = (nx / length, ny / length, nz / length)

        # Cross with the world axis least aligned with the normal, for stability
        ax, ay, az = abs(z[0]), abs(z[1]), abs(z[2])
        if ax <= ay and ax <= az:
            up = (1.0, 0.0, 0.0)
        elif ay <= ax and ay <= az:
            up = (0.0, 1.0, 0.0)
        else:
            up = (0.0, 0.0, 1.0)

        def cross(a, b):
            return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

        def unit(v):
            n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
            return (v[0] / n, v[1] / n, v[2] / n)

        x = unit(cross(z, up))
        y = unit(cross(z, x))
        return x, y, z

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Create 2D grid array of collection instances."""
        app = context.get('app')
        log(app, f"Executing {self.NODE_TYPE}", level=LogLevel.DEBUG, module=self.NODE_TYPE)

        collection_spec = CollectionSpec.from_dict(inputs.get("collection"))
        if not collection_spec or not collection_spec.source_geometries:
            log(app, "Array node requires a collection with source geometry.", level=LogLevel.WARNING, module=self.NODE_TYPE)
            return {"collection": CollectionSpec(collection_type="geometry_collection", collection_id="empty", instances=[], source_geometries=[])}

        # --- Get Inputs ---
        count_x = int(inputs.get("count_x", self.DEFAULT_COUNT_X))
        count_y = int(inputs.get("count_y", self.DEFAULT_COUNT_Y))
        spacing_x = float(inputs.get("spacing_x", self.DEFAULT_SPACING_X))
        spacing_y = float(inputs.get("spacing_y", self.DEFAULT_SPACING_Y))
        spacing_x = hex_column_spacing(inputs.get("array_type", "grid"), spacing_x, spacing_y,
                                       context.get('connected_inputs') or set())
        normal_vec_spec = inputs.get("normal", {"x": 0.0, "y": 0.0, "z": 1.0})

        log(app, f"Creating {count_x}x{count_y} grid with spacing ({spacing_x}, {spacing_y})", level=LogLevel.DEBUG, module=self.NODE_TYPE)

        # --- Generate Grid Positions & Coordinate System ---
        array_type = inputs.get("array_type", "grid")
        positions = self._generate_pattern_positions(array_type, count_x, count_y, spacing_x, spacing_y)
        
        local_x, local_y, local_z = self._grid_axes(normal_vec_spec)

        # One placement per grid point. The rotation is the same for every point,
        # so this is plain arithmetic rather than a Fusion matrix per instance.
        placements = []
        for u_pos, v_pos in positions:
            px = local_x[0] * u_pos + local_y[0] * v_pos
            py = local_x[1] * u_pos + local_y[1] * v_pos
            pz = local_x[2] * u_pos + local_y[2] * v_pos
            placements.append(NoodleAttributes.from_matrix({
                'm00': local_x[0], 'm01': local_y[0], 'm02': local_z[0], 'm03': px,
                'm10': local_x[1], 'm11': local_y[1], 'm12': local_z[1], 'm13': py,
                'm20': local_x[2], 'm21': local_y[2], 'm22': local_z[2], 'm23': pz,
                'm30': 0.0, 'm31': 0.0, 'm32': 0.0, 'm33': 1.0,
            }))

        # Like the surface arrays: every incoming instance is copied to every grid
        # point and keeps its own scale and source geometry. Its position and
        # rotation are replaced by the grid's.
        instances = []
        for source in collection_spec.instances or []:
            source_transform = getattr(source, 'transform', None)
            sx = getattr(source_transform, 'sx', 1.0) or 1.0
            sy = getattr(source_transform, 'sy', 1.0) or 1.0
            sz = getattr(source_transform, 'sz', 1.0) or 1.0
            source_geometry_id = getattr(source, 'source_geometry_id', None) or collection_spec.source_geometries[0].id
            for i, placement in enumerate(placements):
                instances.append(CollectionInstanceSpec(
                    instance_id=f"grid_instance_{len(instances)}",
                    source_geometry_id=source_geometry_id,
                    transform=NoodleAttributes(
                        tx=placement.tx, ty=placement.ty, tz=placement.tz,
                        sx=sx, sy=sy, sz=sz,
                        qx=placement.qx, qy=placement.qy, qz=placement.qz, qw=placement.qw,
                        use_quaternion=True,
                    ),
                    metadata={
                        "grid_u_index": i % count_x,
                        "grid_v_index": i // count_x,
                        "source_instance_id": getattr(source, 'instance_id', None),
                    },
                ))

        # Create output collection for Materializer  
        collection_metadata = {"array_type": "2d_grid", "transform_system": "noodle_attributes", "count_u": count_x, "count_v": count_y}
            
        output_collection = CollectionSpec(
            collection_type="geometry_collection",
            collection_id=f"array_grid_{len(instances)}_instances",
            instances=instances,
            source_geometries=collection_spec.source_geometries,
            metadata=collection_metadata
        )

        log(app, f"Created CollectionSpec with {len(instances)} instances (NoodleAttributes-based)", level=LogLevel.DEBUG, module=self.NODE_TYPE)

        return {"collection": output_collection}
