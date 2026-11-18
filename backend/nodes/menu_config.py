"""
Add Node menu layout.

Keys define the section name and display order. Values are lists of NODE_TYPE
strings (normalized to lowercase with underscores) that appear in that section.

Rules:
- Sections beginning with '_' are hidden: nodes exist in the registry and are
  creatable programmatically, but never shown in the Add Node menu.
- Any registered node whose type does not appear here falls back to its
  NODE_CATEGORY as the menu section.
- This file is the single place to reorganize the menu — no node files need
  to be touched.
"""

MENU_SECTIONS = {
    "sources":    ["cube_generator", "sphere_generator",
                   "cylinder_generator", "polygon_generator", "body_instance"],
    "array":      ["array_2d_grid", "array_surface_uv", "array_surface_grid",
                   "array_surface_hex", "array_surface_spiral", "array_path"],
    "collection": ["null", "atomizer", "materializer", "uv_separator"],
    "curves":     ["interpolize"],
    "effector":   ["uniform_effector", "falloff_effector"],
    "features":   ["pipe"],
    "math":       ["number", "add", "multiply", "absolute", "vector3", "3d_point"],
    "modifiers":  ["modifier_gradient", "modifier_falloff", "modifier_wave",
                   "checkerboard", "random", "noise"],
    "transform":  ["move_transform", "rotate_transform", "scale_transform",
                   "scale_xyz", "aim_transform", "apply_transform"],
    "_hidden":    ["sweep"],  # Experiment: profile is not normal to the path
}
