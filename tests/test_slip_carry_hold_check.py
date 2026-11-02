"""BF#59 carry_hold_check: after every move made while holding, the
executor checks both pads against the held body (the post-lift re-verify's
contact-only rule, one shared helper) and a loss fails the move as an empty
hand; every holding move logs the finger width growth over the carry.

Unit level: the pybullet reads (getContactPoints, getJointState) and the
gripper command are stubbed, so no world and no planner run."""
import inspect

import pytest

import execution
import slip_fixes
import test_full_pipeline
from robot_utils import robot_model

NAME = 'carry_hold_check'
ROBOT, BODY = 1, 7


@pytest.fixture
def registry():
    """The switch state for one test; the module's state restored after."""
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    slip_fixes.ENABLED = frozenset()
    yield slip_fixes
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


class World:
    """Stubbed senses: finger joint positions (m), joint 7 (rad) and the
    pad contacts on the held body (link, normal force)."""

    def __init__(self, monkeypatch, fingers=(0.0102, 0.0102), wrist=0.0,
                 contacts=()):
        self.fingers = list(fingers)
        self.wrist = wrist
        self.contacts = list(contacts)
        self.contact_calls = 0
        self.opened = 0
        monkeypatch.setattr(execution.p, 'getContactPoints', self._contacts)
        monkeypatch.setattr(execution.p, 'getJointState', self._joint)
        monkeypatch.setattr(execution, 'open_gripper', self._open)

    def _contacts(self, bodyA=None, bodyB=None, **kw):
        assert bodyA == ROBOT and bodyB == BODY      # tactile: robot against the held body
        self.contact_calls += 1
        out = []
        for link, nf in self.contacts:
            c = [0] * 14
            c[1], c[2], c[3], c[9] = ROBOT, BODY, link, nf
            out.append(tuple(c))
        return out

    def _joint(self, body, j, **kw):
        m = robot_model()
        if j in m.finger_joints:
            return (self.fingers[m.finger_joints.index(j)], 0.0, (0,) * 6, 0.0)
        if j == m.arm_joints[-1]:
            return (self.wrist, 0.0, (0,) * 6, 0.0)
        return (0.0, 0.0, (0,) * 6, 0.0)

    def _open(self, robot_id, gui=False):
        self.opened += 1


def both_pads(nf=1.5):
    a, b = robot_model().finger_joints
    return [(a, nf), (b, nf)]


def test_registered_and_off_by_default(registry):
    assert NAME in registry.KNOWN
    assert NAME not in registry.configure('')                 # not one of BF#62's four
    assert not registry.on(NAME)
    args = test_full_pipeline.parse_pipeline_args(['--no-gui', '--goal', 'holding'])
    assert args.slip_fixes == ''


def test_off_a_holding_move_reads_nothing_and_prints_nothing(registry, monkeypatch, capsys):
    w = World(monkeypatch, contacts=[])                      # a lost body: off must not see it
    start = execution.carry_hold_begin(ROBOT, BODY)
    assert start is None
    assert execution.carry_hold_end(ROBOT, BODY, start, 'dice', 'q_home') is None
    assert w.contact_calls == 0 and w.opened == 0
    assert 'carry_hold_check' not in capsys.readouterr().out


def test_on_but_empty_hand_does_nothing(registry, monkeypatch, capsys):
    registry.configure(NAME)
    w = World(monkeypatch, contacts=both_pads())
    assert execution.carry_hold_begin(ROBOT, None) is None
    assert w.contact_calls == 0
    assert capsys.readouterr().out == ''


def test_on_a_held_body_passes_and_logs_the_width_growth(registry, monkeypatch, capsys):
    registry.configure(NAME)
    w = World(monkeypatch, fingers=(0.0102, 0.0102), wrist=-2.0,
              contacts=both_pads(2.0))
    start = execution.carry_hold_begin(ROBOT, BODY)
    assert start is not None
    w.fingers = [0.01025, 0.01025]                           # +0.05 mm each
    w.wrist = 0.785
    res = execution.carry_hold_end(ROBOT, BODY, start, 'dice', 'q_home')
    out = capsys.readouterr().out
    assert res.held and res.points == 2
    assert res.growth_mm == pytest.approx(0.1)
    assert res.force == pytest.approx(4.0)
    assert w.contact_calls == 1 and w.opened == 0
    lines = [l for l in out.splitlines() if 'carry_hold_check:' in l]
    assert len(lines) == 1
    line = lines[0]
    assert line.strip().startswith('carry_hold_check: move to q_home holding dice')
    assert '10.200/10.200 mm at the start' in line
    assert '10.250/10.250 mm at the end' in line
    assert 'width growth +0.100 mm' in line
    assert 'wrist travel 159.6 deg' in line
    assert '(2 points, 4.00 N)' in line
    assert line.endswith('position hold: held')
    assert 'grip lost' not in out


def test_on_a_lost_body_fails_the_move_and_prints_the_loss(registry, monkeypatch, capsys):
    registry.configure(NAME)
    w = World(monkeypatch, contacts=both_pads())
    start = execution.carry_hold_begin(ROBOT, BODY)
    w.contacts = []
    res = execution.carry_hold_end(ROBOT, BODY, start, 'dice', 'q_home')
    out = capsys.readouterr().out
    assert res is not None and res.held is False             # the dispatcher's empty-hand path
    assert res.pads == frozenset()
    assert w.opened == 1                                     # closed on nothing: opened, as at place entry
    assert 'position hold: LOST' in out
    assert 'ERROR: grip lost in the carry for dice: pad contacts=none' in out
    # The eval's own lines are not printed by the carry check.
    for line in ('grip lost after post-pick lift', 'PHYSICAL_FAILURE', 'firm grip',
                 'Picking dice'):
        assert line not in out


def test_one_pad_is_a_loss_and_a_light_pinch_is_not(registry, monkeypatch, capsys):
    """Contact presence on both pads decides, no force floor (the eval's
    losses were 'links none' in 35 of 36; reviews/loss_dynamics.md)."""
    registry.configure(NAME)
    a, b = robot_model().finger_joints
    w = World(monkeypatch, contacts=[(a, 3.0)])
    start = execution.carry_hold_begin(ROBOT, BODY)
    assert execution.carry_hold_end(ROBOT, BODY, start, 'dice', 'q_home').held is False
    w.contacts = [(a, 0.05), (b, 0.05)]                      # 0.10 N summed, under 0.5 N
    start = execution.carry_hold_begin(ROBOT, BODY)
    assert execution.carry_hold_end(ROBOT, BODY, start, 'dice', 'q_home').held is True


def test_the_log_line_names_the_force_hold(registry, monkeypatch, capsys):
    if 'force_hold' not in registry.KNOWN:                   # its branch is not merged here
        registry.register('force_hold', 'the force hold (stand-in for its branch)')
    registry.configure(f'{NAME},force_hold')
    World(monkeypatch, contacts=both_pads())
    start = execution.carry_hold_begin(ROBOT, BODY)
    execution.carry_hold_end(ROBOT, BODY, start, 'dice', 'q_home')
    assert 'force_hold hold: held' in capsys.readouterr().out


def test_the_shared_helper_applies_no_rule(monkeypatch):
    a, b = robot_model().finger_joints
    w = World(monkeypatch, contacts=[(a, 0.01), (b, 0.02), (b, 0.03), (99, 5.0)])
    pads, nf, n = execution.held_pad_contacts(ROBOT, BODY)
    assert pads == {a, b}
    assert nf == pytest.approx(0.06)                         # the non-pad contact is not counted
    assert n == 3
    assert w.contact_calls == 1


def test_the_post_lift_check_is_contact_only_and_ungated():
    src = inspect.getsource(execution.execute_pick)
    i = src.index('#P1 F1(b) post-lift re-verify')
    block = src[i:src.index('return _failed()', i)]
    assert 'lift_pads, lift_nf, _ = held_pad_contacts(robot_id, obj_id)' in block
    assert 'if lift_pads != set(_fingers):' in block
    assert 'lift_nf <' not in block and '0.5' not in block   # no force floor
    assert 'slip_fixes' not in block                          # the same with the switch off
    assert 'grip lost after post-pick lift for {obj_name}' in block


def test_the_dispatcher_takes_the_empty_hand_path_on_a_loss():
    src = inspect.getsource(test_full_pipeline.main)
    m = src.index("if action_name == 'move':")
    move = src[m:src.index("elif action_name == 'sense':", m)]
    begin = move.index('_carry0 = carry_hold_begin(robot_id, held_body_id)')
    # The waypoint stream: today's per-pair loop, or carry_trapezoid's one
    # call once that fix is merged beside this one (slip/campaign).
    stream = [i for i in (move.find('for wi, wp in enumerate(traj.waypoints[1:]'),
                          move.find('stream_move_waypoints(robot_id, traj.waypoints'))
              if i >= 0]
    assert stream and begin < min(stream)
    end = move.index('_carry = carry_hold_end(')
    assert move.index("dispatch_end('home_not_reached')") < end
    assert end < move.index('if _integrity_after(')
    path = move[end:move.index('if _integrity_after(')]
    for step in ('if _carry is not None and not _carry.held:',
                 'transit_loss_counts[_lost_obj]',
                 'pick_giveup_objects.add(_lost_obj)',
                 'held_body_id = None',
                 'held_object_boxel_id = None',
                 'audit_robot_held_state(',
                 'env.update_object_positions()',
                 'pose_belief.mark_pose_unknown(registry.get_boxel(_lost_obj))',
                 'refresh_object_aabbs(env, registry, viz=viz,',
                 'retire_lost_objects(',
                 "dispatch_end('empty_hand')",
                 'break'):
        assert step in path, step
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'tools'))
    import bridge_gates
    assert 'empty_hand' in bridge_gates.G3_STATUSES          # no new dispatch status
