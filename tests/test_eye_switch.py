"""Path 9, the arm camera only, step 1 of three (tracks/look/ARM_ONLY_DESIGN.md,
the switch and part 1): --eye fixed|arm, the start configuration and the first
image.  No episode, no planner.

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
"""
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
