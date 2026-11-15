"""Path 9, the arm camera only, step 3 (tracks/look/ARM_ONLY_DESIGN.md, "Step 3
as it will be built"): every render after the first image is the arm camera
where the arm stands, a check judges only what that image holds wholly, and a
body first seen after the first image casts its shadow from the camera that
saw it.  DIRECT worlds of our own (boxel_env.default_scene), no episode, no
planner; a stand-in env and a synthetic view where only a view matters.

1. After the first image every env render is the wrist camera at the arm's
   forward kinematics, and the shadow code casts from there (FACTS case 1).
2. The look manager's rule (2026-11-14, execution.frame_judgement): a check
   after a move judges a body for presence (re-pose, disturbed) when its
   detection lies wholly in the frame, and for absence (the lost check on its
   believed region) when its believed box does and its detection is missing
   or cut; a body with neither keeps its belief, its support relation
   included (case 2, round 2's R1 to R3).  A check's image registers only
   bodies whose detection it holds wholly and refuses one the frame cuts.
   The release check, a lost body's fragments and the pick's re-aim follow
   the same rule.
3. A body first seen by a check's image, and one first seen by a look's
   render, casts from the camera of that image (case 3).
4. With --eye fixed no arm-camera path runs (case 6).
5. The completeness test's render rule (tools/eye_render_audit.py, case 7).
6. view_pose and in_frame.
"""
import ast
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pybullet as p
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import arm_eye  # noqa: E402
import execution  # noqa: E402
import observe_views  # noqa: E402
import perception  # noqa: E402
import robot_utils  # noqa: E402
from belief import BeliefState  # noqa: E402
from boxel_data import BoxelData, BoxelRegistry, BoxelType  # noqa: E402
from boxel_env import BoxelTestEnv  # noqa: E402
from test_eye_switch import BASE_CAMERA, START, THEIR_HOME  # noqa: E402

# A target name no body carries, so every body registered here casts shadows.
NO_TARGET = 'no_target'
# Turns (rad) of the arm's first joint tried in order for a configuration away
# from the start one (REST_POSES): the first that touches no body and that the
# test accepts is taken.
TURNS = (0.6, -0.6, 0.9, -0.9, 0.3, -0.3)
# A synthetic arm camera 1 m above the origin looking straight down (project's
# convention: +x image right, +y image down, +z the optical axis), for the
# checks that need only a view matrix; a 4 cm box under it, and a shift that
# takes a box out of its image.
DOWN = np.array([[1.0, 0.0, 0.0, 0.0],
                 [0.0, -1.0, 0.0, 0.0],
                 [0.0, 0.0, -1.0, 1.0],
                 [0.0, 0.0, 0.0, 1.0]])
HERE = (np.array([-0.02, -0.02, 0.0]), np.array([0.02, 0.02, 0.04]))
SHIFT = np.array([3.0, 0.0, 0.0])
# A synthetic detection's pixel count: well over the detection minimum.
PIXELS = 10 * perception.DETECTION_MIN_PIXELS


@pytest.fixture
def env():
    e = BoxelTestEnv(gui=False)
    yield e
    e.close()


def _arm_mode(env, joints=START):
    """main()'s steps with --eye arm up to the first image: the arm at the
    start configuration, the settle, the arm camera there, the follow."""
    assert arm_eye.place_arm(env, joints)
    env.step_simulation(50)
    env.update_object_positions()
    cam = arm_eye.use_start_view(env)
    arm_eye.follow_arm(env)
    return cam


def _first_scan(env):
    """The first image's boxels as Phase 3 registers them: the registry, the
    shadow ids and the object ids (the census list)."""
    obs = env.get_camera_observation()
    reg = BoxelRegistry()
    for b in obs.boxels:
        reg.add_boxel(b)
    shadows = [b.id for b in obs.boxels if b.boxel_type == BoxelType.SHADOW]
    objects = [b.id for b in obs.boxels if b.boxel_type == BoxelType.OBJECT]
    return reg, shadows, objects


def _move_arm(env, accept=lambda: True):
    """Test control: the arm (both clients, arm_eye.place_arm, refused on a
    touch) at REST_POSES with its first joint turned by the first of TURNS
    that is free and that ``accept`` takes.  Returns the turn."""
    for turn in TURNS:
        q = list(START)
        q[0] += turn
        try:
            arm_eye.place_arm(env, q)
        except ValueError:
            continue
        if accept():
            return turn
    raise AssertionError(f"none of the turns {TURNS} gives a free configuration "
                         f"this test accepts")


def _render(env):
    dets, _, buf, seg = env.detect_objects()
    return dets, (env._depth_buffer_to_meters(buf), seg,
                  *env._view_and_projection_matrices())


def _box(bd):
    return (np.asarray(bd.min_corner, dtype=float), np.asarray(bd.max_corner, dtype=float))


def _corners(boxels):
    return sorted(tuple(np.round(np.concatenate(_box(b)), 4)) for b in boxels)


def _forget(reg, shadows, objects, names):
    """Test control: bodies taken out of the belief, fragments included."""
    for name in names:
        bd = reg.get_boxel(name)
        if bd is None or bd.boxel_type != BoxelType.OBJECT:
            continue
        for sid in list(bd.shadow_boxel_ids):
            reg.remove_boxel(sid)
            if sid in shadows:
                shadows.remove(sid)
        reg.remove_boxel(name)
        if name in objects:
            objects.remove(name)


def _spy_casts(env, monkeypatch):
    """Every shadow cast from here on: (body, the calculator's camera position
    at the cast, the obstacles).  Returns (calls, the real cast)."""
    calc = env.shadow_calculator
    real = calc.calculate_shadow_boxel
    calls = []

    def cast(obj_boxel, obstacles, physics_client=None):
        calls.append((obj_boxel.id, np.array(calc.camera_position, dtype=float),
                      list(obstacles)))
        return real(obj_boxel, obstacles, physics_client=physics_client)

    monkeypatch.setattr(calc, 'calculate_shadow_boxel', cast)
    return calls, real


def _register(env, reg, shadows, objects, dets, render, camera='eye'):
    return execution.register_new_detections(
        env=env, registry=reg, belief=BeliefState(list(shadows), NO_TARGET), viz=None,
        detections=dets, target_name=NO_TARGET, shadows=shadows, occluders=objects,
        shadow_occluder_map={}, boxel_centers={}, boxel_to_pybullet={},
        object_body_ids={}, render=render, camera=camera)


def _check(env, reg, shadows, objects, on_relations=None):
    """world_integrity_check after a move with an empty hand; its events."""
    events, _, _ = execution.world_integrity_check(
        env=env, registry=reg, belief=BeliefState(list(shadows), NO_TARGET), viz=None,
        shadows=shadows, occluders=objects, shadow_occluder_map={}, boxel_centers={},
        on_relations={} if on_relations is None else on_relations, label='test')
    return events


def _lattice(lo, hi):
    """A box's 3 x 3 x 3 lattice, as the arm guards take it."""
    g = [np.linspace(float(lo[k]), float(hi[k]), 3) for k in range(3)]
    return np.array([[x, y, z] for x in g[0] for y in g[1] for z in g[2]])


def _behind_arm(env, render, lo, hi):
    """Does a lattice point of the box lie behind the robot in ``render`` (the
    arm guard of refresh_object_aabbs and register_new_detections)?"""
    robot = env.objects['robot'].object_id
    icp, hids, _ = perception.first_surface_interceptors(_lattice(lo, hi), *render)
    return bool(np.any(icp & (hids == robot)))


def _task_bodies(env, reg):
    return [b for b in reg.get_boxels_by_type(BoxelType.OBJECT)
            if not getattr(env.objects.get(b.id), 'is_tray', False)]


def _believed_in_frame(env, reg, render):
    """Registered task bodies whose believed box lies wholly in the frame."""
    return [b.id for b in _task_bodies(env, reg) if arm_eye.in_frame(render[2], _box(b))]


def _whole_in_view(env, reg):
    """Registered task bodies whose believed box and detection both lie wholly
    in the current render's frame, no lattice point of either behind the arm."""
    dets, render = _render(env)
    out = []
    for b in _task_bodies(env, reg):
        d = dets.get(b.id)
        if d is None:
            continue
        boxes = (_box(b), (d.est_min, d.est_max))
        if (arm_eye.in_frame(render[2], *boxes)
                and not any(_behind_arm(env, render, *box) for box in boxes)):
            out.append(b.id)
    return out


def _cut_detection(env, name, lo, hi, render):
    """Test control: a detection of ``name`` whose box is [lo, hi] stretched in
    xy along an image axis until the frame's edge cuts it (a body seen in
    part), in a direction where no lattice point lies behind the arm, so the
    arm guards pass and the frame rule decides."""
    pose = arm_eye.view_pose(render[2])
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    for col, sign in ((0, 1.0), (0, -1.0), (1, 1.0), (1, -1.0)):
        step = sign * np.array([pose[0, col], pose[1, col], 0.0])
        if np.linalg.norm(step) < 0.1:
            continue
        step = step / np.linalg.norm(step)
        for reach in np.arange(0.05, 3.0, 0.05):
            est_min = np.minimum(lo, lo + reach * step)
            est_max = np.maximum(hi, hi + reach * step)
            if not arm_eye.in_frame(render[2], (est_min, est_max)):
                break
        else:
            continue
        if not _behind_arm(env, render, est_min, est_max):
            return perception.ObjectDetection(
                name=name, body_id=env.objects[name].object_id, pixel_count=PIXELS,
                est_min=est_min, est_max=est_max)
    raise AssertionError(f"no stretch of {name}'s box crosses the frame clear of the arm")


def _slid_out_of_view(render, lo, hi):
    """Test control: the box [lo, hi] slid in xy along the image's right axis
    until no point of its lattice lands in ``render``'s image
    (perception.project_points_to_pixels, the projection every check uses)."""
    h, w = np.asarray(render[0]).shape
    pose = arm_eye.view_pose(render[2])
    step = np.array([pose[0, 0], pose[1, 0], 0.0])
    assert np.linalg.norm(step) > 0.1, "the image's right axis is near vertical"
    step = step / np.linalg.norm(step)
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    for reach in np.arange(0.1, 3.05, 0.1):
        a, b = lo + reach * step, hi + reach * step
        if not perception.project_points_to_pixels(_lattice(a, b), render[2], render[3],
                                                    w, h)[3].any():
            return a, b
    raise AssertionError('no slide in xy takes the box out of the image')


def _inject(env, monkeypatch, extra):
    """Test control: every env render from here on reports the detections
    ``extra`` (name to ObjectDetection) in place of the real ones of those
    names."""
    real = env.detect_objects

    def detect(*args, **kwargs):
        dets, info, buf, seg = real(*args, **kwargs)
        dets = dict(dets)
        dets.update(extra)
        return dets, info, buf, seg

    monkeypatch.setattr(env, 'detect_objects', detect)


def _det(name, lo, hi):
    """A synthetic detection of ``name`` with the box [lo, hi]."""
    return perception.ObjectDetection(name=name, body_id=1, pixel_count=PIXELS,
                                      est_min=np.asarray(lo, dtype=float),
                                      est_max=np.asarray(hi, dtype=float))


class _Followed:
    """An env stand-in marked as followed (--eye arm): its renders report the
    detection dicts given, one per render, from the camera ``view``."""

    def __init__(self, view=None, *renders):
        setattr(self, arm_eye.FOLLOW_FLAG, True)
        self.view = view
        self.renders = list(renders)

    def detect_objects(self):
        return self.renders.pop(0), None, None, None

    def _view_and_projection_matrices(self):
        return self.view, None

    def step_simulation(self, *args):
        pass


def _audit():
    spec = importlib.util.spec_from_file_location(
        'eye_render_audit', ROOT / 'tools' / 'eye_render_audit.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ----- 1. every render after the first image ----------------------------------------

def test_after_the_first_image_every_env_render_is_the_wrist_where_the_arm_stands(
        env, monkeypatch):
    robot = env.objects['robot'].object_id
    start = _arm_mode(env)
    env.get_camera_observation()                                 # the first image
    renders = []
    real = p.getCameraImage

    def camera(*args, **kwargs):
        renders.append((kwargs.get('viewMatrix'), kwargs.get('projectionMatrix'),
                        kwargs.get('physicsClientId', 0)))
        return real(*args, **kwargs)

    monkeypatch.setattr(p, 'getCameraImage', camera)
    _move_arm(env)
    env.detect_objects()
    env.get_camera_observation()
    pose = robot_utils.wrist_camera_pose(robot, env.client_id)
    wview, wproj = robot_utils.wrist_camera_matrices(pose)
    sview, _ = robot_utils.wrist_camera_matrices(start['camera_pose'])
    assert len(renders) == 2                                     # DIRECT: no GUI pane
    for view, proj, client in renders:
        assert client == env.client_id
        assert np.allclose(view, wview, rtol=0, atol=1e-6)
        assert np.allclose(proj, wproj, rtol=0, atol=1e-6)
        assert not np.allclose(view, sview, rtol=0, atol=1e-3)   # not the start view
    assert np.array_equal(env.shadow_calculator.camera_position, pose[:3, 3])
    assert np.array_equal(env.camera_position, pose[:3, 3])
    assert arm_eye.following(env)


# ----- 2. a check judges what its image holds wholly --------------------------------

def test_a_check_after_a_move_judges_only_bodies_wholly_in_the_frame(env):
    """Every registered body is moved away in the simulator (test control).
    Those outside the new frame get no event and keep their boxel; at least
    one of those inside is judged as today (lost or disturbed)."""
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    split = {}

    def both_sides():
        view = env._view_and_projection_matrices()[0]
        bodies = reg.get_boxels_by_type(BoxelType.OBJECT)
        split['inside'] = [b.id for b in bodies if arm_eye.in_frame(view, _box(b))]
        split['outside'] = [b.id for b in bodies if b.id not in split['inside']]
        return bool(split['inside']) and bool(split['outside'])

    _move_arm(env, accept=both_sides)
    kept = {n: tuple(a.copy() for a in _box(reg.get_boxel(n))) for n in split['outside']}
    for name in split['inside'] + split['outside']:
        p.resetBasePositionAndOrientation(env.objects[name].object_id, [0.0, 0.0, -1.0],
                                          [0, 0, 0, 1], physicsClientId=env.client_id)
    events, _, _ = execution.world_integrity_check(
        env=env, registry=reg, belief=BeliefState(list(shadows), NO_TARGET), viz=None,
        shadows=shadows, occluders=objects, shadow_occluder_map={}, boxel_centers={},
        on_relations={}, label='test')
    named = {e['object']: e['kind'] for e in events}
    for name, (lo, hi) in kept.items():
        assert name not in named, (name, named)
        bd = reg.get_boxel(name)
        assert bd is not None and np.array_equal(_box(bd)[0], lo) and np.array_equal(_box(bd)[1], hi)
    assert any(named.get(n) in ('lost', 'disturbed') for n in split['inside']), named


def test_a_check_registers_only_bodies_its_image_holds_wholly(env):
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    _move_arm(env)
    dets, render = _render(env)
    _forget(reg, shadows, objects, list(dets))
    registered = _register(env, reg, shadows, objects, dets, render)
    for name in registered:
        assert arm_eye.in_frame(render[2], (dets[name].est_min, dets[name].est_max)), name
        assert arm_eye.in_frame(render[2], _box(reg.get_boxel(name))), name


def test_frame_judgement_asks_the_detection_for_presence_and_the_belief_for_absence():
    """The look manager's rule (2026-11-14) on a synthetic view."""
    view, _ = robot_utils.wrist_camera_matrices(DOWN)
    here = BoxelData(id='cube', boxel_type=BoxelType.OBJECT,
                     min_corner=HERE[0], max_corner=HERE[1])
    away = BoxelData(id='cube', boxel_type=BoxelType.OBJECT,
                     min_corner=HERE[0] + SHIFT, max_corner=HERE[1] + SHIFT)
    whole = _det('cube', *HERE)
    cut = _det('cube', HERE[0], HERE[1] + SHIFT)                 # the frame's edge cuts it
    judge = execution.frame_judgement
    assert judge(view, here, whole) == 'presence'
    assert judge(view, away, whole) == 'presence'                # B2: seen away from its belief
    assert judge(view, here, cut) == 'absence'                   # B1: the lost check decides
    assert judge(view, here, None) == 'absence'
    assert judge(view, away, cut) == 'keep'
    assert judge(view, away, None) == 'keep'


def test_a_body_believed_in_the_frame_and_seen_in_part_is_lost_when_its_region_renders_empty(
        env, monkeypatch):
    """B1, case R1: every body taken out of the image (test control); a body
    whose believed box the frame holds and whose region renders empty is
    reported by a detection the frame cuts.  The lost check on its believed
    region decides: lost, and retired."""
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    for b in reg.get_boxels_by_type(BoxelType.OBJECT):
        p.resetBasePositionAndOrientation(env.objects[b.id].object_id, [0.0, 0.0, -1.0],
                                          [0, 0, 0, 1], physicsClientId=env.client_id)
    found = []

    def an_empty_believed_region():
        _, render = _render(env)
        found[:] = [n for n in _believed_in_frame(env, reg, render)
                    if execution._fragment_renders_empty(reg.get_boxel(n), render)]
        return bool(found)

    _move_arm(env, accept=an_empty_believed_region)
    name = found[0]
    _, render = _render(env)
    _inject(env, monkeypatch,
            {name: _cut_detection(env, name, *_box(reg.get_boxel(name)), render)})
    named = {e['object']: e['kind'] for e in _check(env, reg, shadows, objects)}
    assert named.get(name) == 'lost', named
    assert reg.get_boxel(name) is None


def test_a_body_believed_in_the_frame_and_seen_in_part_is_kept_where_its_region_is_occupied(
        env, monkeypatch):
    """B1, case R1: a body standing where it is believed, its believed box
    wholly in the frame, reported by a detection the frame cuts: the lost
    check looks at its believed region, finds it occupied, and the box stays
    as it was (no re-pose from the cut detection, no event)."""
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    found = []

    def an_occupied_believed_region():
        _, render = _render(env)
        found[:] = [n for n in _believed_in_frame(env, reg, render)
                    if not execution._fragment_renders_empty(reg.get_boxel(n), render)]
        return bool(found)

    _move_arm(env, accept=an_occupied_believed_region)
    name = found[0]
    lo, hi = (a.copy() for a in _box(reg.get_boxel(name)))
    _, render = _render(env)
    _inject(env, monkeypatch, {name: _cut_detection(env, name, lo, hi, render)})
    looked = []
    real = execution.sense_ray_slices

    def slices(*args, **kwargs):
        looked.append(tuple(np.array(a, dtype=float) for a in args[:2]))
        return real(*args, **kwargs)

    monkeypatch.setattr(execution, 'sense_ray_slices', slices)
    named = {e['object']: e['kind'] for e in _check(env, reg, shadows, objects)}
    assert name not in named, named
    assert any(np.array_equal(a, lo) and np.array_equal(b, hi) for a, b in looked)
    bd = reg.get_boxel(name)
    assert np.array_equal(_box(bd)[0], lo) and np.array_equal(_box(bd)[1], hi)


def test_a_body_seen_wholly_away_from_its_believed_box_is_reposed_and_reported_disturbed(env):
    """B2, case R2: the believed box out of the image (test control: slid
    away in the belief), the body seen wholly in the frame where it stands:
    re-posed on its detection and reported disturbed, never lost."""
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    _move_arm(env, accept=lambda: bool(_whole_in_view(env, reg)))
    name = _whole_in_view(env, reg)[0]
    dets, render = _render(env)
    bd = reg.get_boxel(name)
    bd.min_corner, bd.max_corner = _slid_out_of_view(render, *_box(bd))
    assert not arm_eye.in_frame(render[2], _box(bd))
    events = _check(env, reg, shadows, objects)
    assert [e['kind'] for e in events if e['object'] == name] == ['disturbed'], events
    bd = reg.get_boxel(name)
    assert bd is not None
    assert np.allclose(bd.center[:2], dets[name].est_center[:2], rtol=0, atol=1e-3)


def test_a_body_with_neither_its_belief_nor_its_detection_wholly_in_the_frame_is_kept(
        env, monkeypatch):
    """Case R3: the believed box slid out of the image and the detection cut
    by the frame (test controls): no event, the box and the support relation
    as they were."""
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    _move_arm(env, accept=lambda: bool(_whole_in_view(env, reg)))
    name = _whole_in_view(env, reg)[0]
    _, render = _render(env)
    bd = reg.get_boxel(name)
    cut = _cut_detection(env, name, *_box(bd), render)
    lo, hi = _slid_out_of_view(render, *_box(bd))
    bd.min_corner, bd.max_corner = lo.copy(), hi.copy()
    support = next(b for b in _task_bodies(env, reg) if b.id != name)
    # Judged, the relation would fall (off_support): the bottom is far off the top.
    assert abs(lo[2] - float(support.max_corner[2])) > execution.INTEGRITY_SUPPORT_TOL_M
    on_relations = {name: support.id}
    _inject(env, monkeypatch, {name: cut})
    named = {e['object']: e['kind']
             for e in _check(env, reg, shadows, objects, on_relations)}
    assert name not in named, named
    bd = reg.get_boxel(name)
    assert np.array_equal(_box(bd)[0], lo) and np.array_equal(_box(bd)[1], hi)
    assert on_relations == {name: support.id}


def test_a_checks_image_does_not_register_a_body_the_frame_cuts(env, capsys):
    """A check's image (camera 'eye') registers a body it shows for the first
    time only from a detection wholly in its frame: a cut one is refused, the
    whole one of the same body in the same image is taken."""
    _arm_mode(env)
    reg, shadows, objects = _first_scan(env)
    _move_arm(env, accept=lambda: bool(_whole_in_view(env, reg)))
    name = _whole_in_view(env, reg)[0]
    dets, render = _render(env)
    whole = dets[name]
    cut = _cut_detection(env, name, whole.est_min, whole.est_max, render)
    _forget(reg, shadows, objects, [name])
    capsys.readouterr()
    assert _register(env, reg, shadows, objects, {name: cut}, render) == []
    assert (f"{name} is visible ({PIXELS} px) but not wholly in the arm camera's "
            f"image: not registered from it") in capsys.readouterr().out
    assert reg.get_boxel(name) is None
    assert _register(env, reg, shadows, objects, {name: whole}, render) == [name]


def test_a_release_check_judges_only_detections_wholly_in_their_images():
    """_observe_release with --eye arm (a stand-in env, a synthetic view): a
    body that moved 10 mm between the two renders fails the check when both
    detections lie wholly in the frame; when the frame cuts the second, the
    release is accepted on the tactile checks and nothing is judged."""
    view, _ = robot_utils.wrist_camera_matrices(DOWN)
    step = np.array([0.01, 0.0, 0.0])
    first = _det('cube', *HERE)
    moved = _det('cube', HERE[0] + step, HERE[1] + step)
    ok, diag, _ = execution._observe_release(
        _Followed(view, {'cube': first}, {'cube': moved}), 'cube')
    assert not ok and 'between two renders' in diag
    cut = _det('cube', HERE[0] + step, HERE[1] + SHIFT)
    ok, diag, centre = execution._observe_release(
        _Followed(view, {'cube': first}, {'cube': cut}), 'cube')
    assert ok and centre is None and "not wholly in the arm camera's image" in diag


def test_a_lost_bodys_fragment_the_image_does_not_hold_wholly_is_kept(monkeypatch):
    """retire_lost_objects with --eye arm (a stand-in env, a synthetic view):
    every fragment's slices visible through (test control), the fragment
    wholly in the frame is removed as observed empty and the one the frame
    cuts is kept.  Without the switch both go, as with the fixed camera."""
    view, _ = robot_utils.wrist_camera_matrices(DOWN)
    monkeypatch.setattr(execution, '_fragment_renders_empty', lambda bd, render: True)

    def retire(env):
        reg = BoxelRegistry()
        reg.add_boxel(BoxelData(id='cube', boxel_type=BoxelType.OBJECT,
                                min_corner=HERE[0], max_corner=HERE[1],
                                shadow_boxel_ids=['cube_in', 'cube_cut']))
        reg.add_boxel(BoxelData(id='cube_in', boxel_type=BoxelType.SHADOW,
                                min_corner=HERE[0], max_corner=HERE[1]))
        reg.add_boxel(BoxelData(id='cube_cut', boxel_type=BoxelType.SHADOW,
                                min_corner=HERE[0], max_corner=HERE[1] + SHIFT))
        shadows = ['cube_in', 'cube_cut']
        execution.retire_lost_objects(['cube'], reg, None, shadows, {}, {}, ['cube'],
                                      BeliefState(list(shadows), NO_TARGET),
                                      render=(None, None, view, None), env=env)
        assert reg.get_boxel('cube') is None
        return sorted(shadows)

    assert retire(_Followed(view)) == ['cube_cut']
    assert retire(None) == []


def test_a_pick_re_aims_on_a_detection_the_frame_holds_wholly():
    """execute_pick's re-observation before the descent is a re-pose, a
    presence verdict: with --eye arm its one frame test takes the render's
    view and the fresh detection's box, not the believed box."""
    tree = ast.parse((ROOT / 'execution.py').read_text(encoding='utf-8'))
    (pick,) = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'execute_pick']
    (call,) = [c for c in ast.walk(pick) if isinstance(c, ast.Call)
               and isinstance(c.func, ast.Attribute) and c.func.attr == 'in_frame']
    assert len(call.args) == 2
    assert {n.id for n in ast.walk(call.args[1]) if isinstance(n, ast.Name)} == {'fresh'}


# ----- 3. the shadow of a body first seen after the first image ---------------------

def test_a_body_first_seen_by_a_check_casts_from_that_images_camera(env, monkeypatch):
    robot = env.objects['robot'].object_id
    start = _arm_mode(env)
    reg, shadows, objects = _first_scan(env)

    def holds_a_body():
        dets, render = _render(env)
        return any(arm_eye.in_frame(render[2], (d.est_min, d.est_max)) for d in dets.values())

    _move_arm(env, accept=holds_a_body)
    dets, render = _render(env)
    wrist = robot_utils.wrist_camera_pose(robot, env.client_id)[:3, 3]
    assert not np.allclose(wrist, start['camera_position'], atol=1e-3)
    _forget(reg, shadows, objects, list(dets))
    calls, real = _spy_casts(env, monkeypatch)
    registered = _register(env, reg, shadows, objects, dets, render)
    assert registered and [c[0] for c in calls] == registered
    for _, pos, _ in calls:
        assert np.allclose(pos, wrist, rtol=0, atol=1e-6)
    # The same casts from the start view give other fragments.
    differs = []
    for name, _, obstacles in calls:
        bd = reg.get_boxel(name)
        mine = _corners(reg.get_boxel(s) for s in bd.shadow_boxel_ids)
        env.shadow_calculator.camera_position = np.asarray(start['camera_position'])
        other = _corners(real(bd, obstacles, physics_client=env.shadow_raycast_client))
        differs.append(mine != other)
    assert any(differs)


def test_a_looks_m1_casts_from_the_wrist_at_the_current_joints(env, monkeypatch):
    """The look's M-1 (look_action.py, register_new_detections with camera
    'wrist') takes its detections from a direct wrist render, not from the
    env: the cast comes from that render's camera, not from the env's last
    image."""
    robot = env.objects['robot'].object_id
    start = _arm_mode(env, THEIR_HOME)
    reg, shadows, objects = _first_scan(env)
    _move_arm(env, accept=lambda: bool(observe_views.wrist_observation(env, robot)[0]))
    dets, render = observe_views.wrist_observation(env, robot)
    wrist = robot_utils.wrist_camera_pose(robot, env.client_id)[:3, 3]
    assert np.array_equal(env.shadow_calculator.camera_position, start['camera_position'])
    _forget(reg, shadows, objects, list(dets))
    calls, _ = _spy_casts(env, monkeypatch)
    registered = _register(env, reg, shadows, objects, dets, render, camera='wrist')
    assert registered and calls
    for _, pos, _ in calls:
        assert np.allclose(pos, wrist, rtol=0, atol=1e-6)
        assert not np.allclose(pos, start['camera_position'], atol=1e-3)


# ----- 4. with the fixed camera -----------------------------------------------------

def test_with_the_fixed_camera_no_arm_camera_path_runs(env, monkeypatch):
    """No follow, no frame rule, no cast moved: arm_eye's step-3 geometry
    raises if any of it is reached, and the camera stays the base's."""
    def refuse(*args, **kwargs):
        raise AssertionError('an arm-camera path ran with --eye fixed')

    for name in ('in_frame', 'view_pose', 'use_start_view', 'box_in_frame'):
        monkeypatch.setattr(arm_eye, name, refuse)
    robot = env.objects['robot'].object_id
    assert arm_eye.place_arm(env, THEIR_HOME)                    # test control only
    env.step_simulation(50)
    env.update_object_positions()
    assert not arm_eye.following(env)
    assert '_view_and_projection_matrices' not in vars(env)
    reg, shadows, objects = _first_scan(env)
    # A look's M-1 with --eye fixed casts from the fixed camera.
    dets, render = observe_views.wrist_observation(env, robot)
    _forget(reg, shadows, objects, list(dets))
    calls, _ = _spy_casts(env, monkeypatch)
    registered = _register(env, reg, shadows, objects, dets, render, camera='wrist')
    assert registered and calls
    assert all(np.array_equal(pos, BASE_CAMERA['camera_position']) for _, pos, _ in calls)
    # The check after a move renders and judges from the fixed camera.
    _move_arm(env)
    execution.world_integrity_check(
        env=env, registry=reg, belief=BeliefState(list(shadows), NO_TARGET), viz=None,
        shadows=shadows, occluders=objects, shadow_occluder_map={}, boxel_centers={},
        on_relations={}, label='test')
    for name, want in BASE_CAMERA.items():
        assert np.array_equal(np.asarray(getattr(env, name)), np.asarray(want)), name
    assert np.array_equal(env.shadow_calculator.camera_position, BASE_CAMERA['camera_position'])


# ----- 5. the completeness test's rule ----------------------------------------------

def test_the_audit_rule_passes_the_wrist_at_fk_and_fails_the_start_view_after_a_move(env):
    audit = _audit()
    robot = env.objects['robot'].object_id
    assert arm_eye.place_arm(env, START)
    sview, sproj = robot_utils.wrist_camera_matrices(
        robot_utils.wrist_camera_pose(robot, env.client_id))
    assert audit.wrist_rule(sview, sproj, robot, env.client_id)
    _move_arm(env)
    assert not audit.wrist_rule(sview, sproj, robot, env.client_id)
    view, proj = robot_utils.wrist_camera_matrices(
        robot_utils.wrist_camera_pose(robot, env.client_id))
    assert audit.wrist_rule(view, proj, robot, env.client_id)
    assert not audit.wrist_rule(view, proj, None, env.client_id)     # no robot there
    assert not audit.wrist_rule(*env._view_and_projection_matrices(), robot,
                                env.client_id)                       # the base's eye


def test_the_audit_hook_records_each_render_with_its_verdict(env):
    audit = _audit()
    start = _arm_mode(env)
    sview, sproj = robot_utils.wrist_camera_matrices(start['camera_pose'])
    log = audit.RenderLog()
    log.watch(env)
    log.install()
    try:
        _move_arm(env)
        env.detect_objects()                                     # followed
        p.getCameraImage(32, 24, sview, sproj, physicsClientId=env.client_id)
    finally:
        log.uninstall()
    assert [(r['side'], r['wrist']) for r in log.rows] == [('executing', True),
                                                          ('executing', False)]
    assert 'detect_objects' in log.rows[0]['callers']
    assert [r['k'] for r in log.bad()] == [1]


def test_the_audit_runs_the_scene_run_boxels_builds():
    audit = _audit()
    text = (ROOT / 'run.ps1').read_text(encoding='utf-8')
    default = {name: re.search(rf"\[(?:string|int)\]\${name} = '?([\w-]+)'?", text).group(1)
               for name in ('Scene', 'Goal', 'Occluders')}
    assert audit.RUN_BOXELS == ['--scene', default['Scene'], '--goal', default['Goal'],
                                '--n-occluders', default['Occluders']]
    assert audit.ARM_ONLY == ['--no-gui', '--look', 'boxel', '--eye', 'arm']


# ----- 6. view_pose and in_frame -----------------------------------------------------

def test_view_pose_gives_back_the_camera_a_wrist_view_was_made_from(env):
    robot = env.objects['robot'].object_id
    for joints in (START, THEIR_HOME):
        assert arm_eye.place_arm(env, joints)
        pose = robot_utils.wrist_camera_pose(robot, env.client_id)
        view, _ = robot_utils.wrist_camera_matrices(pose)
        assert np.allclose(arm_eye.view_pose(view), pose, rtol=0, atol=1e-6)


def test_in_frame_asks_every_box_to_lie_wholly_in_the_image(env):
    robot = env.objects['robot'].object_id
    assert arm_eye.place_arm(env, START)
    pose = robot_utils.wrist_camera_pose(robot, env.client_id)
    view, _ = robot_utils.wrist_camera_matrices(pose)
    centre = pose[:3, 3] + 0.3 * pose[:3, 2]                     # on the optical axis
    right = 0.5 * pose[:3, 0]                                    # half a metre to the image's right
    small = (centre - 0.01, centre + 0.01)
    beside = (centre + right - 0.01, centre + right + 0.01)
    across = (centre - 0.01, centre + right + 0.01)              # the frame's edge cuts it
    assert arm_eye.in_frame(view, small)
    assert not arm_eye.in_frame(view, beside)
    assert not arm_eye.in_frame(view, across)
    assert not arm_eye.in_frame(view, small, beside)
    assert arm_eye.in_frame(view)                                # no box: none outside
