"""A 3D Point follows exactly the point the user picked. Fusion's selection and
lookup are stand-ins here; following a real drag is checked in Fusion."""
import unittest
from unittest.mock import MagicMock, patch
from tests import fusion_stub
fusion_stub.install()

from backend.nodes.math_point3d import Point3DNode  # noqa: E402


class Point:
    def __init__(self, token, x, y, z):
        self.entityToken = token
        self.worldGeometry = MagicMock(x=x, y=y, z=z)


def app_with(selected=(), design_points=()):
    app = MagicMock()
    app.userInterface.activeSelections.count = len(selected)
    app.userInterface.activeSelections.item = lambda i: MagicMock(entity=selected[i])
    lookup = {p.entityToken: [p] for p in design_points}
    app.activeProduct.findEntityByToken = lambda token: lookup.get(token, [])
    return app


PICKED = {'point_token': 'TOKEN_A', 'entity_token': 'sketch_point_Sketch1_7', 'point_type': 'sketch',
          'x': 1.0, 'y': 2.0, 'z': 3.0}


class PointTrackingTests(unittest.TestCase):
    def setUp(self):
        self.node = Point3DNode('node_3D_POINT_1_2')
        self.cast = patch('adsk.fusion.Design.cast', side_effect=lambda product: product)
        self.cast.start()

    def tearDown(self):
        self.cast.stop()

    def test_the_picked_point_is_found_by_its_token_after_it_moves(self):
        app = app_with(design_points=[Point('TOKEN_A', 5, 6, 7), Point('TOKEN_B', 9, 9, 9)])
        self.assertEqual(self.node.current_coordinates(app, PICKED), (5, 6, 7))

    def test_dragging_the_picked_point_is_followed_through_the_selection(self):
        app = app_with(selected=[Point('TOKEN_A', 4, 4, 4)], design_points=[Point('TOKEN_A', 1, 2, 3)])
        self.assertEqual(self.node.current_coordinates(app, PICKED), (4, 4, 4))

    def test_another_selected_point_never_takes_over(self):
        app = app_with(selected=[Point('TOKEN_B', 9, 9, 9)], design_points=[Point('TOKEN_A', 5, 6, 7)])
        self.assertEqual(self.node.current_coordinates(app, PICKED), (5, 6, 7))

    def test_a_deleted_point_is_unknown_rather_than_a_guess(self):
        app = app_with(design_points=[Point('TOKEN_B', 9, 9, 9)])
        self.assertIsNone(self.node.current_coordinates(app, PICKED))

    def test_a_poll_reports_a_change_only_when_the_point_moved(self):
        moved = self.node.check_coordinates({'point': PICKED}, {'app': app_with(design_points=[Point('TOKEN_A', 5, 6, 7)])})
        self.assertTrue(moved['coordinates_changed'])
        self.assertEqual(moved['coordinates'], {'x': 5, 'y': 6, 'z': 7})
        still = self.node.check_coordinates({'point': PICKED}, {'app': app_with(design_points=[Point('TOKEN_A', 1, 2, 3)])})
        self.assertFalse(still['coordinates_changed'])

    def test_a_point_that_cannot_be_found_never_reports_a_change(self):
        gone = self.node.check_coordinates({'point': PICKED}, {'app': app_with()})
        self.assertFalse(gone['coordinates_changed'], 'must not snap the point back to where it was picked')


if __name__ == '__main__':
    unittest.main()
