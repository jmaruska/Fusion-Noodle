# Examples

From simplest to most involved. The `.noodle` files are graphs only; the `.f3d` files are Fusion designs that also hold the geometry their graph picks (a face or a curve).

| Example | Shows |
|---|---|
| `2D-grid+falloff.noodle` | A box arrayed on a grid, scaled down near the center by a Falloff Effector. Open the falloff's curve editor to reshape it. |
| `2D-hexGrid+fixedGaps.noodle` | Hexagons on a hexagonal grid with a constant gap: one Number drives the Polygon's Size, and an Add drives the spacing. |
| `2D-grid+falloff+compoundTransforms.noodle` | Transforms chained and effectors stacked: a Move feeding a Scale drives a Falloff Effector, and a Uniform Effector then aims every instance. |
| `arrayOnPath+Bank.f3d` | Instances along a curve, banking into its bends. |
| `surfaceArray_Spiral.f3d` | A spiral of instances wrapped around a surface. |
| `surfaceArray_UV+wireMesh.f3d` | A UV array across a surface, built up into a wire mesh. |

## Open a `.noodle` example

1. Open or create a design in Fusion and open the Noodle palette.
2. Click **Open** (the folder icon) in the palette toolbar and choose a file from this folder.
3. Click **Generate**.

Opening a file replaces the graph on the canvas. It doesn't change your design until you click Generate.

## Open an `.f3d` example

1. In Fusion, choose **File → Open → Open from my computer…** and pick the file. Fusion uploads it to your project.
2. Open the Noodle palette. The graph saved in the design loads onto the canvas, already connected to the design's geometry.
3. Click **Generate** to rebuild it, or change a value first.

## Add an example

Build the graph, click **Save** (the floppy-disk icon), and save the file into this folder. If the graph picks geometry from the design, save the design as an `.f3d` here instead (**File → Export…**), so the picked face or curve comes with it. Keep `.f3d` examples small: Fusion stores the generated bodies' display mesh in the file, and Noodle rebuilds them on Generate anyway.

Every `.noodle` file here is checked automatically: it must load, every node type must exist, and every connection must join ports that exist. The check runs with the other tests:

```sh
python3 -m unittest discover -s tests -t .
```

If a node is later renamed or restructured, add a migration in `backend/graph_format.py` so these files, and everyone's saved graphs, keep loading. `.f3d` examples aren't checked automatically; open them in Fusion after such a change.
