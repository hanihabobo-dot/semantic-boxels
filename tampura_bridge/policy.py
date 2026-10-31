"""#P4 D2: BoxelBridgePolicy and the boxel_episode schema (PAPER_AUDIT.txt
P4.3 D2, P4.4 B2).

The policy returns ONE action per episode, boxel_episode at t=0, and their
no-op afterwards; their rollout, env.step, Belief.update and get_reward run
untouched.  boxel_episode is a schema with no preconditions and identity
effects whose execute_fn runs our whole episode inside their executing
world:
  1. the run logger and its ledger, work/ in its run directory as the
     working directory until execute_fn returns, the episode row (seed,
     scene file),
     the driver's clock and RNG record (G18, G19), and the runtime gate
     hooks (phase 'setup');
  2. D9's set-up, in order, before any physics step: gravity, timestep,
     every task body's class mass, inertia and friction, our pad friction
     and finger opening;
  3. phase 'main' from here: the env adapter (B3(b)'s adopt path) and
     main(), which
     settles (D9 (5)), runs the after_settle check, renders, boxelizes and
     plans, acts and senses;
  4. the terminal observation from physical readback (scoring.py, phase
     'post'), its conf checked bit for bit against the arm readback taken
     when main() returned (G6), and the gate record (G21).
It returns the SceneState it received and that observation.
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pybullet as p

import m8_domain
import robot_utils
import slip_fixes          # BF#59 force_hold (the campaign's switches)
import telemetry
import test_full_pipeline
import world_eye
from run_logger import RunLogger, ledger_event, parse_pipeline_args
from tampura_bridge import gate_hooks, scoring, task_spec
from tampura_bridge.env_adapter import TampuraWorldEnv, symbol_names

SCHEMA_NAME = 'boxel_episode'


@dataclass
class EpisodeConfig:
    seed: int
    scene_file: str
    log_dir: str
    vis: bool = False
    stop_before_planning: bool = False
    log_level: str = 'smart'
    max_plan_time: float = 900.0
    # M8-M10's switches as main()'s CLI flags: {'m8': 'on'|'off', ...}.
    switches: dict = field(default_factory=dict)
    out: dict = field(default_factory=dict)
    # The driver's clock stamps and RNG record (G18, G19's seed hygiene),
    # written to the ledger as its driver_clock row.
    driver: dict = field(default_factory=dict)


def d9_setup(world, model):
    """D9 steps (1) to (4) on the executing client, before any step."""
    c = world.client._client
    p.setGravity(0, 0, task_spec.GRAVITY_Z, physicsClientId=c)
    p.setTimeStep(task_spec.TIMESTEP, physicsClientId=c)
    for body, cat in zip(world.objects, world.categories):
        p.changeDynamics(body, -1, mass=task_spec.CLASS_MASS_KG[cat],
                         localInertiaDiagonal=list(task_spec.CLASS_INERTIA_DIAG[cat]),
                         lateralFriction=task_spec.OBJECT_LATERAL_FRICTION,
                         physicsClientId=c)
    for fj in model.finger_joints:
        p.changeDynamics(world.robot.body, fj,
                         lateralFriction=task_spec.PAD_LATERAL_FRICTION,
                         physicsClientId=c)
        p.resetJointState(world.robot.body, fj, task_spec.FINGER_OPEN,
                          physicsClientId=c)
    # BF#59 force_hold (slip_fixes.py; finger_gear folded in): their URDF
    # couples the fingers (panda.urdf line 356, <mimic
    # joint="panda_finger_joint1"/>) and PyBullet ignores the tag, so a
    # JOINT_GEAR constraint realises it on the executing client, here in
    # phase 'setup' before any step (after set_phase('main') G14 would
    # refuse it).  Only the executing client steps; the plan twin and the kin
    # stream need no gear.  Constants in robot_utils (FINGER_GEAR_*).
    if slip_fixes.on('force_hold'):
        robot_utils.force_hold_requires_solver_iters('d9_setup')
        f1, f2 = model.finger_joints
        gear = p.createConstraint(world.robot.body, f1, world.robot.body, f2,
                                  jointType=p.JOINT_GEAR, jointAxis=[1, 0, 0],
                                  parentFramePosition=[0, 0, 0],
                                  childFramePosition=[0, 0, 0], physicsClientId=c)
        p.changeConstraint(gear, gearRatio=robot_utils.FINGER_GEAR_RATIO,
                           erp=robot_utils.FINGER_GEAR_ERP,
                           maxForce=robot_utils.FINGER_GEAR_MAX_FORCE, physicsClientId=c)
        logging.getLogger(__name__).info(
            "force_hold: finger gear constraint %d on client %d (joints %d, %d, "
            "gearRatio %g, erp %g, maxForce %g N)", gear, c, f1, f2,
            robot_utils.FINGER_GEAR_RATIO, robot_utils.FINGER_GEAR_ERP,
            robot_utils.FINGER_GEAR_MAX_FORCE)


def _poses(world):
    """Write-only (G2): every task body's simulator pose, for the settle
    disclosure only."""
    c = world.client._client
    return {b: p.getBasePositionAndOrientation(b, physicsClientId=c)
            for b in world.objects}


def make_after_settle(world, before, out):
    """D9's read-only check between main()'s settle and its first render:
    the die must be absent from the eye's segmentation; every task body's
    settle displacement is logged (disclosure threshold 1 cm).  It renders
    through the env's own eye and reads poses write-only; it moves and
    steps nothing."""
    names = dict(zip(world.objects, symbol_names(list(world.categories))))
    target = [b for b, cat in zip(world.objects, world.categories)
              if cat == task_spec.TARGET_CATEGORY]

    def after_settle(env):
        with gate_hooks.write_only('after_settle'):
            view, proj = env._view_and_projection_matrices()
            seg = np.asarray(p.getCameraImage(
                env.image_width, env.image_height, viewMatrix=view,
                projectionMatrix=proj, renderer=p.ER_TINY_RENDERER,
                physicsClientId=env.client_id)[4]).reshape(
                    env.image_height, env.image_width)
            after = _poses(world)
            disp = {}
            for b, (p0, o0) in before.items():
                p1, o1 = after[b]
                e0, e1 = p.getEulerFromQuaternion(o0), p.getEulerFromQuaternion(o1)
                dyaw = (e1[2] - e0[2] + np.pi) % (2 * np.pi) - np.pi
                disp[names[b]] = {
                    'dxy_m': round(float(np.hypot(p1[0] - p0[0], p1[1] - p0[1])), 4),
                    'dz_m': round(float(p1[2] - p0[2]), 4),
                    'dyaw_deg': round(float(np.degrees(dyaw)), 2),
                    'tilt_deg': round(float(np.degrees(max(abs(e1[0]), abs(e1[1])))), 2)}
            visible = bool(target) and bool(np.any(seg == target[0]))
            out['scene_changed_by_settle'] = visible
            out['settle'] = disp
            out['settle_max_dxy_m'] = max(d['dxy_m'] for d in disp.values())
            ledger_event('after_settle', scene_changed_by_settle=visible,
                         settle=disp)
            if visible:
                print("  [D9] the die is VISIBLE to the eye after the settle: "
                      "scene_changed_by_settle (reported in its own row)")
    return after_settle


def make_execute_fn(their_env, cfg: EpisodeConfig):
    def execute_fn(action, belief, state, store):
        world = their_env.world
        c = world.client._client
        robot = world.robot.body
        t0 = time.perf_counter()
        logger = RunLogger(verbosity=cfg.log_level, log_dir=cfg.log_dir)
        cfg.out['run_dir'] = str(logger.run_dir)
        observation = None
        # GF8: main() writes boxel_data.json and pddlstream its temp/ and
        # statistics/ into the working directory; they go to work/ under our
        # run directory (main() copies boxel_data.json into the run
        # directory itself), never into their tree.
        cwd = os.getcwd()
        try:
            work = os.path.join(str(logger.run_dir), 'work')
            os.makedirs(work, exist_ok=True)
            os.chdir(work)
            ledger_event('episode', seed=cfg.seed, scene_file=cfg.scene_file)
            ledger_event('driver_clock', **cfg.driver)
            model = robot_utils.resolve_robot_model(robot, c)
            robot_utils.use_robot_model(model)
            names = symbol_names(list(world.categories))
            by_body = dict(zip(world.objects, names))
            target = [n for n, cat in zip(names, world.categories)
                      if cat == task_spec.TARGET_CATEGORY]

            def has_object_boxel(body):
                reg = gate_hooks.latest_registry()
                name = by_body.get(body)
                return (reg is not None and name is not None
                        and reg.get_boxel(name) is not None)

            # G20: the declared eye's matrices, computed exactly as the
            # env computes them (BoxelTestEnv._view_and_projection_matrices).
            view = p.computeViewMatrix(
                cameraEyePosition=np.array(task_spec.EYE_POSITION),
                cameraTargetPosition=np.array(task_spec.EYE_TARGET),
                cameraUpVector=np.array(task_spec.EYE_UP))
            proj = p.computeProjectionMatrixFOV(
                fov=task_spec.EYE_FOV_DEG,
                aspect=task_spec.EYE_WIDTH / task_spec.EYE_HEIGHT,
                nearVal=task_spec.EYE_NEAR, farVal=task_spec.EYE_FAR)
            # B4 / M8: the domain the planner loads (the generated one
            # with M8 on), the same path for main() and G10's runtime pin.
            domain_file = m8_domain.domain_file(cfg.switches.get('m8', 'on') == 'on')
            gate_hooks.install(gate_hooks.GateConfig(
                executing_client=c, robot_id=robot,
                arm_joints=tuple(model.arm_joints),
                task_body_ids=frozenset(world.objects),
                has_object_boxel=has_object_boxel,
                camera_view=tuple(view), camera_proj=tuple(proj),
                wrist_robots={c: robot},
                mission_goal=('and', ('holding', target[0]),
                              ('at_config', 'q_home')),
                target_symbol=target[0], domain_file=domain_file))
            with gate_hooks.write_only('settle_disclosure'):
                before = _poses(world)
            # BF#59 force_hold: the campaign's switches are set here as well,
            # before D9's set-up, because the finger gear must exist before
            # the first step; main() sets the same names again.
            slip_fixes.configure(cfg.switches.get('slip_fixes', ''))
            d9_setup(world, model)
            # GF6: only D9's calls run under 'setup'; the adapter build and
            # main() are checked by G3, G6 and G14.
            gate_hooks.set_phase('main')
            t_setup = time.perf_counter()
            env = TampuraWorldEnv(world, gui=cfg.vis)
            assert env.target_symbol() == target[0]
            # G20: the plan twin's wrist renders (M8's look test).
            gate_hooks.declare_wrist_robot(env.plan_client_id, env.plan_robot_id)
            ledger_event('bridge_timing', d9_setup_s=t_setup - t0,
                         env_build_s=time.perf_counter() - t_setup)
            test_full_pipeline.args = parse_pipeline_args([
                '--no-gui', '--goal', 'holding', '--log-level', cfg.log_level,
                '--max-plan-time', str(cfg.max_plan_time)]
                + [x for k, v in sorted(cfg.switches.items())
                   for x in (f"--{k.replace('_', '-')}", v)])
            from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
            test_full_pipeline.main(
                gui=cfg.vis, run_logger=logger, goal_kind='holding',
                draw_boxel_overlays=False, env=env, target_name=target[0],
                oracle_phases=False,
                after_settle=make_after_settle(world, before, cfg.out),
                stop_before_planning=cfg.stop_before_planning, gui_hold_s=0,
                home_joints=list(DEFAULT_ARM_POS), goal_at_home=True,
                held_cargo_resolve=True,
                home_hold_step_cap=task_spec.HOME_HOLD_STEP_CAP,
                telemetry_enabled=False, domain_file=domain_file)
            gate_hooks.set_phase('post')
            # G6: the arm at main() return, compared bit for bit with the
            # observation's conf below.
            with gate_hooks.scoring():
                q_main = [p.getJointState(robot, j, physicsClientId=c)[0]
                          for j in model.arm_joints]
            ledger_event('main_return_readback', conf=q_main)
            observation = scoring.build_observation(their_env, store, c, robot)
            cfg.out['observation'] = {'grasp_body': observation.grasp_body,
                                      'conf': observation.conf}
            cfg.out['readback_identical'] = gate_hooks.check_readback(
                q_main, observation.conf)
            cfg.out['gates'] = gate_hooks.gate_record()
        except Exception as e:
            cfg.out['error'] = f"{type(e).__name__}: {e}"
            logging.exception("boxel_episode failed")
            if gate_hooks.installed():
                cfg.out['gates'] = gate_hooks.gate_record()
        finally:
            os.chdir(cwd)
            gate_hooks.uninstall()
            world_eye.disable()
            telemetry.disable()
            logger.close()
        if observation is None:
            from tampura_environments.find_dice.env import SceneObservation
            with gate_hooks.scoring():
                q = [p.getJointState(robot, j, physicsClientId=c)[0]
                     for j in robot_utils.robot_model().arm_joints]
            observation = SceneObservation(camera_image=None, poses={},
                                           conf=[float(v) for v in q])
        return state, observation
    return execute_fn


def register_schema(their_env, execute_fn):
    """The one runtime registration of arm O (G13): boxel_episode, no
    preconditions, identity effects, our execute_fn."""
    from tampura.structs import ActionSchema
    spec = their_env.problem_spec
    assert not any(s.name == SCHEMA_NAME for s in spec.action_schemas)
    spec.action_schemas.append(ActionSchema(
        name=SCHEMA_NAME, inputs=[], input_types=[], preconditions=[],
        effects=[], execute_fn=execute_fn))


# BF#41: a GUI run's cleanup between their steps, set by the driver with
# --vis 1 and None when headless.  Their rollout redraws the belief's
# visibility grid as debug lines after every step (vis_updated_belief);
# that grid is their belief, which arm O never reads, so our get_action
# clears it before each step and the GUI shows the scene alone.
GUI_CLEANUP = None


def bridge_policy_class():
    from tampura.policies.policy import Policy
    from tampura.symbolic import Action

    class BoxelBridgePolicy(Policy):
        """boxel_episode at t=0, no-op afterwards (D2)."""

        def __init__(self, config, problem_spec, **kwargs):
            super().__init__(config, problem_spec, **kwargs)
            self._issued = False

        def get_action(self, belief, store):
            if GUI_CLEANUP is not None:
                GUI_CLEANUP()
            if not self._issued:
                self._issued = True
                return Action(SCHEMA_NAME, []), {}, store
            return Action('no-op', []), {}, store

    return BoxelBridgePolicy
