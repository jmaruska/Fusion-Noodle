# Adding a node

A node is one Python file in `backend/nodes/`. The registry finds it automatically, and the frontend builds its UI from the node's spec. Most nodes need no frontend code.

This walkthrough adds a **Subtract** node, modeled on `backend/nodes/math_add.py`.

## 1. Create the file

Name the file `<category>_<name>.py` to match the existing files, for example `math_subtract.py`, `array_path.py`, or `transform_scale_xyz.py`.

The registry imports every `backend/nodes/*.py` except files that start with `_`, `base.py`, and `menu_config.py`.

```python
# backend/nodes/math_subtract.py
"""Subtract node - subtracts b from a."""

from typing import Dict, Any, List
from ..contracts import NodeSpec, PortSpec, PortType
from .base import BaseNode
from ..enforcement import enforce_node_spec
from ..utilities.log_utils import log
from ..specification import LogLevel


@enforce_node_spec
class SubtractNode(BaseNode):
    """Subtracts b from a"""

    NODE_TYPE = "subtract"
    NODE_CATEGORY = "math"
    NODE_NAME = "Subtract"
    NODE_DESCRIPTION = "Subtract B from A"

    @classmethod
    def get_spec(cls) -> NodeSpec:
        return NodeSpec(
            node_type=cls.NODE_TYPE,
            category=cls.NODE_CATEGORY,
            description=cls.NODE_DESCRIPTION,
            inputs=[
                PortSpec("a", PortType.FLOAT, default_value=0.0),
                PortSpec("b", PortType.FLOAT, default_value=0.0),
            ],
            outputs=[
                PortSpec("result", PortType.FLOAT),
            ],
        )

    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        errors = []
        for name in ("a", "b"):
            value = inputs.get(name)
            if value is not None and not isinstance(value, (int, float)):
                errors.append(f"Input '{name}' must be a number")
        return errors

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        a = float(inputs.get("a", 0.0))
        b = float(inputs.get("b", 0.0))
        result = a - b
        log(context.get('app'), f"Subtract: {a} - {b} = {result}",
            level=LogLevel.DEBUG, module="SUBTRACT_NODE")
        return {"result": result}
```

## 2. Meet the requirements

`@enforce_node_spec` checks these requirements when the module is imported. The import fails if any of them is missing.

| Requirement | Notes |
|---|---|
| Class name ends in `Node` | Must match `^[A-Z][a-zA-Z0-9]+Node$`. |
| `NODE_TYPE` | A stable ID. **It's saved in users' graphs, so don't rename it later.** The menu and frontend use the lowercased form, with spaces replaced by `_`. |
| `NODE_CATEGORY` | Picks the node's color and CSS class (`node-category-<category>`). It also sets which nodes run when isolated: `geometry`, `math`, and `transform`. Existing values are `array`, `collection`, `curves`, `effector`, `geometry`, `math`, `modifiers`, and `transform`. |
| `NODE_NAME` | The display name in the menu and the node header. |
| `NODE_DESCRIPTION` | A short description. Also pass `description=cls.NODE_DESCRIPTION` to `NodeSpec` so it appears in `docs/nodes.md`. |
| `get_spec(cls) -> NodeSpec` | A classmethod that returns `NodeSpec(node_type, category, inputs, outputs, description="", version="1.0", wide=False)`. |
| `validate(self, inputs)` | Returns a list of error strings. If the list isn't empty, `execute` doesn't run. |
| `execute(self, inputs, context)` | The full signature is below. |

The `execute` signature, from `backend/nodes/base.py`:

```python
def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
```

- **`inputs`** is keyed by input port name. A port may be missing, so always fall back to a default with `inputs.get(name, default)`. Connected ports hold the upstream node's actual output.
- **`context`** contains `app`, `ui`, `design`, `base_feature` (also available as `noodle_base_feature`), `node_id`, `node_body_names`, and `progress`. Call `context['progress'].step(done, total)` in a long loop so the user sees progress and can cancel (see [Architecture](architecture.md#progress)).
- **The return value** must be a dict keyed by output port name.

**Making geometry.** Nodes run inside the Base Feature edit that Generate opened. Trust that: don't check whether the edit is open, don't wait for it, and don't open or close it. Add bodies with `rootComponent.bRepBodies.add(brep, context['base_feature'])` from a temporary B-Rep, and sketches with `sketches.addToBaseOrFormFeature()`. Some parametric features (pipe, for one) land on the main timeline instead of in the Base Feature; test yours, and if it escapes, follow Pipe's pattern. Read [Faith-based execution](architecture.md#faith-based-execution) first.

Output values are checked against their port type:

- A `COLLECTION` output must be a `CollectionSpec` object, never a dict.
- A `vector3` output needs `x`, `y`, and `z`.
- A `geometry` output needs `kind` and `id`.

## 3. Port types

`PortSpec(name, port_type, default_value=None, required=False, description="", label="", selection_type=None, enum_options=None, enum_icons=None, enum_labels=None, show_input_field=True, show_input_handle=True, min_value=None, max_value=None, label_from=None, unit=None, visible_when=None)`

Use snake_case port names. A port's label defaults to its name in Title Case.

- `unit` is `'length'` (cm) or `'angle'` (degrees). The input shows it as a suffix; values are never converted.
- `visible_when` shows a port only for some values of a sibling dropdown, for example `{'port': 'shape', 'values': ['box'], 'default': 'sphere'}`. The Falloff nodes use it to change their ports with their Shape. These are the `PortType` values from `backend/contracts.py`:

| PortType | Value | Input UI |
|---|---|---|
| `FLOAT` | `float` | number field |
| `INTEGER` | `integer` | number field |
| `BOOLEAN` | `boolean` | checkbox |
| `STRING` | `string` | text field |
| `ENUM` | `enum` | dropdown (`enum_options`, optional `enum_labels`, `enum_icons`) |
| `VECTOR3` | `vector3` | X/Y/Z fields; values are `{'x','y','z'}` dicts |
| `TRANSFORM` | `transform` | connection only |
| `GEOMETRY` | `geometry` | connection only |
| `COLLECTION` | `collection` | connection only; carries `CollectionSpec` |
| `SURFACE` | `surface` | Select button (face) |
| `BODY` | `body` | Select button (body) |
| `POINT` | `point` | Select button (point or vertex) |
| `CURVE` | `curve` | Select button (edge or sketch curve) |
| `SPACER` | `spacer` | Visual gap only. Give each one a unique name (`spacer_0`, `output_spacer`, ...). |

`BREP` is an alias for `GEOMETRY`.

Follow these rules when your node touches the Fusion API or produces bodies:

- Don't use `from adsk ...` imports, because `spec_tests.py` rejects them. Use `import adsk.core` / `import adsk.fusion` inside the method that needs them, as the geometry nodes do.
- Lengths are in centimeters.
- To create a body, build it with `adsk.fusion.TemporaryBRepManager` and call `design.rootComponent.bRepBodies.add(brep, context['base_feature'])`. Then call `self._register_body_name(context, body.name)` so the visibility toggle can find the body. `geometry_box.py` is the simplest example.

## 4. Add it to the menu

Add the normalized type to a section in `backend/nodes/menu_config.py`:

```python
"math": ["number", "add", "subtract", "multiply", "absolute", "vector3", "3d_point"],
```

If a node isn't listed there, the Add Node menu puts it in the section named after its `NODE_CATEGORY`. If no section has that name, the node doesn't appear in the menu at all. List new nodes explicitly. A section whose name starts with `_` is hidden.

## 5. Frontend work

**Required:** nothing, as long as the node uses an existing category and existing port types. The UI is generated from the spec, so you don't need to rebuild it.

**Optional:**

- **Live values downstream.** Before Generate, a connected input shows a value only when everything feeding it is a pure calculation. If your node is one (it only does arithmetic on its inputs and never uses `adsk`, the design, or a selection), set `PREVIEWABLE = True` on the class. The backend then runs it as the user edits, and the palette shows its outputs on whatever they connect to. No frontend code is needed. A test fails if a previewable node references `adsk`.
- **Helper nodes.** A node with a collection input gets an Atomizer added before it, and one that also has a collection output gets a Materializer after it, when the graph has none. This is derived from the ports in `backend/nodes/companions.py`. If your node needs an array upstream and a bare Atomizer would be useless, set `AUTO_COMPANIONS = False` on the class.
- **Frontend validation.** Add rules in `ui/src/hooks/useNodeValidation.js`. A validation error disables **Generate**.
- **Custom rendering.** `ui/src/components/ModularCustomNode.jsx` special-cases a few types. For example, the Falloff Effector, Falloff modifier and Gradient modifier embed the falloff curve editor (`FalloffCurveEditor.jsx`).
- **A new `NODE_CATEGORY`.** Add `--node-category-<name>` to `ui/styles/theme.css` and a `ui/styles/nodes/<name>-node.css` file. Then import that file in `ui/src/main.jsx`. Without these, the node has no category color.
- **A new port type.** This touches several files:
  - `PortType` in `contracts.py`
  - `allowed_port_types` in `specification.py`
  - a `case` in `ui/src/components/PortFactory.jsx` (which `spec_tests.py` checks for)
  - the color and compatibility rules in `ui/src/modules/EdgeManager.js`

If you changed anything under `ui/`, rebuild it. See [Building the UI](building-the-ui.md).

## Changing an existing node

Saved graphs, in documents and in `.noodle` files, refer to nodes by type and to ports by name. Some changes need a migration so those graphs keep loading:

| Change | Migration needed |
|---|---|
| Add a port | No. It takes its default. |
| Remove a port | No. Its saved value is ignored. |
| Change a label or description | No. |
| Rename a node type (`NODE_TYPE`) | Yes |
| Rename a port | Yes |
| Rename a dropdown option | Yes |

To add one, open `backend/graph_format.py`, add 1 to `GRAPH_FORMAT`, and append an entry to `MIGRATIONS`. The module's docstring shows the entry format. The tests check that the list stays consistent and that every file in `examples/` still loads.

## 6. Check, document, reload

From the repository root, run the checks:

```sh
python3 backend/spec_tests.py
python3 -m unittest discover -s tests -t .
python3 scripts/generate_node_docs.py
```

- `spec_tests.py` must print that all modules comply.
- The tests must pass. They check your node automatically: every dropdown option must be handled in the node's code, and every declared input must be read.
- `generate_node_docs.py` rewrites `docs/nodes.md`. Commit the result.
- `python3 scripts/generate_node_docs.py --check` exits with status 1 if `docs/nodes.md` is stale. Run it before you open a pull request.

Then reload the add-in in Fusion. Open **Utilities → Add-Ins** (Shift+S), select **Noodle**, and click **Stop**, then **Run**. Open the palette, find your node under **Add Node**, and test it with **Generate**. Stop and Run reloads every Noodle module, so there's no need to restart Fusion.

The automated tests check specs, contracts and pure calculations. Anything that creates geometry is tested in Fusion.
