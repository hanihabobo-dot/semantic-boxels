"""#P4 GF9 (BF#14): B3's test (4), the adopted goal_at_home episode with held
cargo and a corrective move, run under gate_hooks.install with the bridge's
GateConfig shape (policy.make_execute_fn).  The gate record must be empty
and the ledger reader green.  Kept as the regression test for B4 to B6.
It also times is_config_collision_free on the plan twin with and without
the hooks, and reports main()'s plan() times.  Our scene only (B3's
random-pairs seed), so nothing is fitted to their layouts.
"""
import importlib.util
import json
import os
import time

import pybullet as p

import robot_utils
import telemetry
import test_full_pipeline as tfp
import world_eye
from run_logger import RunLogger, parse_pipeline_args
from tampura_bridge import gate_hooks
from tampura_bridge.env_adapter import PoselessObjectInfo, TampuraWorldEnv
from tampura_bridge.tests.test_b3_parameterisation import (  # noqa: F401
    SEED, AdoptedEnv, world)

REPO = gate_hooks.REPO
_spec = importlib.util.spec_from_file_location(
    '_bridge_gates_gf9', os.path.join(REPO, 'tools', 'bridge_gates.py'))
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)

N_TIMED = 200


class GatedAdoptedEnv(AdoptedEnv):
    """B3's adopted env with the bridge adapter's oracle overrides (G16):
    oracle_detect_objects raises, update_object_positions is the counted
    no-op, and every ObjectInfo is poseless."""
    oracle_detect_objects = TampuraWorldEnv.oracle_detect_objects
    update_object_positions = TampuraWorldEnv.update_object_positions

    def _adopt_scene(self):
        super()._adopt_scene()
        for n, i in list(self.objects.items()):
            self.objects[n] = PoselessObjectInfo(
                object_id=i.object_id, name=n, position=None, orientation=None,
                size=i.size, is_visible=i.is_visible, is_occluder=i.is_occluder,
                is_tray=i.is_tray)


def _time_collision_checks(env):
    rid = env.plan_robot_id
    q = [p.getJointState(rid, j, physicsClientId=env.plan_client_id)[0]
         for j in robot_utils.robot_model().arm_joints]
    t0 = time.perf_counter()
    for _ in range(N_TIMED):
        robot_utils.is_config_collision_free(rid, q, physics_client=env.plan_client_id,
                                             log_collisions=False)
    return (time.perf_counter() - t0) / N_TIMED


def test_gated_goal_at_home_episode(world, tmp_path, monkeypatch):
    src, shown, _ = world
    env = GatedAdoptedEnv(src)
    env.shadow_raycast_client = env.plan_client_id
    names = {i.object_id: n for n, i in env.objects.items()}
    robot = env.objects['robot'].object_id
    task = frozenset(i.object_id for n, i in env.objects.items()
                     if n not in ('plane', 'table', 'robot') and not i.is_tray)

    # The injected at-home miss of B3's test (4).
    calls = []
    orig_read = tfp.arm_joint_positions

    def readback(*a, **k):
        q = orig_read(*a, **k)
        calls.append(1)
        if len(calls) == 2:
            q = q.copy()
            q[0] += 5e-3
        return q
    monkeypatch.setattr(tfp, 'arm_joint_positions', readback)

    t_plain = _time_collision_checks(env)
    tfp.args = parse_pipeline_args(['--no-gui', '--scene', 'random-pairs',
                                    '--seed', str(SEED), '--goal', 'holding',
                                    '--log-level', 'quiet'])
    logger = RunLogger(verbosity='quiet', log_dir=str(tmp_path / 'logs'))

    def has_object_boxel(body):
        reg = gate_hooks.latest_registry()
        return (reg is not None and body in names
                and reg.get_boxel(names[body]) is not None)

    view, proj = env._view_and_projection_matrices()
    try:
        gate_hooks.install(gate_hooks.GateConfig(
            executing_client=env.client_id, robot_id=robot,
            arm_joints=tuple(robot_utils.robot_model().arm_joints),
            task_body_ids=task, has_object_boxel=has_object_boxel,
            camera_view=tuple(view), camera_proj=tuple(proj),
            mission_goal=('and', ('holding', shown), ('at_config', 'q_home')),
            target_symbol=shown))
        gate_hooks.set_phase('main')
        t_gated = _time_collision_checks(env)
        t0 = time.perf_counter()
        out = tfp.main(gui=False, run_logger=logger, goal_kind='holding',
                       draw_boxel_overlays=False, env=env, target_name=shown,
                       oracle_phases=False, gui_hold_s=0, goal_at_home=True,
                       held_cargo_resolve=True, home_hold_step_cap=2400)
        t_main = time.perf_counter() - t0
        gate_hooks.set_phase('post')
        record = gate_hooks.gate_record()
    finally:
        gate_hooks.uninstall()
        telemetry.disable()
        world_eye.disable()
        logger.close()

    assert record['counts'] == {}, record
    report = bg.Report()
    bg.run_ledger(report, str(logger.run_dir))
    report.show()
    assert not report.failed(), report.rows

    rows = [json.loads(line) for line in
            open(logger.run_dir / 'ledger.jsonl', encoding='utf-8')]
    tests = [r for r in rows if r['kind'] == 'at_home_test']
    assert tests and tests[0]['passed'] is False       # the injected miss
    assert any(r['kind'] == 'step' and r['action'] == 'move'
               and r['args'][:2] == ['cfg:q_readback_1', 'cfg:q_home']
               for r in rows)                          # the corrective move
    plan_s = [round(r['plan_time_s'], 3) for r in rows
              if r['kind'] == 'plan' and r.get('plan_time_s') is not None]
    timing = {'is_config_collision_free_ms': {'plain': round(t_plain * 1e3, 4),
                                              'gated': round(t_gated * 1e3, 4)},
              'plan_s': plan_s, 'main_s': round(t_main, 2),
              'steps': record['steps'], 'main_returned': out}
    print('[GF9] ' + json.dumps(timing))
    with open(logger.run_dir / 'gf9_timing.json', 'w') as f:
        json.dump(timing, f, indent=1)
