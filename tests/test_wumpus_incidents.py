"""Rule 18 in the Wumpus env (wumpus/incidents.py): drops and collisions are
recorded, and recording them changes no action, pose or simulation step (the
same episodes with the detectors on and off).  The drops and collisions here
are made by the test's own hand between or inside actions.  Builds DIRECT
envs; run under `flock /root/sb_pipeline.lock` with the other env tests."""
import json

import numpy as np
import pybullet as p
import pytest

from wumpus import incidents as inc
from wumpus.env import STOW_Q, WumpusEnv
from wumpus.explore import run_explore
from wumpus.world import WumpusWorld

PIT = "(:hidden (wumpus-at p5-5) (pit-at p2-1) (gold-at p5-1))"
WUMPUS = "(:hidden (wumpus-at p1-2) (pit-at p5-4) (gold-at p5-1))"


def teleport(env, cell):
    """Place the base on a cell's centre (the checks stand the robot where they
    want it; no controller does this)."""
    c = env.cell_center(cell)
    env._place_base([c[0], c[1], 0.0])
    env._tick(2)


class Calls:
    """The env as a controller sees it: every call with its result (wall time left
    out), the pose after it and the simulation step count."""

    def __init__(self, env):
        self.env, self.log = env, []

    def cells(self):
        return self.env.cells()

    def adjacent(self):
        return self.env.adjacent()

    def robot_cell(self):
        return self.env.robot_cell()

    def _keep(self, name, arg, r):
        self.log.append((name, arg, {k: v for k, v in r.items() if k != 'wall_s'},
                         self.env.pose(), self.env.sim_steps))
        return r

    def perceive(self):
        return self._keep('perceive', None, self.env.perceive())

    def move(self, cell):
        return self._keep('move', cell, self.env.move(cell))

    def grab(self):
        return self._keep('grab', None, self.env.grab())


def state(env):
    """Where everything is at the end: every joint of the arm, the bar, the base."""
    c = env.cid
    joints = tuple(p.getJointState(env.panda, j, physicsClientId=c)[0]
                   for j in range(p.getNumJoints(env.panda, physicsClientId=c)))
    pos, orn = p.getBasePositionAndOrientation(env.bar, physicsClientId=c)
    return env.sim_steps, joints, tuple(pos), tuple(orn), tuple(float(v) for v in env.base_xyz)


def explore(env):
    calls = Calls(env)
    return run_explore(calls, max_steps=200), calls


def carry(env):
    """explore to the gold, then back one cell and in again with the bar held"""
    out, calls = explore(env)
    moves = [arg for name, arg, *_ in calls.log if name == 'move']
    here = env.robot_cell()
    calls.move(moves[-2] if len(moves) > 1 else 'p1-1')
    calls.move(here)
    return out, calls


def walk(cells):
    def play(env):
        calls = Calls(env)
        for c in cells:
            calls.move(c)
        calls.perceive()
        return None, calls
    return play


SCENES = {
    'explore': (lambda: WumpusWorld.random(5, 0), explore),
    'carry': (lambda: WumpusWorld.random(5, 0), carry),
    'pit': (lambda: WumpusWorld.from_hidden(5, PIT), walk(['p2-1', 'p1-1'])),
    'wumpus': (lambda: WumpusWorld.from_hidden(5, WUMPUS), walk(['p1-2'])),
}


@pytest.mark.parametrize('scene', sorted(SCENES))
def test_the_detectors_change_nothing(scene):
    """The same calls, results, poses, simulation steps and final state with the
    detectors on and off (as the narration's test does for the console)."""
    make, play = SCENES[scene]
    runs = []
    for detect in (True, False):
        env = WumpusEnv(make(), detect=detect)
        try:
            out, calls = play(env)
            runs.append((out, calls.log, state(env)))
        finally:
            env.close()
    assert runs[0] == runs[1]


def test_the_runner_records_a_clean_success(tmp_path):
    """explore on random(5, 0), the smoke's episode, wins with no drop and no
    collision, and episode.json says how both were looked for."""
    from wumpus import run_wumpus
    code = run_wumpus.main(['--size', '5', '--seed', '0', '--vis', '0', '--quiet', '--log-level', 'quiet',
                            '--log-dir', str(tmp_path / 'logs'), '--save-dir', str(tmp_path / 'save')])
    rec = json.loads((tmp_path / 'save' / 'episode.json').read_text(encoding='utf-8'))
    assert code == 0 and rec['outcome']['outcome'] == 'success'
    assert rec['incidents'] == [], rec['incidents']
    assert (rec['drops'], rec['collisions'], rec['clean_success']) == (0, 0, True)
    assert rec['drop_detector'] == inc.DROP_DETECTOR
    assert rec['collision_detector'] == inc.COLLISION_DETECTOR


def test_without_detectors_the_record_says_not_detected():
    env = WumpusEnv(WumpusWorld.random(5, 0), detect=False)
    try:
        env.move('p1-2')
    finally:
        env.close()
    rec = inc.record(env, True)
    assert rec['drops'] is None and rec['collisions'] is None and rec['incidents'] == []
    assert rec['drop_detector'] == rec['collision_detector'] == 'not detected'
    assert rec['clean_success'] is None


def test_a_drive_with_the_bar_held_drops_it_and_the_record_says_so():
    """The base is placed kinematically (2.5 cm steps), so the friction grip cannot
    follow it: a drive with the bar held loses the bar (explore and LW1 end at
    the grab, so no run of theirs drives with it).  One drop, at that move's end."""
    env = WumpusEnv(WumpusWorld.random(5, 0))
    try:
        out = run_explore(env, max_steps=200)
        assert out['outcome'] == 'success' and env.incidents == []
        env.move('p1-2')
        assert env.drops == 1, env.incidents
        d = env.incidents[0]
        assert (d['kind'], d['body'], d['action'], d['robot_cell']) == ('drop', 'gold', 'move', 'p1-2')
    finally:
        env.close()


def test_a_held_bar_that_leaves_the_grip_is_one_drop():
    """Held after the grab; the test opens the fingers between two actions; the
    next action's end finds the grab's test failing: one drop, counted once."""
    w = WumpusWorld.random(5, 0)
    env = WumpusEnv(w)
    try:
        teleport(env, w.gold)
        assert env.grab()['held']
        assert env.incidents == []
        env._open()                              # the test's hand: the bar falls
        env.grab()                               # 'already holding' (the env's own word)
        assert (env.drops, env.collisions) == (1, 0), env.incidents
        (d,) = env.incidents
        assert d['kind'] == 'drop' and d['body'] == 'gold' and d['action'] == 'grab'
        assert d['how'].startswith('the bar left the gripper (pads ')
        env.grab()
        assert env.drops == 1
        assert inc.record(env, True)['clean_success'] is False
    finally:
        env.close()


def test_a_bar_lost_in_the_stow_is_one_drop(monkeypatch):
    """Held after the lift, lost in the stow (the test opens the fingers as the
    stow starts): grab's own test fails, the grab holds nothing, one drop."""
    w = WumpusWorld.random(5, 0)
    env = WumpusEnv(w)
    try:
        teleport(env, w.gold)
        move_arm = env._move_arm

        def stow_with_open_fingers(q, **kw):
            if np.allclose(q, STOW_Q):
                env._open()
            return move_arm(q, **kw)
        monkeypatch.setattr(env, '_move_arm', stow_with_open_fingers)
        r = env.grab()
        assert not r['held'] and r['why'].startswith('the bar is not held'), r
        assert (env.drops, env.collisions) == (1, 0), env.incidents
        (d,) = env.incidents
        assert d['how'].startswith('the bar left the gripper in the stow') and d['action'] == 'grab'
    finally:
        env.close()


def test_the_arm_touching_a_body_is_one_collision_per_action():
    """A fixed box where the stowed hand is (the test's, outside the chassis
    check): the first move touches it once, the move back touches it again, and
    a move that starts in touch with it adds nothing."""
    env = WumpusEnv(WumpusWorld.random(5, 0))
    try:
        c = env.cid
        hand = p.getLinkState(env.panda, env.model.ee_link, physicsClientId=c)[0]
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.03] * 3, physicsClientId=c)
        box = p.createMultiBody(0, col, -1, list(hand), physicsClientId=c)
        env.bodies[box] = ('wall', '')
        assert env.move('p2-1')['ok']
        assert (env.drops, env.collisions) == (0, 1), env.incidents
        (h,) = env.incidents
        assert (h['kind'], h['how'], h['body'], h['action']) == ('collision', 'the arm touched it', 'wall', 'move')
        assert h['robot_cell'] == 'p1-1' and h['sim_step'] > 0
        env.move('p1-1')                          # back into the box
        assert env.collisions == 2
        if env._arm_touching():                   # still in touch: not new for the next move
            env.move('p2-1')
            assert env.collisions == 2
    finally:
        env.close()


def test_the_chassis_entering_a_fixed_box_is_a_collision():
    """The chassis has no collision shape; a low fixed box in the next cell (below
    the arm) is seen by the box check alone."""
    env = WumpusEnv(WumpusWorld.random(5, 0))
    try:
        ctr = env.cell_center('p2-1')
        env._box([0.05, 0.05, 0.04], [ctr[0], ctr[1], 0.07], (1, 0, 0, 1), kind='wall', cell='p2-1')
        assert env.move('p2-1')['ok']
        assert env.collisions == 1, env.incidents
        (h,) = env.incidents
        assert (h['how'], h['body'], h['body_cell']) == ('the chassis entered its box', 'wall', 'p2-1')
    finally:
        env.close()


def test_the_bar_off_its_pedestal_while_never_held_is_one_collision():
    """The test's hand lays the bar on the floor between two actions: the next
    action's end sees it moved and lying low, one collision, and once only."""
    w = WumpusWorld.random(5, 0)
    env = WumpusEnv(w)
    try:
        g = env.cell_center(w.gold)
        p.resetBasePositionAndOrientation(env.bar, [g[0] + 0.38, g[1] - 0.2, 0.013], [0, 0, 0, 1],
                                          physicsClientId=env.cid)
        env.move('p1-2')
        assert (env.drops, env.collisions) == (0, 1), env.incidents
        (h,) = env.incidents
        assert h['body'] == 'gold' and h['how'].startswith('the bar moved ') and h['how'].endswith('never held')
        env.move('p1-1')
        assert env.collisions == 1
    finally:
        env.close()
