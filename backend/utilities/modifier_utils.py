"""
Modifier evaluation utility.

A modifier is a plain dict with a `modifier_type` key.  Any node that outputs
such a dict on a FLOAT port is a modifier node.  The Effector calls
evaluate_modifier(config, instance_metadata) per instance to obtain a strength
float — which may be outside 0..1, including negative.

Adding a new modifier type:
  1. Add a branch in evaluate_modifier().
  2. Create a node in backend/nodes/ with NODE_CATEGORY = "modifiers"
     whose execute() returns {"modifier": {"modifier_type": "<name>", ...}}.
"""

from typing import Any, Dict


def evaluate_modifier(config: Dict[str, Any], instance_metadata: Dict[str, Any]) -> float:
    """
    Evaluate a modifier config against a single instance's metadata.

    Returns an unbounded float — callers must NOT clamp before applying,
    since negative values drive the transform in the opposite direction
    (e.g. Checkerboard over/under weave).
    """
    modifier_type = config.get("modifier_type", "")
    amplitude_raw = config.get("amplitude", 1.0)
    if isinstance(amplitude_raw, dict) and "modifier_type" in amplitude_raw:
        amplitude = evaluate_modifier(amplitude_raw, instance_metadata)
    else:
        amplitude = float(amplitude_raw)

    # ── Checkerboard ──────────────────────────────────────────────────────────
    # Alternates +amplitude / -amplitude in a checkerboard across the grid.
    # Reads strand_index + strand_position (post-Separator) with fallback to
    # grid_v_index + grid_u_index (post-Array, no Separator).
    # phase=1 inverts the pattern — use on V channel to get over/under weave.
    if modifier_type == "checkerboard":
        phase = int(config.get("phase", 0))
        si = int(instance_metadata.get(
            "strand_index",
            instance_metadata.get("grid_v_index", 0)
        ))
        sp = int(instance_metadata.get(
            "strand_position",
            instance_metadata.get("grid_u_index", 0)
        ))
        sign = 1.0 if (si + sp + phase) % 2 == 0 else -1.0
        return sign * amplitude

    # ── Wave ──────────────────────────────────────────────────────────────────
    # Sinusoidal pattern along strand_position.
    if modifier_type == "wave":
        import math
        frequency  = float(config.get("frequency",    1.0))
        phase_offset = float(config.get("phase_offset", 0.0))
        sp = float(instance_metadata.get(
            "strand_position",
            instance_metadata.get("grid_u_index", 0)
        ))
        return math.sin(sp * frequency + phase_offset) * amplitude

    # ── Gradient ──────────────────────────────────────────────────────────────
    # The falloff curve along a strand: t = strand_position / (strand_length - 1),
    # falling back to grid_u_index / (count_u - 1) after an Array with no Separator.
    if modifier_type == "gradient":
        from .field_curve import field_curve
        sp    = float(instance_metadata.get("strand_position", instance_metadata.get("grid_u_index", 0)))
        count = float(instance_metadata.get("strand_length",   instance_metadata.get("count_u", 1)))
        t = max(0.0, min(1.0, sp / (count - 1.0))) if count > 1.0 else 0.0
        return field_curve(config.get("curve"), open_ends=True).value(t) * amplitude

    # ── Random ────────────────────────────────────────────────────────────────
    # Stable per-instance random value seeded by strand coords.
    if modifier_type == "random":
        import random as _random
        seed = int(config.get("seed", 0))
        mn   = float(config.get("min", -1.0))
        mx   = float(config.get("max",  1.0))
        si   = int(instance_metadata.get("strand_index",    0))
        sp   = int(instance_metadata.get("strand_position", 0))
        rng  = _random.Random(seed ^ (si * 2654435761) ^ (sp * 2246822519))
        return rng.uniform(mn, mx) * amplitude

    # ── Falloff ───────────────────────────────────────────────────────────────
    # A sphere, linear or box falloff field at the instance's world position.
    # Reads surface_point from instance metadata; the falloff curve shapes the fade.
    if modifier_type == "falloff":
        from .field_sources import field_strength
        sp = instance_metadata.get("surface_point", {})
        if not isinstance(sp, dict):
            sp = {}
        point = (float(sp.get("x", 0.0)), float(sp.get("y", 0.0)), float(sp.get("z", 0.0)))
        return field_strength(config, point, "center") * amplitude

    # Unknown modifier — return amplitude as neutral passthrough
    return amplitude
