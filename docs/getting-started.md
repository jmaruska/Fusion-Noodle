# Getting started

This guide walks you through the Noodle palette and then has you build one complete graph. It assumes you've already installed and run the add-in. If you haven't, follow the [README](../README.md#install) first.

## Open the palette

1. Open or create a design in Fusion.
2. In the **Design** workspace, go to the **Solid** tab and click **Noodle** in the **Create** panel. The button sits next to Pattern and is also promoted to the toolbar.

The Noodle palette opens docked on the right. Along the top is a toolbar with **Add Node**, then Open, Save, Revert, and Clear icons, and **Generate** on the far right. Below the toolbar, a status line shows how many nodes are on the canvas and what's selected. It also shows messages, such as why Generate is disabled or why the last Generate failed.

If the document already has a saved Noodle graph, it loads when the palette opens.

## Work with nodes

**Add a node.** Click **Add Node**, hover over a category (Sources, Array, Collection, Curves, Effector, Features, Math, Modifiers, Transform), and click a node. The new node appears on the canvas, highlighted until you hover over it or click it.

**Helper nodes are added for you.** An array or an effector works on a collection, so it needs an **Atomizer** before it and a **Materializer** after it. When you add one and the graph doesn't have those yet, Noodle adds them, connects them, and places the group clear of your other nodes. All of the new nodes are selected, so you can drag them as a group. If the graph already has an Atomizer or a Materializer, Noodle doesn't add another.

**Move around the canvas.** Drag a node to move it. Scroll, or drag an empty part of the canvas, to pan. Use the controls in the bottom-left corner to zoom or to fit the graph in view.

**Delete.** Select a node or a connection and press Delete or Backspace. Shift, Ctrl, or Cmd lets you select more than one.

**Connect ports.** Inputs are on the left edge of a node and outputs are on the right. Drag from an output to an input. A few rules apply:

- Each input accepts one connection. An output can feed any number of inputs.
- The port types must be compatible. Noodle won't let you drop a connection on an incompatible input. Matching types always connect. Integer and float ports connect to each other. Geometry, body, and surface ports connect to each other.
- Connections are colored by the type of the output they start from:

| Color | Types |
|---|---|
| Orange | float, integer, vector3, point |
| Green | geometry, body, surface |
| Blue | collection |
| Purple | transform |
| Teal | curve |
| Light gray-blue | boolean, string, and anything else |

A geometry output can't connect directly to a collection input. To feed a Box into an array, put an **Atomizer** between them.

**Edit values.** Type into numeric fields, check boxes for booleans, and pick from dropdowns for options like an array's Type. A field that fails validation is flagged, the status line names it, and **Generate** stays disabled until you fix it. Press Tab to commit a value and move to the next field in the same node, or Shift+Tab to go back. Tab stays within the node and wraps around, skipping connected fields. Once an input is connected, its value comes from the connection.

**Units.** Lengths are always in **centimeters**, which is Fusion's internal unit, whatever your document units are. For example, a Box with Width 2 is 2 cm wide, even in a millimeter or inch document. Angles are in degrees. Inputs that take a length or an angle show `cm` or `°` after their label. A Number node has no unit, so the same number can feed a count and a length.

## Select Fusion geometry

Some inputs take geometry from your design rather than a typed value:

| Port type | What to select | Used by |
|---|---|---|
| body | A solid body | Body Instance |
| surface | A face | Surface UV/Grid/Hex Array, Surface Spiral |
| curve | An edge or sketch curve | Array on Path |
| point | A construction point, sketch point, or vertex | 3D Point |

A 3D Point follows the point you picked. Move or drag that point in Fusion and anything driven by the 3D Point, such as a falloff's position and its visualizer, follows it. Graphs saved before this behavior was added need the point picked again.

These ports show a **Select** button (for example, **Select Surface**).

- If something of the right kind is already selected in Fusion, clicking the button uses it right away.
- Otherwise the button changes to **Selecting...**. Click the entity in the canvas, and Noodle picks it up automatically. To cancel, click the button again.
- Only one selection can be in progress. Starting a selection on another node cancels the first one.
- If you don't pick anything within 30 seconds, selection is cancelled.
- After a selection is captured, the button reads **1 Selected**.
- When a connection feeds the port, the button is disabled. For example, Interpolize curves can feed Array on Path.

## Generate geometry

Geometry is not created as you edit. Click **Generate** to run the graph. Noodle then does the following:

- Deletes the previous `Noodle_Geometry` Base Feature, if there is one, and creates a fresh one.
- Runs every node that leads to a terminal node (a node whose outputs aren't connected to anything), plus isolated source, math, and transform nodes.
- Creates the resulting bodies inside that Base Feature.
- Saves the graph into the document.

Nodes that aren't on a path to a terminal node are skipped.

When something goes wrong, the graph stops at the failing node. Noodle selects that node and shows the error in the status line. Detailed logs go to Fusion's Text Commands window.

## Visibility

Nodes that produce bodies, such as the source primitives, Materializer, and Pipe, have an eye icon in their header. Click it to show or hide that node's bodies in the design.

After each Generate, Noodle automatically hides the bodies of any node that feeds an Atomizer or an array, because those bodies are only templates for the instances. You can show them again with the eye icon.

## Preview an effector before you generate

Effectors have an eye icon too, and it does something different. It turns on the **visualizer**, which draws a dot in the Fusion viewport at every instance, colored by how strongly the effector acts on it:

| Color | Meaning |
|---|---|
| White | Fully affected |
| Yellow, orange, red | Partly affected, from more to less |
| Black | Not affected |

Use it to place a falloff and tune its radius without waiting for a Generate. The dots update as you change the effector, the array feeding it, a modifier on its Strength, or the point a 3D Point node follows.

- The dots show where instances will end up. A Move displaces them. A Scale or Rotate changes only their color.
- The eye is off by default. Turning it on hides generated bodies, so they don't cover the dots.
- You can turn on several effectors at once. Dots then show the combined effect. When effectors add up to more than 100%, the colors are scaled so the most affected instance is white.
- A negative strength counts the same as a positive one.
- To get your geometry back, click the eye on a body node such as the Materializer, or click **Generate**. Either one turns the visualizer off.
- The visualizer doesn't create anything in your design and adds nothing to Fusion's undo history. Closing the palette removes the dots.

An effector needs a transform connected before it shows anything. A branch that depends on something only Generate can make, such as curves from Interpolize, can't be previewed. The status line says so.

## Saving and switching documents

A document keeps up to two versions of its graph:

- **The generated graph** is the one that built the geometry in the design. It's written each time you click **Generate**, even if the Generate fails, and stored on the `Noodle_Geometry` Base Feature.
- **Your working copy** is the graph as you've edited it since. Noodle remembers it while Fusion is running, so closing the palette or switching documents doesn't lose your edits. It's written into the document when you save the document.

Both are saved and reopened with the Fusion document, so **save the Fusion document** to keep them.

- When the canvas differs from the generated graph, the status line shows **Edited since last Generate**.
- When a document has a working copy, the palette opens with it and says so. The geometry in the design still comes from the last Generate until you generate again.
- **Revert** (the arrow icon) discards your edits and shows the generated graph again. Click it once, then click **Revert?** to confirm.
- **Generate** makes the two the same, so the working copy goes away.
- When you switch to another document, the palette reloads and shows that document's graph, or an empty canvas if it has none.
- **Clear** (the trash icon) empties the canvas and deletes the `Noodle_Geometry` Base Feature, the generated graph, and your working copy. Click it once, then click **Clear?** within 3 seconds to confirm.
- **Save** (the down-arrow icon) writes the graph to a `.noodle` file. **Open** (the folder icon) loads one, replacing the graph on the canvas. Use them to move a graph between documents or share it. Opening a graph doesn't change your design until you click Generate.
- Graph files from older versions of Noodle are updated when they open. A graph saved by a newer version won't open; update Noodle first.
- The [`examples`](../examples/) folder has graphs you can open.

## Example: a grid of boxes that shrink toward the center

This graph makes a 7 × 7 grid of boxes, with the boxes near the center scaled down.

```
Box ──► Atomizer ──► Array 2D Grid ──► Falloff Effector ──► Materializer
                                            ▲
                                  Scale ────┘ (Transform)
```

1. **Add the nodes.** Add each of these from the **Add Node** menu:
   - **Sources → Box**
   - **Array → Array 2D Grid**. Noodle also adds an **Atomizer** and a **Materializer**, connected on either side of the array.
   - **Effector → Falloff Effector**
   - **Transform → Scale**
2. **Connect the main chain.** The effector goes between the array and the Materializer:
   - Box **Geometry** → Atomizer **Geometry**
   - Click the connection from Array 2D Grid to Materializer and press Delete. An input takes only one connection.
   - Array 2D Grid **Collection** → Falloff Effector **Collection**
   - Falloff Effector **Collection** → Materializer **Collection**
3. **Connect the transform.** Connect Scale **Transform** → Falloff Effector **Transform**.
4. **Set values.** Use these settings:
   - Box: Width, Height, and Depth = 2.
   - Array 2D Grid: Type = Grid, Count X = 7, Count Y = 7, Spacing X = 3, Spacing Y = 3. The grid is centered on the origin.
   - Scale: Scale Factor = 0.25.
   - Falloff Effector: leave Shape at Sphere and Center at 0, 0, 0. Set Radius = 8 and leave Strength at 1.
5. **Click Generate.**

The Materializer produces 49 boxes in the `Noodle_Geometry` Base Feature, and the original Box is hidden. Boxes near the origin are scaled toward 0.25. The effect fades out with distance and stops at the Radius, so the outer boxes keep their full 2 cm size.

**Try these next:**

- Change Radius or Scale Factor and click Generate again.
- Click the curve on the Falloff Effector to open the curve editor. Pick the **Ripple** preset, or drag the points, and watch the dots in the viewport follow. See [Shaping a falloff](#shaping-a-falloff).
- Swap Scale for **Move** (raise Z) or **Rotate**.
- Change the array Type to **Hexagonal**.
- Replace the Falloff Effector with a **Uniform Effector** and connect **Random** or **Noise** to its **Strength** input. Each instance then gets its own strength.

## Shaping a falloff

The Falloff Effector and the Falloff and Gradient modifiers share one curve editor. Click the curve on the node to open it.

- **Where** the falloff sits is set on the node. **Shape** picks Sphere, Linear or Box, and the node shows only that shape's inputs. Sphere and Box share Center, Radius, Inner Radius and Scale; Scale stretches a sphere into an ellipsoid along the X Axis and Y Axis. Linear fades from Start to End.
- **How** it fades is the curve. The left of the curve is the center (or Start); the right is Radius (or End). Drag the square points, double-click to add or remove one, or start from a **Preset**.
- **Repeat** copies the curve outward, either mirrored or restarting, and **Decay** fades the copies. **Invert** flips the curve. **At start** and **At end** set the strength at each end.
- The chips under the curve show how smoothly it joins at the center, the edge and between repeats: G2 is the smoothest, G0 a corner.

While the editor is open, the effectors it feeds show their strengths as dots in the viewport, with a faint outline of the shape, and the bodies are hidden. Closing the editor puts the view back.

For every node's inputs, outputs, and defaults, see the [node reference](nodes.md).
