"""#P4 G6: the scoring-channel controls (PAPER_AUDIT.txt #P4, G6; BF#14 GF4).

The positive controls run on the real chain: their FindDiceEnv on seed 0
(initialize as run_planner.py does), D9's set-up, a held body, our
scoring.build_observation, then THEIR SceneBelief.update, abstract and
ProblemSpec.get_reward, exactly the calls of their rollout:
  (1)  a verified two-pad hold of the die with the arm at DEFAULT_ARM_POS
       gives 1.0;
  (2)  the same hold of a cup gives 0.0;
  (1b) the die hold with one arm joint 2e-3 rad off DEFAULT_ARM_POS gives
       0.0 (their at-home tolerance is 1e-4 plus 1e-4 relative).
The set-up is a test control, not an episode: it places the body between
the open pads, closes the fingers under our pad friction and close force
and steps until the squeeze holds, then sets the arm to the control's
configuration without a further step (the contacts read are the last
step's).  It lives in this file only, outside the campaign import graph, so
it needs no allowlist entry.  The fault injections (3) to (5) run with B7's
full episodes (GF4).
Also: G6's readback check (gate_hooks.check_readback) and the round trip of
an arm O RolloutHistory pickle into arm T's venv.
Run from their tampura_environments directory in the arm-O venv (D12) with
their trees on PYTHONPATH.
"""
import glob
import os
import random
import subprocess

import numpy as np
import pybullet as p
import pytest

import robot_utils
from tampura_bridge import gate_hooks, policy as bridge_policy, scoring, task_spec

REPO = gate_hooks.REPO
TW = os.environ.get('TAMPURA_WORK', '/root/tampura-work')
CONFIG = './env_configs/find_dice.yml'
SETTLE_STEPS = 240
SQUEEZE_INSIDE_M = 0.0005      # execute_pick's target inside the surface (robot_utils.GRIP_SQUEEZE, BF#44)
CLOSE_FORCE_N = 60.0           # robot_utils.close_gripper's default
ARM_HOLD_FORCE_N = 500.0


@pytest.fixture(autouse=True)
def _isolated():
    """Leave no state behind: the robot model the hold installs and the
    clients their env connects."""
    model = robot_utils.robot_model()
    before = {i for i in range(64) if p.isConnected(physicsClientId=i)}
    yield
    robot_utils.use_robot_model(model)
    for i in range(64):
        if i not in before and p.isConnected(physicsClientId=i):
            p.disconnect(physicsClientId=i)


def _their_env(tmp_path):
    from tampura.config import config as tconfig
    import tampura_environments  # noqa: F401  (registers find_dice)
    arg_dict = {'config': CONFIG, 'global_seed': 0, 'vis': False,
                'save_dir': str(tmp_path)}
    config = tconfig.load_config(config_file=CONFIG, arg_dict=arg_dict)
    random.seed(0)
    np.random.seed(0)
    env = tconfig.get_env(config['task'])(config=config)
    b0, store = env.initialize()
    return env, b0, store


def _hold(env, store, category, arm_offset=0.0):
    """The control set-up; returns (held body, SceneObservation)."""
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world = env.world
    c, robot = world.client._client, world.robot.body
    model = robot_utils.resolve_robot_model(robot, c)
    robot_utils.use_robot_model(model)
    bridge_policy.d9_setup(world, model)
    cats = list(world.categories)
    if category == 'cup':
        cups = [k for k, cat in enumerate(cats) if cat in task_spec.CUP_CATEGORIES]
        k = min(cups, key=lambda i: task_spec.CLASS_EXTENTS[cats[i]][0])
    else:
        k = cats.index(task_spec.TARGET_CATEGORY)
    body, cat = world.objects[k], cats[k]
    half = task_spec.CLASS_EXTENTS[cat][0] / 2.0

    for j, q in zip(model.arm_joints, DEFAULT_ARM_POS):
        p.resetJointState(robot, j, q, physicsClientId=c)
        p.setJointMotorControl2(robot, j, p.POSITION_CONTROL, targetPosition=q,
                                force=ARM_HOLD_FORCE_N, physicsClientId=c)
    for fj in model.finger_joints:
        p.resetJointState(robot, fj, half + 0.001, physicsClientId=c)
    ee = p.getLinkState(robot, model.ee_link, computeForwardKinematics=True,
                        physicsClientId=c)
    p.resetBasePositionAndOrientation(body, ee[4], ee[5], physicsClientId=c)
    p.resetBaseVelocity(body, [0, 0, 0], [0, 0, 0], physicsClientId=c)
    for fj in model.finger_joints:
        p.setJointMotorControl2(robot, fj, p.POSITION_CONTROL,
                                targetPosition=half - SQUEEZE_INSIDE_M,
                                force=CLOSE_FORCE_N, physicsClientId=c)
    for _ in range(SETTLE_STEPS):
        p.stepSimulation(physicsClientId=c)
    assert scoring.held_body(c, robot) == body, 'the control hold did not form'
    for n, (j, q) in enumerate(zip(model.arm_joints, DEFAULT_ARM_POS)):
        p.resetJointState(robot, j, q + (arm_offset if n == 0 else 0.0),
                          physicsClientId=c)
    return body, scoring.build_observation(env, store, c, robot)


def _reward(tmp_path, category, arm_offset=0.0):
    from tampura.symbolic import Action
    env, b0, store = _their_env(tmp_path)
    body, obs = _hold(env, store, category, arm_offset)
    bp = b0.update(Action(bridge_policy.SCHEMA_NAME, []), obs, store)
    return obs, env.problem_spec.get_reward(bp.abstract(store), store)


def test_1_positive_die_hold_scores_one(tmp_path):
    obs, reward = _reward(tmp_path, 'die')
    assert obs.grasp_body is not None and obs.grasp is not None
    assert reward == 1.0


def test_2_positive_cup_hold_scores_zero(tmp_path):
    obs, reward = _reward(tmp_path, 'cup')
    assert obs.grasp_body is not None        # the cup IS held
    assert reward == 0.0


def test_1b_die_hold_off_home_scores_zero(tmp_path):
    obs, reward = _reward(tmp_path, 'die', arm_offset=2e-3)
    assert obs.grasp_body is not None
    assert reward == 0.0


@pytest.mark.skip(reason='fault injection runs with B7 full episodes (GF4)')
def test_3_fault_go_home_without_path_scores_zero():
    pass


@pytest.mark.skip(reason='fault injection runs with B7 full episodes (GF4)')
def test_4_fault_failed_lift_scores_zero():
    pass


@pytest.mark.skip(reason='fault injection runs with B7 full episodes (GF4)')
def test_5_fault_slip_after_lift_scores_zero():
    pass


def test_readback_check():
    gate_hooks.reset_counts()
    q = [0.1, -0.2, 0.3]
    assert gate_hooks.check_readback(q, list(q)) and gate_hooks.counts() == {}
    assert not gate_hooks.check_readback(q, [0.1, -0.2, 0.3 + 1e-12])
    assert gate_hooks.counts() == {'G6': 1}


def test_rollout_history_loads_in_their_venv(tmp_path):
    """G6 / D12: arm O's driver (seed 0, stop before planning) writes their
    RolloutHistory pickle; arm T's python loads it with only their trees on
    PYTHONPATH, from a directory outside this repository."""
    env = dict(os.environ, PYTHONHASHSEED='0', BOXEL_EYE_IMAGES='0')
    out = tmp_path / 'armO'
    r = subprocess.run(
        [os.sys.executable, os.path.join(REPO, 'tampura_bridge',
                                         'run_bridge_on_finddice.py'),
         '--global-seed', '0', '--vis', '0', '--stop-before-planning', '1',
         '--save-dir', str(out)], env=env, capture_output=True, text=True,
        timeout=900)
    pkls = glob.glob(str(out / '*.pkl'))
    assert len(pkls) == 1, r.stdout[-2000:] + r.stderr[-2000:]
    their_env = {k: v for k, v in env.items() if k != 'PYTHONPATH'}
    their_env['PYTHONPATH'] = f"{TW}/tampura:{TW}/tampura_environments"
    load = ("import pickle, sys; h = pickle.load(open(sys.argv[1], 'rb')); "
            "print(type(h).__module__, len(h.rewards), h.rewards[-1]); "
            "assert not any('tampura_bridge' in m for m in sys.modules)")
    r2 = subprocess.run([os.path.join(TW, '.venv', 'bin', 'python'), '-c', load,
                         pkls[0]], env=their_env, cwd=str(tmp_path),
                        capture_output=True, text=True, timeout=300)
    assert r2.returncode == 0, r2.stderr[-2000:]
    assert r2.stdout.startswith('tampura.policies.policy')
