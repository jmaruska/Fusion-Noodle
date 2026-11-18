# Developer documentation

These docs are for people who want to change Noodle itself.

- [Architecture](architecture.md): repository layout, the message path from the palette to the backend, graph execution, collections, the Base Feature, persistence, node discovery, the specification system, and logging.
- [Adding a node](adding-a-node.md): a step-by-step guide with a minimal working example.
- [Falloff curves](falloff-fields.md): the curve that shapes every falloff, its continuity rules, the shapes it's measured over, and the curve editor.
- [Building the UI](building-the-ui.md): building the React palette, loading changes in Fusion, and the checks to run before you commit.
- [Node reference](../nodes.md): generated from the node specs by `scripts/generate_node_docs.py`. Don't edit it by hand.

## Testing

Pure logic is tested outside Fusion; anything whose result comes from Fusion is tested in Fusion. See [Building the UI → Testing](building-the-ui.md#testing) for what runs where and how.
