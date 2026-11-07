"""BF#63: the generated-scene eval.  G19's manifest pins seeds outside the
campaign's map and never re-pins the campaign's twenty; the committed
scenes match their manifest; an episode counts only on its own scene with
an outcome (the declared validity rule); arm O's failure screenshots keep
the final overviews first and leave no image in the run; the tables'
statistics."""
import hashlib
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'tools'))
import gen_scene_eval as gse  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    'bridge_gates_bf63', os.path.join(REPO, 'tools', 'bridge_gates.py'))
bg = importlib.util.module_from_spec(_spec)
# the campaign's map alone, whether or not this shell names a manifest
_manifest_env = os.environ.pop('BRIDGE_SCENE_MANIFEST', None)
try:
    _spec.loader.exec_module(bg)
finally:
    if _manifest_env is not None:
        os.environ['BRIDGE_SCENE_MANIFEST'] = _manifest_env
SCENES = os.path.join(REPO, 'tampura_bridge', 'gen_scenes', 'find_dice')


def _manifest(tmp_path, scenes):
    p = tmp_path / 'manifest.json'
    p.write_text(json.dumps({'scenes': scenes}))
    return str(p)


def test_manifest_pins_new_seeds_only(tmp_path):
    m = bg.merge_scene_manifest(dict(bg.SCENE_MAP),
                                _manifest(tmp_path, {'100': 'find_dice_gen_s100.json'}))
    assert m[100] == 'find_dice_gen_s100.json'
    assert {s: m[s] for s in bg.SCENE_MAP} == bg.SCENE_MAP


def test_manifest_never_repins_a_campaign_seed(tmp_path):
    with pytest.raises(SystemExit):
        bg.merge_scene_manifest(dict(bg.SCENE_MAP),
                                _manifest(tmp_path, {'1': 'find_dice_gen_s1.json'}))


def test_committed_scenes_match_their_manifest():
    with open(os.path.join(SCENES, 'manifest.json')) as f:
        man = json.load(f)
    assert man['scenes']
    for seed, name in man['scenes'].items():
        assert int(seed) not in bg.SCENE_MAP
        assert name == f'find_dice_gen_s{seed}.json'
        with open(os.path.join(SCENES, name), 'rb') as f:
            assert hashlib.sha256(f.read()).hexdigest() == man['details'][seed]['sha256']


def test_validity_rule_arm_t():
    read = {'scene_ok': True, 'standard_read': True}
    assert gse.classify_t(dict(read, status='success')) == (True, '')
    assert gse.classify_t(dict(read, status='failure')) == (True, '')
    assert gse.classify_t({'scene_ok': True, 'status': 'killed'}) == (True, 'timeout')   # no read needed
    assert not gse.classify_t({'scene_ok': True, 'status': 'crashed', 'error': 'rc 1'})[0]
    assert not gse.classify_t({'scene_ok': True, 'status': 'gate_failed'})[0]
    assert not gse.classify_t({'scene_ok': False, 'status': 'success', 'standard_read': True})[0]


def test_validity_rule_arm_t_needs_the_final_world_read():
    # DV-1: an outcome without a readable final world does not count (it runs once more)
    counts, why = gse.classify_t({'scene_ok': True, 'status': 'success'})
    assert not counts and why == 'final world unreadable: no final_world.json'
    counts, why = gse.classify_t({'scene_ok': True, 'status': 'failure', 'standard_read': False,
                                  'final_world': {'ok': False, 'error': 'AttributeError: x'}})
    assert not counts and why == 'final world unreadable: AttributeError: x'


def test_validity_rule_arm_o(tmp_path):
    s = 'find_dice_gen_s100.json'
    base = {'scene_file': s, 'save_dir': str(tmp_path)}
    assert gse.classify_o(dict(base, bridge_status='success'), s) == (True, '')
    assert gse.classify_o(dict(base, bridge_status='failure'), s) == (True, '')
    assert not gse.classify_o(dict(base, bridge_status='crashed'), s)[0]
    assert not gse.classify_o(dict(base, bridge_status='gate_failed'), s)[0]
    assert not gse.classify_o(dict(base, scene_file='find_dice_gen_s101.json',
                                   bridge_status='success'), s)[0]
    # a kill at the cap leaves no episode file: the scene comes from stdout
    (tmp_path / 'stdout.txt').write_text(f'... Loading scene from {s}\n')
    assert gse.classify_o({'save_dir': str(tmp_path), 'timed_out': True,
                           'bridge_status': None}, s) == (True, 'timeout')


def _o_run(tmp_path):
    d = tmp_path / 'run'
    eye = d / 'ours' / 'run_x'
    eye.mkdir(parents=True)
    for k in (1, 2, 3):
        (eye / f'eye_{k:03d}_camera.png').write_bytes(b'png')
    (eye / 'eye_003_gui.png').write_bytes(b'png')
    (eye / 'eye.jsonl').write_text('{"k": 1}\n{"k": 3, "tag": "final"}\n')
    (d / 'overview_final.png').write_bytes(b'png')
    (d / 'overview_final_top.png').write_bytes(b'png')
    (d / 'stdout.txt').write_text('a\nb\n')
    return d


def test_o_shots_keep_the_overviews_first(tmp_path):
    d, dest = _o_run(tmp_path), tmp_path / 'failures' / 'O_s100_r0_a1'
    shots = gse.o_shots(str(d), str(dest), True)
    assert shots == {'images': ['overview_final.png', 'overview_final_top.png',
                                'eye_002_camera.png', 'eye_003_camera.png'], 'taken': 6}
    assert sorted(os.listdir(dest)) == sorted(shots['images'] + ['console_tail.txt', 'eye_last.json'])
    assert json.loads((dest / 'eye_last.json').read_text())['tag'] == 'final'
    assert not [f for _, _, fs in os.walk(d) for f in fs if f.endswith('.png')]


def test_o_shots_of_a_success_delete_every_image(tmp_path):
    d, dest = _o_run(tmp_path), tmp_path / 'failures' / 'O_s100_r0_a1'
    assert gse.o_shots(str(d), str(dest), False) == {'images': [], 'taken': 6}
    assert not dest.exists()
    assert not [f for _, _, fs in os.walk(d) for f in fs if f.endswith('.png')]


def test_statistics():
    lo, hi = gse.wilson(40, 60)
    assert 0.53 < lo < 0.55 and 0.77 < hi < 0.79
    assert gse.mcnemar_exact(0, 0) == 1.0
    assert abs(gse.mcnemar_exact(10, 0) - 2 / 2 ** 10) < 1e-12
    assert gse.mcnemar_exact(3, 3) == 1.0

# ---------------------------------------------------------------------------
# Path 6: arm O2 (arm O from a second snapshot, PLAN.md P6-Q9)
# ---------------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402


def test_parse_arms():
    assert gse.parse_arms('T,O') == ('T', 'O')
    assert gse.parse_arms('O,T') == ('T', 'O')                       # always in running order
    assert gse.parse_arms('T,O,O2', '/x/sb_y') == ('T', 'O', 'O2')
    assert gse.parse_arms('T+O+O2', '/x/sb_y') == ('T', 'O', 'O2')   # '+' survives sbatch --export
    assert gse.parse_arms('O2', '/x/sb_y') == ('O2',)
    for bad, snap in (('', None), ('X', None), ('T,T', None), ('T,O,O2', None), ('T,O', '/x/sb_y')):
        with pytest.raises(SystemExit):
            gse.parse_arms(bad, snap)


def _scene_dir(root, names_to_bytes):
    d = root / 'tampura_bridge' / 'gen_scenes' / 'find_dice'
    d.mkdir(parents=True)
    for n, b in names_to_bytes.items():
        (d / n).write_bytes(b)
    return str(root)


def test_o2_needs_the_same_scene_files_as_o(tmp_path):
    files = {'manifest.json': b'{}', 'find_dice_gen_s140.json': b'a', 'find_dice_gen_s141.json': b'b'}
    man = {'scenes': {'140': 'find_dice_gen_s140.json', '141': 'find_dice_gen_s141.json'}}
    one = _scene_dir(tmp_path / 'one', files)
    two = _scene_dir(tmp_path / 'two', files)
    gse.check_same_scenes(one, two, [140, 141], man)                     # equal: passes
    three = _scene_dir(tmp_path / 'three', dict(files, **{'find_dice_gen_s141.json': b'changed'}))
    with pytest.raises(SystemExit):
        gse.check_same_scenes(one, three, [140, 141], man)
    four = _scene_dir(tmp_path / 'four', dict(files, **{'manifest.json': b'{"x": 1}'}))
    with pytest.raises(SystemExit):
        gse.check_same_scenes(one, four, [140, 141], man)


def _row(arm, seed, success, counts=True, rep=0, attempt=1, why='', timed_out=False, wall=30.0, **rec):
    return {'arm': arm, 'seed': seed, 'rep': rep, 'attempt': attempt, 'scene': f'find_dice_gen_s{seed}.json',
            'n_cups': 3, 'counts': counts, 'why': why, 'success': success, 'timed_out': timed_out,
            'wall_s': wall, 'loop_s': wall, 'host': 'n', 'finished': 'x', 'rec': dict(rec)}


def _write_rows(d, rows):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / 'results.jsonl', 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')


def test_report_default_arms_is_bf63s(tmp_path):
    rows = []
    for seed, (t, o) in {1: (True, True), 2: (False, True), 3: (False, False), 4: (True, False)}.items():
        rows += [_row('T', seed, t), _row('O', seed, o, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert 'O2' not in text
    assert ("paired (both arms counted on the same scene and repetition): 4 pairs; "
            "both succeed 1, only O 1, only T 1, neither 1; exact McNemar p = 1") in text
    assert f"{'seed':>6} {'cups':>5} {'O':>6} {'T':>6}   T's last actions when it failed" in text
    assert 'arm O die carries 4, lost in the hand 0' in text


def test_report_with_arm_o2_adds_its_pairs(tmp_path):
    # seeds: O2 beats O on 2 scenes, O beats O2 on none; O2 beats T on 3, T beats O2 on 1
    table = {1: (True, True, True),     # T, O, O2
             2: (False, False, True),
             3: (False, False, True),
             4: (True, False, False),
             5: (False, True, True)}
    rows = []
    for seed, (t, o, o2) in table.items():
        rows += [_row('T', seed, t), _row('O', seed, o, carries=2, losses=1), _row('O2', seed, o2, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert "paired O2 against O (both counted on the same scene and repetition): 5 pairs; " \
           "both succeed 2, only O2 2, only O 0, neither 1; exact McNemar p = 0.5" in text
    assert "paired O2 against T (both counted on the same scene and repetition): 5 pairs; " \
           "both succeed 1, only O2 3, only T 1, neither 0; exact McNemar p = 0.625" in text
    assert f"{'seed':>6} {'cups':>5} {'O':>6} {'O2':>6} {'T':>6}   T's last actions when it failed" in text
    assert 'arm O2 die carries 5, lost in the hand 0' in text
    assert 'arm O die carries 10, lost in the hand 5' in text
    # the table row of an arm that did not count shows 0/0, not another arm's cell
    rows.append(_row('O2', 6, False, counts=False, why='scene x'))
    _write_rows(tmp_path / 'j2', rows)
    assert 'left out of the pairs of O2 and O' in gse.report([str(tmp_path / 'j2')])


def _fake_run_episode(calls):
    def fake(ns, arm, seed, rep, extra_args=(), extra_env=None):
        calls.append({'out': ns.out, 'snapshot': ns.snapshot, 'python': ns.python, 'arm': arm})
        save_dir = os.path.join(ns.out, arm, f'seed{seed:02d}_r{rep}')
        os.makedirs(save_dir, exist_ok=True)
        return {'arm': arm, 'seed': seed, 'rep': rep, 'rc': 0, 'timed_out': False, 'process_wall_s': 1.0,
                'save_dir': save_dir, 'bridge_status': 'success', 'scene_file': f'find_dice_gen_s{seed}.json',
                'metrics': {'outcome': 'success', 'wall_s': 1.0}, 'carries': 1, 'losses': 0, 'pick_tries': 1}
    return fake


def test_run_one_o2_runs_arm_o_from_the_second_snapshot(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(gse.se, 'run_episode', _fake_run_episode(calls))
    monkeypatch.setattr(os, 'uname', lambda: SimpleNamespace(nodename='testnode'), raising=False)

    def plain_cwd(a, arm, seed, rep, attempt, scene):
        d = tmp_path / 'cwd' / f'{arm}_s{seed}_r{rep}_a{attempt}'
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    monkeypatch.setattr(gse, 'episode_cwd', plain_cwd)
    a = SimpleNamespace(out=str(tmp_path / 'out'), snapshot='/w/sb_a2', snapshot_o2='/w/sb_aprime',
                        python_o='/w/venv/bin/python', cap=900.0, shots='none', cups={'140': 3})
    scene = 'find_dice_gen_s140.json'
    row_o = gse.run_one(a, 'O', 140, 0, 1, scene, 0)
    row_o2 = gse.run_one(a, 'O2', 140, 0, 1, scene, 1)
    row_o2_retry = gse.run_one(a, 'O2', 140, 0, 2, scene, 2)
    assert [c['snapshot'] for c in calls] == ['/w/sb_a2', '/w/sb_aprime', '/w/sb_aprime']
    assert [os.path.basename(c['out']) for c in calls] == ['O', 'O2', 'O2_retry']
    assert all(c['arm'] == gse.ARM_O and c['python'] == '/w/venv/bin/python' for c in calls)
    assert (row_o['arm'], row_o2['arm']) == ('O', 'O2')
    assert row_o['success'] and row_o2['success'] and row_o2['counts']
    assert row_o2_retry['attempt'] == 2


# ---------------------------------------------------------------------------
# Path 6: DV-1 (the standard success test) and DV-2 (the 20-action cap)
# ---------------------------------------------------------------------------
import re  # noqa: E402


def test_t_equiv_is_the_dv2_proxy():
    m = {'picks': 3, 'places': 2, 'senses': 4, 'observes': 6, 'moves': 30}
    assert gse.t_equiv(m, True) == 16                 # picks + places + senses + observes + 1 go-home
    assert gse.t_equiv(m, False) == 15                # no go-home without a success
    assert gse.t_equiv({'picks': 1, 'places': 1}, True) is None
    assert gse.t_equiv(None, True) is None
    assert gse.CAP_ACTIONS == 20


def _plain_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'uname', lambda: SimpleNamespace(nodename='testnode'), raising=False)

    def plain_cwd(a, arm, seed, rep, attempt, scene):
        d = tmp_path / 'cwd' / f'{arm}_s{seed}_r{rep}_a{attempt}'
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    monkeypatch.setattr(gse, 'episode_cwd', plain_cwd)
    monkeypatch.setattr(gse.bc, 'machine_check', lambda: [])
    return SimpleNamespace(out=str(tmp_path / 'out'), snapshot='/w/sb_a2', snapshot_o2='/w/sb_aprime',
                           python_o='/w/venv/bin/python', venv_t='/w/tw/.venv', tampura_work='/w/tw',
                           cap=900.0, shots='none', cups={'140': 3})


def _fake_t(status, standard_read=True, standard_success=False, **extra):
    def fake(ns, rep, seed, order, scene_map, others):
        rec = {'arm': 'T', 'status': status, 'scene_ok': True, 'standard_read': standard_read,
               'standard_success': standard_success, 'save_dir': ns.out, 'wall_s': 5.0, 'loop_s': 4.0,
               'history_read': {}}
        rec.update(extra)
        return rec
    return fake


@pytest.mark.parametrize('status,read,standard,counts,success,reward', [
    ('success', True, True, True, True, True),        # both tests agree
    ('success', True, False, True, False, True),      # their reward says success, the world does not
    ('failure', True, True, True, True, False),       # the world says success, their reward does not
    ('failure', True, False, True, False, False),
    ('success', False, False, False, False, True),    # unreadable: does not count, runs once more
    ('killed', False, False, True, False, False),     # the cap: a failure of the arm
])
def test_run_one_arm_t_scores_the_standard_test(tmp_path, monkeypatch, status, read, standard,
                                                counts, success, reward):
    a = _plain_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(gse.bc, 'episode_t', _fake_t(status, read, standard))
    row = gse.run_one(a, 'T', 140, 0, 1, 'find_dice_gen_s140.json', 0)
    assert (row['counts'], row['success'], row['t_reward_success']) == (counts, success, reward)
    assert row['capped_success'] == success            # T keeps its own 20 steps
    assert row['t_equiv'] is None


def _fake_o(**metrics):
    base = {'outcome': 'success', 'wall_s': 1.0, 'picks': 3, 'places': 2, 'senses': 5, 'observes': 9}
    base.update(metrics)

    def fake(ns, arm, seed, rep, extra_args=(), extra_env=None):
        save_dir = os.path.join(ns.out, arm, f'seed{seed:02d}_r{rep}')
        os.makedirs(save_dir, exist_ok=True)
        ok = base.get('outcome') == 'success'
        return {'arm': arm, 'seed': seed, 'rep': rep, 'rc': 0, 'timed_out': False, 'process_wall_s': 1.0,
                'save_dir': save_dir, 'bridge_status': 'success' if ok else 'failure',
                'scene_file': f'find_dice_gen_s{seed}.json', 'metrics': base,
                'carries': 1, 'losses': 0, 'pick_tries': 1}
    return fake


@pytest.mark.parametrize('metrics,success,capped,t', [
    ({}, True, True, 20),                                     # 3 + 2 + 5 + 9 + 1: on the cap, within it
    ({'observes': 10}, True, False, 21),                      # one over: a success the cap turns into a failure
    ({'outcome': 'failure'}, False, False, 19),               # no go-home on a failure
    ({'outcome': 'failure', 'observes': 40}, False, False, 50),
    ({'picks': None}, True, False, None),                     # no count: not a capped success
])
def test_run_one_arm_o_cut_off_at_twenty_actions(tmp_path, monkeypatch, metrics, success, capped, t):
    a = _plain_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(gse.se, 'run_episode', _fake_o(**metrics))
    for arm in ('O', 'O2'):
        row = gse.run_one(a, arm, 140, 0, 1, 'find_dice_gen_s140.json', 0)
        assert row['success'] is success                      # the uncapped result is kept
        assert row['capped_success'] is capped and row['t_equiv'] == t
        assert row['t_reward_success'] is None


def _crow(arm, seed, success, capped=None, t=None, reward=None, **kw):
    r = _row(arm, seed, success, **kw)
    r.update(capped_success=success if capped is None else capped, t_equiv=t, t_reward_success=reward)
    return r


def _views(text):
    head, rest = text.split('== headline: success within 20 actions ==\n')
    capped, rest = rest.split('\n== the same episodes without the action limit ==\n')
    uncapped, tail = rest.split('\nwith against without the 20-action limit', 1)
    return head, capped, uncapped, 'with against without the 20-action limit' + tail


def test_report_prints_the_capped_headline_and_the_uncapped_view(tmp_path):
    # O: five successes without the limit (t 12, 18, 20, 21, 30), three within it; seed 6 fails
    o = {1: (True, True, 12), 2: (True, True, 18), 3: (True, True, 20),
         4: (True, False, 21), 5: (True, False, 30), 6: (False, False, 25)}
    # T: standard test on seeds 1, 2, 6; their reward on seeds 1, 3
    t = {1: (True, True), 2: (True, False), 3: (False, True), 4: (False, False),
         5: (False, False), 6: (True, False)}
    rows = []
    for s in range(1, 7):
        rows.append(_crow('O', s, o[s][0], capped=o[s][1], t=o[s][2], carries=1, losses=0))
        rows.append(_crow('T', s, t[s][0], reward=t[s][1]))
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    head, capped, uncapped, tail = _views(text)
    assert 'success = the standard test (DV-1)' in head and "T's 20-action horizon" in head
    # headline: O 3 of 6 within the limit, T 3 of 6; pairs 2 both, 1 each way, 2 neither
    assert re.search(r'^O\s+6\s+3\s', capped, re.M) and re.search(r'^T\s+6\s+3\s', capped, re.M)
    assert ("paired (both arms counted on the same scene and repetition): 6 pairs; "
            "both succeed 2, only O 1, only T 1, neither 2; exact McNemar p = 1") in capped
    # the same episodes without the limit: O 5 of 6; the pairs move to 2, 3 and 1
    assert re.search(r'^O\s+6\s+5\s', uncapped, re.M) and re.search(r'^T\s+6\s+3\s', uncapped, re.M)
    assert ("paired (both arms counted on the same scene and repetition): 6 pairs; "
            "both succeed 2, only O 3, only T 1, neither 0; exact McNemar p = 0.625") in uncapped
    assert 'per scene' in capped and 'per scene' not in uncapped
    # with against without: 5 against 3, two lost (t 21 and 30), the proxy's median 20 and maximum 30
    line = next(l for l in tail.splitlines() if l.startswith('O '))
    assert line.split() == ['O', '6', '5', '3', '2', '2/5', '20.0', '30', '2']
    assert 'O seed 4 rep 0 (t 21), O seed 5 rep 0 (t 30)' in tail
    assert 'not printed' in tail
    # T: the standard test against their reward
    assert ("arm T, the standard test against their own reward (6 counted episodes): "
            "both say success 1, only the standard test 2, only their reward 1") in text


def test_report_of_rows_without_cap_fields_is_the_old_uncapped_block(tmp_path):
    rows = [_row('T', 1, True), _row('O', 1, True, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert 'headline' not in text and 'DV-2' not in text
    assert 'paired (both arms counted on the same scene and repetition): 1 pairs;' in text


def test_report_with_arm_o2_prints_its_pairs_in_both_views(tmp_path):
    rows = []
    for s, (t, o, o2, o2c) in {1: (False, True, True, True), 2: (False, False, True, False)}.items():
        rows += [_crow('T', s, t, reward=t), _crow('O', s, o, t=10, carries=1, losses=0),
                 _crow('O2', s, o2, capped=o2c, t=30 if o2 and not o2c else 10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    _, capped, uncapped, tail = _views(text)
    assert 'paired O2 against T (both counted on the same scene and repetition): 2 pairs; ' \
           'both succeed 0, only O2 1, only T 0, neither 1' in capped
    assert 'paired O2 against T (both counted on the same scene and repetition): 2 pairs; ' \
           'both succeed 0, only O2 2, only T 0, neither 0' in uncapped
    assert 'O2 seed 2 rep 0 (t 30)' in tail
