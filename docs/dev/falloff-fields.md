# Falloff curves

Every falloff in Noodle (the Falloff Effector, the Falloff modifier and the Gradient modifier) is shaped by the same curve and edited in the same curve editor. This document describes the curve, the shapes it is measured over, the editor, and how old graphs were converted.

A falloff is a **shape** that measures each instance (distance from a point, progress along a line, position along a strand) and maps it to `t` in 0..1, followed by a **curve** that maps `t` to strength:

```
instance ──shape──▶ t ∈ [0, 1] ──curve──▶ v ∈ [0, 1] ──output range──▶ strength
```

The curve is the thing users want to shape; how distance is measured is a separate choice. Before this design each node had its own hand-written shape, and every new shape meant another parameter with its own edge cases.

## The curve

### Data

```json
"curve": {
  "degree": 3,
  "points": [[0, 1], [0.2, 1], [0.65, 0], [1, 0]],
  "repeat": 1,
  "repeat_style": "mirror",
  "decay": 0.0,
  "invert": false,
  "lead": "start"
},
"output": { "start": 1.0, "end": 0.0 }
```

- `points` are the control points of a clamped, uniform B-spline, drawn as one **tile**. The first point has x = 0, the last x = 1, and x strictly increases. Because x is monotone, the curve is a function: one value per `t`, no loops.
- `degree` is 3 (cubic, G2 inside the tile) or 5 (quintic, G4). Quintic needs at least six points; the editor adds midpoints when switching.
- `repeat` (1 to 12) counts copies of the drawn shape along `t`. With `restart` that is `repeat` tiles. With `mirror` a reflected copy sits between each pair, so it is `2 · repeat − 1` tiles, and the far edge always ends the way the drawn tile ends (a Smooth tile mirrored 5 times is a center peak and four rings, ending at 0 on the radius).
- `decay` (0 to 1) scales the result by `1 − decay · smootherstep(t)`. Smootherstep has zero slope and curvature at both ends, so decay never adds a crease.
- `invert` maps v to 1 − v before decay.
- `output.start` and `output.end` map v = 1 and v = 0 to strengths. Values below 0 and above 1 are allowed by the data, though the editor offers 0% to 100%.

Presets are starting values for these same fields, not modes, and are there to show what is possible and what good practice looks like, so people go on to make their own. Every control stays available, so a Gaussian can become a ripple by raising Repeat.

| Preset | Tile | Repeat | Shows |
|---|---|---|---|
| Smooth, Gaussian, Linear, Ease out, Plateau | single fades | 1 | basic easing; Linear is the only one with a crease at the edge, on purpose |
| Ring | 0 → 1 → 0 bump | 1 | a band at a distance |
| Ripple | the Smooth tile | 5, Mirror, decay 0.7 | rings radiating from a center peak; every seam is a mirror, so continuity is free |
| Pulse | fast rise, slow tail | 4, Restart, decay 0.4 | asymmetric pulses, which only Restart can make; shows the linked seam |

### What the user draws and what the field uses

The user draws one tile and, by convention, gives each end a **level tangent**: two points at the same height (G1). The field never uses that tile as-is. For each tile it derives the control points from what each end of the tile meets:

| The end meets | Where | Rule |
|---|---|---|
| **Flat ground** | the inner plateau (Inner > 0), the outer edge | Add a third level point, G2 to flat |
| **Its own mirror image** | the center (Inner = 0) | Nothing. A mirrored G1 is already G2 |
| **A mirrored neighbour tile** | a Mirror repeat seam | Slide the level neighbour back to the drawn tile's curvature at that end |
| **The next tile** | a Restart repeat seam | The level points either side are linked: the side dragged last leads, the other slides to match its curvature |
| **Nothing** | a Gradient's first and last instance | Nothing. The ends are used exactly as drawn, and not graded |

Mirror seams need sliding too. A tile that gained a hold point has one more control point, so its knots are spaced differently and its end no longer bends exactly like its neighbour's. Without the slide, Smooth with Mirror repeats graded G1. Each tile is therefore slid back to the drawn tile's own curvature, which is a no-op for tiles that didn't change.

Hold points are never stored. In the editor:

- **Squares** are the user's points.
- **Filled circles** are linked across a Restart seam. They are drawn at their real position and can be dragged; grabbing one makes that side lead. Only `lead` (`"start"` or `"end"`) is stored, beside the curve.
- Holds added to meet flat ground are not drawn: there is nothing the user can do with them.

**The hold point.** When an end meets flat ground, a level point is inserted on the level leg, 30% of the way in from the end point (between points 1 and 2 at 30%; mirrored at the far end). Splitting the leg that is already there keeps the drawn shape nearly identical and only firms up the very end. Earlier tries put the point between points 2 and 3, which made a large flat spot appear as soon as Inner left zero.

**Restart seams.** With a level tangent, moving the level neighbour to distance `d` from the end scales the end curvature by `1/d²` and changes nothing else (y″ depends only on heights, x′ is proportional to `d`). So the seam can be matched exactly in closed form:

1. Measure the drawn tile's curvature at its start, `κs`, and its end, `κe`.
2. If both bend the same way, the target `κ*` is the leading side's curvature.
3. In every tile with a Restart seam, move each side's level neighbour to `d · √(κ / κ*)`, clamped so x stays ordered. On the leading side this changes nothing unless the tile gained a hold point.

When the seam cannot be matched this way, the curve falls back:

- If the two ends bend opposite ways, or one end is already flat, the only shared curvature is zero. Both sides get a hold point (G2 to flat).
- If the ends are not level, or not at the same height, the seam is left alone. That is a deliberate crease or step, such as Smooth with Restart making a sawtooth.

This is what fixes ripples. A Restart seam used to show the tile's flat end hold followed by its flat start hold, which reads as a flat dwell between every ripple. Now interior troughs keep their curvature, and only the true outer edge is held flat.

Because each tile only depends on what its two ends meet, there are at most four distinct tile variants (first, middle, last, and the single-tile case). Each one is built once per evaluation.

Decay does not break these seams. With `y = env · f`, a seam where `f′ = 0` on both sides has `y″ = env · f″ + env″ · f`, so matching `f″` is enough.

### Continuity readout

The editor grades the center or inner edge, the outer edge, and the worst repeat seam as Gap, G0, G1 or G2. It measures value and the first and second derivative from each side with one-sided five-point stencils. The step must sit well inside the shortest leg, `2e-4 / repeat` in `t`. The prototype's first version used `2e-3`, which straddled the hold point and reported G1 where the curve was exactly G2.

## Shapes

Each shape produces `t` for one instance. Distances are in cm, like every other length in Noodle.

| Source | `t` is | Inputs |
|---|---|---|
| Sphere | distance from the center, from Inner Radius to Radius | Center, Radius, Inner Radius, Scale, X Axis, Y Axis |
| Linear | progress from Start to End along the line between them (held before Start and past End) | Start, End |
| Box | the same as Sphere, measured square (the largest distance along the three local axes), so every contour is a box | Center, Radius, Inner Radius, Scale, X Axis, Y Axis |
| Along a strand (Gradient modifier) | strand position over strand length, falling back to the grid U index after an Array with no Separator; 0 at the first instance | none |

The shapes and their ports are in `backend/utilities/field_sources.py`; the Gradient's measure is in `modifier_utils.py`.

**Shaping and application are split.** Where a field sits is chosen on the node: a Shape dropdown (Sphere, Linear, Box) on the Falloff nodes, with each shape's ports shown only while it is chosen (`visible_when` on the PortSpec). A connection into a hidden port is kept, so switching back restores it. How the field fades is set in the curve editor, which only names the shape and carries its distance settings (Radius and Inner Radius, for Sphere and Box). Points and vectors are never edited in the modal.

Sphere and Box share their controls, so switching between them keeps every value and only changes round to square. Scale stretches the field along its local axes, measured in that stretched space: a sphere becomes an ellipsoid and a cube a box. The X Axis and Y Axis turn it (local Z is X × Y), and Scale's x, y and z follow those local axes. The defaults are the world axes. With Scale 1, 1, 1 a sphere looks the same however it is turned.

Orientation lives on the node, not in the curve editor. A sphere needs none. Linear needs no up vector: its two points give the direction, and the start point places it relative to the origin. Sphere and Box carry a full frame, an X Axis and a Y Axis (later, perhaps a picked construction plane), which matters once Scale is not uniform. The axes are named for what Scale's components stretch along: an earlier "Up" that set local Z sent Scale y somewhere unexpected.


## The editor

One React component, `ui/src/components/FalloffCurveEditor.jsx`, used by the Falloff Effector, the Falloff modifier and the Gradient modifier. The node shows a small preview of the curve; clicking it opens a fixed-size modal.

The layout is a side panel: curve and profile on the left, controls in a right column. That keeps the curve area close to square, which matters for reading the comb. (A stacked layout, controls below the curve, needed 920 × 600 and still left the curve wide and short.) The modal has two sizes, 720 × 480 and 920 × 600, and uses the larger one only when the palette has room for it with a margin (about 980 × 720), re-checking when the palette is resized. The layout is the same at both sizes; the larger one just gives the curve more room.

The header holds the node's name and a Preset dropdown (showing "Custom" once a point is moved). The strip under the curve holds the continuity chips, the Cubic/Quintic switch and the Comb toggle. The comb scales itself so its longest tooth is a fixed share of the canvas height, so there is no comb-size control.

Contents:

- Curve canvas with draggable points (double-click adds or deletes), the control polygon, linked and hold points as described above, and the curvature comb.
- Presets: Smooth, Gaussian, Linear, Ease out, Plateau, Ring, Ripple, Pulse.
- Degree switch (Cubic G2, Quintic G4).
- Shape: Repeat, Mirror or Restart, Decay, Invert.
- Output: At start and At end.
- The shape's distance settings: Radius and Inner Radius for Sphere and Box. Center, Scale and the axes are set on the node.
- Continuity chips, with the worst problem explained in words when there is one.
- A short profile across the shape.

The dot preview is not in the modal: the effector visualizer in Fusion's viewport already shows it, live.

**Opening the editor turns the visualizer on**, for the node itself or, for a modifier, every effector it feeds. Closing it puts the view back: visualizers that were off go off again, and bodies that were showing come back. Dots draw first and bodies are hidden only once the dots are on screen, for the eye as well. Hiding and showing run inside a Fusion command as one undo step, which takes well under a second even for thousands of bodies (see [Architecture](architecture.md#showing-and-hiding-bodies-as-one-undo-step)).

**Outlines.** With the dots, each falloff in the pass draws a faint guide in the curve color, in front of bodies: the silhouette of the Radius ellipsoid (fainter and dashed for Inner Radius) for Sphere, the outer box solid and the inner box fainter and dashed for Box (these are exact contours of the fade), and an arrow from Start to End with a dashed ring at each end for Linear (sized to frame the instances). Gradients have no outline.

An ellipsoid's outline depends on the view. `field_sources.ellipsoid_rim` traces it exactly: squashed to a unit sphere, the outline seen from an eye e is the circle q · e = 1 (from a direction v, the great circle q · v = 0), and stretching it back keeps tangency. The visualizer draws outlines in their own custom-graphics group and redraws only that group on `cameraChanged`.

While the modal is open, edits are committed to the node every 120 ms, and the visualizer redraws from them like any other input change.

## One evaluator

The curve and every source are implemented twice, in Python for Generate and in JavaScript for the editor. They must agree exactly, so:

- A shared file of test examples, `tests/fixtures/field_curve_vectors.json`, lists curves and expected values at chosen `t` values, including seams, hold points and decay.
- `tests/test_field_curve.py` and `ui/tests/fieldCurve.test.js` both run every example and agree to 1e-9. The Python side is `backend/utilities/field_curve.py`; the JavaScript side is `ui/src/utils/fieldCurve.js`.
- Python does not import numpy. De Boor evaluation and the x-to-u bisection are a few dozen lines in pure Python.
- Evaluation per instance: bisection on x(u) (about 40 steps) is the cost. For large collections Python builds a dense lookup table per tile variant once and interpolates; built curves are cached.

## Migration from old graphs

The old falloff shapes can't be reproduced exactly by the new curve, so they are approximated and the user is told. `graph_format.py` converts nodes in place with a per-node-type `convert_inputs` function, which returns whether the result is approximate; approximate conversions get a note.

- **Format 3** converts the Falloff Effector and Falloff modifier to a curve. See `__docs/LEGACY_FALLOFF_CURVE.md` for the old shape and the mapping.
- **Format 4** converts the Gradient modifier. The old gradient is sampled and a cubic is fitted by least squares (4 to 12 points). A straight ramp is exact; anything more than 1% off (steps, sharp corners) is noted. See `__docs/LEGACY_GRADIENT.md`.

## Open questions

- **Quintic holds.** For degree 5 the hold rule still gives G2 to flat. G3 or G4 to flat would need two or three more level points. Is G2 enough at the edges of a quintic?
- **Restart seams the user doesn't want matched.** Is there a case where a user wants the drawn, unmatched seam? If so, it is a per-curve switch, off by default.
- **Hold position.** 30% was chosen by trying it. Expose it, or keep it fixed?
