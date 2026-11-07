"""#P4 path 6, DV-1: the read of arm T's final world (tampura_bridge/final_world.py).

Fakes only: the reader takes their world through six attributes (state.grasp,
state.current_q, state.world.objects/categories/robot/client), so every case
below builds those by hand.  Nothing here needs pybullet or their packages;
the one read against their real world is the single local T episode that
checks the amendment (held until Go has reviewed it).
"""
import json
import os
import types

import pytest

from tampura_bridge import final_world as fw

HOME = [-0.08, -1.67, 0.07, -2.74, 0.08, 1.75, 0.78]
CAT = 'target-class'
GROUP = 'gripper-group'


class FakeClient:
    """pybullet's getClosestPoints on a table {(body, link): [distances]}."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def getClosestPoints(self, bodyA, bodyB, distance, linkIndexA):
        self.calls.append((bodyA, bodyB, distance, linkIndexA))
        # a pybullet contact tuple has contactDistance at index 8
        return [(0, bodyA, bodyB, linkIndexA, -1, (0, 0, 0), (0, 0, 0), (0, 0, 1), d)
                for d in self.table.get((bodyB, linkIndexA), [])]


def make_env(held=None, q=None, gaps=None, objects=(5, 6, 7),
             categories=(CAT, 'other', 'other'), links=(9, 10)):
    client = FakeClient(gaps if gaps is not None else {})
    robot = types.SimpleNamespace(
        body=1,
        get_group_joints=lambda group, client=None: [101, 102],
        get_finger_links=lambda joints, client=None: list(links))
    world = types.SimpleNamespace(objects=list(objects), categories=list(categories),
                                  robot=robot, client=client)
    state = types.SimpleNamespace(
        world=world,
        grasp=None if held is None else types.SimpleNamespace(body=held),
        current_q=list(HOME if q is None else q))
    return types.SimpleNamespace(state=state), client


def read(env, **kw):
    kw.setdefault('target_category', CAT)
    kw.setdefault('home', HOME)
    kw.setdefault('gripper_group', GROUP)
    raw = fw.read_world(env, **kw)
    return raw, fw.verdict(raw)


def test_success_target_held_pads_close_arm_home():
    env, client = make_env(held=5, gaps={(5, 9): [0.0004, 0.01], (5, 10): [0.0006]})
    raw, v = read(env)
    assert raw['attached'] and raw['grasp_body'] == 5 and raw['target_bodies'] == [5]
    assert raw['pad_links'] == [9, 10]
    assert raw['pad_gaps_m'] == [0.0004, 0.0006]          # the nearest point of each pad
    assert raw['at_home'] and raw['home_dev_max_rad'] == 0.0
    assert v == {'pads_on_target': True, 'standard_success': True}
    # the search is on the held body, one query per pad, with the stated radius
    assert client.calls == [(1, 5, fw.SEARCH_DISTANCE_M, 9), (1, 5, fw.SEARCH_DISTANCE_M, 10)]


def test_nothing_held_is_a_failure_and_the_lone_target_is_still_measured():
    env, client = make_env(held=None, gaps={(5, 9): [0.0], (5, 10): [0.0]})
    raw, v = read(env)
    assert not raw['attached'] and raw['grasp_body'] is None
    assert raw['gap_body'] == 5 and raw['pad_gaps_m'] == [0.0, 0.0]
    assert not v['standard_success']


def test_holding_another_body_is_a_failure():
    env, _ = make_env(held=6, gaps={(6, 9): [0.0], (6, 10): [0.0]})
    raw, v = read(env)
    assert raw['grasp_body'] == 6 and not raw['attached']
    assert not v['standard_success']


def test_a_store_symbol_names_its_body():
    env, _ = make_env(held='physical#5', gaps={(5, 9): [0.001], (5, 10): [0.001]})
    assert read(env)[1]['standard_success']
    assert fw.body_id('physical#12') == 12 and fw.body_id(7) == 7 and fw.body_id('3') == 3


@pytest.mark.parametrize('gap,ok', [(0.002, True), (0.0021, False), (-0.002, True),
                                    (-0.0021, False), (0.05, False)])
def test_pad_bound_is_two_millimetres_either_side(gap, ok):
    env, _ = make_env(held=5, gaps={(5, 9): [gap], (5, 10): [0.0]})
    assert read(env)[1]['pads_on_target'] is ok


def test_one_pad_away_or_unseen_fails():
    env, _ = make_env(held=5, gaps={(5, 9): [0.0], (5, 10): [0.02]})
    assert not read(env)[1]['standard_success']
    env, _ = make_env(held=5, gaps={(5, 9): [0.0]})                  # no point near pad 10
    raw, v = read(env)
    assert raw['pad_gaps_m'] == [0.0, None] and not v['standard_success']


def test_the_pad_gap_bound_is_a_parameter_and_is_recorded():
    env, _ = make_env(held=5, gaps={(5, 9): [0.003], (5, 10): [0.003]})
    raw, v = read(env, pad_gap_max_m=0.004)
    assert raw['pad_gap_max_m'] == 0.004 and v['standard_success']


def test_arm_home_follows_their_allclose():
    off = list(HOME)
    off[3] += 1e-3
    env, _ = make_env(held=5, q=off, gaps={(5, 9): [0.0], (5, 10): [0.0]})
    raw, v = read(env)
    assert not raw['at_home'] and abs(raw['home_dev_max_rad'] - 1e-3) < 1e-12
    assert not v['standard_success']
    near = list(HOME)
    near[0] += 5e-5                                    # inside atol 1e-4
    env, _ = make_env(held=5, q=near, gaps={(5, 9): [0.0], (5, 10): [0.0]})
    assert read(env)[1]['standard_success']
    assert not fw.all_close([0.0] * 6, [0.0] * 7)      # a short reading is not home


def test_all_close_is_numpys():
    np = pytest.importorskip('numpy')
    rng = np.random.default_rng(0)
    for _ in range(200):
        b = rng.normal(size=7)
        a = b + rng.normal(scale=2e-4, size=7)
        assert fw.all_close(list(a), list(b)) == bool(np.allclose(a, b, rtol=1e-4, atol=1e-4))


def test_record_writes_the_file_next_to_the_verdict(tmp_path):
    env, _ = make_env(held=5, gaps={(5, 9): [0.0004], (5, 10): [0.0006]})
    rec = fw.record_after_rollout(env, str(tmp_path / 'run'), target_category=CAT,
                                  home=HOME, gripper_group=GROUP)
    assert rec['ok'] and rec['standard_success'] and rec['schema'] == fw.SCHEMA
    on_disk = json.loads((tmp_path / 'run' / fw.FILE).read_text())
    assert on_disk == json.loads(json.dumps(rec))
    assert not (tmp_path / 'run' / (fw.FILE + '.tmp')).exists()


def test_a_failed_read_is_recorded_and_never_raised(tmp_path):
    env = types.SimpleNamespace(state=None)               # their world is not there
    rec = fw.record_after_rollout(env, str(tmp_path), target_category=CAT,
                                  home=HOME, gripper_group=GROUP)
    assert rec['ok'] is False and rec['standard_success'] is False
    assert rec['error'].startswith('AttributeError')
    assert json.loads((tmp_path / fw.FILE).read_text())['ok'] is False


def test_an_unwritable_folder_is_swallowed(tmp_path, monkeypatch):
    env, _ = make_env(held=5, gaps={(5, 9): [0.0], (5, 10): [0.0]})

    def boom(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(os, 'replace', boom)
    rec = fw.record_after_rollout(env, str(tmp_path), target_category=CAT,
                                  home=HOME, gripper_group=GROUP)
    assert rec['ok']                                       # the harness sees no file instead
    assert not (tmp_path / fw.FILE).exists()


@pytest.mark.parametrize('save_dir', [None, 7])
def test_a_write_that_fails_with_anything_but_oserror_is_swallowed(save_dir):
    # R3 of the G13 review: "never raises" holds for the write too (os.makedirs(None) is a TypeError)
    env, _ = make_env(held=5, gaps={(5, 9): [0.0], (5, 10): [0.0]})
    rec = fw.record_after_rollout(env, save_dir, target_category=CAT, home=HOME, gripper_group=GROUP)
    assert rec['ok'] and rec['standard_success']


def test_their_defaults_are_imported_only_when_a_constant_is_missing(monkeypatch):
    called = []
    monkeypatch.setattr(fw, '_their_defaults',
                        lambda: called.append(1) or (CAT, HOME, GROUP))
    env, _ = make_env(held=5, gaps={(5, 9): [0.0], (5, 10): [0.0]})
    fw.read_world(env, target_category=CAT, home=HOME, gripper_group=GROUP)
    assert not called
    assert fw.read_world(env)['target_category'] == CAT and called == [1]
