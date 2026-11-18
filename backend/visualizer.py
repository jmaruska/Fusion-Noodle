"""
Effector visualizer: colored dots in the Fusion viewport, one per instance,
showing how strongly an effector acts on each instance.

White is fully affected, then yellow, orange, red, and black is unaffected.

Each dot is a small disk that always faces the camera, stays the same size on
screen at any zoom, and draws in front of bodies, so a dot on a curved face is
never half hidden by it. Custom graphics add nothing to Fusion's undo history.
"""

import math
import time
from typing import Any, Dict, Iterable, List, Sequence, Tuple

STEPS = 32
GROUP_ID = 'Noodle_Visualizer'

# Strength 0..1 -> color. Black (unaffected) to white (fully affected).
RAMP: Sequence[Tuple[float, Tuple[int, int, int]]] = (
    (0.00, (0, 0, 0)),
    (0.30, (205, 30, 20)),
    (0.60, (245, 140, 25)),
    (0.82, (250, 222, 50)),
    (1.00, (255, 255, 255)),
)


def ramp_color(t: float) -> Tuple[int, int, int]:
    """The ramp color for a strength between 0 and 1."""
    t = min(1.0, max(0.0, float(t)))
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return RAMP[-1][1]


def step_for(strength: float, steps: int = STEPS) -> int:
    """Which color step a strength falls in. Sign is ignored: -1 is as affected as +1."""
    magnitude = min(1.0, abs(float(strength)))
    return min(steps - 1, int(round(magnitude * (steps - 1))))


def step_color(step: int, steps: int = STEPS) -> Tuple[int, int, int]:
    return ramp_color(step / (steps - 1))


def group_by_step(points: Iterable[Tuple[float, float, float, float]],
                  steps: int = STEPS) -> Dict[int, List[float]]:
    """Sort (x, y, z, strength) points into {step: [x, y, z, x, y, z, ...]}."""
    grouped: Dict[int, List[float]] = {}
    for x, y, z, strength in points:
        grouped.setdefault(step_for(strength, steps), []).extend((float(x), float(y), float(z)))
    return grouped


STRENGTHS_KEY = 'effector_strengths'  # Set on each instance by effectors (nodes/effector_base.py)


def _instances_of(collection: Any) -> list:
    if collection is None:
        return []
    if isinstance(collection, dict):
        return list(collection.get('instances') or [])
    return list(getattr(collection, 'instances', None) or [])


def _metadata_of(instance: Any) -> dict:
    metadata = instance.get('metadata') if isinstance(instance, dict) else getattr(instance, 'metadata', None)
    return metadata or {}


def _position_of(instance: Any) -> Tuple[float, float, float]:
    transform = instance.get('transform') if isinstance(instance, dict) else getattr(instance, 'transform', None)
    if transform is None:
        return (0.0, 0.0, 0.0)
    read = (lambda k: transform.get(k, 0.0)) if isinstance(transform, dict) else (lambda k: getattr(transform, k, 0.0))
    return (float(read('tx') or 0.0), float(read('ty') or 0.0), float(read('tz') or 0.0))


def collect_dots(outputs: Dict[str, Dict[str, Any]], visualized: Sequence[str]) -> List[Tuple[float, float, float, float]]:
    """Turn effector results into dots: (x, y, z, strength 0..1) per instance.

    outputs:    {node_id: {'collection': ...}} from preview_collections
    visualized: ids of the effectors whose eye is on

    A dot sits where the instance ends up, so a Move effector displaces its dots.
    Its color is the combined strength of every visualized effector the instance
    passed through. Sign is ignored. A single effector shows its true strength;
    when effectors combine to more than 100%, everything is scaled so the most
    affected instance is white.

    When one visualized effector feeds another, only the downstream one is drawn:
    its instances already carry the upstream strength and position.
    """
    wanted = [node_id for node_id in visualized if node_id in outputs]
    instances_by_node = {node_id: _instances_of(outputs[node_id].get('collection')) for node_id in wanted}

    def carried(node_id):
        """Visualized effectors whose strength this effector's instances carry."""
        instances = instances_by_node[node_id]
        return set(_metadata_of(instances[0]).get(STRENGTHS_KEY) or {}) if instances else set()

    superseded = {upstream for node_id in wanted for upstream in carried(node_id)
                  if upstream != node_id and upstream in instances_by_node}

    raw = []
    for node_id in wanted:
        if node_id in superseded:
            continue
        for instance in instances_by_node[node_id]:
            strengths = _metadata_of(instance).get(STRENGTHS_KEY) or {}
            total = sum(abs(float(value)) for key, value in strengths.items() if key in visualized)
            raw.append((*_position_of(instance), total))

    scale = max([1.0] + [total for *_xyz, total in raw])
    return [(x, y, z, total / scale) for x, y, z, total in raw]


DISK_PIXEL_RADIUS = 4      # Dot radius on screen, in pixels
DISK_SEGMENTS = 12
# Opacity just under 1 with the show-through effect is what puts the dots in
# front of bodies: Fusion sorts them with transparent things and draws them last.
SHOW_THROUGH_OPACITY = 0.95

# Falloff outlines: thin, faint, in the curve color, drawn in front so a body never hides them
OUTLINE_COLOR = (50, 188, 173)
OUTLINE_OPACITY = 0.35
INNER_OUTLINE_OPACITY = 0.18   # Inner outlines: fainter as well as dashed, in case dashes don't show
OUTLINE_WEIGHT = 1.0
OUTLINE_GROUP_ID = GROUP_ID + '_Outline'   # Starts with GROUP_ID, so clear() removes it too


def disk_geometry():
    """A unit disk in the XY plane at the origin: flat coords, triangle indices, normals."""
    coords = [0.0, 0.0, 0.0]
    for i in range(DISK_SEGMENTS):
        angle = 2 * math.pi * i / DISK_SEGMENTS
        coords += [math.cos(angle), math.sin(angle), 0.0]
    indices = []
    for i in range(DISK_SEGMENTS):
        indices += [0, 1 + i, 1 + (i + 1) % DISK_SEGMENTS]
    normals = [0.0, 0.0, 1.0] * (DISK_SEGMENTS + 1)
    return coords, indices, normals


class VisualizerRenderer:
    """Draws and removes the dots. Only ever touches graphics it created."""

    def __init__(self, app: Any):
        self.app = app

    def _root(self):
        import adsk.fusion  # type: ignore
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        return design.rootComponent if design else None

    def clear_everywhere(self) -> int:
        """Remove the dots from every open document, not just the active one.
        Dots stay in the document they were drawn in, so after a document switch
        they may be somewhere other than the active design."""
        import adsk.fusion  # type: ignore
        removed = 0
        documents = self.app.documents
        for i in range(documents.count):
            document = adsk.fusion.FusionDocument.cast(documents.item(i))
            design = document.design if document else None
            if design:
                removed += self._clear_root(design.rootComponent)
        if removed:
            self.app.activeViewport.refresh()
        return removed

    def clear(self) -> int:
        """Remove every visualizer group from the active design. Returns how many."""
        removed = self._clear_root(self._root())
        if removed:
            self.app.activeViewport.refresh()
        return removed

    def _clear_root(self, root) -> int:
        if not root:
            return 0
        groups = root.customGraphicsGroups
        removed = 0
        for i in range(groups.count - 1, -1, -1):
            group = groups.item(i)
            if group and group.isValid and str(group.id).startswith(GROUP_ID):
                group.deleteMe()
                removed += 1
        return removed

    def draw(self, points: Iterable[Tuple[float, float, float, float]], outlines: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
        """Replace the dots with one per (x, y, z, strength), and draw the falloff outlines
        (see field_sources.field_outline). Coordinates are in cm."""
        import adsk.core  # type: ignore
        import adsk.fusion  # type: ignore
        started = time.perf_counter()
        root = self._root()
        if not root:
            return {'points': 0, 'seconds': 0.0}

        self.clear()
        group = root.customGraphicsGroups.add()
        group.id = GROUP_ID

        coords, indices, normals = disk_geometry()
        disk = adsk.fusion.CustomGraphicsCoordinates.create(coords)
        origin = adsk.core.Point3D.create(0, 0, 0)
        screen = adsk.fusion.CustomGraphicsBillBoardStyles.ScreenBillBoardStyle

        count = 0
        for step, flat in sorted(group_by_step(points).items()):
            # One color effect per step, shared by every dot of that color
            color = adsk.fusion.CustomGraphicsShowThroughColorEffect.create(
                adsk.core.Color.create(*step_color(step), 255), SHOW_THROUGH_OPACITY)
            for p in range(0, len(flat), 3):
                x, y, z = flat[p], flat[p + 1], flat[p + 2]
                mesh = group.addMesh(disk, indices, normals, indices)
                mesh.isSelectable = False
                # Pixel-sized and camera-facing, anchored at the instance. The view
                # scale has to be set before the transform.
                mesh.viewScale = adsk.fusion.CustomGraphicsViewScale.create(DISK_PIXEL_RADIUS, origin)
                matrix = adsk.core.Matrix3D.create()
                matrix.translation = adsk.core.Vector3D.create(x, y, z)
                mesh.transform = matrix
                billboard = adsk.fusion.CustomGraphicsBillBoard.create(adsk.core.Point3D.create(x, y, z))
                billboard.billBoardStyle = screen
                mesh.billBoarding = billboard
                mesh.color = color
                count += 1

        self.draw_outlines(outlines, refresh=False)
        self.app.activeViewport.refresh()
        return {'points': count, 'seconds': round(time.perf_counter() - started, 3)}

    def _lines(self, group, polylines, dashed: bool):
        """Faint lines in front of bodies, solid or dashed."""
        import adsk.core  # type: ignore
        import adsk.fusion  # type: ignore
        coords, indices = [], []
        for line in polylines:
            base = len(coords) // 3
            for p in line:
                coords.extend(p)
            for i in range(len(line) - 1):
                indices += [base + i, base + i + 1]
        if not indices:
            return None
        lines = group.addLines(adsk.fusion.CustomGraphicsCoordinates.create(coords), indices, False)
        lines.isSelectable = False
        lines.weight = OUTLINE_WEIGHT
        lines.color = adsk.fusion.CustomGraphicsShowThroughColorEffect.create(
            adsk.core.Color.create(*OUTLINE_COLOR, 255), INNER_OUTLINE_OPACITY if dashed else OUTLINE_OPACITY)
        if dashed:
            pattern = getattr(adsk.fusion.LineStylePatterns, 'dashedLineStylePattern', None)
            if pattern is not None:
                lines.lineStylePattern = pattern
        return lines

    def draw_outlines(self, outlines: Sequence[Dict[str, Any]], refresh: bool = True) -> None:
        """Replace just the falloff outlines. Called with the dots, and again whenever the camera
        moves, because an ellipsoid's outline depends on where it is seen from."""
        root = self._root()
        if not root:
            return
        groups = root.customGraphicsGroups
        for i in range(groups.count - 1, -1, -1):
            group = groups.item(i)
            if group and group.isValid and str(group.id) == OUTLINE_GROUP_ID:
                group.deleteMe()
        if not outlines:
            return
        group = groups.add()
        group.id = OUTLINE_GROUP_ID
        view = self._camera()
        for outline in outlines:
            try:
                self._draw_outline(group, outline, view)
            except Exception:
                pass  # A guide that can't be drawn must never cost the dots
        if refresh:
            self.app.activeViewport.refresh()

    def _camera(self) -> Dict[str, Any]:
        """Where the active view looks from: the eye for a perspective camera, the viewing
        direction for an orthographic one."""
        import adsk.core  # type: ignore
        try:
            camera = self.app.activeViewport.camera
            eye = (float(camera.eye.x), float(camera.eye.y), float(camera.eye.z))
            target = (float(camera.target.x), float(camera.target.y), float(camera.target.z))
            if camera.cameraType == adsk.core.CameraTypes.OrthographicCameraType:
                view = tuple(t - e for t, e in zip(target, eye))
                if sum(c * c for c in view) > 1e-18:
                    return {'view': view}
                return {}
            return {'eye': eye}
        except Exception:
            return {}

    def _draw_outline(self, group, outline: Dict[str, Any], view: Dict[str, Any] = None):
        from .utilities.field_sources import ellipsoid_rim
        view = view or {}
        self._lines(group, outline.get('solid') or [], False)
        self._lines(group, outline.get('dashed') or [], True)
        for center, axes, semi, dashed in outline.get('ellipsoids') or []:
            rim = ellipsoid_rim(center, axes, semi, eye=view.get('eye'), view=view.get('view'))
            if rim:
                self._lines(group, [rim], dashed)
