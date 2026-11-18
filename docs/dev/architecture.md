# Architecture

Noodle has two halves:

- **Frontend:** a React + React Flow app that runs in a Fusion HTML palette.
- **Backend:** a Python package that runs inside Fusion's add-in runtime.

The frontend only edits the graph. The backend executes it and creates geometry through the Fusion API.

## Repository layout

```
Noodle.py              Add-in entry point: run()/stop(), toolbar button, palette, HTML event handler
Noodle.manifest        Fusion add-in manifest
config.py              LOG_LEVEL, GENERATE_AS_SINGLE_UNDO, SHOW_GENERATE_PROGRESS, MODULE_LOGGING_ENABLED
backend/
  __init__.py          initialize(), handle_message()
  core.py              Application singleton, action routing, Base Feature lifecycle
  contracts.py         PortType, PortSpec, NodeSpec, NoodleAttributes, GeometryEnvelope, CollectionSpec
  specification.py     Machine-readable rules (logging format, node requirements, naming, imports)
  enforcement.py       @enforce_node_spec, @enforce_logging, static source checks
  spec_tests.py        Runs the static checks + contract tests outside Fusion
  graph_format.py      Graph file format version and the migrations that bring old graphs up to it
  preview.py           Runs a graph without creating geometry: live values and the visualizer
  visualizer.py        Draws the visualizer's dots and falloff outlines as custom graphics
  handlers/            One class per concern: graph, geometry, selection, persistence, node_registry
  nodes/               One file per node, plus base.py, effector_base.py, menu_config.py, __init__.py (registry)
  services/            transform_composition_service.py
  utilities/           log_utils, transform/vector math, surface grid generators, modifier/noise evaluation,
                       naming, field_curve/field_sources (falloff curves and shapes), progress (Generate's dialog)
ui/
  index.html           Palette page; defines window.returnData bridge, loads dist/bundle.{js,css}
  src/                 React app (main.jsx, NoodleApp.jsx, components/, hooks/, modules/, bridge/)
  styles/              CSS, including styles/nodes/<category>-node.css
  dist/                Committed build output
scripts/generate_node_docs.py   Generates docs/nodes.md from the node registry
tests/                 Behavior tests that run outside Fusion (python -m unittest), fixtures/ shared with ui/tests
docs/                  User and developer documentation
```

## Message path

All communication is request/response, and the frontend always starts it:

1. The frontend calls `window.adsk.fusionSendData(action, jsonString)`.
   - On startup, `main.jsx` goes through `window.returnData` instead. This is a wrapper in `ui/index.html` that waits up to 5 s for `window.adsk` to appear.
   - Later calls go through `FusionBridge.sendMessage` or call `fusionSendData` directly.
2. `PaletteHTMLEventHandler.notify` in `Noodle.py` receives the event, parses `args.data` as JSON, and calls `backend.handle_message(action, data)`.
3. `Application.handle_message` in `backend/core.py` handles `palette_ready` itself. Every other action is routed to the handler that declares it and dispatched through that handler's `handle(action, data)`:

| Handler | Actions |
|---|---|
| `graph_handler` | `generateGeometry`, `checkCoordinates`, `previewValues`, `updateVisualizer`, `clearVisualizer` |
| `geometry_handler` | `clearBaseFeature`, `set_node_visibility`, `set_nodes_visibility`, `get_node_visibility` |
| `selection_handler` | `select{Surface,Body,Point,Curve}`, `check{Surface,Body,Point,Curve}Selection`, `cancelSelection` |
| `persistence_handler` | `scanDocument`, `refreshGraph`, `saveGraphFile`, `openGraphFile`, `updateWorkingGraph`, `discardWorkingGraph` |
| `node_registry_handler` | `deleteNode` (acknowledgement only) |

   Each handler declares its actions in a class-level `ACTIONS` table that maps the action name to the method that answers it. That table is the only place an action is declared. At startup `Application.build_routes()` builds the routing table from the handlers' `ACTIONS`, and stops with an error if two handlers declare the same action or one names a method that doesn't exist. To add an action, add one line to the handler's `ACTIONS` and write the method. `tests/test_message_routing.py` also checks that every action the palette sends is one the add-in accepts.

4. The handler returns a dict, which `Noodle.py` serializes into `args.returnData`. That becomes the return value of `fusionSendData` in the browser. Responses always contain `success`, and failed ones also contain `error`.

Selection is polled. A `select*` call either takes Fusion's current `activeSelections` or marks a selection as pending. The frontend then polls `check*Selection` until it gets a result, or until 30 s pass.

### Generate as one undo step

Fusion groups everything done inside a command's execute handler into one undo entry. Work done directly in a palette message is not grouped, so each body Generate creates would be its own undo entry.

With `GENERATE_AS_SINGLE_UNDO = True` in `config.py` (the default), `Noodle.py` runs `generateGeometry` inside a command:

1. It stores the graph data, executes a hidden command (`jm_NoodleGenerateCommand`), and answers the palette at once with `{success: true, deferred: true}`.
2. Fusion runs the command after the message handler returns. Its execute handler calls `backend.handle_message('generateGeometry', data)`.
3. The result is pushed to the palette with `palette.sendInfoToHTML('generateResult', json)`. `ui/src/bridge/backendEvents.js` receives it and `GenerationManager` continues as if the response had arrived directly.

Hiding template bodies (those feeding an Atomizer or an array) happens in the backend at the end of Generate, so it is part of the same undo entry. Set the switch to `False` to run Generate directly from the palette message, as a fallback.

### Showing and hiding bodies as one undo step

The eye icons, the visualizer (which hides bodies once its dots are drawn) and the curve editor (which puts them back when it closes) all send `set_node_visibility` or `set_nodes_visibility`. `Noodle.py` runs these inside a second hidden command, `jm_NoodleVisibilityCommand`, shown in the undo history as "Noodle Show/Hide Bodies".

This matters for speed as well as undo. Set from a palette message, each body is its own undo entry with its own redraw: seconds, and 1,600 undo entries, for 1,600 bodies. Inside a command the same loop took 0.22 s for 450 bodies.

Requests that arrive before the command runs are merged, the latest one per node winning, and the command applies them all. If the command hasn't run within 2 seconds it is taken as dropped and started again. If it can't be started, visibility is set directly. The palette answers at once with `{success: true, deferred: true}`. No result is sent back; the eye icons have already changed.

Selecting the bodies and running Fusion's own Show/Hide (`executeTextCommand('Commands.Start VisibilityToggleCmd')`) was also fast (0.17 s for 450), but it replaces the user's selection and relies on an unsupported call.

## Graph execution

The frontend owns the graph as React Flow state. Clicking **Generate** sends the whole state (`reactFlowInstance.toObject()`) in a `generateGeometry` request. `GraphHandler._generate_geometry` then does the following:

1. **Convert the graph.** Each node's `data.currentInputs` (typed values) and `data.computedInputs` (values the frontend propagated) are merged into `{id, type, inputs}`.
2. **Instantiate nodes.** A fresh node instance is created for every node through `NodeRegistry.get_node_class(type)`. Nothing is cached between runs.
3. **Choose what runs.** `_find_connected_nodes` keeps every node upstream of a terminal sink, meaning a node with incoming edges but no outgoing ones. It also keeps isolated nodes whose `NODE_CATEGORY` is `geometry`, `math`, or `transform`. Everything else is skipped.
4. **Order the nodes.** `_topological_sort` runs Kahn's algorithm over the kept nodes. If it finds a cycle, it logs a warning and appends the remaining nodes.
5. **Execute.** Inside a Base Feature edit, each node runs `execute(inputs, context)` in order.
   - `_resolve_inputs` starts from the node's stored inputs and overwrites every connected port with the upstream node's actual output. Edge handles are `output-<port>` and `input-<port>`.
   - The first exception stops the run, and the error is returned.
6. **Respond.** Results are stripped of Fusion objects and returned. The React Flow state is saved to the document whenever a fresh Base Feature exists, even after a failure, because the previous Base Feature and the graph saved on it are already gone (see Persistence).

### Progress

A Generate that lasts more than a second shows Fusion's progress dialog, with a Cancel button (`backend/utilities/progress.py`). The palette can't repaint while Generate runs on Fusion's main thread; the dialog can. Nodes get it as `context['progress']` and call `progress.step(done, total)` in long loops, which throttles itself and raises `GenerationCancelled` when the user cancels. Pumping events to notice Cancel also redraws the viewport, which slows as bodies are added, so it happens at most every 2 s. `SHOW_GENERATE_PROGRESS` in `config.py` turns it off.

Nodes that need a parametric feature leave the edit and reopen it inside `execute()`, as Pipe does. See [Faith-based execution](#faith-based-execution).

### Live values

Before a Generate, the palette shows the value arriving at a connected input, such as a Number feeding a Box's Width. The frontend has no copy of any node's logic. `ui/src/hooks/useFlowComputation.js` sends the graph in a `previewValues` message whenever nodes, connections, or inputs change. `backend/preview.py` runs the nodes marked `PREVIEWABLE` (pure calculations that never touch Fusion) and returns their outputs, and the hook copies each output along its connection into the target node's `computedInputs`.

A node is skipped when any of its inputs comes from something that can't be known without generating, such as geometry, a collection, or a modifier. That input is shown as connected, with no value. A 3D Point's coordinates come from the picked entity, so the palette passes them in as a known output.

This is display-only. Generate recomputes everything.

### Effector visualizer

An effector whose eye is on has `data.visualize` set on its node. While any are on, `ui/src/hooks/useVisualizer.js` sends the graph in an `updateVisualizer` message whenever an input, a connection, or the set of visualized effectors changes. Requests never overlap; a change that arrives mid-request is sent when that request returns.

The backend does three things:

1. **Runs the graph without creating anything.** `preview_collections()` in `backend/preview.py` uses the same walk as live values, but lets every node run except those that output geometry or curves, since running one of those adds bodies, sketches, or features to the design. Those nodes are stood in for by an empty geometry envelope, which is enough for an Atomizer to start a collection. Arrays and effectors run for real and read faces and curves from the design.
2. **Turns results into dots.** Each effector tags every instance it processes with its strength, under `effector_strengths` in the instance metadata, keyed by node id. `collect_dots()` in `backend/visualizer.py` sums the strengths of the visualized effectors per instance and takes the dot's position from the instance's final transform.
3. **Draws them.** Each dot is a small disk mesh in a custom graphics group. It is billboarded so it always faces the camera, view-scaled so it stays the same size on screen, and given a show-through color effect with an opacity just under 1, which makes Fusion draw it in front of bodies. Without that, a dot on a curved face is half hidden by the face. Strengths are sorted into 32 color steps, and the dots of one step share a color effect. Custom graphics add nothing to the undo history.

Falloff nodes also get a faint outline of their shape: an arrow with end rings for Linear, the box edges for Box, and for Sphere the exact silhouette of its ellipsoid as seen from the current camera. That silhouette depends on the view, so it is traced again on every `cameraChanged`. The inner radius is drawn fainter. See [falloff-fields.md](falloff-fields.md).

Opening a falloff's curve editor turns on the visualizer for the effectors it feeds, then hides bodies once the dots are drawn, and puts both back when it closes.

Things learned the hard way about custom graphics:
- `addPointSet` takes one image per set, so points can't be colored individually. That is why dots are meshes.
- Set `viewScale` before `transform`.
- A custom graphics group belongs to one document and survives palette close and document switches unless deleted. Check `isValid` before `deleteMe()`, and never delete a group Noodle doesn't own (every Noodle group id starts with the visualizer's prefix).
- Graphics drawn while a Fusion command is running are rolled back when it ends. The visualizer redraws after `commandTerminated`, except for Noodle's own Generate and visibility commands.

The dots are removed when the last eye turns off, on Generate, when the palette opens or closes, and when the add-in stops. Closing the palette clears them from every open document, since dots stay in the document they were drawn in, and refuses any redraw still on its way until the palette opens again.

## Collections and transforms

Most nodes don't pass bodies around. They pass a **`CollectionSpec`**, defined in `contracts.py`:

- `source_geometries`: a list of `GeometryEnvelope` (`kind`, `id`, the Fusion `geometry` object, `geometry_name`).
- `instances`: a list of `CollectionInstanceSpec`. Each instance has an `instance_id`, a `source_geometry_id`, `metadata` (for example grid U/V indices or strand positions), and a `transform`.

The `transform` is a **`NoodleAttributes`**: flat, Maya-style primitives (`tx..tz`, `rx..rz`, `sx..sz`, an optional quaternion `qx..qw` with `use_quaternion`, and `v` for visibility). Its transform fields may never be `None`.

Data moves through a typical chain like this:

- **Atomizer** turns geometry into a one-instance collection. **Null to Collection** gives one instance with no geometry.
- **Arrays** multiply instances.
- **Effectors** change each instance's `NoodleAttributes`. They compose transforms through `services/transform_composition_service.py`, component by component, so position and scale stay independent. Strength can be a plain float, or a descriptor from a modifier, Random, or Noise node that `effector_base.py` evaluates per instance.
- **Materializer** copies each source body with `TemporaryBRepManager`, applies the instance transform, and adds the result to the Base Feature.

On the wire, `COLLECTION` ports must carry `CollectionSpec` objects. `@enforce_node_spec` raises an error if a node returns a dict. Call `to_dict()` only at serialization boundaries.

## Geometry and the Base Feature

All generated geometry lives in one Base Feature named `Noodle_Geometry` in the root component. A Base Feature is Fusion's container for direct-modeled geometry inside a parametric design. Noodle depends on one Fusion behaviour that is easy to get wrong, so read this section before touching Generate or writing a node that makes geometry.

### Faith-based execution

**Noodle is inside the Base Feature edit because it opened the edit, not because Fusion says so.** Fusion gives no reliable way to ask whether a Base Feature edit is open, and no event or callback when one opens or closes. Code that checks the edit state, waits for a signal, or retries until the edit "looks" open will misbehave, because Fusion never answers. So:

1. `startEdit()` is called once. When it returns, everything that follows runs as if inside the edit. Nothing checks.
2. Every node runs.
3. `finishEdit()` is called in a `finally`, so the edit is closed whatever happened.

The graph handler owns this (`GraphHandler._generate_geometry`). Nodes never open or close the edit, with one exception (Pipe, below). This is why the lifecycle is so short and so strict: one open, one close, nothing in between that asks Fusion where it is.

With `GENERATE_AS_SINGLE_UNDO` on (the default), the whole Generate runs inside Noodle's hidden command (see "Generate as one undo step"), so the edit opens and closes within one undo step.

### One Generate, step by step

1. **Recreate.** `core._recreate_base_feature()` deletes every Base Feature whose name starts with `Noodle_Geometry`, adds a new one and names it. Starting fresh is faster than deleting bodies one by one, and means no node ever finds geometry from a previous run.
2. **Open the edit** with `startEdit()`, and trust it.
3. **Execute the nodes in order.** Inside the edit, geometry is made only in ways that land in the Base Feature:
   - Bodies: build a temporary B-Rep (`TemporaryBRepManager`) and add it with `rootComponent.bRepBodies.add(brep, base_feature)`. Most nodes work this way, including the Materializer.
   - Sketches: `rootComponent.sketches.addToBaseOrFormFeature(plane, base_feature, True)`, as Interpolize does.
   - An extrude from such a sketch also stays inside the edit (Polygon).
4. **Close the edit** with `finishEdit()`, always.
5. **Save the graph** on the new Base Feature (see Persistence).

### What breaks it

- **Writing to the timeline.** Some parametric features are accepted inside the edit but end up on the main timeline when it closes, outside the Base Feature. `pipeFeatures.add()` does (reported to Autodesk as a bug); `extrudeFeatures.add()` doesn't. Test any other feature type before relying on it. A node that needs one that escapes must leave the edit to make it. Pipe does:
  1. capture the spline references,
  2. `finishEdit()`,
  3. run `pipeFeatures.add()`, copy each body into a temporary B-Rep, and delete the feature,
  4. `startEdit()` in a `finally`,
  5. add the B-Reps to the Base Feature.

  Follow that pattern exactly, reopening in a `finally`, or the rest of the graph runs outside the edit. The pipe features exist only for a moment inside Generate's undo step, so the user never sees them. (`features_sweep.py` is a hidden, unfinished experiment that tests whether `sweepFeatures.add()` escapes the same way; there's no recorded answer yet.)
- **Checking or waiting for the edit state.** See above: there is nothing to wait for.
- **Holding references across `finishEdit()`.** The Base Feature and the bodies in it go stale when the edit closes. Look them up again by name (`geometry_handler._find_bodies_fresh`, and `core` scans Base Features by name).
- **Creating the Base Feature early.** It is created when Generate runs, never when the palette opens.
- **Direct-modeling designs.** A design with history capture turned off can't hold a Base Feature. Generate stops with an error there rather than switching the design's mode.

### Bodies and their names

- Nodes record body names in `context['node_body_names']` through `BaseNode._register_body_name`. `geometry_handler` looks names up there to apply per-node visibility.
- Body names come from `utilities/geometry_naming.py`: `generate_geometry_name()` builds `<type>_<short id>_<source>[_<index>]`, where the short id is the trailing digits of the node id. That record is lost when a document is reopened, so `geometry_name_prefix()` finds a node's bodies by that prefix instead. A Materializer names bodies with its own prefix, whatever array placed the instances.
- `clearBaseFeature` deletes the Base Feature entirely.

## Persistence and document switching

`persistence_handler.py` stores the sanitized React Flow JSON as the attribute `noodle` / `reactflow_json` on the `Noodle_Geometry` Base Feature. It's written by every `generateGeometry` that created a fresh Base Feature, even one that failed.

The handler also subscribes to `documentActivated`, `documentOpened`, and `documentClosed`. When the active document changes:

1. `_on_document_activated` sets the HTML URL of the palette to itself (`palette.htmlFileURL = palette.htmlFileURL`), which reloads it, and clears core state.
2. The reloaded page sends `palette_ready`.
3. `core._handle_palette_ready` scans the new document's Base Features for a saved state. It returns the node specs, the menu sections, and the first `reactFlowState` it finds.
4. `main.jsx` stashes these values on `window`, and `NoodleApp` restores the graph.

`NoodleApp` also calls `refreshGraph` on mount, which reads the document the same way.

### Generated graph and working copy

A document holds up to two snapshots of its graph. The generated graph is an attribute on the `Noodle_Geometry` Base Feature, written by Generate. The working copy is the graph as edited since.

The palette (`ui/src/hooks/useWorkingGraph.js`) compares the canvas with the graph that was last loaded or generated. When they differ, it sends `updateWorkingGraph` shortly after the last change. The persistence handler keeps the working copy in memory, keyed by the root component's id, and writes it to an attribute on the root component in the `documentSaving` event. Writing only at save time keeps graph edits out of Fusion's undo history.

Loading (`palette_ready`, `scanDocument`, `refreshGraph`) returns the working copy when there is one and sets `workingCopy: true`. Generate and Clear remove it. `discardWorkingGraph` removes it and returns the generated graph.

### Graph files and the format version

`backend/graph_format.py` owns the saved-graph format. Every saved graph carries `"noodle": {"format": N, "version": "x.y.z"}`. `migrate()` brings an older graph up to the current format by applying the entries in `MIGRATIONS`, and refuses a graph from a newer format. It runs when a graph loads from a document and when a `.noodle` file is opened. `saveGraphFile` and `openGraphFile` in the persistence handler show Fusion's file dialog and read or write the file.

## Node discovery and the menu

`NodeRegistry.initialize()` in `backend/nodes/__init__.py` runs on every `palette_ready`:

- It imports every `backend/nodes/*.py` except `_*`, `base.py`, and `menu_config.py` with `importlib`.
- It registers each `BaseNode` subclass that has a non-empty `NODE_TYPE`.
- It serializes `get_spec()` to the frontend format with `PortSpec.to_dict()`.

`menu_config.py` sets the **Add Node** sections and their order. It maps section names to normalized node types (lowercase, spaces replaced with `_`). Sections that start with `_` are hidden. The frontend renders whatever the backend sends. There is no per-node registration in the UI.

## Specification and enforcement

`specification.py` holds the rules as data. For example:

- Nodes need `get_spec`, `validate`, and `execute`.
- Nodes need the `NODE_TYPE`, `NODE_CATEGORY`, `NODE_NAME`, and `NODE_DESCRIPTION` class attributes.
- Node class names must match `^[A-Z][a-zA-Z0-9]+Node$`.
- `from adsk ...` imports are forbidden.
- The log format is defined here too.

`enforcement.py` applies the rules:

- **`@enforce_node_spec`** checks a node class at import time. It also wraps `execute` so that every run checks data-flow integrity, calls `validate(inputs)`, and checks the outputs against the port contracts.
- **`SpecificationEnforcer.check_module`** statically scans backend files for `print()`, forbidden imports, and invalid `PortType.X` names. It also scans selected node UI files for inline styles and hard-coded colors.

`backend/spec_tests.py` runs these static checks, a PortFactory coverage check, and the contract round-trip tests. It runs outside Fusion.

## Imports

Fusion runs every add-in in one Python interpreter and loads each one as a package named after its folder. Noodle's modules therefore load as `Noodle.backend...`, and all imports inside the add-in are package-relative (`from ..contracts import PortSpec`). Don't add the add-in folder to `sys.path` or use absolute `from backend...` imports: top-level names like `backend` or `config` would be shared with every other add-in. `Noodle.py` reads `config.py` and passes the logging settings to the backend with `configure_logging()`.

The scripts that run outside Fusion (`backend/spec_tests.py`, `scripts/generate_node_docs.py`) put the repo root on the path and import `backend` as a top-level package. Relative imports resolve the same way in both cases.

## Logging

Use `backend.utilities.log_utils.log(app, message, level=LogLevel.X, module="NAME")`. Never use `print()`, because `spec_tests.py` rejects it. Output goes to Fusion's Text Commands window.

To silence a noisy module, set its name to `False` in `MODULE_LOGGING_ENABLED` in `config.py`. Modules that aren't listed are logged.
