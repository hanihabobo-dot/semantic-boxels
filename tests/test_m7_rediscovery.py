"""M7 (PAPER_AUDIT M7, BF#15, TB-46): a sense that finds a registered body
again keeps the body's still-hidden fragments and carves the recast against
every fragment; with M7 off the old cleanup drops them unrendered.

The real handle_sense_action runs on a hand-made top-down render (as in
test_sense_sliver_pose.py) with a stand-in env.  The classification of each
fragment is scripted (sense_shadow_from_render is replaced by a table keyed
by fragment id), so each case says which fragment the render shows empty and
which still hidden; everything after the classification is the real code.
The stand-in shadow calculator casts one fixed box behind the body and carves
it with ShadowCalculator's own subtraction against the obstacles it is given
(a second stand-in casts nothing, the case of a body that hides part of the
region but casts no fragment of its own, audit #103).
The ledger rows are read back and judged by tools/bridge_gates.py's G5 (B5
deliverable (3), review TB-46 b4; the last four tests are R5 of the M7 code
review, prefreeze/analysis/REVIEW_M7_CODE.md)."""
import importlib.util
import json
import os
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

from acting import execution
from world import interior_regions
from sensing import perception
from sensing import pose_belief
from console import run_logger
from acting import slip_fixes
from sensing.belief import BeliefState
from world.boxel_data import BoxelData, BoxelRegistry, BoxelType
from world.shadow_calculator import ShadowCalculator

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'bridge_gates', os.path.join(REPO, 'tools', 'bridge_gates.py'))
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)

W, H = 64, 48
NEAR, FAR = 0.02, 5.0
EYE = (0.5, 0.0, 1.0)                 # straight above the table (z = 0)
TABLE, BLUE, RED, TARGET = 0, 7, 8, 9  # seg ids; the target is not in the image
BLUE_TOP = 0.04
NAMES = {BLUE: 'blue', TARGET: 'target'}
NAMES_RED = {**NAMES, RED: 'red'}       # a second body, for the two-body case
SENSED = 'shadow_sensed'
HIDDEN = 'shadow_of_blue__00'         # blue's old fragment the render still hides
EMPTY = 'shadow_of_blue__01'          # blue's old fragment the render shows empty
OTHER = 'shadow_other'                # another region, untouched by this render


@pytest.fixture
def main_defaults():
    saved, enabled = dict(pose_belief.SWITCHES), slip_fixes.ENABLED
    pose_belief.SWITCHES.update({k: True for k in saved})
    slip_fixes.configure('')
    interior_regions.configure('off')
    # with a default, so the two M7 off tests also run against d14199d's
    # execution.py, which has no flag (the equivalence run, review R2)
    m7 = getattr(execution, 'M7', True)
    yield
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)
    slip_fixes.ENABLED = enabled
    execution.M7 = m7


def _buffer(depth_m):
    return FAR * (1.0 - NEAR / depth_m) / (FAR - NEAR)


def _meters(buf):
    return FAR * NEAR / (FAR - (FAR - NEAR) * buf)


def _render(red=False):
    """The table everywhere, and blue as a 5 x 5 pixel block at the centre
    (with red: red as a second 5 x 5 block, one column beside blue)."""
    view = p.computeViewMatrix(list(EYE), [EYE[0], EYE[1], 0.0], [0.0, 1.0, 0.0])
    proj = p.computeProjectionMatrixFOV(50.0, W / H, NEAR, FAR)
    seg = np.full((H, W), TABLE, dtype=int)
    buf = np.full((H, W), _buffer(EYE[2]))
    seg[22:27, 30:35] = BLUE
    buf[22:27, 30:35] = _buffer(EYE[2] - BLUE_TOP)
    if red:
        seg[22:27, 36:41] = RED
        buf[22:27, 36:41] = _buffer(EYE[2] - BLUE_TOP)
    return seg, buf, view, proj


def _box(lo, hi):
    return np.array(lo, dtype=float), np.array(hi, dtype=float)


class Caster:
    """The stand-in shadow calculator: one raw box behind the body (+y),
    carved against the given obstacles by ShadowCalculator's own step 3."""

    def __init__(self):
        self.calls = []
        self._calc = ShadowCalculator.__new__(ShadowCalculator)

    def calculate_shadow_boxel(self, bd, obstacles, physics_client=None):
        self.calls.append((bd.id, [o.id for o in obstacles]))
        lo = np.array([bd.min_corner[0], bd.max_corner[1], 0.0])
        hi = np.array([bd.max_corner[0], bd.max_corner[1] + 0.10, 0.06])
        active = [BoxelData(boxel_type=BoxelType.SHADOW, min_corner=lo,
                            max_corner=hi, created_by_object=bd.object_name)]
        for ob in obstacles:
            nxt = []
            for frag in active:
                if self._calc._check_aabb_intersection(frag, ob):
                    nxt.extend(self._calc._subtract_aabb(frag, ob, np.zeros(3)))
                else:
                    nxt.append(frag)
            active = nxt
        return active


class NothingCaster(Caster):
    """A body that casts no fragment from this view (a body not resting on
    the table, audit #103, or a cast carved away entirely)."""

    def calculate_shadow_boxel(self, bd, obstacles, physics_client=None):
        self.calls.append((bd.id, [o.id for o in obstacles]))
        return []


def _env(render, caster, names=NAMES):
    seg, buf, view, proj = render

    def detect_objects():
        dets = perception.detect_objects_from_render(
            seg, buf, view, proj, names, EYE[:2], 0.0)
        return dets, None, buf, seg
    return SimpleNamespace(
        objects={n: SimpleNamespace(object_id=b) for b, n in names.items()},
        detect_objects=detect_objects,
        _depth_buffer_to_meters=_meters,
        _view_and_projection_matrices=lambda: (view, proj),
        camera_position=np.array(EYE), table_surface_height=0.0,
        plan_body_id=lambda body: body, shadow_raycast_client=None,
        shadow_calculator=caster,
        generate_free_space=lambda obstacles, visualize=False: [],
        use_uniform_grid=True,
        annotate_free_space_surface=lambda cells: None)


def _scene(moved=False, first=False, red=False):
    """The registry before the sense: blue registered (at its true box, or
    15 cm away in x for a body the arm had moved, seed 188's pattern), its
    two old fragments, the sensed region and one other region.  With first:
    blue was never registered, so neither blue nor its fragments are there
    (a first discovery).  With red: red stands beside blue, unregistered,
    and the sensed region holds both."""
    render = _render(red)
    dets = perception.detect_objects_from_render(
        render[0], render[1], render[2], render[3],
        NAMES_RED if red else NAMES, EYE[:2], 0.0)
    det = dets['blue']
    bmin, bmax = np.array(det.est_min, float), np.array(det.est_max, float)
    smin, smax = bmin, bmax
    if red:
        smin = np.minimum(bmin, np.array(dets['red'].est_min, float))
        smax = np.maximum(bmax, np.array(dets['red'].est_max, float))
    dx = np.array([0.15, 0.0, 0.0]) if moved else np.zeros(3)
    reg = BoxelRegistry()
    frags = {}
    hidden_part = None
    if not first:
        blue = BoxelData(id='blue', boxel_type=BoxelType.OBJECT, min_corner=bmin + dx,
                         max_corner=bmax + dx, object_name='blue', is_occluder=True,
                         on_surface='table', surface_z=0.0)
        reg.add_boxel(blue)
        ob = blue
        # behind blue's believed box, 10 cm deep (its old shadow)
        frags[HIDDEN] = _box([ob.min_corner[0], ob.max_corner[1], 0.0],
                             [ob.max_corner[0], ob.max_corner[1] + 0.10, 0.06])
        frags[EMPTY] = _box([0.20, -0.30, 0.0], [0.26, -0.24, 0.06])
        # the still-hidden part of HIDDEN: its first 4 cm behind the body
        hidden_part = _box([ob.min_corner[0], ob.max_corner[1], 0.0],
                           [ob.max_corner[0], ob.max_corner[1] + 0.04, 0.06])
    # the sensed region holds blue (and red) where it truly stands
    frags[SENSED] = _box([smin[0] - 0.01, smin[1] - 0.01, 0.0],
                         [smax[0] + 0.01, smax[1] + 0.03, 0.06])
    frags[OTHER] = _box([0.70, 0.20, 0.0], [0.76, 0.26, 0.06])
    for sid, (lo, hi) in frags.items():
        caster = 'blue' if sid in (HIDDEN, EMPTY) else None
        reg.add_boxel(BoxelData(id=sid, boxel_type=BoxelType.SHADOW,
                                min_corner=lo, max_corner=hi,
                                created_by_object=caster,
                                created_by_boxel_id=caster,
                                on_surface='table', surface_z=0.0))
    if not first:
        blue.shadow_boxel_ids = [HIDDEN, EMPTY]
    return render, reg, hidden_part


def _scripted(hidden_part, bodies=(BLUE,)):
    """sense_shadow_from_render as a table: the sensed region contains blue
    (or every body in bodies), EMPTY is seen empty, HIDDEN is still blocked
    by blue (shrunk to hidden_part), anything else is blocked with no
    reveal."""
    def fake(shadow_boxel, *_a, **_k):
        sid = str(shadow_boxel.id)
        if sid == SENSED:
            return ('contains_nontarget', 0.0, set(bodies), None,
                    {b: 12 for b in bodies})
        if sid == EMPTY:
            return 'clear_but_empty', 0.0, set(), None, {}
        if sid == HIDDEN:
            return 'still_blocked', 0.6, set(), hidden_part, {BLUE: 20}
        return 'still_blocked', 1.0, set(), None, {}
    return fake


def _run(tmp_path, monkeypatch, *, m7, moved=False, counts=None, first=False,
         red=False, caster=None, redetected=(), after=None):
    """One sense of SENSED under plan 1 step 1; returns (result, registry,
    belief, rows, caster, parked).  counts is the episode's rediscovery
    counter itself (passed, not copied, so a test can read it after the
    sense); redetected names the bodies in belief.redetected (F20's
    exemption); first, red and caster as in _scene and NothingCaster;
    after(belief) runs once the step is closed, before the ledger closes
    (the loop's top, where a suspension ends)."""
    execution.M7 = m7
    render, reg, hidden_part = _scene(moved, first=first, red=red)
    names = NAMES_RED if red else NAMES
    monkeypatch.setattr(execution, 'sense_shadow_from_render',
                        _scripted(hidden_part, (BLUE, RED) if red else (BLUE,)))
    caster = caster or Caster()
    env = _env(render, caster, names)
    ids = [SENSED, OTHER] if first else [SENSED, HIDDEN, EMPTY, OTHER]
    belief = BeliefState(list(ids), 'target')
    belief.redetected.update(redetected)
    parked = set()
    occluder_map = {} if first else {HIDDEN: ['blue'], EMPTY: ['blue']}
    known = {} if first else {'blue': {'name': 'blue', 'pybullet_id': BLUE,
                                       'position': np.zeros(3)}}
    run_logger.ledger_open(tmp_path)
    try:
        run_logger.dispatch_begin(1, 1, 'sense', ['target', SENSED])
        result = execution.handle_sense_action(
            action_params=('target', SENSED), env=env, registry=reg,
            belief=belief, viz=None, target_name='target', robot_id=None,
            support_body_ids=frozenset({TABLE}), shadows=list(ids),
            occluders=[] if first else ['blue'], shadow_occluder_map=occluder_map,
            blocked_counts={}, blocked_giveup_shadows=parked,
            nontarget_rediscovery_counts=counts if counts is not None else {},
            boxel_centers={}, boxel_to_pybullet=known,
            object_body_ids={}, body_id_to_name=names, show_free=False)
        run_logger.ledger_event('sense_result', reason=result.reason,
                                continue_=result.continue_)
        run_logger.dispatch_end('sense_outcome')
        if after is not None:
            after(belief)
    finally:
        run_logger.ledger_close()
    with open(tmp_path / 'ledger.jsonl', encoding='utf-8') as f:
        rows = [json.loads(line) for line in f]
    return result, reg, belief, rows, caster, parked


def _belief_rows(rows):
    return [(r['region'], r['op'], r.get('status'), r.get('channel'))
            for r in rows if r['kind'] == 'belief']


def _g5(tmp_path):
    rep = bg.Report()
    bg.run_ledger(rep, str(tmp_path))          # m7 'on', the gate's default
    return {g: (s, d) for g, s, d in rep.rows}['G5']


def _overlap(a, b):
    return bool(np.all(np.minimum(a.max_corner, b.max_corner)
                       - np.maximum(a.min_corner, b.min_corner) > 1e-6))


def test_m7_off_is_the_old_cleanup_and_fails_g5(tmp_path, monkeypatch, main_defaults):
    result, reg, belief, rows, caster, _ = _run(tmp_path, monkeypatch, m7=False)
    assert result.reason == 'sense_contains_nontarget'
    b = _belief_rows(rows)
    new = [s for s in reg.get_boxel('blue').shadow_boxel_ids]
    # The rows of the code before M7, in order: the sensed region, the sweep,
    # the unrendered drop of the still-hidden fragment, the recast.
    assert b == [
        (SENSED, 'status', 'not_here', 'planned_sense_render'),
        (SENSED, 'remove', None, 'planned_sense_render'),
        (EMPTY, 'status', 'not_here', 'sweep_render'),
        (EMPTY, 'remove', None, 'sweep_render'),
        (HIDDEN, 'remove', None, 'superseded_unrendered'),
        (HIDDEN, 'forget', None, 'superseded_unrendered'),
    ] + [(s, 'add', 'unknown', 'planned_sense_render') for s in new]
    assert reg.get_boxel(HIDDEN) is None and HIDDEN not in belief.shadow_status
    assert not [r for r in rows if r['kind'] == 'sense_discovery']
    # The recast is carved against OBJECT boxes only (here none but blue's own).
    assert caster.calls == [('blue', [])]
    status, detail = _g5(tmp_path)
    assert status == 'FAIL' and 'unrendered rediscovery removals' in detail


def test_m7_keeps_the_hidden_fragment_and_removes_the_empty_one(
        tmp_path, monkeypatch, main_defaults):
    result, reg, belief, rows, caster, parked = _run(tmp_path, monkeypatch, m7=True)
    assert result.reason == 'sense_contains_nontarget'
    b = _belief_rows(rows)
    assert (EMPTY, 'remove', None, 'sweep_render') in b
    assert not [x for x in b if x[0] == HIDDEN]
    assert not [x for x in b if x[3] == 'superseded_unrendered']
    kept = reg.get_boxel(HIDDEN)
    assert kept is not None and belief.shadow_status[HIDDEN] == 'unknown'
    blue = reg.get_boxel('blue')
    assert blue.shadow_boxel_ids[0] == HIDDEN
    disc = [r for r in rows if r['kind'] == 'sense_discovery']
    assert len(disc) == 1
    d = disc[0]
    assert d['body'] == 'blue' and d['rediscovery'] and d['kept'] == [HIDDEN]
    assert d['recast'] and not d['giveup'] and not d['parked']
    assert d['plan'] == 1 and d['step'] == 1
    assert d['recast'] == blue.shadow_boxel_ids[1:]
    assert reg.get_boxel(SENSED) is None and not parked
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)


def test_kept_and_recast_are_disjoint_with_the_own_fragment_in_the_carve_set(
        tmp_path, monkeypatch, main_defaults):
    _, reg, _, rows, caster, _ = _run(tmp_path, monkeypatch, m7=True)
    (body, obstacles), = caster.calls
    assert body == 'blue' and 'blue' not in obstacles
    # every fragment in the registry at the recast, blue's kept one included
    assert HIDDEN in obstacles and OTHER in obstacles
    assert SENSED not in obstacles and EMPTY not in obstacles
    blue = reg.get_boxel('blue')
    recast = [reg.get_boxel(s) for s in blue.shadow_boxel_ids[1:]]
    assert recast
    every = reg.get_shadow_boxels()
    for i, a in enumerate(every):
        for c in every[i + 1:]:
            assert not _overlap(a, c), (a.id, c.id)
    # the recast covers the rest of the raw shadow: behind the kept part
    kept = reg.get_boxel(HIDDEN)
    assert min(r.min_corner[1] for r in recast) == pytest.approx(kept.max_corner[1])


def test_give_up_keeps_and_parks_the_sensed_fragment(tmp_path, monkeypatch, main_defaults):
    # the third rediscovery of blue: F9 casts nothing (seed 293's pattern)
    result, reg, belief, rows, caster, parked = _run(
        tmp_path, monkeypatch, m7=True, counts={'blue': 2})
    assert result.reason == 'sense_contains_nontarget'
    assert not caster.calls
    assert reg.get_boxel(SENSED) is not None
    # the park is a suspension (Hani, 2026-11-20), not a blocked view
    assert belief.shadow_status[SENSED] == 'unresolved' and SENSED not in parked
    assert belief.get_suspended_shadows() == [SENSED]
    s = belief.suspended[SENSED]
    assert s['bodies'] == {'blue': 3}
    assert s['until'] - s['start'] == pytest.approx(execution.M7_SUSPEND_S)
    b = _belief_rows(rows)
    assert (SENSED, 'status', 'unresolved', 'strike_park') in b
    assert not [x for x in b if x[0] == SENSED and x[1] in ('remove', 'forget')]
    assert not [x for x in b if x[0] == HIDDEN]
    assert reg.get_boxel('blue').shadow_boxel_ids == [HIDDEN]
    d, = [r for r in rows if r['kind'] == 'sense_discovery']
    assert d['giveup'] and d['parked'] and d['recast'] == [] and d['kept'] == [HIDDEN]
    susp, = [r for r in rows if r['kind'] == 'm7_suspension']
    assert (susp['op'], susp['region'], susp['bodies'], susp['seconds']) == (
        'start', SENSED, {'blue': 3}, execution.M7_SUSPEND_S)
    assert (susp['plan'], susp['step']) == (1, 1)
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)


def test_the_suspension_ends_when_its_time_is_up(tmp_path, monkeypatch, main_defaults):
    # Hani, 2026-11-20: after M7_SUSPEND_S the region is offered again; the
    # loop's top releases it under the suspension_over channel, and G5 reads
    # that row as the end of the park before it.
    def after(belief):
        until = belief.suspended[SENSED]['until']
        with run_logger.provenance('suspension_over'):
            assert belief.release_suspended(until - 1.0) == []
            assert belief.get_suspended_shadows() == [SENSED]
            assert belief.release_suspended(until) == [SENSED]
    _, reg, belief, rows, _, _ = _run(tmp_path, monkeypatch, m7=True,
                                      counts={'blue': 2}, after=after)
    assert belief.shadow_status[SENSED] == 'unknown'
    assert SENSED in belief.get_unknown_shadows() and reg.get_boxel(SENSED) is not None
    assert not belief.suspended and not belief.get_suspended_shadows()
    assert belief.suspensions[0]['ended_by'] == 'released'
    assert _belief_rows(rows)[-1] == (SENSED, 'status', 'unknown', 'suspension_over')
    ends = [r for r in rows if r['kind'] == 'm7_suspension']
    assert [(r['op'], r.get('ended_by')) for r in ends] == [('start', None),
                                                            ('end', 'released')]
    assert 'step' not in ends[1]                      # no step was open
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)


def test_give_up_with_m7_off_drops_both_and_fails_g5(tmp_path, monkeypatch, main_defaults):
    _, reg, belief, rows, caster, parked = _run(
        tmp_path, monkeypatch, m7=False, counts={'blue': 2})
    assert not caster.calls and not parked
    assert reg.get_boxel(SENSED) is None and reg.get_boxel(HIDDEN) is None
    assert _g5(tmp_path)[0] == 'FAIL'


def test_a_moved_body_keeps_its_old_pose_remainder(tmp_path, monkeypatch, main_defaults):
    # blue believed 15 cm away (moved by the arm, seed 188's pattern): its
    # old fragment behind the old pose stays, the recast is cast at the new
    # pose, and the two hold no common space.
    _, reg, belief, rows, caster, _ = _run(tmp_path, monkeypatch, m7=True, moved=True)
    kept = reg.get_boxel(HIDDEN)
    assert kept is not None and belief.shadow_status[HIDDEN] == 'unknown'
    blue = reg.get_boxel('blue')
    assert blue.shadow_boxel_ids[0] == HIDDEN
    recast = [reg.get_boxel(s) for s in blue.shadow_boxel_ids[1:]]
    assert recast and all(not _overlap(kept, r) for r in recast)
    # the new boxel stands at the render's estimate, not at the old pose
    assert blue.max_corner[0] < kept.min_corner[0]
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)


# ----- R5 of the M7 code review ---------------------------------------------

def test_a_first_discovery_is_cast_against_every_fragment(
        tmp_path, monkeypatch, main_defaults):
    # blue was never registered: the row says so, the cast is carved against
    # every fragment there is (choice C4, a first discovery too), G5 PASS.
    result, reg, belief, rows, caster, parked = _run(
        tmp_path, monkeypatch, m7=True, first=True)
    assert result.reason == 'sense_contains_nontarget'
    (body, obstacles), = caster.calls
    assert body == 'blue' and obstacles == [OTHER]
    assert reg.get_boxel(SENSED) is None and not parked
    blue = reg.get_boxel('blue')
    d, = [r for r in rows if r['kind'] == 'sense_discovery']
    assert d['body'] == 'blue' and not d['rediscovery'] and d['kept'] == []
    assert d['recast'] and d['recast'] == blue.shadow_boxel_ids
    assert not d['giveup'] and not d['parked']
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)


def test_a_first_discovery_that_casts_nothing_fails_g5(
        tmp_path, monkeypatch, main_defaults):
    # The known G5 class (review point 3): nothing covers again what the body
    # hides, the sensed region still leaves the belief, and G5 fails the
    # step, naming the body as a first discovery.  Pinned here so the gate is
    # not loosened unseen.
    result, reg, belief, rows, caster, parked = _run(
        tmp_path, monkeypatch, m7=True, first=True, caster=NothingCaster())
    assert [c[0] for c in caster.calls] == ['blue']
    assert reg.get_boxel(SENSED) is None and not parked
    assert (SENSED, 'remove', None, 'planned_sense_render') in _belief_rows(rows)
    d, = [r for r in rows if r['kind'] == 'sense_discovery']
    assert not d['rediscovery'] and d['recast'] == [] and not d['giveup']
    status, detail = _g5(tmp_path)
    assert status == 'FAIL'
    assert (f'{SENSED} removed with nothing recast and nothing parked '
            f'(first discovery of blue)') in detail


def test_two_bodies_one_at_its_give_up_park_the_region(
        tmp_path, monkeypatch, main_defaults):
    # Choice C5: blue at its third rediscovery and red, found for the first
    # time, in the same sense.  Blue's give-up parks the sensed region; red is
    # still cast, carved against the parked region; one row per body; G5 PASS.
    counts = {'blue': 2}
    result, reg, belief, rows, caster, parked = _run(
        tmp_path, monkeypatch, m7=True, counts=counts, red=True)
    assert reg.get_boxel(SENSED) is not None and SENSED not in parked
    assert belief.shadow_status[SENSED] == 'unresolved'
    assert belief.suspended[SENSED]['bodies'] == {'blue': 3}   # red has no give-up
    calls = dict(caster.calls)
    assert set(calls) == {'red'}                     # blue's give-up casts nothing
    assert SENSED in calls['red'] and 'red' not in calls['red']
    disc = {r['body']: r for r in rows if r['kind'] == 'sense_discovery'}
    assert set(disc) == {'blue', 'red'}
    assert disc['blue']['rediscovery'] and disc['blue']['giveup']
    assert disc['blue']['recast'] == [] and disc['blue']['kept'] == [HIDDEN]
    assert not disc['red']['rediscovery'] and not disc['red']['giveup']
    assert disc['red']['recast'] == reg.get_boxel('red').shadow_boxel_ids
    assert disc['red']['recast'] and disc['blue']['parked'] and disc['red']['parked']
    assert counts == {'blue': 3}
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)


def test_the_redetected_exemption_neither_counts_nor_parks(
        tmp_path, monkeypatch, main_defaults):
    # Blue entered the registry from a whole-workspace observation and is
    # found inside a fragment for the first time (F20's exemption): at count
    # 2 it is not counted and not given up, so the region is not parked and
    # blue is cast again.  The one place where the give-up predictor and the
    # discovery loop could drift apart.
    counts = {'blue': 2}
    result, reg, belief, rows, caster, parked = _run(
        tmp_path, monkeypatch, m7=True, counts=counts, redetected=('blue',))
    assert counts == {'blue': 2} and 'blue' not in belief.redetected
    assert not parked and reg.get_boxel(SENSED) is None
    assert [c[0] for c in caster.calls] == ['blue']
    d, = [r for r in rows if r['kind'] == 'sense_discovery']
    assert d['rediscovery'] and not d['giveup'] and not d['parked'] and d['recast']
    assert _g5(tmp_path)[0] == 'PASS', _g5(tmp_path)
