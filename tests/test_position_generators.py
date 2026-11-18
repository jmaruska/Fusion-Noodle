import math
import unittest
from tests import fusion_stub

NODES = fusion_stub.all_node_classes()


class Array2DGridPatternTests(unittest.TestCase):
    def setUp(self):
        self.node = NODES['array_2d_grid']('grid_test')

    def positions(self, array_type, cx=3, cy=3, sx=5.0, sy=4.0):
        return self.node._generate_pattern_positions(array_type, cx, cy, sx, sy)

    def test_grid_count_and_centering(self):
        pts = self.positions('grid', 4, 3)
        self.assertEqual(len(pts), 12)
        self.assertAlmostEqual(sum(p[0] for p in pts), 0.0)
        self.assertAlmostEqual(sum(p[1] for p in pts), 0.0)
        self.assertAlmostEqual(pts[1][0] - pts[0][0], 5.0)

    def test_stagger_offsets_alternate_rows_by_half_spacing(self):
        grid, stagger = self.positions('grid'), self.positions('stagger')
        self.assertEqual(len(stagger), 9)
        for i, (g, s) in enumerate(zip(grid, stagger)):
            row = i // 3
            self.assertAlmostEqual(s[0] - g[0], 2.5 if row % 2 else 0.0)
            self.assertAlmostEqual(s[1], g[1])

    def test_hexagonal_rows_form_equilateral_triangles(self):
        pts = self.positions('hexagonal', 3, 2, sx=5.0, sy=99.0)  # spacing_y is ignored
        a, b = pts[0], pts[3]  # first point of row 0 and of row 1
        self.assertAlmostEqual(math.dist(a, b), 5.0, places=2)

    def test_types_produce_different_layouts(self):
        self.assertNotEqual(self.positions('grid'), self.positions('stagger'))
        self.assertNotEqual(self.positions('stagger'), self.positions('hexagonal'))



class Array2DGridInstanceTests(unittest.TestCase):
    """The grid copies every incoming instance, as the surface arrays do."""

    def run_grid(self, instances, **inputs):
        from backend.contracts import CollectionSpec, GeometryEnvelope
        node = NODES['array_2d_grid']('grid_test')
        collection = CollectionSpec(
            collection_type='geometry_collection', collection_id='in',
            instances=instances,
            source_geometries=[GeometryEnvelope(id='g1', kind='body', geometry=None, geometry_name='Box'),
                               GeometryEnvelope(id='g2', kind='body', geometry=None, geometry_name='Ball')])
        values = {'collection': collection, 'count_x': 2, 'count_y': 3, 'spacing_x': 10.0,
                  'spacing_y': 10.0, 'array_type': 'grid', 'normal': {'x': 0.0, 'y': 0.0, 'z': 1.0}}
        values.update(inputs)
        return node.execute(values, {'app': None, 'node_id': 'grid_test'})['collection']

    def instance(self, iid, geometry_id, scale):
        from backend.contracts import CollectionInstanceSpec, NoodleAttributes
        return CollectionInstanceSpec(instance_id=iid, source_geometry_id=geometry_id,
                                      transform=NoodleAttributes(sx=scale, sy=scale, sz=scale), metadata={})

    def test_each_incoming_instance_fills_the_grid_and_keeps_its_scale(self):
        out = self.run_grid([self.instance('a', 'g1', 2.0), self.instance('b', 'g2', 0.5)])
        self.assertEqual(len(out.instances), 12)
        first, second = out.instances[:6], out.instances[6:]
        self.assertTrue(all(i.source_geometry_id == 'g1' and i.transform.sx == 2.0 for i in first))
        self.assertTrue(all(i.source_geometry_id == 'g2' and i.transform.sx == 0.5 for i in second))

    def test_grid_indices_and_positions(self):
        out = self.run_grid([self.instance('a', 'g1', 1.0)])
        self.assertEqual([(i.metadata['grid_u_index'], i.metadata['grid_v_index']) for i in out.instances],
                         [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)])
        # Centered on the origin, in the plane normal to Z
        self.assertAlmostEqual(sum(i.transform.tx for i in out.instances), 0.0)
        self.assertAlmostEqual(sum(i.transform.ty for i in out.instances), 0.0)
        self.assertTrue(all(abs(i.transform.tz) < 1e-9 for i in out.instances))
        spread = {round(i.transform.tx, 6) for i in out.instances} | {round(i.transform.ty, 6) for i in out.instances}
        self.assertIn(5.0, {abs(v) for v in spread})

    def test_a_tilted_normal_keeps_points_in_its_plane(self):
        out = self.run_grid([self.instance('a', 'g1', 1.0)], normal={'x': 1.0, 'y': 0.0, 'z': 1.0})
        for i in out.instances:
            self.assertAlmostEqual(i.transform.tx + i.transform.tz, 0.0)  # Perpendicular to (1, 0, 1)


if __name__ == '__main__':
    unittest.main()
