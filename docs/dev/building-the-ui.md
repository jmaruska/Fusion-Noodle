# Building the UI

The palette UI is a React app (React 19, `@xyflow/react` 12) that Vite builds. The build output in `ui/dist/` is committed, so people who only install Noodle never need to build it. Rebuild only when you change something under `ui/src/` or `ui/styles/`.

## Prerequisites

- Node.js `^20.19.0` or `>=22.12.0`. This is what Vite 7 requires.
- npm.

## Build

```sh
cd ui
npm install
npm run build
```

`npm run build` runs `vite build` with `ui/vite.config.js`:

- The entry point is `src/main.jsx`.
- The output is exactly two files, `ui/dist/bundle.js` and `ui/dist/bundle.css`. `ui/index.html` loads both by those fixed names.
- Minification is off, so the bundle stays readable while you debug.

Commit the updated `ui/dist/` files along with your source changes.

## No standalone dev server

`ui/package.json` defines `npm run dev` (`vite`), but the app can't run outside Fusion. On startup, `main.jsx` sends `palette_ready` through `window.adsk.fusionSendData`, which exists only inside a Fusion palette. In a regular browser, the page gives up after 5 seconds and shows "Failed to connect to backend". Test UI changes in Fusion.

## Load your changes in Fusion

- **UI only** (`ui/dist/` rebuilt): close the Noodle palette and click the **Noodle** button again. The palette is recreated and loads the new bundle. Switching documents also reloads the palette.
- **Python changes** (`backend/`, `Noodle.py`, `config.py`): open **Utilities → Add-Ins** (Shift+S), select **Noodle**, then click **Stop** and **Run**. You don't need to restart Fusion. On Stop, Noodle removes its document event listeners and drops its own modules from Python's import cache, so Run imports the code from disk. If a change still doesn't show up, restart Fusion.

## Logs

Backend messages go to Fusion's Text Commands window through `backend.utilities.log_utils.log`. Only messages at `LOG_LEVEL` in `config.py` and above are written. The default is `INFO`. To see debug output without editing the file, set the `NOODLE_LOG_LEVEL` environment variable to `DEBUG` before starting Fusion. To silence individual modules, edit `MODULE_LOGGING_ENABLED` in `config.py`.

The frontend reports problems to the browser console with `console.warn` and `console.error`. It doesn't use `console.log`, and a test fails if one is added. To trace messages between the palette and the add-in, set `debug: true` where `FusionBridge` is created at the bottom of `ui/src/bridge/FusionBridge.js`, then rebuild.

## Checks before committing

Run these checks before every commit:

```sh
python3 backend/spec_tests.py
python3 -m unittest discover -s tests -t .
python3 scripts/generate_node_docs.py --check
(cd ui && npm test)
```

- `spec_tests.py` scans the backend for spec violations. It also scans the node UI components in `ui/src/` for inline `style={{...}}` and hard-coded colors: `BaseNode.jsx`, `ModularCustomNode.jsx`, `components/ports/`, `SelectionButton.jsx`, and `StatusPanel.jsx`. Put styling for those files in `ui/styles/`, using the CSS variables in `ui/styles/theme.css`.
- The tests in `tests/` cover logic that doesn't depend on Fusion: graph ordering, position generators, transform composition, modifiers, selection rules, error messages, and packaging. They also check every node for consistency, for example that each dropdown option a node declares is handled by its code. See [Testing](#testing).
- `npm test` in `ui/` runs the JavaScript tests in `ui/tests/` with Node's built-in test runner. They cover palette logic that needs no browser, such as planning where new nodes go and the falloff curve. The curve is computed in both Python and JavaScript, and both sets of tests check it against the same file, `tests/fixtures/field_curve_vectors.json`. Keep that kind of logic in plain modules under `ui/src/utils/` so it can be tested this way.
- `generate_node_docs.py --check` fails if `docs/nodes.md` doesn't match the node specs. To regenerate the file, run the script without `--check`.

Run them all before opening a pull request, and rebuild the UI so the committed `ui/dist/` matches the source.

If you use [pre-commit](https://pre-commit.com), this config runs the checks automatically before each commit:

```yaml
repos:
  - repo: local
    hooks:
      - id: check-specification
        name: Check Specification Compliance
        entry: python3 backend/spec_tests.py
        language: system
        files: ^backend/.*\.py$
        pass_filenames: false
      - id: behavior-tests
        name: Behavior tests (outside Fusion)
        entry: python3 -m unittest discover -s tests -t .
        language: system
        files: ^(backend|tests)/.*\.py$|^Noodle\.(py|manifest)$
        pass_filenames: false
      - id: check-node-docs
        name: Check docs/nodes.md is up to date
        entry: python3 scripts/generate_node_docs.py --check
        language: system
        files: ^backend/(nodes|contracts)/?.*\.py$
        pass_filenames: false
```

The specification hook runs only when backend files change. If you edit one of the node UI components listed above, run `spec_tests.py` yourself.

## Testing

Noodle is tested in two places.

**Outside Fusion** (`tests/`, run with `python3 -m unittest discover -s tests -t .`). These tests cover pure logic only. Fusion's `adsk` modules are replaced with empty stand-ins so the backend can be imported, but no test checks what a Fusion API call returns. Don't add tests that fake Fusion's behavior. A test that passes against a fake tells you nothing about Fusion.

**Inside Fusion.** Anything whose result comes from Fusion is tested by running the add-in: geometry, selections, the timeline, undo, and palette behavior.

When you add a node, the consistency tests in `tests/test_node_specs.py` cover it automatically. Add a focused test when the node has logic that can run without Fusion, such as a position generator or a validation rule.
