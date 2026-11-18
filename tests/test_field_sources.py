"""Falloff shapes: where an instance sits in the field, before the curve shapes the fade."""

import json
import unittest

from backend.utilities import field_sources as fs
from backend.utilities.field_curve import preset_curve, sphere_strength
from backend.utilities.modifier_utils import evaluate_modifier

LINEAR = json.dumps(preset_curve('Linear'))   # strength = 1 - t, so strength reads back t


def t_at(params, point, center='position'):
    return 1.0 - fs.field_strength({'curve': LINEAR, **params}, point, center)


class Sphere(unittest.TestCase):

    def test_matches_the_sphere_falloff_it_replaces(self):
        smooth = json.dumps(preset_curve('Smooth'))
        for d in (0, 1, 3, 6, 9, 12):
            params = {'shape': 'sphere', 'position': {'x': 1, 'y': 2, 'z': 3}, 'radius': 10, 'inner_radius': 2, 'curve': smooth}
            self.assertAlmostEqual(fs.field_strength(params, (1 + d, 2, 3), 'position'),
                                   sphere_strength(d, 10, 2, smooth), places=12)

    def test_no_shape_means_sphere(self):
        self.assertAlmostEqual(t_at({'radius': 10}, (5, 0, 0)), 0.5, places=3)


class Linear(unittest.TestCase):
    params = {'shape': 'linear', 'start': {'x': 0, 'y': 0, 'z': 0}, 'end': {'x': 0, 'y': 20, 'z': 0}}

    def test_t_runs_from_start_to_end_along_the_line(self):
        self.assertAlmostEqual(t_at(self.params, (0, 5, 0)), 0.25, places=3)
        self.assertAlmostEqual(t_at(self.params, (7, 15, -3)), 0.75, places=3)   # off the line counts by projection

    def test_holds_before_the_start_and_past_the_end(self):
        self.assertAlmostEqual(t_at(self.params, (0, -50, 0)), 0.0, places=6)
        self.assertAlmostEqual(t_at(self.params, (0, 99, 0)), 1.0, places=6)

    def test_start_and_end_in_the_same_place_is_reported(self):
        params = {**self.params, 'end': {'x': 0, 'y': 0, 'z': 0}}
        self.assertTrue(fs.shape_problems(params))


class Box(unittest.TestCase):
    params = {'shape': 'box', 'position': {'x': 0, 'y': 0, 'z': 0}, 'radius': 10, 'inner_radius': 2}

    def test_distance_is_measured_square(self):
        self.assertAlmostEqual(t_at(self.params, (1, 1.5, -1)), 0.0, places=6)     # inside the core
        self.assertAlmostEqual(t_at(self.params, (6, 0, 0)), 0.5, places=3)
        self.assertAlmostEqual(t_at(self.params, (6, 5, -6)), 0.5, places=3)       # same box contour
        self.assertAlmostEqual(t_at(self.params, (40, 0, 0)), 1.0, places=6)

    def test_scale_stretches_the_box_along_its_axes(self):
        long = {**self.params, 'scale': {'x': 3, 'y': 1, 'z': 1}}
        self.assertAlmostEqual(t_at(long, (18, 0, 0)), 0.5, places=3)               # 6 in local units
        self.assertAlmostEqual(t_at(long, (0, 6, 0)), 0.5, places=3)

    def test_the_x_axis_turns_the_stretched_box(self):
        turned = {**self.params, 'scale': {'x': 3, 'y': 1, 'z': 1}, 'direction': {'x': 0, 'y': 1, 'z': 0}}
        self.assertAlmostEqual(t_at(turned, (0, 18, 0)), 0.5, places=3)
        self.assertAlmostEqual(t_at(turned, (6, 0, 0)), 0.5, places=3)

    def test_axes_stay_square_when_up_leans_or_matches_direction(self):
        for up in ({'x': 1, 'y': 1, 'z': 0}, {'x': 1, 'y': 0, 'z': 0}, {'x': 0, 'y': 0, 'z': 0}):
            x, y, z = fs.box_axes({'x': 1, 'y': 0, 'z': 0}, up)
            for a, b in ((x, y), (y, z), (z, x)):
                self.assertAlmostEqual(sum(p * q for p, q in zip(a, b)), 0.0, places=9)


class Ellipsoid(unittest.TestCase):

    def test_scale_y_stretches_along_the_y_axis(self):
        # The reported case: Scale 1, 2, 1 with the Y Axis on world Y stretches along world Y
        params = {'shape': 'sphere', 'radius': 10, 'scale': {'x': 1, 'y': 2, 'z': 1}, 'up': {'x': 0, 'y': 1, 'z': 0}}
        self.assertAlmostEqual(t_at(params, (0, 10, 0)), 0.5, places=3)
        self.assertAlmostEqual(t_at(params, (5, 0, 0)), 0.5, places=3)
        self.assertAlmostEqual(t_at(params, (0, 0, 5)), 0.5, places=3)
        # And turning the Y Axis to world Z carries the stretch with it
        params['up'] = {'x': 0, 'y': 0, 'z': 1}
        self.assertAlmostEqual(t_at(params, (0, 0, 10)), 0.5, places=3)

    def test_default_axes_are_the_world_axes(self):
        self.assertEqual(fs.box_axes(None, None), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))

    def test_scale_makes_a_sphere_an_ellipsoid(self):
        params = {'shape': 'sphere', 'radius': 10, 'scale': {'x': 1, 'y': 1, 'z': 4}}
        self.assertAlmostEqual(t_at(params, (5, 0, 0)), 0.5, places=3)
        self.assertAlmostEqual(t_at(params, (0, 0, 20)), 0.5, places=3)

    def test_a_uniform_sphere_ignores_direction(self):
        a = {'shape': 'sphere', 'radius': 10}
        b = {**a, 'direction': {'x': 0.3, 'y': 0.9, 'z': 0.1}, 'up': {'x': 1, 'y': 0, 'z': 0}}
        for p in ((3, 4, 0), (0, -7, 2), (6, 6, 6)):
            self.assertAlmostEqual(t_at(a, p), t_at(b, p), places=9)

    def test_zero_scale_is_reported(self):
        self.assertTrue(fs.shape_problems({'shape': 'sphere', 'radius': 5, 'scale': {'x': 1, 'y': 0, 'z': 1}}))


class Validation(unittest.TestCase):

    def test_only_the_chosen_shape_is_checked(self):
        # A sphere's inner radius is irrelevant to a Linear falloff
        self.assertEqual(fs.shape_problems({'shape': 'linear', 'inner_radius': 99, 'radius': 1}), [])
        self.assertTrue(fs.shape_problems({'shape': 'sphere', 'inner_radius': 99, 'radius': 1}))
        self.assertTrue(fs.shape_problems({'shape': 'box', 'inner_radius': 99, 'radius': 1}))

    def test_an_unknown_shape_is_reported(self):
        self.assertTrue(fs.shape_problems({'shape': 'torus'}))


class Modifier(unittest.TestCase):

    def test_the_falloff_modifier_uses_the_same_shapes(self):
        from backend.nodes.modifier_falloff import FalloffModifierNode
        node = FalloffModifierNode.__new__(FalloffModifierNode)
        config = node.execute({'shape': 'linear', 'start': {'x': 0, 'y': 0, 'z': 0}, 'end': {'x': 10, 'y': 0, 'z': 0},
                               'curve': LINEAR, 'amplitude': 2.0}, {})['modifier']
        value = evaluate_modifier(config, {'surface_point': {'x': 2.5, 'y': 0, 'z': 0}})
        self.assertAlmostEqual(value, 2.0 * 0.75, places=3)


if __name__ == '__main__':
    unittest.main()


class Outlines(unittest.TestCase):
    """The faint guides the visualizer draws for each shape."""

    def test_a_sphere_is_an_ellipsoid_traced_from_the_camera_plus_a_dashed_inner_one(self):
        out = fs.field_outline({'shape': 'sphere', 'position': {'x': 1, 'y': 2, 'z': 3}, 'radius': 10, 'inner_radius': 4,
                                'scale': {'x': 2, 'y': 1, 'z': 1}}, 'position')
        self.assertEqual([(e[0], e[2], e[3]) for e in out['ellipsoids']],
                         [((1, 2, 3), (20.0, 10.0, 10.0), False), ((1, 2, 3), (8.0, 4.0, 4.0), True)])

    def test_linear_is_an_arrow_with_a_ring_at_each_end(self):
        out = fs.field_outline({'shape': 'linear', 'start': {'x': 0, 'y': 0, 'z': 0}, 'end': {'x': 0, 'y': 20, 'z': 0}},
                               'position', points=[(6, 10, 0)])
        self.assertEqual(out['solid'][0], [(0, 0, 0), (0, 20, 0)])
        self.assertEqual(len(out['dashed']), 2)
        ring = out['dashed'][0]
        for p in ring:   # Each ring sits across the line, framing the instances (6 cm off the line)
            self.assertAlmostEqual(p[1], 0.0, places=9)
            self.assertAlmostEqual((p[0] ** 2 + p[2] ** 2) ** 0.5, 6.0, places=6)

    def test_a_box_is_its_outer_edges_plus_a_dashed_inner_box(self):
        out = fs.field_outline({'shape': 'box', 'position': {'x': 0, 'y': 0, 'z': 0}, 'radius': 5, 'inner_radius': 2}, 'position')
        self.assertEqual(len(out['solid']), 12)
        self.assertEqual(len(out['dashed']), 12)
        self.assertEqual(max(abs(c) for edge in out['solid'] for p in edge for c in p), 5.0)
        self.assertEqual(max(abs(c) for edge in out['dashed'] for p in edge for c in p), 2.0)

    def test_the_silhouette_touches_the_ellipsoid_where_the_view_grazes_it(self):
        axes = fs.box_axes({'x': 1, 'y': 1, 'z': 0}, {'x': 0, 'y': 0, 'z': 1})
        center, semi = (3.0, -2.0, 1.0), (8.0, 3.0, 5.0)
        local = lambda p: [sum((p[k] - center[k]) * axes[i][k] for k in range(3)) / semi[i] for i in range(3)]
        normal = lambda q: [sum(q[i] / semi[i] * axes[i][k] for i in range(3)) for k in range(3)]
        eye = (60.0, 25.0, 40.0)
        for view in ({'eye': eye}, {'view': (-1.0, -0.5, -0.8)}):
            rim = fs.ellipsoid_rim(center, axes, semi, **view)
            self.assertEqual(len(rim), 97)
            for p in rim:
                q = local(p)
                self.assertAlmostEqual(sum(c * c for c in q), 1.0, places=9)        # on the ellipsoid
                sight = [p[k] - eye[k] for k in range(3)] if 'eye' in view else list(view['view'])
                self.assertAlmostEqual(sum(a * b for a, b in zip(normal(q), sight)), 0.0, places=6)  # grazing

    def test_no_silhouette_from_inside(self):
        axes = fs.box_axes(None, None)
        self.assertEqual(fs.ellipsoid_rim((0, 0, 0), axes, (5, 5, 5), eye=(1, 1, 1)), [])

    def test_the_visualizer_outlines_every_falloff_the_preview_ran(self):
        from tests import fusion_stub
        fusion_stub.install()
        from backend.handlers.graph_handler import GraphHandler
        nodes = [{'id': 'f', 'type': 'Falloff_Effector'}, {'id': 'm', 'type': 'Modifier_Falloff'}, {'id': 'u', 'type': 'Uniform_Effector'}]
        result = {'inputs': {'f': {'shape': 'sphere', 'radius': 5}, 'm': {'shape': 'box'}, 'u': {}}}
        outlines = GraphHandler._falloff_outlines(nodes, result, [])
        self.assertEqual(len(outlines), 2)


class FalloffModifierPassesEveryShapePortTests(unittest.TestCase):
    def test_every_shape_port_reaches_the_evaluator(self):
        from tests import fusion_stub
        from backend.utilities.field_sources import shape_ports
        node = fusion_stub.all_node_classes()['modifier_falloff']('n')
        from backend.contracts import PortType
        from backend.utilities.field_curve import default_curve_json
        sample = {PortType.VECTOR3: {'x': 1.0, 'y': 2.0, 'z': 3.0}, PortType.FLOAT: 4.0}
        values = {port.name: sample.get(port.port_type) for port in shape_ports("center")}
        values.update(shape='sphere', radius=10.0, inner_radius=2.0, curve=default_curve_json('Smooth'))
        self.assertNotIn(None, values.values(), 'a shape port of a type this test does not fill')
        config = node.execute(values, {})['modifier']
        for name in values:
            with self.subTest(port=name):
                self.assertEqual(config.get(name), values[name])
