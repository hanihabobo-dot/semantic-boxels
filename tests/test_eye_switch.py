"""Path 9, the arm camera only, steps 1 and 2 of three (tracks/look/
ARM_ONLY_DESIGN.md, the switch, part 1 and part 2): --eye fixed|arm, the start
configuration, the first image and the part of the table it does not show.  No
episode, no planner.

1. The flag: fixed by default; arm needs a look; a start configuration from the
   command line.
2. Without the switch the env's camera is the base's (track/freeze 15d5ff4),
   attribute for attribute.
3. With it, the first image is observe_views.wrist_render at the start
   configuration, pixel for pixel, and the shadow code casts from there.
4. The start configuration is scene construction in a world of our own and
   moves nothing in an adopted one.
5. The launcher: without -Eye the command is the one of before; -Eye arm adds
   one flag and needs -Look.
6. The unseen regions after the first scan, on a scene of ours: none shares a
   volume with an object box, a shadow fragment or another region; each lies
   in the safe window; free space made with them enters none.
7. The wiring in main(): with --eye arm the unseen regions join the first
   scan's boxels before free space is made; with --eye fixed none of it runs
   and the run's record has no eye key; main() cuts no region to a look's
   cell side (PLAN 11.16: a region is cut only by what an image saw).
"""
import ast
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import arm_eye  # noqa: E402
import observe_views  # noqa: E402
import robot_utils  # noqa: E402
import run_logger  # noqa: E402
import streams  # noqa: E402
from boxel_data import BoxelType  # noqa: E402
from boxel_env import BoxelTestEnv  # noqa: E402
from test_look_correspondence import _PWSH, _dry, needs_pwsh  # noqa: E402

# The base's overview camera (boxel_env.BoxelTestEnv.__init__ at 15d5ff4).
BASE_CAMERA = dict(camera_position=[0.1, -0.8, 0.7], camera_target=[0.1, 0.0, 0.5],
                   camera_up=[0, 0, 1], fov=60.0, image_width=640, image_height=480,
                   near_plane=0.01, far_plane=5.0)
START = list(robot_utils.REST_POSES)


@pytest.fixture
def env():
    e = BoxelTestEnv(gui=False)
    yield e
    e.close()


def _arm(env, client=None, robot=None):
    client = env.client_id if client is None else client
    robot = env.objects['robot'].object_id if robot is None else robot
    return np.array([p.getJointState(robot, j, physicsClientId=client)[0]
                     for j in robot_utils.robot_model().arm_joints])


# ----- 1. the flag ---------------------------------------------------------------

def test_the_flag_is_fixed_unless_asked():
    assert run_logger.parse_pipeline_args(['--no-gui']).eye == 'fixed'
    assert run_logger.parse_pipeline_args(['--no-gui']).eye_start_joints == ''
    args = run_logger.parse_pipeline_args(['--no-gui', '--look', 'centred', '--eye', 'arm'])
    assert args.eye == 'arm'
    with pytest.raises(SystemExit):
        run_logger.parse_pipeline_args(['--no-gui', '--eye', 'wrist'])


@pytest.mark.parametrize('eye, look, ok', [
    ('fixed', 'off', True), ('fixed', 'boxel', True), ('fixed', 'centred', True),
    ('arm', 'boxel', True), ('arm', 'centred', True), ('arm', 'off', False)])
def test_the_arm_camera_needs_a_look(eye, look, ok):
    if ok:
        arm_eye.check_mode(eye, look)
    else:
        with pytest.raises(ValueError, match='needs --look'):
            arm_eye.check_mode(eye, look)


def test_an_unknown_eye_is_refused():
    with pytest.raises(ValueError, match='--eye is one of'):
        arm_eye.check_mode('wrist', 'boxel')


def test_a_start_configuration_from_the_command_line():
    assert arm_eye.parse_joints('') is None and arm_eye.parse_joints(None) is None
    text = '-0.08,-1.67, 0.07,-2.74,0.08,1.75,0.78'
    assert arm_eye.parse_joints(text) == [-0.08, -1.67, 0.07, -2.74, 0.08, 1.75, 0.78]
    args = run_logger.parse_pipeline_args(['--no-gui', f'--eye-start-joints={text}'])
    assert arm_eye.parse_joints(args.eye_start_joints) == arm_eye.parse_joints(text)
    with pytest.raises(ValueError, match='7 joint angles'):
        arm_eye.parse_joints('0,0,0')
    with pytest.raises(ValueError, match='radians'):
        arm_eye.parse_joints('a,b,c,d,e,f,g')


# ----- 2. without the switch -------------------------------------------------------

def test_without_the_switch_the_camera_is_the_bases(env):
    for name, want in BASE_CAMERA.items():
        assert np.array_equal(np.asarray(getattr(env, name)), np.asarray(want)), name
    assert np.array_equal(env.shadow_calculator.camera_position, BASE_CAMERA['camera_position'])
    view, proj = env._view_and_projection_matrices()
    assert view == p.computeViewMatrix(cameraEyePosition=BASE_CAMERA['camera_position'],
                                       cameraTargetPosition=BASE_CAMERA['camera_target'],
                                       cameraUpVector=BASE_CAMERA['camera_up'])
    assert proj == p.computeProjectionMatrixFOV(fov=60.0, aspect=640 / 480,
                                                nearVal=0.01, farVal=5.0)
    assert set(arm_eye.CAMERA_ATTRIBUTES) == set(BASE_CAMERA)


# ----- 3. the first image ----------------------------------------------------------

def test_the_first_image_is_the_wrist_render_at_the_start_configuration(env):
    """Pixel for pixel: the env's own render path, with the switched
    attributes, and the look's wrist render give one image."""
    robot = env.objects['robot'].object_id
    assert arm_eye.place_arm(env, START)
    cam = arm_eye.use_start_view(env)
    assert np.allclose(cam['camera_pose'], robot_utils.wrist_camera_pose(robot, env.client_id))
    _dets, _rgb, depth_buffer, seg = env.detect_objects()
    wcam, wbuf, wdepth_m, wseg, wview, wproj = observe_views.wrist_render(env.client_id, robot)
    assert env._view_and_projection_matrices() == (wview, wproj)
    assert depth_buffer.shape == (robot_utils.WRIST_CAMERA_HEIGHT, robot_utils.WRIST_CAMERA_WIDTH)
    assert np.array_equal(depth_buffer, wbuf)
    assert np.array_equal(seg, wseg)
    assert np.allclose(env._depth_buffer_to_meters(depth_buffer), wdepth_m, rtol=0, atol=1e-12)
    assert (seg >= 0).any(), 'the image shows nothing of the scene'
    assert np.allclose(wcam, cam['camera_pose'])


def test_the_first_scan_runs_from_the_arm_cameras_view(env):
    """Today's first scan (detections, boxels, shadows) with the arm camera's
    view: the shadow code casts from the arm camera's position."""
    arm_eye.place_arm(env, START)
    cam = arm_eye.use_start_view(env)
    assert np.array_equal(env.shadow_calculator.camera_position, cam['camera_position'])
    assert np.array_equal(env.camera_position, cam['camera_position'])
    obs = env.get_camera_observation()
    assert obs.depth_image.shape == (480, 640) and isinstance(obs.boxels, list)
    assert set(obs.visible_objects) <= set(env.objects)


# ----- 4. the start configuration --------------------------------------------------

def test_the_arm_stands_at_the_start_configuration_in_both_clients_and_holds(env):
    assert not np.allclose(_arm(env), START, atol=1e-3)          # the scene leaves it elsewhere
    assert arm_eye.place_arm(env, START)
    assert np.allclose(_arm(env), START, atol=1e-9)
    assert np.allclose(_arm(env, env.plan_client_id, env.plan_robot_id), START, atol=1e-9)
    env.step_simulation(50)                                      # main()'s settle
    assert np.allclose(_arm(env), START, atol=2e-3)


def test_an_adopted_world_is_not_moved(env):
    before = _arm(env)
    env._adopted = True
    try:
        assert arm_eye.place_arm(env, START) is False
        assert np.array_equal(_arm(env), before)
        cam = arm_eye.use_start_view(env)                        # from where the arm is
        robot = env.objects['robot'].object_id
        assert np.allclose(cam['camera_pose'],
                           robot_utils.wrist_camera_pose(robot, env.client_id))
    finally:
        env._adopted = False


def test_a_start_configuration_that_touches_a_body_is_refused(env):
    robot = env.objects['robot'].object_id
    arm_eye.place_arm(env, START)
    hand = p.getLinkState(robot, robot_utils._hand_link(robot, env.client_id),
                          computeForwardKinematics=True, physicsClientId=env.client_id)[4]
    half = [0.03, 0.03, 0.03]
    body = p.createMultiBody(
        0.0, p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=env.client_id),
        basePosition=list(hand), physicsClientId=env.client_id)
    env.objects['in_the_way'] = SimpleNamespace(object_id=body)
    try:
        with pytest.raises(ValueError, match="touches \\['in_the_way'\\]"):
            arm_eye.place_arm(env, START)
    finally:
        env.objects.pop('in_the_way')


def test_a_start_configuration_of_the_wrong_length_is_refused(env):
    with pytest.raises(ValueError, match='joints'):
        arm_eye.place_arm(env, START[:5])


# ----- 5. the launcher -------------------------------------------------------------

@needs_pwsh
@pytest.mark.parametrize('args', ['boxels -Seed 3 -Headless', 'boxels -Seed 3 -Headless -Look boxel',
                                  'boxels -Seed 3 -Headless -Eye fixed', 'tampura -Seed 5'])
def test_without_the_eye_switch_no_flag_is_added(args):
    assert '--eye' not in _dry(ROOT / 'run.ps1', args)


@needs_pwsh
@pytest.mark.parametrize('look', ['boxel', 'centred'])
def test_the_eye_switch_appends_one_flag(look):
    off = _dry(ROOT / 'run.ps1', f'boxels -Seed 3 -Headless -Look {look}')
    on = _dry(ROOT / 'run.ps1', f'boxels -Seed 3 -Headless -Look {look} -Eye arm')
    assert on.count('--eye') == 1
    assert on.replace(' --eye arm', '', 1) == off
    assert f"--look {look} --eye arm'" in on


@needs_pwsh
@pytest.mark.parametrize('args', ['boxels -Seed 3 -Headless -Eye arm',
                                  'tampura -Seed 5 -Look boxel -Eye arm'])
def test_the_launcher_refuses_the_arm_camera_where_it_cannot_run(args):
    """Without a look (sense is the fixed camera's action), and on the bridge,
    whose driver and gates do not know the arm camera yet (step 3)."""
    ps1 = ROOT / 'run.ps1'
    win = subprocess.run(['wslpath', '-w', str(ps1)], capture_output=True, text=True,
                         check=True).stdout.strip()
    # pwsh -Command ends with 1 when the script it calls exits non-zero; the
    # script's own code is passed on with an explicit exit.
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command',
                           f"& '{win}' {args} -DryRun; exit $LASTEXITCODE"],
                          capture_output=True, text=True, timeout=120, cwd=str(ps1.parent))
    said = proc.stdout + proc.stderr
    assert proc.returncode == 2, said
    assert '-Eye arm' in said and '--eye' not in said


# ----- 6. the unseen regions on a scene of ours ------------------------------------

# TAMPURA's home joints, their DEFAULT_ARM_POS, as recorded in
# tracks/look/evidence/arm_camera_home_pose_20261112.txt.
THEIR_HOME = [-0.0806406098426434, -1.6722951504174777, 0.07069076842695393,
              -2.7449419709102822, 0.08184716251979611, 1.7516337599063168,
              0.7849295270972781]


def _overlap(a_lo, a_hi, b_lo, b_hi):
    """True when two boxes share a volume; touching faces do not."""
    return bool(np.all(np.minimum(a_hi, b_hi) - np.maximum(a_lo, b_lo) > 1e-9))


@pytest.mark.parametrize('joints', [START, THEIR_HOME], ids=['rest_poses', 'their_home'])
def test_the_unseen_regions_after_the_first_scan(env, joints):
    """The env fixture's scene, boxel_env.default_scene (seven blocks at x 0.0
    to 0.3, none taller than 0.075 m): neither start configuration touches a
    body in it.  Main()'s steps up to free space: the arm at the start
    configuration, the settle, the arm camera, the first scan, the unseen
    regions over the safe window at the planner's prior height."""
    assert arm_eye.place_arm(env, joints)
    env.step_simulation(50)
    env.update_object_positions()
    cam = arm_eye.use_start_view(env)
    known = env.get_camera_observation().boxels
    if joints == THEIR_HOME:
        assert known, 'blocks of this scene stand in the home view'
    table_z = env.table_surface_height
    height = float(streams.NOMINAL_HIDDEN_EXTENTS[2])
    (x_lo, x_hi), (y_lo, y_hi) = env._SAFE_TABLE_X_RANGE, env._SAFE_TABLE_Y_RANGE
    unseen = arm_eye.unseen_boxels(cam['camera_pose'], env._SAFE_TABLE_X_RANGE,
                                   env._SAFE_TABLE_Y_RANGE, table_z, height, known=known)
    assert unseen, 'the window is larger than the start view'
    assert [u.id for u in unseen] == [f"unseen_{i:03d}" for i in range(len(unseen))]
    eps = 1e-9
    for i, u in enumerate(unseen):
        assert u.boxel_type == BoxelType.SHADOW
        assert u.created_by_object is None and u.created_by_boxel_id is None
        assert x_lo - eps <= u.min_corner[0] < u.max_corner[0] <= x_hi + eps
        assert y_lo - eps <= u.min_corner[1] < u.max_corner[1] <= y_hi + eps
        assert table_z - eps <= u.min_corner[2] < u.max_corner[2] <= table_z + height + eps
        for k in known:
            assert not _overlap(u.min_corner, u.max_corner, k.min_corner, k.max_corner), (u.id, k.id)
        for v in unseen[i + 1:]:
            assert not _overlap(u.min_corner, u.max_corner, v.min_corner, v.max_corner), (u.id, v.id)
    free = env.generate_free_space(known + unseen, visualize=False)
    assert free
    for fb in free:
        for u in unseen:
            assert not _overlap(fb.min_corner, fb.max_corner, u.min_corner, u.max_corner), u.id


# ----- 7. the wiring in main() ------------------------------------------------------

PIPELINE = ast.parse((ROOT / 'test_full_pipeline.py').read_text(encoding='utf-8'))
MAIN = next(n for n in ast.walk(PIPELINE) if isinstance(n, ast.FunctionDef) and n.name == 'main')


def _under(tree, test):
    """The ids of every node in the body (not the else) of an ``if`` whose
    test reads ``test``."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test) == test:
            for stmt in node.body:
                out.update(id(n) for n in ast.walk(stmt))
    return out


def _calls(tree, name):
    return [c for c in ast.walk(tree) if isinstance(c, ast.Call)
            and getattr(c.func, 'attr', getattr(c.func, 'id', None)) == name]


def _assigns(tree, target):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and len(n.targets) == 1 and ast.unparse(n.targets[0]) == target]


def test_with_the_arm_camera_the_unseen_regions_join_the_first_scan_before_free_space():
    arm = _under(MAIN, "eye == 'arm'")
    (call,) = _calls(MAIN, 'unseen_boxels')
    assert id(call) in arm
    assert [ast.unparse(a) for a in call.args] == [
        'eye_camera_pose', 'env._SAFE_TABLE_X_RANGE', 'env._SAFE_TABLE_Y_RANGE',
        'env.table_surface_height', 'float(streams.NOMINAL_HIDDEN_EXTENTS[2])']
    assert [(k.arg, ast.unparse(k.value)) for k in call.keywords] == [('known', 'all_known')]
    (scan,) = [n for n in _assigns(MAIN, 'all_known') if ast.unparse(n.value) == 'obs.boxels']
    (join,) = [n for n in _assigns(MAIN, 'all_known')
               if ast.unparse(n.value) == 'all_known + _unseen']
    (free,) = _calls(MAIN, 'generate_free_space')
    assert id(join) in arm and ast.unparse(free.args[0]) == 'all_known'
    assert scan.lineno < call.lineno < join.lineno < free.lineno
    # The camera pose is the one use_start_view returned, kept in the settle block.
    (pose,) = _assigns(MAIN, 'eye_camera_pose')
    (start_view,) = _calls(MAIN, 'use_start_view')
    assert id(pose) in arm and ast.unparse(pose.value) == "_cam['camera_pose']"
    assert start_view.lineno < pose.lineno < scan.lineno
    assert any(isinstance(n, ast.Import)
               and [(a.name, a.asname) for a in n.names] == [('streams', None)]
               for n in PIPELINE.body)
    # main() cuts no region to a look's cell side (PLAN 11.16).
    text = ast.unparse(MAIN)
    assert 'max_fragment_side' not in text and 'look_cell_side' not in text


def test_with_the_fixed_camera_main_makes_no_unseen_region_and_records_no_eye():
    """Case 7: every path-9 call in main() is under ``if eye == 'arm':``, so
    with --eye fixed (the default) none runs; the record's literal has no eye
    key, and one plain ``if`` after it adds the key for --eye arm alone."""
    arm = _under(MAIN, "eye == 'arm'")
    for name in ('place_arm', 'use_start_view', 'unseen_boxels'):
        calls = _calls(MAIN, name)
        assert calls and all(id(c) in arm for c in calls), name
    (literal,) = [n for n in _assigns(PIPELINE, 'run_config') if isinstance(n.value, ast.Dict)]
    keys = [k.value for k in literal.value.keys if isinstance(k, ast.Constant)]
    spread = [ast.unparse(v) for k, v in zip(literal.value.keys, literal.value.values)
              if k is None]
    assert 'eye' not in keys and not any("'eye'" in s for s in spread)
    assert any("'look'" in s for s in spread)          # the look entry beside it stays
    (record,) = _assigns(PIPELINE, "run_config['eye']")
    assert ast.unparse(record.value) == "'arm'"
    assert id(record) in _under(PIPELINE, "getattr(args, 'eye', 'fixed') == 'arm'")
    assert literal.lineno < record.lineno
