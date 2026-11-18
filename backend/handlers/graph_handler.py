"""
Graph handler - manages graph execution and connections.
Spec-compliant implementation.
"""

import time
from typing import Dict, Any, List
from ..utilities.log_utils import log
from ..specification import LogLevel
from ..utilities.progress import GenerateProgress, GenerationCancelled

class GraphHandler:
    """Handles graph operations and execution"""

    # Messages this handler accepts, and the method that answers each.
    # The core builds its routing table from these (see Application._build_routes),
    # so adding a message means adding one line here and nowhere else.
    ACTIONS = {
        'generateGeometry': '_generate_geometry',
        'checkCoordinates': '_check_coordinates',
        'previewValues': '_preview_values',
        'updateVisualizer': '_update_visualizer',
        'clearVisualizer': '_clear_visualizer',
    }
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.app = context['app']
        self.ui = context['ui']
        self.core = context['core']

        # The last visualizer request, so the dots can be redrawn after a Fusion
        # command (see _on_command_terminated)
        self._last_visualizer_request = None
        self._command_terminated_handler = None
        self._subscribe_command_terminated()

        # Falloff outlines from the last draw. An ellipsoid's outline depends on the view, so
        # these are traced again whenever the camera moves (see _on_camera_changed).
        self._last_outlines = None
        self._camera_changed_handler = None
        self._subscribe_camera_changed()

    # Graphics drawn while a Fusion command is running (moving a point with the
    # Move command, for example) are rolled back when the command finishes, which
    # puts the previous dots back. Redrawing once any command ends fixes that.
    VISUALIZER_REDRAW_SKIP_COMMANDS = ('jm_NoodleGenerateCommand', 'jm_NoodleVisibilityCommand')

    def _subscribe_command_terminated(self):
        try:
            import adsk.core  # type: ignore
            handler_owner = self

            class _CommandTerminatedHandler(adsk.core.ApplicationCommandEventHandler):
                def __init__(self):
                    super().__init__()

                def notify(self, args):
                    try:
                        handler_owner._on_command_terminated(getattr(args, 'commandId', ''))
                    except Exception as e:
                        log(handler_owner.app, f"Visualizer redraw after command failed: {e}",
                            level=LogLevel.WARNING, module="GRAPH_HANDLER")

            self._command_terminated_handler = _CommandTerminatedHandler()
            self.ui.commandTerminated.add(self._command_terminated_handler)
        except Exception as e:
            log(self.app, f"Could not watch for finished commands: {e}", level=LogLevel.WARNING, module="GRAPH_HANDLER")
            self._command_terminated_handler = None

    def _subscribe_camera_changed(self):
        try:
            import adsk.core  # type: ignore
            handler_owner = self

            class _CameraChangedHandler(adsk.core.CameraEventHandler):
                def __init__(self):
                    super().__init__()

                def notify(self, args):
                    try:
                        handler_owner._on_camera_changed()
                    except Exception as e:
                        log(handler_owner.app, f"Falloff outline redraw failed: {e}",
                            level=LogLevel.WARNING, module="GRAPH_HANDLER")

            self._camera_changed_handler = _CameraChangedHandler()
            self.app.cameraChanged.add(self._camera_changed_handler)
        except Exception as e:
            log(self.app, f"Could not watch the camera: {e}", level=LogLevel.WARNING, module="GRAPH_HANDLER")
            self._camera_changed_handler = None

    def _on_camera_changed(self):
        outlines = self._last_outlines
        if not outlines or not any(o.get('ellipsoids') for o in outlines):
            return
        if not getattr(self.core, 'palette_open', True):
            return
        from ..visualizer import VisualizerRenderer
        VisualizerRenderer(self.app).draw_outlines(outlines, refresh=False)

    def _on_command_terminated(self, command_id: str):
        request = self._last_visualizer_request
        if not request or command_id in self.VISUALIZER_REDRAW_SKIP_COMMANDS:
            return
        if not getattr(self.core, 'palette_open', True):
            return
        self._update_visualizer(request)

    def shutdown(self):
        """Stop watching for finished commands. Called when the add-in stops."""
        handler, self._command_terminated_handler = self._command_terminated_handler, None
        self._last_visualizer_request = None
        self._last_outlines = None
        camera_handler, self._camera_changed_handler = self._camera_changed_handler, None
        if camera_handler is not None:
            try:
                self.app.cameraChanged.remove(camera_handler)
            except Exception as e:
                log(self.app, f"Could not stop watching the camera: {e}", level=LogLevel.WARNING, module="GRAPH_HANDLER")
        if handler is not None:
            try:
                self.ui.commandTerminated.remove(handler)
            except Exception as e:
                log(self.app, f"Could not stop watching commands: {e}", level=LogLevel.WARNING, module="GRAPH_HANDLER")
    
    # The design and Base Feature always come from the application, which
    # refreshes them on every message. A copy kept here would go stale as soon
    # as the user switches documents.
    @property
    def design(self):
        return self.core.design

    @property
    def base_feature(self):
        return self.core.base_feature

    def handle(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Route graph-related actions"""
        method_name = self.ACTIONS.get(action)
        if method_name:
            return getattr(self, method_name)(data)
        
        return {'success': False, 'error': f'Unknown graph action: {action}'}
    
    def _preview_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Compute live values for the palette by running the pure nodes. Creates nothing."""
        from ..nodes import NodeRegistry
        from ..preview import preview_values
        NodeRegistry.ensure_initialized(self.app)
        result = preview_values(data.get('nodes') or [], data.get('edges') or [],
                                NodeRegistry.get_node_class, self.app)
        return {'success': True,
                'outputs': self._make_results_serializable(result['outputs']),
                'errors': result['errors']}

    # ------------------------------------------------------------------
    # Effector visualizer
    # ------------------------------------------------------------------

    def _update_visualizer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redraw the visualizer dots for the effectors whose eye is on.

        Runs the arrays and effectors that feed them (creating nothing in the
        design), then draws one dot per instance, colored by combined strength.
        """
        import adsk.fusion  # type: ignore
        from ..nodes import NodeRegistry
        from ..preview import preview_collections
        from ..visualizer import VisualizerRenderer, collect_dots

        started = time.perf_counter()
        visualized = [str(node_id) for node_id in (data.get('visualized') or [])]
        renderer = VisualizerRenderer(self.app)
        if not getattr(self.core, 'palette_open', True):
            # A refresh that was already on its way when the palette closed
            self._last_visualizer_request = None
            self._last_outlines = None
            return {'success': True, 'points': 0, 'skipped': 'palette closed'}
        self._last_visualizer_request = data if visualized else None
        if not visualized:
            self._last_outlines = None
            return {'success': True, 'points': 0, 'removed': renderer.clear()}

        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return {'success': False, 'error': 'The visualizer needs an open design.'}
        NodeRegistry.ensure_initialized(self.app)

        result = preview_collections(
            data.get('nodes') or [], data.get('edges') or [], visualized,
            NodeRegistry.get_node_class,
            {'app': self.app, 'ui': self.ui, 'design': design})

        dots = collect_dots(result['outputs'], visualized)
        self._last_outlines = self._falloff_outlines(data.get('nodes') or [], result, dots)
        stats = renderer.draw(dots, self._last_outlines)

        # Say why an effector shows nothing, in the node's own words
        problems = []
        for node_id in visualized:
            if node_id in result['outputs'] and result['outputs'][node_id].get('collection') is not None:
                continue
            reason = result['errors'].get(node_id)
            if not reason:
                upstream = next(iter(result['errors'].items()), None)
                reason = upstream[1] if upstream else 'it has no collection to show yet'
            node_class = NodeRegistry.get_node_class(
                next((str(n.get('type')) for n in data.get('nodes') or [] if n.get('id') == node_id), ''))
            problems.append(f"{getattr(node_class, 'NODE_NAME', 'Effector')}: {reason}")
        response = {'success': True, **stats, 'passSeconds': round(time.perf_counter() - started, 2)}
        if problems:
            response['warnings'] = problems
        return response

    @staticmethod
    def _falloff_outlines(nodes, result, dots) -> list:
        """An outline for every falloff the preview pass ran: the visualized Falloff Effectors,
        and Falloff modifiers feeding a visualized effector."""
        from ..utilities.field_sources import FALLOFF_NODE_CENTER, field_outline
        types = {n.get('id'): str(n.get('type', '')) for n in nodes if isinstance(n, dict)}
        points = [(x, y, z) for x, y, z, _strength in dots]
        outlines = []
        for node_id, inputs in (result.get('inputs') or {}).items():
            center_name = FALLOFF_NODE_CENTER.get(types.get(node_id))
            if center_name:
                outlines.append(field_outline(inputs, center_name, points))
        return outlines

    def _clear_visualizer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove the visualizer dots."""
        from ..visualizer import VisualizerRenderer
        self._last_visualizer_request = None
        self._last_outlines = None
        return {'success': True, 'removed': VisualizerRenderer(self.app).clear()}

    def _generate_geometry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point the frontend calls to generate geometry."""
        # Generate replaces the visualizer: remove its dots so the new bodies show
        self._clear_visualizer({})

        # Check if we have a design
        if not self.design:
            return {
                'success': False,
                'error': 'No active document. Please create or open a document first.'
            }
        
        # ReactFlow's native format is stored for persistence and converted for execution
        reactflow_state = data.get('reactFlowState')
        if not reactflow_state:
            return {'success': False, 'error': 'Missing reactFlowState'}
        
        graph_data = self._convert_reactflow_to_graph(reactflow_state)
        
        log(self.app, f"Generating geometry for graph with {len(graph_data.get('nodes', {}))} nodes", 
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        
        # Update core graph state (both formats)
        self.core.current_graph = graph_data
        self.core.current_reactflow_state = reactflow_state
        
        # Rebuild node instances from graph data
        unknown_types = self._rebuild_node_instances(graph_data)
        
        # Execute the graph
        result = self._execute_graph({'graph': graph_data})
        if unknown_types:
            result.setdefault('warnings', []).append(
                f"Skipped nodes of unknown type: {', '.join(sorted(unknown_types))}. "
                "This graph may come from a different version of Noodle.")
        
        # Hide template bodies as part of Generate, so it lands in the same undo step
        if result.get('success'):
            result['visibility'] = self._apply_auto_visibility(graph_data)
            # The generated graph now matches the canvas, so there is no working copy
            persistence = self.core.handlers.get('persistence')
            if persistence:
                persistence.clear_working_graph(self.design)

        # Save the graph whenever a fresh BaseFeature exists, even if execution failed.
        # The previous BaseFeature (and the graph saved on it) was already deleted, so
        # skipping this would lose the user's graph on a failed Generate.
        if self.core.base_feature:
            try:
                persistence_handler = self.core.handlers.get('persistence')
                if persistence_handler:
                    if persistence_handler._save_reactflow_state_to_base_feature(reactflow_state):
                        log(self.app, "Successfully saved ReactFlow state to BaseFeature", 
                            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
                    else:
                        log(self.app, "Failed to save ReactFlow state to BaseFeature", 
                            level=LogLevel.WARNING, module="GRAPH_HANDLER")
            except Exception as e:
                log(self.app, f"Could not save ReactFlow state: {e}", 
                    level=LogLevel.WARNING, module="GRAPH_HANDLER")
        
        return result
    
    # Node types that take geometry into a collection pipeline. A body feeding one
    # of these is only a template for the instances, so it is hidden after Generate.
    COLLECTION_CONSUMER_TYPES = frozenset({
        'atomizer', 'collection_atomizer',
        'array', 'array_2d_grid', 'array_path', 'array_surface_grid',
        'array_surface_hex', 'array_surface_spiral', 'array_surface_uv',
    })

    def _auto_hidden_nodes(self, graph_data: Dict[str, Any]) -> set:
        """IDs of nodes whose bodies should be hidden: those feeding an Atomizer or an array."""
        from ..nodes import NodeRegistry
        nodes = graph_data.get('nodes', {})
        hidden = set()
        for edge in graph_data.get('edges', []):
            target = nodes.get(edge.get('target'))
            if not target or edge.get('source') not in nodes:
                continue
            target_type = str(target.get('type', ''))
            node_class = NodeRegistry.get_node_class(target_type)
            category = str(getattr(node_class, 'NODE_CATEGORY', '')).lower()
            if target_type.lower() in self.COLLECTION_CONSUMER_TYPES or category == 'array':
                hidden.add(edge['source'])
        return hidden

    def _apply_auto_visibility(self, graph_data: Dict[str, Any]) -> Dict[str, bool]:
        """Show or hide each node's bodies after a Generate. Returns {node_id: visible}."""
        visibility = {}
        geometry_handler = self.core.handlers.get('geometry')
        if not geometry_handler:
            return visibility
        hidden = self._auto_hidden_nodes(graph_data)
        for node_id in graph_data.get('nodes', {}):
            visible = node_id not in hidden
            try:
                geometry_handler._set_node_visibility({
                    'nodeId': node_id, 'visible': visible,
                    'nodeType': graph_data['nodes'][node_id].get('type')})
                visibility[node_id] = visible
            except Exception as e:
                log(self.app, f"Could not set visibility for {node_id}: {e}",
                    level=LogLevel.WARNING, module="GRAPH_HANDLER")
        return visibility

    def _convert_reactflow_to_graph(self, reactflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ReactFlow state to internal graph format for execution"""
        graph_data = {
            'nodes': {},
            'edges': reactflow_state.get('edges', [])
        }
        
        # Convert ReactFlow nodes to internal format
        for node in reactflow_state.get('nodes', []):
            if node.get('data', {}).get('nodeType'):
                # Merge currentInputs and computedInputs (computed values override manual values)
                current_inputs = node['data'].get('currentInputs', {})
                computed_inputs = node['data'].get('computedInputs', {})
                merged_inputs = {**current_inputs, **computed_inputs}
                
                graph_data['nodes'][node['id']] = {
                    'id': node['id'],
                    'type': node['data']['nodeType'],
                    'inputs': merged_inputs,  # Use merged inputs from frontend computation
                    'position': node.get('position', {'x': 0, 'y': 0})
                }
        
        return graph_data
    
    def _rebuild_node_instances(self, graph_data: Dict[str, Any]):
        """Rebuild node instances from graph data"""
        from ..nodes import NodeRegistry
        
        nodes_data = graph_data.get('nodes', {})
        
        # Clear existing instances
        self.core.node_instances.clear()
        unknown_types = set()
        
        # Recreate instances
        for node_id, node_info in nodes_data.items():
            node_type = node_info.get('type')
            if node_type:
                node_class = NodeRegistry.get_node_class(node_type)
                if node_class:
                    self.core.node_instances[node_id] = node_class(node_id)
                    log(self.app, f"Recreated node instance: {node_id} ({node_type})", 
                        level=LogLevel.DEBUG, module="GRAPH_HANDLER")
                else:
                    unknown_types.add(node_type)
                    log(self.app, f"Unknown node type '{node_type}' for node {node_id}; skipping",
                        level=LogLevel.WARNING, module="GRAPH_HANDLER")
        return unknown_types
    
    def _execute_graph(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the entire graph, recreating the BaseFeature for performance"""
        graph_data = data.get('graph', self.core.current_graph)
        
        log(self.app, "Executing graph...", 
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        
        # Delete and recreate BaseFeature for fast clearing
        # This is much faster than deleting individual geometry pieces
        if not self.core._recreate_base_feature():
            return {'success': False, 'error': 'Could not recreate BaseFeature for geometry generation'}
        
        # Prepare execution context with fresh BaseFeature
        # Clear the name registry so this execution starts fresh
        core = self.context.get('core')
        if core and hasattr(core, 'node_body_names'):
            core.node_body_names.clear()

        settings = getattr(self.core, 'settings', {}) or {}
        progress = GenerateProgress(self.ui, enabled=settings.get('show_progress', True))
        
        context = {
            'app': self.app,
            'ui': self.ui,
            'design': self.design,
            'base_feature': self.base_feature,
            'noodle_base_feature': self.base_feature,
            'progress': progress,
            'node_body_names': core.node_body_names if (core and hasattr(core, 'node_body_names')) else {},
        }
        
        log(self.app, f"Using recreated BaseFeature for execution",
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        # Start editing the new BaseFeature
        try:
            if hasattr(self.base_feature, 'startEdit'):
                self.base_feature.startEdit()
                log(self.app, "Started BaseFeature editing", 
                    level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        except Exception as e:
            log(self.app, f"Warning: Could not start BaseFeature editing: {e}", 
                level=LogLevel.WARNING, module="GRAPH_HANDLER")
        
        try:
            # Topological sort for execution order
            execution_order = self._topological_sort(graph_data)
            if execution_order is None:
                return {'success': False,
                        'error': 'The graph has a loop: a node depends on its own output. Remove one of the connections in the loop.'}
            
            # Execute nodes in order
            results = {}
            runnable = [node_id for node_id in execution_order if node_id in self.core.node_instances]
            progress.start(len(runnable))
            timings = []  # (node name, seconds, size of its output)
            generate_started = time.perf_counter()
            for position, node_id in enumerate(runnable, 1):
                node = self.core.node_instances[node_id]
                node_data = graph_data['nodes'].get(node_id, {})
                inputs = self._resolve_inputs(node_id, node_data, graph_data, results)
                
                # Add node_id to context for this execution
                node_context = context.copy()
                node_context['node_id'] = node_id
                # Inputs fed by a connection, for nodes whose inputs are linked (hexagonal spacing)
                node_context['connected_inputs'] = {
                    str(edge.get('targetHandle', '')).replace('input-', '', 1)
                    for edge in graph_data.get('edges', []) if edge.get('target') == node_id}
                node_name = getattr(type(node), 'NODE_NAME', None) or node_data.get('type') or node_id
                
                try:
                    progress.node(position, len(runnable), node_name)
                    node_started = time.perf_counter()
                    outputs = node.execute(inputs, node_context)
                    timings.append((node_name, time.perf_counter() - node_started, _output_size(outputs)))
                    results[node_id] = outputs
                    log(self.app, f"Executed node {node_id}", 
                        level=LogLevel.DEBUG, module="GRAPH_HANDLER")
                except GenerationCancelled:
                    log(self.app, f"Generate cancelled by the user at node {node_id}",
                        level=LogLevel.INFO, module="GRAPH_HANDLER")
                    return {'success': False, 'cancelled': True,
                            'error': 'Generate was cancelled. The geometry is incomplete; Generate again to rebuild it.'}
                except Exception as e:
                    log(self.app, f"Error executing node {node_id}: {e}", 
                        level=LogLevel.ERROR, module="GRAPH_HANDLER")
                    return {'success': False, 'error': f'{node_name}: {str(e)}', 'failed_node_id': node_id}
            
            log(self.app, f"Graph executed successfully: {len(results)} nodes", 
                level=LogLevel.DEBUG, module="GRAPH_HANDLER")
            log(self.app, _timing_report(timings, time.perf_counter() - generate_started),
                level=LogLevel.INFO, module="GRAPH_HANDLER")
            
            # Create a JSON-safe summary of results for the palette
            safe_results = self._make_results_serializable(results)
            
            return {
                'success': True,
                'message': f'Executed {len(results)} nodes',
                'results': safe_results
            }
        
        finally:
            progress.finish()

            # Always finish editing the BaseFeature
            try:
                if hasattr(self.base_feature, 'finishEdit'):
                    finish_started = time.perf_counter()
                    self.base_feature.finishEdit()
                    log(self.app, f"Finished the Base Feature edit in {time.perf_counter() - finish_started:.2f} s",
                        level=LogLevel.INFO, module="GRAPH_HANDLER")

            except Exception as e:
                log(self.app, f"Warning: Could not finish BaseFeature editing: {e}", 
                    level=LogLevel.WARNING, module="GRAPH_HANDLER")
    
    def _find_connected_nodes(self, graph_data: Dict[str, Any]) -> set:
        """Find all nodes that should execute.

        Two patterns:
        1. SINK CHAINS — walk backward from every terminal sink (any node with no
           outgoing edges that has at least one incoming edge).  This covers
           Materializer, Interpolize, and any future output node without needing
           a hardcoded type list.
        2. STANDALONE — isolated nodes (no edges at all) whose category is known to
           produce useful output on their own (geometry, math, transform).
        """
        nodes = graph_data.get('nodes', {})
        edges = graph_data.get('edges', [])

        # Build adjacency sets: nodes_with_outgoing, nodes_with_incoming
        nodes_with_outgoing = set()
        nodes_with_incoming = set()

        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            if source and target and source in nodes and target in nodes:
                nodes_with_outgoing.add(source)
                nodes_with_incoming.add(target)

        # PATTERN 1: Backward walk from all terminal sinks
        # A sink is any node that has at least one incoming edge but no outgoing edges.
        sink_nodes = [
            node_id for node_id in nodes
            if node_id in nodes_with_incoming and node_id not in nodes_with_outgoing
        ]

        connected_to_sinks = set()
        if sink_nodes:
            log(self.app, f"Found {len(sink_nodes)} terminal sink(s): {sink_nodes}",
                level=LogLevel.DEBUG, module="GRAPH_HANDLER")

            to_visit = sink_nodes.copy()
            while to_visit:
                current = to_visit.pop()
                if current in connected_to_sinks:
                    continue
                connected_to_sinks.add(current)
                for edge in edges:
                    if edge.get('target') == current:
                        source = edge.get('source')
                        if source and source not in connected_to_sinks:
                            to_visit.append(source)

        # PATTERN 2: Standalone isolated nodes (no edges at all) in known categories
        standalone_capable_categories = {'geometry', 'math', 'transform'}
        standalone_nodes = set()

        from ..nodes import NodeRegistry

        for node_id, node_data in nodes.items():
            if node_id in connected_to_sinks:
                continue
            if node_id in nodes_with_outgoing or node_id in nodes_with_incoming:
                continue  # Has edges but wasn't reached — truly disconnected mid-chain

            node_type = node_data.get('type', '')
            # category is not serialized into node_data — resolve from registry
            node_class = NodeRegistry.get_node_class(node_type)
            category = (node_class.NODE_CATEGORY if node_class else '').lower()

            if category in standalone_capable_categories:
                standalone_nodes.add(node_id)
                log(self.app, f"Including standalone {category} node: {node_id} ({node_type})",
                    level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        all_executable_nodes = connected_to_sinks.union(standalone_nodes)

        disconnected_count = len(nodes) - len(all_executable_nodes)
        if disconnected_count > 0:
            disconnected_nodes = [nid for nid in nodes if nid not in all_executable_nodes]
            log(self.app, f"Found {disconnected_count} disconnected nodes (will be skipped): {disconnected_nodes}",
                level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        if connected_to_sinks:
            log(self.app, f"Sink chains: {len(connected_to_sinks)} nodes reachable from {len(sink_nodes)} terminal(s)",
                level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        if standalone_nodes:
            log(self.app, f"Standalone execution: {len(standalone_nodes)} isolated nodes",
                level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        log(self.app, f"Total executable nodes: {len(all_executable_nodes)}",
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        return all_executable_nodes

    def _topological_sort(self, graph_data: Dict[str, Any]) -> List[str]:
        """Return nodes in dependency execution order (connected + standalone nodes)"""
        # Filter to only executable nodes (connected to materializers OR standalone-capable)
        executable_nodes = self._find_connected_nodes(graph_data)
        
        if not executable_nodes:
            log(self.app, "No executable nodes found in graph - nothing to execute", 
                level=LogLevel.WARNING, module="GRAPH_HANDLER")
            return []
        
        # Only process executable nodes
        all_nodes = graph_data.get('nodes', {})
        nodes = {node_id: all_nodes[node_id] for node_id in executable_nodes if node_id in all_nodes}
        edges = graph_data.get('edges', [])
        
        log(self.app, f"Topological sort: processing {len(nodes)} executable nodes (connected + standalone) with {len(edges)} total edges", 
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        # Build dependency graph: node_id -> [nodes it depends on]
        dependencies = {node_id: [] for node_id in nodes.keys()}
        
        # Process edges to build dependencies
        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            
            if source and target and source in nodes and target in nodes:
                # target depends on source - avoid duplicate dependencies
                if source not in dependencies[target]:
                    dependencies[target].append(source)
                else:
                    log(self.app, f"Skipped duplicate dependency: {target} already depends on {source}", 
                        level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        
        log(self.app, f"Computed dependencies for {len(dependencies)} nodes", 
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")

        # Kahn's algorithm for topological sort
        # Find nodes with no dependencies
        no_deps = [node_id for node_id, deps in dependencies.items() if not deps]
        execution_order = []
        remaining_deps = {k: list(v) for k, v in dependencies.items()}  # Copy
        
        while no_deps:
            # Remove a node with no dependencies
            current = no_deps.pop(0)
            execution_order.append(current)
            
            # Remove this node from all dependency lists
            for node_id in remaining_deps:
                if current in remaining_deps[node_id]:
                    remaining_deps[node_id].remove(current)
                    
                    # If this node now has no dependencies, add it to no_deps
                    if not remaining_deps[node_id] and node_id not in execution_order:
                        no_deps.append(node_id)
        
        # Check for cycles
        if len(execution_order) != len(nodes):
            log(self.app, "Dependency cycle detected in graph", 
                level=LogLevel.ERROR, module="GRAPH_HANDLER")
            return None
        
        log(self.app, f"Execution order: {execution_order}", 
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        
        return execution_order
    
    def _resolve_inputs(self, node_id: str, node_data: Dict, graph_data: Dict, results: Dict) -> Dict:
        """Resolve node inputs from connections and previous results"""
        base_inputs = node_data.get('inputs', {})
        resolved_inputs = {}
        
        # Start with base inputs (manual values, defaults)
        for input_name, value in base_inputs.items():
            resolved_inputs[input_name] = value
        
        # Override with connected inputs from backend execution results
        edges = graph_data.get('edges', [])
        for edge in edges:
            if edge.get('target') == node_id:
                source_node_id = edge.get('source')
                source_handle = edge.get('sourceHandle', '').replace('output-', '')
                target_handle = edge.get('targetHandle', '').replace('input-', '')
                
                # Get the source node's execution result
                if source_node_id in results:
                    source_outputs = results[source_node_id]
                    if isinstance(source_outputs, dict) and source_handle in source_outputs:
                        resolved_inputs[target_handle] = source_outputs[source_handle]
                        log(self.app, f"Connected: {source_node_id}.{source_handle} → {node_id}.{target_handle}",
                            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        
        log(self.app, f"Node {node_id} inputs: {sorted(resolved_inputs.keys())}", 
            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        
        return resolved_inputs
    
    def _check_coordinates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check coordinates for a 3D Point node without full execution"""
        node_id = data.get('nodeId')
        inputs = data.get('inputs', {})
        
        if not node_id:
            return {'success': False, 'error': 'nodeId is required'}
        
        # Try to get existing node instance, or create temporary one for coordinate checking
        node = None
        if node_id in self.core.node_instances:
            node = self.core.node_instances[node_id]
            log(self.app, f"Using existing node instance for coordinate check: {node_id}", 
                level=LogLevel.DEBUG, module="GRAPH_HANDLER")
        else:
            # Create temporary node instance for coordinate checking
            # Extract node type from node_id pattern (node_3D_POINT_...)
            if '3D_POINT' in node_id:
                try:
                    from ..nodes import NodeRegistry
                    node_class = NodeRegistry.get_node_class('3D_POINT')
                    if node_class:
                        node = node_class(node_id)
                        log(self.app, f"Created temporary 3D Point node instance for coordinate check: {node_id}", 
                            level=LogLevel.DEBUG, module="GRAPH_HANDLER")
                    else:
                        return {'success': False, 'error': '3D Point node class not found in registry'}
                except Exception as e:
                    log(self.app, f"Error creating temporary node instance: {e}", 
                        level=LogLevel.ERROR, module="GRAPH_HANDLER")
                    return {'success': False, 'error': f'Could not create temporary node instance: {str(e)}'}
            else:
                return {'success': False, 'error': f'Node {node_id} not found (not a 3D Point node)'}
        
        # Only allow coordinate checking on 3D Point nodes
        if getattr(node, 'NODE_TYPE', '') != '3D_POINT':
            return {'success': False, 'error': 'Coordinate checking only supported for 3D Point nodes'}
        
        context = {
            'app': self.app,
            'ui': self.ui,
            'design': self.design,
            'noodle_base_feature': self.base_feature
        }
        
        try:
            # Use the check_coordinates method we added to the 3D Point node
            result = node.check_coordinates(inputs, context)
            return {
                'success': True,
                'nodeId': node_id,
                **result  # Include coordinates and coordinates_changed
            }
        except Exception as e:
            log(self.app, f"Error checking coordinates for node {node_id}: {e}", 
                level=LogLevel.ERROR, module="GRAPH_HANDLER")
            return {'success': False, 'error': str(e)}
    
    def _make_results_serializable(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Strip Fusion API objects from node results to make them JSON-serializable."""
        safe = {}
        for node_id, outputs in results.items():
            try:
                node_safe = {}
                for key, value in outputs.items():
                    # Geometry outputs may include Fusion objects; keep metadata only
                    if isinstance(value, dict) and 'kind' in value and 'id' in value:
                        node_safe[key] = {
                            'kind': value.get('kind'),
                            'id': value.get('id'),
                            'geometry_name': value.get('geometry_name')
                        }
                    else:
                        # Basic types are fine
                        if isinstance(value, (str, int, float, bool, type(None))):
                            node_safe[key] = value
                        elif isinstance(value, dict):
                            # Shallow clean dicts
                            node_safe[key] = self._clean_dict(value)
                        elif isinstance(value, list):
                            node_safe[key] = self._clean_list(value)
                        else:
                            # Skip non-serializable objects
                            continue
                safe[node_id] = node_safe
            except Exception:
                # Fallback to empty outputs for this node
                safe[node_id] = {}
        return safe
    
    def _clean_dict(self, data: dict) -> dict:
        """Recursively clean a dictionary to remove non-serializable objects"""
        clean_dict = {}
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                clean_dict[key] = value
            elif isinstance(value, dict):
                clean_dict[key] = self._clean_dict(value)
            elif isinstance(value, list):
                clean_dict[key] = self._clean_list(value)
            # Skip non-serializable objects
        return clean_dict
    
    def _clean_list(self, data: list) -> list:
        """Clean a list to remove non-serializable objects"""
        clean_list = []
        for item in data:
            if isinstance(item, (str, int, float, bool, type(None))):
                clean_list.append(item)
            elif isinstance(item, dict):
                clean_list.append(self._clean_dict(item))
            elif isinstance(item, list):
                clean_list.append(self._clean_list(item))
            # Skip non-serializable objects
        return clean_list


def _output_size(outputs: Any) -> str:
    """'1600 instances' or '1600 bodies' for a node's output, or '' if neither."""
    for value in (outputs or {}).values() if isinstance(outputs, dict) else []:
        instances = getattr(value, 'instances', None)
        if instances is None and isinstance(value, dict):
            instances = value.get('instances')
        if isinstance(instances, list):
            return f"{len(instances)} instances"
        if isinstance(value, dict) and isinstance(value.get('instance_count'), int):
            return f"{value['instance_count']} bodies"
    return ''


def _timing_report(timings, total_seconds: float) -> str:
    """One readable block: how long each node took during a Generate."""
    lines = [f"Generate ran {len(timings)} nodes in {total_seconds:.2f} s"]
    for name, seconds, size in timings:
        lines.append(f"  {name}: {seconds:.2f} s" + (f" ({size})" if size else ""))
    return "\n".join(lines)
