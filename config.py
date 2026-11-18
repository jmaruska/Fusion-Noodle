# Application Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

import os

# ── Log level ─────────────────────────────────────────────────────────────────
# Messages below this level are not written to the Text Commands window.
# One of DEBUG, INFO, WARNING, ERROR, CRITICAL. Set the NOODLE_LOG_LEVEL
# environment variable to override it without editing this file.
LOG_LEVEL = os.environ.get("NOODLE_LOG_LEVEL", "INFO")

# ── Generate as one undo step ─────────────────────────────────────────────────
# True:  Generate runs inside a Fusion command, so the whole build is a single
#        entry in Fusion's undo history ("Noodle Generate").
# False: Generate runs directly from the palette message, and every body it
#        creates is its own undo entry.
# Set to False if Generate misbehaves.
GENERATE_AS_SINGLE_UNDO = True

# ── Progress dialog ───────────────────────────────────────────────────────────
# Show Fusion's progress dialog, with a Cancel button, when a Generate takes
# longer than about a second. Set to False if the dialog causes problems.
SHOW_GENERATE_PROGRESS = True

# ── Per-module logging ────────────────────────────────────────────────────────
# Single place to silence noisy modules without touching source files.
# True  = log normally   |   False = hide that module's DEBUG and INFO lines
# Warnings and errors are always written, whatever is set here.
# Unrecognised module names default to True (logged).
MODULE_LOGGING_ENABLED = {
    "GEOMETRY_HANDLER":     False,  # Verbose visibility lookups
    "TRANSFORM_UTILS":      False,  # 100+ messages per array - suppress by default
    "EFFECTOR_FALLOFF":     True,
    "EFFECTOR":             True,
    "ARRAY_2D_GRID":        True,
    "INSTANCE_UTILS":       False,  # 100+ instance-creation messages per generate
    "SURFACE_GRID_GEN":     True,
    "ARRAY_UV":             True,
    "SURFACE_GRID":         True,
    "MATERIALIZER":         True,
    "BOX_NODE":             False,
    "ATOMIZER":             True,
    "NUMBER_NODE":          False,
    "GRAPH_HANDLER":        True,
    "APPLICATION":          False,
    "PALETTE_HANDLER":      False,
    "PERSISTENCE_HANDLER":  False,
}
