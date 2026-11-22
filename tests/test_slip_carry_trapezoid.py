"""BF#59 carry_trapezoid: one acceleration-bounded schedule per move made
while holding (test_full_pipeline's move action, stream_move_waypoints).

The schedule is checked on synthetic joint-space paths (no world); the
move action's streaming is checked with move_robot_smooth, the joint
readback and the robot model stubbed, so the calls can be counted."""
import ast
import inspect
import logging
import re
import types

import numpy as np
import pytest

import slip_fixes
import test_full_pipeline as tfp
import robot_utils

DT = robot_utils.SIM_TIMESTEP
VMAX = robot_utils.JOINT_VELOCITY_LIMITS
AMAX = tfp.CARRY_TRAP_ACCEL_LIMITS


@pytest.fixture
def switch():
    """The registry as the import left it, every switch off for the test;
    ENABLED and KNOWN restored after."""
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    slip_fixes.configure('none')
    yield slip_fixes
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


def _wp(q):
    return types.SimpleNamespace(joint_positions=np.asarray(q, dtype=float))


def _with_rest(q0, commands):
    """The commanded sequence with the arm at rest before and after."""
    return np.array([q0, q0] + list(commands) + [commands[-1], commands[-1]])


Q0 = np.array([0.6, 0.3, -0.2, -2.0, 0.1, 2.0, -2.4])
HOME = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785])


def test_registered_and_off_by_default(switch):
    assert 'carry_trapezoid' in switch.KNOWN
    assert not switch.on('carry_trapezoid')
    assert 'carry_trapezoid' not in switch.configure('')      # not one of BF#62's four
    assert switch.configure('carry_trapezoid') == {'carry_trapezoid'}
    assert switch.on('carry_trapezoid')


def test_a_straight_path_merges_to_one_segment_without_a_rest():
    pts = [Q0, 0.5 * (Q0 + HOME), HOME]
    commands, vertices = tfp.carry_trapezoid_schedule(pts)
    assert len(vertices) == 2                              # one segment
    np.testing.assert_allclose(vertices[0], Q0)
    np.testing.assert_allclose(vertices[1], HOME)
    np.testing.assert_allclose(commands[-1], HOME, atol=1e-12)
    # no rest in the middle: the commanded speed at the middle waypoint is
    # the cruise speed, not zero
    speed = np.linalg.norm(np.diff(np.array(commands), axis=0), axis=1)
    mid = int(np.argmin(np.linalg.norm(np.array(commands) - pts[1], axis=1)))
    assert speed[min(mid, len(speed) - 1)] > 0.5 * speed.max()
    # the 10 waypoints of _linear_trajectory are one segment too
    lin = [Q0 + (HOME - Q0) * t for t in np.linspace(0.0, 1.0, 10)]
    assert len(tfp.carry_trapezoid_schedule(lin)[1]) == 2


def test_a_bent_path_rests_at_the_bend():
    bend = 0.5 * (Q0 + HOME) + np.array([0.25, -0.35, 0.0, 0.25, 0.0, 0.0, 0.0])
    pts = [Q0, bend, HOME]
    commands, vertices = tfp.carry_trapezoid_schedule(pts)
    assert len(vertices) == 3                              # two segments, one rest
    cmd = np.array(commands)
    k = [i for i, c in enumerate(cmd) if np.allclose(c, bend, rtol=0.0, atol=1e-12)]
    assert len(k) == 1                                     # the bend is commanded exactly
    k = k[0]
    # at rest there: the steps on either side are within half a step of
    # the bound's acceleration from it (zero velocity at the bend)
    for nb in (cmd[k - 1], cmd[k + 1]):
        assert np.all(np.abs(nb - bend) <= 0.5 * AMAX * DT ** 2 * (1 + 1e-9) + 1e-15)
    np.testing.assert_allclose(cmd[-1], HOME, atol=1e-12)


@pytest.mark.parametrize('pts', [
    [Q0, HOME],
    [Q0, 0.5 * (Q0 + HOME), HOME],
    [Q0, 0.5 * (Q0 + HOME) + np.array([0.25, -0.35, 0, 0.25, 0, 0, 0]), HOME],
    [Q0, Q0 + np.array([0.01, 0, 0, 0, 0, 0, 0.002])],              # a short hop: a triangle
    [Q0, Q0 + 0.3, Q0 + np.array([0.3, 0.3, 0.3, 0.3, 0.3, 0.3, -0.5]), HOME],
])
def test_the_acceleration_and_velocity_bounds_hold_along_the_schedule(pts):
    commands, _ = tfp.carry_trapezoid_schedule(pts)
    seq = _with_rest(np.asarray(pts[0], dtype=float), commands)
    vel = np.abs(np.diff(seq, axis=0)) / DT
    acc = np.abs(seq[2:] - 2 * seq[1:-1] + seq[:-2]) / DT ** 2
    assert np.all(vel <= VMAX * (1 + 1e-9) + 1e-9)
    assert np.all(acc <= AMAX * (1 + 1e-6) + 1e-6)
    np.testing.assert_allclose(seq[-1], np.asarray(pts[-1], dtype=float), atol=1e-12)


def test_the_bound_is_reached_on_a_long_carry():
    # the schedule is not slower than it has to be: the slowest-bound
    # joint reaches its velocity limit on a wrist-heavy carry
    commands, _ = tfp.carry_trapezoid_schedule([Q0, HOME])
    vel = np.abs(np.diff(np.array([Q0] + list(commands)), axis=0)) / DT
    assert np.max(vel / VMAX) > 0.99


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, robot_id, target, gui=False, steps=60, settle=False,
                 velocity_bounded=True, on_step=None):
        self.calls.append(dict(target=np.asarray(target, dtype=float)[:7], steps=steps,
                               settle=settle, velocity_bounded=velocity_bounded))
        if on_step is not None:
            on_step()


@pytest.fixture
def stubbed(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(tfp, 'move_robot_smooth', rec)
    monkeypatch.setattr(tfp, 'robot_model',
                        lambda: types.SimpleNamespace(arm_joints=list(range(7))))
    fake_p = types.SimpleNamespace(getJointState=lambda body, j: (float(Q0[j]), 0.0, None, 0.0))
    monkeypatch.setattr(tfp, 'p', fake_p)
    return rec


def _linear_traj(n=10):
    return [_wp(Q0 + (HOME - Q0) * t) for t in np.linspace(0.0, 1.0, n)]


@pytest.mark.parametrize('on,holding', [(False, True), (False, False), (True, False)])
def test_off_or_empty_handed_the_stream_is_todays(switch, stubbed, on, holding):
    if on:
        switch.configure('carry_trapezoid')
    traj = _linear_traj(10)
    tfp.stream_move_waypoints(0, traj, False, holding=holding)
    assert len(stubbed.calls) == 9                         # one call per pair
    assert all(c['steps'] == 30 and c['velocity_bounded'] for c in stubbed.calls)
    assert [c['settle'] for c in stubbed.calls] == [False] * 8 + [True]
    for c, wp in zip(stubbed.calls, traj[1:]):
        np.testing.assert_array_equal(c['target'], wp.joint_positions)


def test_on_and_holding_one_schedule_then_todays_settle(switch, stubbed, caplog):
    switch.configure('carry_trapezoid')
    traj = _linear_traj(10)
    ticks = []
    with caplog.at_level(logging.INFO, logger='test_full_pipeline'):
        tfp.stream_move_waypoints(0, traj, False, holding=True,
                                  on_step=lambda: ticks.append(1))
    commands, vertices = tfp.carry_trapezoid_schedule(
        [Q0] + [w.joint_positions for w in traj[1:]])
    calls = stubbed.calls
    assert len(calls) == len(commands) + 1
    assert all(c['steps'] == 1 and not c['settle'] and not c['velocity_bounded']
               for c in calls[:-1])
    assert calls[-1]['settle'] and calls[-1]['steps'] == 1
    np.testing.assert_array_equal(calls[-1]['target'], traj[-1].joint_positions)
    assert len(ticks) == len(calls)                        # on_step on every step
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith('carry_trapezoid:')]
    assert len(lines) == 1
    assert re.search(r"10 waypoints in \(readback \+ 9\), 1 segment\(s\) after merging, "
                     r"0 rest\(s\) inserted, %d schedule steps \+ 1 settle steps" % len(commands),
                     lines[0])


def _reached_from_main(stages):
    """The names of the functions cut out of main() that main() reaches: it
    calls them by name, or a function it reaches does."""
    by_name = {f.__name__: f for f in stages}
    seen, todo = set(), [tfp.main]
    while todo:
        for c in ast.walk(ast.parse(inspect.getsource(todo.pop()))):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) \
                    and c.func.id in by_name and c.func.id not in seen:
                seen.add(c.func.id)
                todo.append(by_name[c.func.id])
    return seen


def test_the_move_action_calls_the_stream_with_the_held_body():
    # The move action is do_move, cut out of main(); the names are fields of
    # the episode state st.
    src = inspect.getsource(tfp.do_move)
    assert re.search(r"stream_move_waypoints\(st\.setup\.robot_id, traj\.waypoints, st\.opts\.gui,\s*"
                     r"holding=st\.hand\.held_body_id is not None\)", src)
    # The stream lives in the helper: main() and every function cut out of
    # it (its first parameter is st) are without the call, as main() was.
    stages = [f for f in vars(tfp).values() if inspect.isfunction(f)
              and next(iter(inspect.signature(f).parameters), None) == 'st']
    assert tfp.do_move in stages
    # The tie to main(): main() reaches do_move through the functions cut out
    # of it that it calls by name (the plan's loop and its dispatcher).
    assert 'do_move' in _reached_from_main(stages)
    for fn in [tfp.main] + stages:
        assert 'move_robot_smooth(' not in inspect.getsource(fn), fn.__name__
