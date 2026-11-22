"""TB-22: telemetry's drop and collision counts, on a scripted simulator.

The observer reads the simulator through ``telemetry.p``; here that is a
scripted stand-in (contacts, poses and velocities set by the test), so the
counting is checked on synthetic events without an episode.  Body 0 is the
robot with finger links 9 and 10; bodies 5 and 6 are objects; body 99 is
the table (not in the observer's body list, like the pipeline's supports).
One check is two simulation steps (telemetry.EVENT_STRIDE).
"""
import json

import pybullet
import pytest

from console import telemetry

ROBOT, TABLE, BOX, CUP = 0, 99, 5, 6
PADS = (9, 10)
NAMES = {BOX: 'box', CUP: 'cup'}


class ScriptedSim:
    """The reads telemetry makes, answered from the test's script."""

    def __init__(self):
        self.pos = {BOX: [0.5, 0.0, 0.05], CUP: [0.6, 0.2, 0.05]}
        self.vel = {BOX: [0.0, 0.0, 0.0], CUP: [0.0, 0.0, 0.0]}
        self.contacts = set()            # (body a, body b, link a, link b)
        self.fingers = [0.02, 0.02]
        self.calls = []

    # -- the script ---------------------------------------------------------
    def pinch(self, body, pads=PADS, robot_first=True):
        self.release(body)
        for i, link in enumerate(pads):
            # every other contact pair in the opposite body order
            if robot_first and i == 0:
                self.contacts.add((ROBOT, body, link, -1))
            else:
                self.contacts.add((body, ROBOT, -1, link))

    def release(self, body):
        self.contacts = {c for c in self.contacts
                         if not ({c[0], c[1]} == {ROBOT, body})}

    def rest(self, body, on=TABLE):
        self.contacts.add((body, on, -1, -1))

    def lift(self, body):
        self.contacts = {c for c in self.contacts
                         if not (body in (c[0], c[1]) and ROBOT not in (c[0], c[1]))}

    # -- pybullet's reads ---------------------------------------------------
    def getContactPoints(self, bodyA=None, bodyB=None, physicsClientId=0):
        self.calls.append('getContactPoints')
        out = []
        for a, b, la, lb in sorted(self.contacts):
            if bodyA is not None and bodyA not in (a, b):
                continue
            if bodyB is not None and bodyB not in (a, b):
                continue
            out.append((0, a, b, la, lb, (0, 0, 0), (0, 0, 0), (0, 0, 1), 0.0, 1.0))
        return out

    def getBasePositionAndOrientation(self, bid, physicsClientId=0):
        self.calls.append('getBasePositionAndOrientation')
        return tuple(self.pos[bid]), (0.0, 0.0, 0.0, 1.0)

    def getBaseVelocity(self, bid, physicsClientId=0):
        self.calls.append('getBaseVelocity')
        return tuple(self.vel[bid]), (0.0, 0.0, 0.0)

    def getJointStates(self, robot, joints, physicsClientId=0):
        self.calls.append('getJointStates')
        if list(joints) == list(PADS):
            return [(f, 0.0, (), 0.0) for f in self.fingers]
        return [(0.0, 0.0, (), 0.0) for _ in joints]

    def getLinkState(self, robot, link, computeLinkVelocity=0,
                     computeForwardKinematics=0, physicsClientId=0):
        self.calls.append('getLinkState')
        z = ((0, 0, 0), (0, 0, 0, 1))
        return z + z + ((0.5, 0.0, 0.3), (0, 0, 0, 1), (0, 0, 0), (0, 0, 0))

    def getAABB(self, bid, physicsClientId=0):
        self.calls.append('getAABB')
        x, y, z = self.pos[bid]
        return (x - 0.02, y - 0.02, z - 0.02), (x + 0.02, y + 0.02, z + 0.02)

    getEulerFromQuaternion = staticmethod(pybullet.getEulerFromQuaternion)
    getMatrixFromQuaternion = staticmethod(pybullet.getMatrixFromQuaternion)


@pytest.fixture
def sim(monkeypatch):
    s = ScriptedSim()
    monkeypatch.setattr(telemetry, 'p', s)
    return s


def observer(run_dir=None, counts_only=True):
    return telemetry.WorldTelemetry(0, ROBOT, NAMES, run_dir,
                                    finger_joints=PADS, counts_only=counts_only)


def checks(tele, n):
    for _ in range(n * telemetry.EVENT_STRIDE):
        tele.tick()


def carry(sim, tele, body=BOX):
    """A verified pick: close, both pads on the body while it stands on the
    table, then the lift."""
    tele.gripper_command(opening=False)
    sim.rest(body)
    sim.pinch(body)
    checks(tele, 2)
    sim.lift(body)
    checks(tele, telemetry.CARRIED_CHECKS)


def n_drops(tele):
    return len(tele.counts()['drops'])


# ----- drops ---------------------------------------------------------------

def test_a_carried_body_that_leaves_the_pads_is_one_drop(sim):
    tele = observer()
    carry(sim, tele)
    assert n_drops(tele) == 0
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS - 1)
    assert n_drops(tele) == 0                 # not yet: a hold may flicker
    checks(tele, 1)
    assert n_drops(tele) == 1
    assert tele.counts()['drops'][0]['object'] == 'box'
    sim.rest(BOX)
    checks(tele, 20)                          # on the table for good: once
    assert n_drops(tele) == 1


def test_a_grasp_that_never_lifted_the_body_is_no_drop(sim):
    tele = observer()
    tele.gripper_command(opening=False)
    sim.rest(BOX)
    sim.pinch(BOX)
    checks(tele, 10)
    sim.release(BOX)                          # the pads slide off, it stays
    checks(tele, 10)
    assert n_drops(tele) == 0


def test_the_squeeze_of_a_grasp_is_no_carry(sim):
    # Off the table for fewer checks than CARRIED_CHECKS, then down again.
    tele = observer()
    tele.gripper_command(opening=False)
    sim.rest(BOX)
    sim.pinch(BOX)
    checks(tele, 2)
    sim.lift(BOX)
    checks(tele, telemetry.CARRIED_CHECKS - 1)
    sim.rest(BOX)
    checks(tele, 2)
    sim.release(BOX)
    checks(tele, 10)
    assert n_drops(tele) == 0


def test_the_release_of_a_place_is_no_drop(sim):
    tele = observer()
    carry(sim, tele)
    sim.rest(BOX)                             # lowered onto the table
    checks(tele, 3)
    tele.gripper_command(opening=True, placing=True)
    sim.release(BOX)
    checks(tele, 20)
    assert n_drops(tele) == 0


def test_a_place_that_lets_the_body_fall_the_last_bit_is_no_drop(sim):
    # The place opens above the support: still the release of a place.
    tele = observer()
    carry(sim, tele)
    tele.gripper_command(opening=True, placing=True)
    sim.release(BOX)
    checks(tele, 5)
    sim.rest(BOX)
    checks(tele, 5)
    assert n_drops(tele) == 0


def test_an_open_outside_a_place_drops_the_carried_body(sim):
    # The pipeline notices a body hanging on one pad and opens the gripper.
    tele = observer()
    carry(sim, tele)
    sim.pinch(BOX, pads=(PADS[0],))
    checks(tele, 4)
    assert n_drops(tele) == 0                 # one pad still holds it
    tele.gripper_command(opening=True)
    assert n_drops(tele) == 1
    assert 'outside the release of a place' in tele.counts()['drops'][0]['how']


def test_a_body_knocked_out_onto_another_body_is_a_drop(sim):
    # TB-23's second cause: the carry strikes a body; the held one leaves
    # the pads while it touches that body (GRIP_LOST asked for "touching
    # nothing" and missed it).
    tele = observer()
    carry(sim, tele)
    sim.rest(BOX, on=CUP)
    checks(tele, 1)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS)
    assert n_drops(tele) == 1


def test_a_loss_just_before_the_release_of_a_place(sim):
    # One check without the pads and off every support: it had left.
    tele = observer()
    carry(sim, tele)
    sim.release(BOX)
    checks(tele, 1)
    tele.gripper_command(opening=True, placing=True)
    assert n_drops(tele) == 1
    # One check without the pads while it stands on the table: a flicker
    # at the release, not a loss.
    tele = observer()
    carry(sim, tele, body=CUP)
    sim.rest(CUP)
    checks(tele, 2)
    sim.release(CUP)
    checks(tele, 1)
    tele.gripper_command(opening=True, placing=True)
    assert n_drops(tele) == 0


def test_no_grip_without_a_close_command(sim):
    tele = observer()                         # the hand counts as open
    sim.pinch(BOX)
    checks(tele, 10)
    sim.release(BOX)
    checks(tele, 10)
    assert n_drops(tele) == 0


def test_a_second_pick_of_the_same_body_can_drop_again(sim):
    tele = observer()
    carry(sim, tele)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS)
    sim.rest(BOX)
    tele.gripper_command(opening=True)        # the pipeline's open after it
    assert n_drops(tele) == 1
    carry(sim, tele)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS)
    assert n_drops(tele) == 2


def test_wide_fingers_do_not_hide_a_drop(sim, tmp_path):
    # The 35 mm gap: fingers levered open count as "opening" for GRIP_LOST,
    # which then says nothing; the drop count does not read the width.
    tele = observer(tmp_path, counts_only=False)
    carry(sim, tele)
    sim.fingers = [0.0362, 0.0362]
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS + 2)
    tele.close()
    log = (tmp_path / 'telemetry.log').read_text(encoding='utf-8')
    assert 'GRIP_LOST' not in log
    assert n_drops(tele) == 1 and '!! DROP' in log


# ----- collisions ----------------------------------------------------------

def knock(sim, tele, body, mm, link=3):
    """An arm link (no finger) touches the body for one check; the body is
    then ``mm`` further along x."""
    sim.contacts.add((ROBOT, body, link, -1))
    checks(tele, 1)
    sim.contacts.discard((ROBOT, body, link, -1))
    sim.pos[body][0] += mm / 1000.0


def knocked(tele):
    return [(e['object'], e['by']) for e in tele.counts()['collisions']]


def test_a_knocked_bystander_counts_once_per_action(sim):
    tele = observer()
    tele.phase('move 1')
    knock(sim, tele, CUP, 5.0)
    checks(tele, 30)                          # over 3 mm on every check
    assert len(tele.counts()['collisions']) == 1
    tele.phase('move 2')
    checks(tele, 5)
    assert len(tele.counts()['collisions']) == 1   # not touched in this action
    knock(sim, tele, CUP, 4.0)
    knock(sim, tele, BOX, 7.5)
    checks(tele, 5)
    events = tele.counts()['collisions']
    assert [(e['object'], e['phase']) for e in events] == [
        ('cup', 'move 1'), ('cup', 'move 2'), ('box', 'move 2')]
    assert events[2]['moved_mm'] == 7.5 and events[2]['by'] == 'arm link 3'


def test_what_is_no_collision(sim):
    tele = observer()
    tele.phase('move')
    knock(sim, tele, CUP, 2.9)                # touched, but under 3 mm
    checks(tele, 5)
    sim.pos[BOX][0] += 0.02                   # moved, but nothing touched it
    sim.vel[BOX] = [0.1, 0.0, 0.0]
    checks(tele, 5)
    assert tele.counts()['collisions'] == []
    # the body the gripper holds in this action moves with the hand
    tele.gripper_command(opening=False)
    sim.pinch(CUP)
    checks(tele, 1)
    sim.pos[CUP][0] += 0.05
    checks(tele, 5)
    tele.gripper_command(opening=True, placing=True)
    sim.release(CUP)
    sim.pos[CUP][2] -= 0.01                   # and settles after the release
    checks(tele, 5)
    assert tele.counts()['collisions'] == []


def test_a_body_still_settling_when_execution_starts_is_no_collision(sim):
    # find_dice seed 0 (2026-11-12): the die was still tumbling under its
    # cup when the first action began and came to rest 5.8 mm away; the arm
    # touched neither.  Nor does a light touch of the cup make the die's
    # own motion a collision: the cup was not knocked.
    tele = observer()
    tele.phase('move to the first look')
    sim.rest(BOX, on=CUP)
    sim.pos[BOX][2] -= 0.0058
    sim.vel[BOX] = [0.0, 0.0, -0.2]
    checks(tele, 5)
    sim.contacts.add((ROBOT, CUP, 3, -1))
    sim.pos[BOX][2] -= 0.004
    checks(tele, 5)
    assert tele.counts()['collisions'] == []


def test_a_touch_of_one_step_is_seen(sim):
    tele = observer()
    tele.phase('move')
    sim.contacts.add((CUP, ROBOT, -1, 5))
    tele.tick()                               # an odd step: no check on it
    sim.contacts.clear()
    sim.pos[CUP][1] += 0.006
    tele.tick()
    assert knocked(tele) == [('cup', 'arm link 5')]


def test_a_bystander_brushed_by_a_finger_counts(sim):
    # The DISTURBED line leaves out every body a finger touched; the count
    # leaves out only what the gripper held.
    tele = observer()
    carry(sim, tele)                          # the box is in the hand
    tele.phase('move')
    sim.pinch(CUP, pads=(PADS[1],))           # the outside of a finger
    checks(tele, 1)
    sim.pos[CUP][0] += 0.004
    checks(tele, 2)
    assert knocked(tele) == [('cup', 'arm link 10')]
    assert n_drops(tele) == 0


def test_a_bystander_knocked_by_the_held_body_counts(sim):
    tele = observer()
    carry(sim, tele)
    tele.phase('move')
    sim.rest(BOX, on=CUP)                     # the carried box strikes the cup
    checks(tele, 1)
    sim.lift(BOX)
    sim.pos[CUP][0] += 0.01
    checks(tele, 1)
    assert knocked(tele) == [('cup', 'held box')]
    assert n_drops(tele) == 0


def test_how_a_held_body_that_touches_another_body_is_counted(sim):
    tele = observer()
    carry(sim, tele)
    tele.phase('move')
    sim.rest(BOX, on=CUP)                     # the carried box lies on the cup
    checks(tele, 2)
    sim.pos[CUP][0] += 0.002                  # and gives it 2 mm: a touch only
    checks(tele, 2)
    assert tele.counts()['collisions'] == []
    sim.pos[BOX][0] += 0.05                   # the held box itself never counts
    sim.pos[CUP][0] += 0.003                  # 5 mm from where it was touched
    checks(tele, 1)
    assert knocked(tele) == [('cup', 'held box')]
    sim.release(BOX)                          # the strike takes the box as well
    checks(tele, telemetry.DROP_CHECKS)
    assert n_drops(tele) == 1 and len(tele.counts()['collisions']) == 1
    sim.pos[CUP][0] += 0.02                   # the falling box shoves it on:
    checks(tele, 3)                           # still the one collision
    events = tele.counts()['collisions']
    assert len(events) == 1 and events[0]['moved_mm'] == 25.0


def test_what_a_knocked_body_runs_into_counts_too(sim):
    tele = observer()
    tele.phase('move')
    knock(sim, tele, CUP, 8.0)
    checks(tele, 1)                           # the cup is counted
    sim.rest(CUP, on=BOX)                     # and slides into the box
    checks(tele, 1)
    sim.pos[BOX][0] += 0.005
    checks(tele, 1)
    assert knocked(tele) == [('cup', 'arm link 3'), ('box', 'knocked cup')]


def test_a_picks_own_body_shoved_before_both_pads_hold_it_is_no_collision(
        sim, tmp_path):
    tele = observer(tmp_path)
    tele.phase('pick box')
    tele.gripper_command(opening=False)
    sim.rest(BOX)
    sim.pinch(BOX, pads=(PADS[0],))           # one pad reaches it first
    checks(tele, 1)
    sim.pos[BOX][0] += 0.004                  # and pushes it to the other
    checks(tele, 1)
    assert knocked(tele) == [('box', 'arm link 9')]    # so far a shoved body
    sim.pinch(BOX)
    checks(tele, 1)
    assert tele.counts()['collisions'] == []           # the grasp's own body
    on_disk = json.loads((tmp_path / telemetry.COUNTS_FILE).read_text())
    assert on_disk['collisions'] == []
    # a grasp that never gets both pads on the body stays a collision
    tele.gripper_command(opening=True)
    sim.release(BOX)
    tele.phase('pick cup')
    tele.gripper_command(opening=False)
    sim.pinch(CUP, pads=(PADS[0],))
    checks(tele, 1)
    sim.pos[CUP][0] += 0.004
    checks(tele, 3)
    sim.release(CUP)
    checks(tele, 3)
    assert knocked(tele) == [('cup', 'arm link 9')]


def test_a_placed_body_under_the_retreat_is_no_collision(sim):
    tele = observer()
    tele.phase('place box')
    carry(sim, tele)
    sim.rest(BOX)
    checks(tele, 2)
    tele.gripper_command(opening=True, placing=True)
    sim.pinch(BOX, pads=(PADS[0],))           # one pad still lies on it
    checks(tele, 2)
    tele.phase('move home')
    checks(tele, 1)
    sim.pos[BOX][0] += 0.005                  # the retreat drags it a little
    checks(tele, 3)
    assert tele.counts()['collisions'] == [] and n_drops(tele) == 0
    sim.release(BOX)
    checks(tele, 1)
    tele.phase('look')                        # an action later it is a bystander
    knock(sim, tele, BOX, 5.0)
    checks(tele, 1)
    assert knocked(tele) == [('box', 'arm link 3')]


def test_the_fall_of_a_dropped_body_is_no_collision(sim):
    tele = observer()
    tele.phase('move')
    carry(sim, tele)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS)
    assert n_drops(tele) == 1
    sim.pos[BOX][2] -= 0.04                   # it falls, in the drop's action
    checks(tele, 3)
    tele.gripper_command(opening=True)        # the pipeline's open after it
    tele.phase('move home')                   # and still rolls in the next one
    sim.rest(BOX)
    sim.pos[BOX][0] += 0.04
    checks(tele, 5)
    assert tele.counts()['collisions'] == []
    knock(sim, tele, BOX, 6.0)                # the arm then runs into it
    checks(tele, 1)
    assert knocked(tele) == [('box', 'arm link 3')]


# ----- the two modes, the file, the cost ------------------------------------

def scripted_episode(sim, tele):
    tele.phase('pick box')
    carry(sim, tele)
    tele.phase('move')
    knock(sim, tele, CUP, 6.0)
    checks(tele, 4)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS + 1)
    sim.rest(BOX)
    tele.gripper_command(opening=True)
    tele.phase('pick box again')
    carry(sim, tele)
    tele.phase('place box')
    sim.rest(BOX)
    checks(tele, 2)
    tele.gripper_command(opening=True, placing=True)
    sim.release(BOX)
    checks(tele, 4)


def _core(counts):
    return ([(e['object'], e['phase'], e['how']) for e in counts['drops']],
            [(e['object'], e['phase']) for e in counts['collisions']])


def test_the_recorder_and_the_counts_mode_count_the_same(monkeypatch, tmp_path):
    results = []
    for counts_only in (True, False):
        s = ScriptedSim()
        monkeypatch.setattr(telemetry, 'p', s)
        tele = observer(tmp_path / str(counts_only), counts_only=counts_only)
        scripted_episode(s, tele)
        tele.close()
        results.append(_core(tele.counts()))
    assert results[0] == results[1]
    assert results[0] == ([('box', 'move', 'left the finger pads with no '
                                           'release commanded')],
                          [('cup', 'move')])
    log = (tmp_path / 'False' / 'telemetry.log').read_text(encoding='utf-8')
    assert '!! COLLISION' in log and 'after the arm link 3 touched it' in log


def test_the_counts_file_is_there_before_the_run_ends(sim, tmp_path):
    tele = observer(tmp_path)
    armed = json.loads((tmp_path / telemetry.COUNTS_FILE).read_text())
    assert armed['drops'] == [] and armed['closed'] is False
    carry(sim, tele)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS)
    on_disk = json.loads((tmp_path / telemetry.COUNTS_FILE).read_text())
    assert len(on_disk['drops']) == 1 and on_disk['closed'] is False  # no close
    tele.close()
    assert json.loads((tmp_path / telemetry.COUNTS_FILE).read_text())['closed']


def test_the_counts_mode_writes_no_stream_and_reads_only_what_it_counts(sim, tmp_path):
    tele = observer(tmp_path)
    scripted_episode(sim, tele)
    tele.note('ignored')
    tele.close()
    assert sorted(f.name for f in tmp_path.iterdir()) == [telemetry.COUNTS_FILE]
    assert set(sim.calls) <= {'getContactPoints', 'getBasePositionAndOrientation'}


def test_an_action_that_touches_nothing_reads_one_contact_list_per_step(sim):
    tele = observer()
    tele.phase('move')
    sim.calls.clear()
    checks(tele, 10)
    assert sim.calls == ['getContactPoints'] * (10 * telemetry.EVENT_STRIDE)


def test_the_counts_mode_clocks_its_own_checks(sim, tmp_path):
    tele = observer(tmp_path)
    assert tele.counts()['check_s'] == 0.0
    scripted_episode(sim, tele)
    tele.close()
    cost = tele.counts()['check_s']
    assert 0.0 < cost < 1.0                   # a few dozen scripted checks
    assert json.loads((tmp_path / telemetry.COUNTS_FILE).read_text())['check_s'] == cost
    # the recorder's cost is its recording, not this clock
    assert observer(tmp_path / 'rec', counts_only=False).counts()['check_s'] is None


def test_the_counts_mode_needs_no_run_directory(sim):
    tele = observer(None)
    carry(sim, tele)
    sim.release(BOX)
    checks(tele, telemetry.DROP_CHECKS)
    tele.close()
    assert n_drops(tele) == 1


def test_the_module_switches(sim, tmp_path):
    assert telemetry.run_counts() is None and not telemetry.is_counting()
    telemetry.gripper_command(opening=True)   # a no-op when nothing watches
    try:
        telemetry.enable(0, ROBOT, NAMES, tmp_path, finger_joints=PADS,
                         counts_only=True)
        assert telemetry.is_counting() and not telemetry.is_active()
        telemetry.phase('pick box')
        telemetry.gripper_command(opening=False)
        sim.pinch(BOX)
        for _ in range(2 * telemetry.CARRIED_CHECKS):
            telemetry.tick()
        telemetry.gripper_command(opening=True)
        assert len(telemetry.run_counts()['drops']) == 1
    finally:
        telemetry.disable()
    assert telemetry.run_counts() is None
