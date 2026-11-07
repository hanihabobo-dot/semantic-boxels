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
    assert line.split() == ['O', '6', '5', '3', '2', '2/5', '20.0', '30', '2', '0']
    assert 'O seed 4 rep 0 (t 21), O seed 5 rep 0 (t 30)' in tail
    assert 'not printed' in tail
    # T: the standard test against their reward
    assert ("arm T, the standard test against their own reward (6 counted episodes): "
            "both say success 1, only the standard test 2, only their reward 1") in text


def test_report_of_rows_without_cap_fields_is_the_old_uncapped_block(tmp_path):
    rows = [_row('T', 1, True), _row('O', 1, True, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert 'headline' not in text and 'DV-2' not in text and 'Caveat' not in text
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


# ---------------------------------------------------------------------------
# the review of the G13 amendment (Sub-manager T (2), R1 to R5)

def _unread_row(seed, attempt=1, rep=0, err='AttributeError: x'):
    return _crow('T', seed, False, counts=False, rep=rep, attempt=attempt,
                 why=f'{gse.UNREAD_WHY}: {err}', final_world={'ok': False, 'error': err})


def test_an_unread_final_world_counts_like_a_gate_failure():
    unread = _unread_row(140)
    assert gse.gate_names(unread) == ['FINAL_WORLD']
    assert gse.gate_names(dict(unread, arm='O')) == []          # only arm T has a final world to read
    g13 = _crow('T', 141, False, counts=False, why='gate_failed: pin', gate_failures={'G13': 'pin'})
    assert gse.gate_names(g13) == ['G13']
    assert gse.gate_names(_crow('T', 142, True)) == []


def test_the_stop_rule_is_three_of_one_arm_under_one_gate():
    rows = [_unread_row(140), _unread_row(140, attempt=2)]
    assert gse.stop_reached(gse.stop_counts(rows)) is None
    # a third unread world on another arm is not the same arm
    assert gse.stop_reached(gse.stop_counts(rows + [dict(_unread_row(141), arm='O')])) is None
    rows.append(_unread_row(141))
    assert gse.stop_reached(gse.stop_counts(rows)) == {'rule': 'HARNESS_STOP', 'arm': 'T',
                                                       'gate': 'FINAL_WORLD', 'count': 3}
    # an unread world and a G13 failure are two gates: two and two do not stop
    mixed = [_unread_row(1), _unread_row(2)] + [
        _crow('T', s, False, counts=False, why='gate_failed: pin', gate_failures={'G13': 'pin'}) for s in (3, 4)]
    assert gse.stop_reached(gse.stop_counts(mixed)) is None


def _run_setup(tmp_path, monkeypatch, seeds):
    scenes = tmp_path / 'scenes'
    scenes.mkdir()
    (scenes / 'manifest.json').write_text(json.dumps({
        'scenes': {str(s): f'find_dice_gen_s{s}.json' for s in seeds},
        'details': {str(s): {'n_cups': 3} for s in seeds}}))
    monkeypatch.setenv('BRIDGE_SCENE_MANIFEST', str(scenes / 'manifest.json'))
    monkeypatch.setattr(os, 'uname', lambda: SimpleNamespace(nodename='testnode'), raising=False)
    monkeypatch.setattr(gse.se, 'pipeline_alive', lambda pid: [])
    monkeypatch.setattr(gse.se, 'check_arms', lambda *a, **k: None)
    monkeypatch.setattr(gse.bc, 'cpu_model', lambda: 'cpu')
    return SimpleNamespace(scenes=str(scenes), out=str(tmp_path / 'out'), seeds=f'{seeds[0]}-{seeds[-1]}',
                           reps=1, arms='T,O', snapshot='/w/sb', snapshot_o2=None, python_o='py',
                           venv_t='vt', tampura_work='/w/tw', cap=900.0, shots='none')


def test_run_stops_after_three_unread_worlds_and_says_so(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140, 141, 142, 143])
    calls = []

    def fake(a_, arm, seed, rep, attempt, scene, order):
        calls.append((arm, seed, attempt))
        if arm == 'T':
            return _unread_row(seed, attempt=attempt, rep=rep)
        return _crow('O', seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0)
    monkeypatch.setattr(gse, 'run_one', fake)
    assert gse.run(a) == 2
    # T seed 140 twice (the retry), O seed 140, then T seed 141: the third unread world stops the job
    assert calls == [('T', 140, 1), ('T', 140, 2), ('O', 140, 1), ('T', 141, 1)]
    out = capsys.readouterr().out
    assert '[gen] STOPPED: ' in out and '"gate": "FINAL_WORLD"' in out
    assert 'STOPPED by the harness stop rule' in out                      # the report repeats it
    assert 'arm T outcomes whose final world could not be read' in out
    md = json.loads((tmp_path / 'out' / 'metadata.json').read_text())
    assert md['status'] == 'stopped' and md['stop']['count'] == 3
    assert md['stop_counts'] == {'T:FINAL_WORLD': 3}
    # a resumed run does not go on past a rule the rows already meet
    calls.clear()
    assert gse.run(a) == 2 and calls == []


def test_run_without_a_stop_finishes_with_exit_zero(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140, 141])
    monkeypatch.setattr(gse, 'run_one', lambda a_, arm, seed, rep, attempt, scene, order:
                        _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0))
    assert gse.run(a) == 0
    md = json.loads((tmp_path / 'out' / 'metadata.json').read_text())
    assert md['status'] == 'finished' and md['stop'] is None and md['stop_counts'] == {}
    assert 'STOPPED' not in capsys.readouterr().out


def test_report_lists_the_unread_worlds_apart_with_their_errors(tmp_path):
    rows = [_unread_row(140, err='AttributeError: robot'), _crow('T', 140, True, attempt=2, reward=True),
            _crow('O', 140, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert ('arm T outcomes whose final world could not be read (they do not count and ran once more; '
            '3 stop the job, R2 of the G13 review): 1\n'
            '  T seed 140 rep 0 attempt 1: AttributeError: robot') in text


def test_report_repeats_a_stop_from_a_jobs_metadata(tmp_path):
    _write_rows(tmp_path / 'j1', [_crow('T', 1, True, reward=True), _crow('O', 1, True, t=10, carries=1, losses=0)])
    (tmp_path / 'j1' / 'metadata.json').write_text(json.dumps(
        {'stop': {'rule': 'HARNESS_STOP', 'arm': 'T', 'gate': 'FINAL_WORLD', 'count': 3}}))
    text = gse.report([str(tmp_path / 'j1')])
    assert 'STOPPED by the harness stop rule' in text and '"gate": "FINAL_WORLD"' in text


def test_report_opens_with_the_caveat_on_the_two_forms_of_the_test(tmp_path):
    _write_rows(tmp_path / 'j1', [_crow('T', 1, True, reward=True), _crow('O', 1, True, t=10, carries=1, losses=0)])
    text = gse.report([str(tmp_path / 'j1')])
    assert text.startswith('Caveat first: TAMPURA carries the die kinematically')
    assert 'geometrically' in text.split('\n\n')[0] and 'physical' in text.split('\n\n')[0]
    assert text.index('Caveat first') < text.index('== headline')


def _fw(gaps, attached=True, at_home=True):
    pads = len(gaps) == 2 and all(g is not None and abs(g) <= 0.002 for g in gaps)
    return {'ok': True, 'attached': attached, 'at_home': at_home, 'pad_gaps_m': gaps,
            'pad_gap_max_m': 0.002, 'pads_on_target': pads}


def test_report_prints_arm_ts_pad_gaps_and_the_episodes_the_bound_alone_fails(tmp_path):
    rows = [_crow('T', 1, True, reward=True, final_world=_fw([0.00045, 0.00045])),
            _crow('T', 2, True, reward=True, final_world=_fw([0.0006, -0.0008])),     # the larger gap is 0.8 mm
            _crow('T', 3, False, reward=True, final_world=_fw([0.0004, 0.0031])),     # attached, home, 3.1 mm: the bound alone
            _crow('T', 4, False, reward=False, final_world=_fw([0.0004, 0.0004], at_home=False)),   # not at home
            _crow('T', 5, False, reward=False, final_world=_fw([None, None], attached=False)),      # nothing held
            _crow('T', 6, True, reward=True, final_world=_fw([0.0005, 0.0005])),
            _crow('O', 1, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert ("final_world): target attached in 5 counted episodes; largest pad gap 3.10 mm (seed 3 rep 0), "
            "median of the larger gap per episode 0.50 mm; attached and at home but failed by the pad "
            "bound alone: 1") in text
    assert ("  T seed 3 rep 0: pad gaps 0.40 mm and 3.10 mm, bound 2 mm, their reward success; "
            "reported to Sub-manager T and Go before a wave counts") in text
    assert 'T seed 4 rep 0: pad gaps' not in text and 'T seed 5 rep 0: pad gaps' not in text


def test_report_without_final_worlds_prints_no_pad_lines(tmp_path):
    _write_rows(tmp_path / 'j1', [_crow('T', 1, True, reward=True), _crow('O', 1, True, t=10, carries=1, losses=0)])
    assert 'pad gaps' not in gse.report([str(tmp_path / 'j1')])


def test_with_vs_without_counts_an_unknown_proxy_apart(tmp_path):
    rows = [_crow('O', 1, True, t=10, carries=1, losses=0),
            _crow('O', 2, True, capped=False, t=25, carries=1, losses=0),
            _crow('O', 3, True, capped=False, t=None, carries=1, losses=0),
            _crow('T', 1, True, reward=True), _crow('T', 2, True, reward=True), _crow('T', 3, True, reward=True)]
    _write_rows(tmp_path / 'j1', rows)
    _, _, _, tail = _views(gse.report([str(tmp_path / 'j1')]))
    assert 't unknown' in tail
    line = next(l for l in tail.splitlines() if l.startswith('O '))
    # counted 3, without 3, with 1, lost 2 (one above the limit, one without a proxy count)
    assert line.split() == ['O', '3', '3', '1', '2', '2/3', '17.5', '25', '1', '1']
    assert 'the limit turns these successes into failures: O seed 2 rep 0 (t 25)' in tail
    assert 'a missing count, not an action-limit failure' in tail and 'O seed 3 rep 0' in tail

# ---------------------------------------------------------------------------
# rule 16: memory around every episode, and the stop (tools/memwatch.py)

GB = 1024 * 1024        # kB


def _mem_rows(tmp_path):
    return [json.loads(ln) for ln in (tmp_path / 'out' / 'results.jsonl').read_text().splitlines()]


def test_run_records_mem_in_every_row_and_logs_it(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140, 141])
    monkeypatch.setattr(gse.mw, 'mem_available_kb', lambda path='/proc/meminfo': 8 * GB)
    monkeypatch.setattr(gse, 'run_one', lambda a_, arm, seed, rep, attempt, scene, order:
                        _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0))
    assert gse.run(a) == 0
    rows = _mem_rows(tmp_path)
    assert len(rows) == 4
    for r in rows:
        assert r['mem']['avail_start_kb'] == r['mem']['avail_end_kb'] == 8 * GB
        assert r['mem']['min_avail_limit_kb'] == 4 * GB and r['mem']['peak_limit_kb'] == 6 * GB
        assert r['peak_over_6gb'] is False
    out = capsys.readouterr().out
    assert 'mem T seed 140 rep 0 attempt 1 end: MemAvailable 8.00 GB' in out
    assert 'memory: 4 episodes recorded; lowest MemAvailable 8.00 GB' in out


def test_run_stops_with_exit_4_after_the_episode_that_drops_memory(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140, 141, 142])
    state = {'avail': 8 * GB}
    monkeypatch.setattr(gse.mw, 'mem_available_kb', lambda path='/proc/meminfo': state['avail'])
    calls = []

    def fake(a_, arm, seed, rep, attempt, scene, order):
        calls.append((arm, seed))
        if (arm, seed) == ('O', 140):
            state['avail'] = 3 * GB                      # memory falls during this episode
        return _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0)
    monkeypatch.setattr(gse, 'run_one', fake)
    assert gse.run(a) == 4
    assert calls == [('T', 140), ('O', 140)]            # the stop comes after the row of the episode that dropped it
    out = capsys.readouterr().out
    assert '[mem] STOPPED_LOW_MEMORY: O seed 140 rep 0 attempt 1 end: MemAvailable 3.00 GB under the limit 4.00 GB' in out
    assert 'STOPPED_LOW_MEMORY (' in out                 # the report repeats it
    assert (tmp_path / 'out' / 'STOPPED_LOW_MEMORY.txt').read_text().startswith('STOPPED_LOW_MEMORY')
    md = json.loads((tmp_path / 'out' / 'metadata.json').read_text())
    assert md['status'] == 'stopped' and md['stop']['rule'] == 'STOPPED_LOW_MEMORY' and md['stop']['where'] == 'end'
    rows = _mem_rows(tmp_path)
    assert len(rows) == 2 and rows[1]['mem']['avail_end_kb'] == 3 * GB
    # nothing starts while memory stays low
    calls.clear()
    assert gse.run(a) == 4 and calls == []
    assert json.loads((tmp_path / 'out' / 'metadata.json').read_text())['stop']['where'] == 'start'
    # a limit of 0 only records: the job goes on to the end
    a.min_avail_gb = 0
    assert gse.run(a) == 0 and len(calls) == 4          # T 141, O 141, T 142, O 142


def test_a_peak_over_the_limit_is_flagged_in_the_row_and_the_report(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140])
    monkeypatch.setattr(gse.mw, 'mem_available_kb', lambda path='/proc/meminfo': 8 * GB)
    marks = iter([1_000_000, 7 * GB, 7 * GB, 7 * GB])           # the children's high-water mark before and after each of the
    real = gse.mw.EpisodeWatch                                  # two episodes: it rises past 6 GB in the first one only
    monkeypatch.setattr(gse.mw, 'EpisodeWatch', lambda *args, **kw: real(*args, rusage=lambda: next(marks), **kw))
    monkeypatch.setattr(gse, 'run_one', lambda a_, arm, seed, rep, attempt, scene, order:
                        _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0))
    assert gse.run(a) == 0
    rows = _mem_rows(tmp_path)
    assert [r['peak_over_6gb'] for r in rows] == [True, False] and rows[0]['mem']['peak_exact'] is True
    out = capsys.readouterr().out
    assert 'OVER 6 GB (report it)' in out and 'memory: OVER the peak limit: T seed 140 rep 0 attempt 1' in out

def test_report_prints_the_job_scripts_memory_lines(tmp_path):
    rows = [_crow('T', 1, True, reward=True), _crow('O', 1, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    (tmp_path / 'j1' / 'memory_lines.txt').write_text(
        'memory at the start: MemTotal: 196000000 kB  MemAvailable: 150000000 kB  local fs /tmp xfs '
        '(tmpfs is RAM), Slurm --mem 24576 MB\n'
        'memory after the job: 0 pipeline processes of ours alive, 0 names in /dev/shm, MemAvailable 149000000 kB\n')
    text = gse.report([str(tmp_path / 'j1')])
    assert f"memory ({tmp_path / 'j1'}): memory at the start: MemTotal: 196000000 kB" in text
    assert f"memory ({tmp_path / 'j1'}): memory after the job: 0 pipeline processes of ours alive, " \
           "0 names in /dev/shm" in text
    # no mem in the rows and no such file: no memory block at all
    _write_rows(tmp_path / 'j2', rows)
    assert '\nmemory' not in gse.report([str(tmp_path / 'j2')])