import React, { useState } from 'react';
import { showPortTipSoon, hidePortTip } from './PortTip';
import ConfirmDialog from './ConfirmDialog';

/**
 * The toolbar, laid out like Fusion's quick access toolbar: an Add Node menu,
 * borderless 16 px icon buttons for Open, Save, Revert and Clear, and Generate.
 *
 * Generate shows where the design stands (see generateState in NoodleApp.jsx):
 * out of date, up to date, generating, invalid, failed, or nothing to generate.
 * Its tip says why. Revert and Clear throw work away, so they ask first, in a
 * dialog like Fusion's own "Unsaved changes".
 */

// Toolbar icons are the SVG files, drawn in the text colour through a CSS mask.
// The URL is made absolute: a relative url() inside a CSS variable resolves
// against the stylesheet that uses it (ui/dist/), not this page.
const Icon = ({ src }) => (
  <span className="noodle-icon" aria-hidden="true"
        style={{ '--icon': `url("${new URL(src, document.baseURI).href}")` }} />
);

// Generate's state icons, drawn in currentColor
const STATE_ICONS = {
  stale: <path d="M13 8a5 5 0 1 1-1.46-3.54M13 2.5v3h-3" fill="none" stroke="currentColor" strokeWidth="1.5" />,
  current: <path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="1.6" />,
  invalid: <><path d="M8 2l6.5 11.5h-13z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M8 6.5v3.2M8 11.3v.2" stroke="currentColor" strokeWidth="1.5" /></>,
  failed: <><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" stroke="currentColor" strokeWidth="1.4" /></>,
  generating: <path d="M8 2a6 6 0 1 1-6 6" fill="none" stroke="currentColor" strokeWidth="1.6" />,
};

const GENERATE_LABEL = { current: 'Generated', generating: 'Generating' };

// Hover tip for a toolbar button, the same tip nodes use
const tipHandlers = (tip) => tip ? {
  onMouseEnter: (e) => showPortTipSoon({ anchor: e.currentTarget, ...tip }),
  onMouseLeave: (e) => hidePortTip(e.currentTarget),
} : {};

const Toolbar = ({
  // Node menu state
  nodeMenu,
  categories,
  showCascadingMenu,
  setShowCascadingMenu,
  hoveredCategory,
  setHoveredCategory,
  version,

  // Node operations
  createNode,
  nodes,

  // Graph operations
  openGraphFile,
  saveGraphFile,
  revertGraph,
  isEdited,
  clearGraph,
  handleGenerate,
  generateState   // {state, title, body}
}) => {
  const [confirming, setConfirming] = useState(null); // 'clear' | 'revert' | null

  const state = generateState?.state || 'empty';
  const generateDisabled = state === 'empty' || state === 'invalid' || state === 'generating';

  return (
    <div className="noodle-toolbar">
      <div className="cascading-menu-container">
        <button
          className="noodle-qat-menu"
          onClick={() => setShowCascadingMenu(!showCascadingMenu)}
          onBlur={() => setShowCascadingMenu(false)}
          aria-expanded={showCascadingMenu}
        >
          Add Node
          <span className="noodle-qat-caret" aria-hidden="true" />
        </button>

        {showCascadingMenu && (
          // preventDefault keeps focus on the button, so its onBlur doesn't close
          // the menu before a click on a menu item lands.
          <div className="cascading-menu" onMouseDown={(e) => e.preventDefault()}>
            {categories.map(category => (
              <div
                key={category}
                className="cascading-category"
                onMouseEnter={() => setHoveredCategory(category)}
                onMouseLeave={() => setHoveredCategory(null)}
              >
                {/* Menu sections are lower-case ids (menu_config.py); show them capitalised */}
                <div className="cascading-category-label">{category.charAt(0).toUpperCase() + category.slice(1)}</div>

                {hoveredCategory === category && (
                  <div className="cascading-submenu">
                    {nodeMenu
                      .filter(n => n.menu_category === category)
                      .sort((a, b) => a.name.localeCompare(b.name))
                      .map(n => (
                      <div
                        key={n.type}
                        className="cascading-submenu-item"
                        onClick={() => {
                          createNode(n.type);
                          setShowCascadingMenu(false);
                          setHoveredCategory(null);
                        }}
                      >
                        {n.name}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {version && <div className="cascading-menu-version">Noodle v{version}</div>}
          </div>
        )}
      </div>

      <div className="noodle-qat" role="group" aria-label="Graph">
        <button className="noodle-qat-button" onClick={openGraphFile} aria-label="Open"
                {...tipHandlers({ title: 'Open', body: 'Open a graph from a .noodle file.' })}>
          <Icon src="./icons/open-16.svg" />
        </button>
        <button className="noodle-qat-button" onClick={saveGraphFile} disabled={nodes.length === 0} aria-label="Save"
                {...tipHandlers({ title: 'Save', body: 'Save the graph to a .noodle file.' })}>
          <Icon src="./icons/save-16.svg" />
        </button>
        <button className="noodle-qat-button" onClick={() => setConfirming('revert')} disabled={!isEdited} aria-label="Revert"
                {...tipHandlers({ title: 'Revert', body: 'Discard the edits made since the last Generate.' })}>
          <Icon src="./icons/revert-16.svg" />
        </button>
        <button className="noodle-qat-button" onClick={() => setConfirming('clear')} disabled={nodes.length === 0} aria-label="Clear"
                {...tipHandlers({ title: 'Clear', body: 'Remove every node and delete the Noodle geometry.' })}>
          <Icon src="./icons/delete-16.svg" />
        </button>
      </div>

      <div className="noodle-toolbar-spacer" />

      <button
        className={`noodle-generate noodle-generate-${state}`}
        onClick={handleGenerate}
        disabled={generateDisabled}
        aria-label={`${GENERATE_LABEL[state] || 'Generate'}${generateState?.title ? `: ${generateState.title}` : ''}`}
        {...tipHandlers(generateState?.title ? { title: generateState.title, body: generateState.body } : null)}
      >
        {STATE_ICONS[state] && (
          <svg className="noodle-generate-icon" viewBox="0 0 16 16" aria-hidden="true">{STATE_ICONS[state]}</svg>
        )}
        {GENERATE_LABEL[state] || 'Generate'}
      </button>

      {confirming === 'revert' && (
        <ConfirmDialog
          title="Revert edits"
          confirmLabel="Revert"
          onConfirm={() => { setConfirming(null); revertGraph(); }}
          onCancel={() => setConfirming(null)}
        >
          The edits made since the last Generate will be discarded. The design keeps the last Generate.
        </ConfirmDialog>
      )}
      {confirming === 'clear' && (
        <ConfirmDialog
          title="Clear graph"
          confirmLabel="Clear"
          onConfirm={() => { setConfirming(null); clearGraph(); }}
          onCancel={() => setConfirming(null)}
        >
          Every node will be removed and the <b>Noodle_Geometry</b> Base Feature will be deleted from the design.
        </ConfirmDialog>
      )}
    </div>
  );
};

export default Toolbar;
