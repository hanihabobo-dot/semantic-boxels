"""BF#63: the generated-scene eval.  G19's manifest pins seeds outside the
campaign's map and never re-pins the campaign's twenty; the committed
scenes match their manifest; an episode counts only on its own scene with
an outcome (the declared validity rule); arm O's failure screenshots keep
the final overviews first and leave no image in the run; the tables'
statistics."""
import glob
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
    # a crash of their code is a failure of the arm and counts (Hani, 14 Nov); a gate or another scene is a harness fault
    assert gse.classify_t({'scene_ok': True, 'status': 'crashed', 'error': 'rc 1'}) == (True, 'crashed: rc 1')
    assert not gse.classify_t({'scene_ok': True, 'status': 'gate_failed'})[0]
    assert not gse.classify_t({'scene_ok': False, 'status': 'success', 'standard_read': True})[0]


def test_validity_rule_arm_t_an_unread_final_world_is_a_failure():
    # DV-1: the standard test needs the final world; without it the episode is a failure of arm T (first attempt)
    counts, why = gse.classify_t({'scene_ok': True, 'status': 'success', 'standard_read': False})
    assert counts and why == 'final world unreadable: no final_world.json'
    # a record from before DV-1 has no standard_read key: no final world was ever read, success is their reward
    assert gse.classify_t({'scene_ok': True, 'status': 'success'}) == (True, '')
    assert gse.score_rec('T', {'scene_ok': True, 'status': 'success'}, 's')[2] is True
    assert gse.score_rec('T', {'scene_ok': True, 'status': 'failure'}, 's')[2] is False
    counts, why = gse.classify_t({'scene_ok': True, 'status': 'failure', 'standard_read': False,
                                  'final_world': {'ok': False, 'error': 'AttributeError: x'}})
    assert counts and why == 'final world unreadable: AttributeError: x'
    assert gse.failure_kind({'counts': True, 'why': why}) == 'unread world'
    assert gse.failure_kind({'counts': True, 'why': 'crashed: x'}) == 'crashed'
    assert gse.failure_kind({'counts': True, 'why': 'timeout'}) == 'timeout'
    assert gse.failure_kind({'counts': True, 'why': ''}) is None and gse.failure_kind({'counts': False, 'why': 'scene x'}) is None


def test_validity_rule_arm_o(tmp_path):
    s = 'find_dice_gen_s100.json'
    base = {'scene_file': s, 'save_dir': str(tmp_path)}
    assert gse.classify_o(dict(base, bridge_status='success'), s) == (True, '')
    assert gse.classify_o(dict(base, bridge_status='failure'), s) == (True, '')
    # our own crash, or no outcome, is a failure of arm O and counts; a failed gate is a harness fault
    assert gse.classify_o(dict(base, bridge_status='crashed', bridge_error='boom'), s) == (True, 'crashed: boom')
    assert gse.classify_o(dict(base, bridge_status=None), s) == (True, 'no outcome: ')
    # only the scene gates (G19, G19h) do not count; any other failed gate is a counted failure of arm O
    assert not gse.classify_o(dict(base, bridge_status='gate_failed', gate_failures={'G19': 'x'}), s)[0]
    assert not gse.classify_o(dict(base, bridge_status='gate_failed', gate_failures={'G19': 'x', 'G19h': 'y'}), s)[0]
    assert gse.classify_o(dict(base, bridge_status='gate_failed', gate_failures={'G21': 'x'}), s) == (
        True, 'gate_failed G21: ')
    assert gse.classify_o(dict(base, bridge_status='gate_failed', gate_failures={'G19': 'x', 'G11': 'y'}), s)[0]
    assert gse.classify_o(dict(base, bridge_status='gate_failed'), s) == (True, 'gate_failed (gate not recorded): ')
    # the order: a scene that was seen and is another one first, then the kill, then the outcome
    assert gse.classify_o({'save_dir': str(tmp_path), 'timed_out': True, 'bridge_status': None}, s) == (True, 'timeout')
    assert gse.classify_o({'save_dir': str(tmp_path), 'bridge_status': None, 'bridge_error': 'FileNotFoundError'},
                          s) == (True, 'no outcome: FileNotFoundError')
    assert not gse.classify_o(dict(base, scene_file='find_dice_gen_s101.json', timed_out=True), s)[0]
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
    text2 = gse.report([str(tmp_path / 'j2')])
    assert 'headline cells: the cells where every arm has a counting first attempt' in text2
    assert 'seed 6 rep 0 (O2 did not count)' in text2 and '1 harness fault' in text2 or 'harness faults' in text2


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
    ('success', False, False, True, False, True),     # unreadable: a failure of the arm, counted, never run again
    ('crashed', False, False, True, False, False),    # their crash: a failure of the arm, counted
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


def _two_criteria_rows():
    o = {1: (True, True, 12), 2: (True, True, 18), 3: (True, True, 20),
         4: (True, False, 21), 5: (True, False, 30), 6: (False, False, 25)}
    t = {1: (True, True), 2: (True, False), 3: (False, True), 4: (False, False),
         5: (False, False), 6: (True, False)}              # standard test on seeds 1, 2, 6; their reward on 1, 3
    rows = []
    for s in range(1, 7):
        rows.append(_crow('O', s, o[s][0], capped=o[s][1], t=o[s][2], carries=1, losses=0))
        rows.append(_crow('T', s, t[s][0], reward=t[s][1], final_world=_fw([0.001, 0.003])))
    return rows


def test_report_prints_both_criteria_per_t_episode_and_counts_both(tmp_path):
    _write_rows(tmp_path / 'j1', _two_criteria_rows())
    text = gse.report([str(tmp_path / 'j1')])
    assert ("arm T, both criteria counted (6 counted episodes, first attempts, a crash a failure): the standard test "
            "3/6 [0.19, 0.81], their own reward 2/6 [0.10, 0.70] (95 % Wilson); the headline above uses the standard "
            "test (T_HEADLINE = standard)") in text
    assert 'one episode\'s grasp can lie between 2 and 5 mm of the pad bound' in text
    rows = {int(l.split()[0]): l for l in text.splitlines()
            if re.match(r'^\s+\d+\s+0\s+(success|failure)\s+(success|failure|unknown)\s', l)}
    assert set(rows) == {1, 2, 3, 4, 5, 6}
    assert 'the two differ' not in rows[1] and 'the two differ' in rows[2] and 'the two differ' in rows[3]
    assert '1.00 mm and 3.00 mm' in rows[2] and rows[2].split()[2:4] == ['success', 'failure']
    # nowhere does the report say the pad bound changes no result
    assert 'no result' not in text and 'changes nothing' not in text


def test_t_headline_reward_swaps_arm_ts_success_but_keeps_both_counted(tmp_path, monkeypatch):
    _write_rows(tmp_path / 'j1', _two_criteria_rows())
    monkeypatch.setattr(gse, 'T_HEADLINE', 'reward')
    text = gse.report([str(tmp_path / 'j1')])
    head, capped, uncapped, tail = _views(text)
    assert 'TAMPURA\'s own reward for arm T (T_HEADLINE = reward)' in head
    assert re.search(r'^O\s+6\s+3\s', capped, re.M) and re.search(r'^T\s+6\s+2\s', capped, re.M)    # their reward: 2 of 6
    # pairs on their reward: O within the limit on 1, 2, 3; T on 1, 3
    assert ("both succeed 2, only O 1, only T 0, neither 3; exact McNemar p = 1") in capped
    # both criteria still counted both ways, from the standard-test view
    assert "the standard test 3/6" in text and "their own reward 2/6" in text and '(T_HEADLINE = reward)' in text
    assert ("arm T, the standard test against their own reward (6 counted episodes): "
            "both say success 1, only the standard test 2, only their reward 1") in text


def test_the_cli_t_headline_switch_resets_itself(tmp_path, capsys):
    _write_rows(tmp_path / 'j1', _two_criteria_rows())
    assert gse.main(['--report', str(tmp_path / 'j1'), '--t-headline', 'reward']) == 0
    assert 'T_HEADLINE = reward' in capsys.readouterr().out and gse.T_HEADLINE == 'standard'
    assert gse.main(['--report', str(tmp_path / 'j1')]) == 0
    assert 'the headline above uses the standard test' in capsys.readouterr().out


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
    return _crow('T', seed, False, counts=True, rep=rep, attempt=attempt,
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
    # one attempt per cell, no retry: T 140, O 140, T 141, O 141, T 142: the third unread world stops the job
    assert calls == [('T', 140, 1), ('O', 140, 1), ('T', 141, 1), ('O', 141, 1), ('T', 142, 1)]
    out = capsys.readouterr().out
    assert '[gen] STOPPED: ' in out and '"gate": "FINAL_WORLD"' in out
    assert 'STOPPED by the harness stop rule' in out                      # the report repeats it
    assert 'arm T outcomes whose final world our reader could not read' in out
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
    assert ('arm T outcomes whose final world our reader could not read (our read failed: ours, not a failure of '
            'arm T; 3 stop the job, R2 of the G13 review): 1\n'
            '  T seed 140 rep 0 attempt 1: AttributeError: robot') in text
    assert 'our read failed (arm T\'s final world could not be read by our reader; ours, never booked as their ' \
           'failure, counted in the denominator as a non-success): 1' in text


def _cell_attempt(arm, seed, attempt, success, counts=True, why='', rep=0, **kw):
    return _crow(arm, seed, success, counts=counts, attempt=attempt, why=why, rep=rep, **kw)


def test_the_first_attempt_is_the_result_and_a_later_attempt_is_a_listed_rerun(tmp_path):
    rows = [_cell_attempt('T', 140, 1, False, why='crashed: ZeroDivisionError', reward=False),
            _cell_attempt('T', 140, 2, True, reward=True),                      # a rerun that would have succeeded
            _cell_attempt('O', 140, 1, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    rows_, final, reruns = gse.final_rows_listed([str(tmp_path / 'j1')])
    assert final[('T', 140, 0)]['attempt'] == 1 and not final[('T', 140, 0)]['success']
    assert [(r['attempt'], kind) for r, _, kind in reruns] == [(2, 'later attempt')]
    assert gse.final_rows([str(tmp_path / 'j1')])[1] == final
    text = gse.report([str(tmp_path / 'j1')])
    assert ('failures that count (first attempt; a crash, a hang to the cap, a failed gate of our arm or an '
            'episode cut after its start is a failure of that arm): 1 crashed') in text
    assert '  T seed 140 rep 0 crashed: crashed: ZeroDivisionError' in text
    assert 'reruns and duplicate rows (never counted, listed here, none collapsed silently): 1' in text
    assert 'T seed 140 rep 0 attempt 2 (later attempt, counts, success)' in text and 'NOT FULL: 1 rerun/duplicate row(s)' in text
    assert re.search(r'^T\s+1\s+0\s', text, re.M)                              # T: counted 1, successes 0


def test_a_duplicate_of_the_same_attempt_in_two_folders_is_listed_not_collapsed(tmp_path):
    _write_rows(tmp_path / 'j1', [_cell_attempt('T', 140, 1, True, reward=True),
                                  _cell_attempt('O', 140, 1, True, t=10, carries=1, losses=0)])
    _write_rows(tmp_path / 'j2', [_cell_attempt('T', 140, 1, False, reward=False)])
    _, final, reruns = gse.final_rows_listed([str(tmp_path / 'j1'), str(tmp_path / 'j2')])
    assert final[('T', 140, 0)]['success'] is True                              # the row read first, never the last
    assert [(r['success'], kind) for r, p, kind in reruns] == [(False, 'duplicate')]
    assert reruns[0][1].endswith(os.path.join('j2', 'results.jsonl'))
    text = gse.report([str(tmp_path / 'j1'), str(tmp_path / 'j2')])
    assert '(duplicate, counts, no success)' in text and 'NOT FULL' in text


def test_a_harness_fault_is_listed_not_run_again_and_not_full(tmp_path):
    rows = [_cell_attempt('T', 140, 1, False, counts=False, why='gate_failed: pin', reward=False),
            _cell_attempt('O', 140, 1, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert 'harness faults, first attempts that do not count' in text and '  T seed 140 rep 0: gate_failed: pin' in text
    assert 'NOT FULL: 1 harness fault(s)' in text
    clean = tmp_path / 'clean'
    _write_rows(clean, [_cell_attempt('T', 140, 1, True, reward=True), _cell_attempt('O', 140, 1, True, t=10, carries=1, losses=0)])
    assert 'full: not said (the planned cells are unknown)' in gse.report([str(clean)])       # no metadata.json
    (clean / 'metadata.json').write_text(json.dumps({'seeds': [140, 141], 'reps': 1, 'arms': ['T', 'O']}))
    text = gse.report([str(clean)])
    assert 'planned cells 4 (arms x seeds x repetitions), rows for 2; cells with no row: 2' in text
    assert 'NOT FULL: 2 planned cell(s) have no row' in text                  # a cut job is never "full"
    (clean / 'metadata.json').write_text(json.dumps({'seeds': [140], 'reps': 1, 'arms': ['T', 'O']}))
    assert 'full: every planned cell has one first attempt that counts' in gse.report([str(clean)])


def test_run_makes_one_attempt_per_cell_and_skips_a_cell_that_has_a_row(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140, 141])
    calls = []

    def fake(a_, arm, seed, rep, attempt, scene, order):
        calls.append((arm, seed, attempt))
        if (arm, seed) == ('T', 140):
            return _cell_attempt('T', 140, attempt, False, counts=False, why='gate_failed: pin', reward=False)   # a harness fault
        if (arm, seed) == ('O', 141):
            return _cell_attempt('O', 141, attempt, False, why='crashed: boom', t=10, carries=0, losses=0)       # our crash
        return _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0, reward=True)
    monkeypatch.setattr(gse, 'run_one', fake)
    assert gse.run(a) == 0
    assert calls == [('T', 140, 1), ('O', 140, 1), ('T', 141, 1), ('O', 141, 1)]      # no second attempt, not after a fault
    out = capsys.readouterr().out
    assert 'FAILURE (crashed): crashed: boom' in out and 'HARNESS FAULT, DOES NOT COUNT: gate_failed: pin' in out
    assert '(ours: needs a BUGS.md entry with its cause)' in out
    calls.clear()
    assert gse.run(a) == 0 and calls == []                                           # a resume starts nothing


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
    pads = len(gaps) == 2 and all(g is not None and abs(g) <= 0.005 for g in gaps)
    return {'ok': True, 'attached': attached, 'at_home': at_home, 'pad_gaps_m': gaps,
            'pad_gap_max_m': 0.005, 'pads_on_target': pads}


def test_report_prints_arm_ts_pad_gaps_and_the_episodes_the_bound_alone_fails(tmp_path):
    rows = [_crow('T', 1, True, reward=True, final_world=_fw([0.00045, 0.00045])),
            _crow('T', 2, True, reward=True, final_world=_fw([0.0006, -0.0008])),     # the larger gap is 0.8 mm
            _crow('T', 3, False, reward=True, final_world=_fw([0.0004, 0.0062])),     # attached, home, 6.2 mm: the bound alone
            _crow('T', 4, False, reward=False, final_world=_fw([0.0004, 0.0004], at_home=False)),   # not at home
            _crow('T', 5, False, reward=False, final_world=_fw([None, None], attached=False)),      # nothing held
            _crow('T', 6, True, reward=True, final_world=_fw([0.0005, 0.0005])),
            _crow('O', 1, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert ("final_world): target attached in 5 counted episodes; largest pad gap 6.20 mm (seed 3 rep 0), "
            "median of the larger gap per episode 0.50 mm; attached and at home but failed by the pad "
            "bound alone: 1") in text
    assert ("  T seed 3 rep 0: pad gaps 0.40 mm and 6.20 mm, bound 5 mm, their reward success; "
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


# ---------------------------------------------------------------------------
# rule 18: drops, collisions and clean success in the report (the rows carry the
# fields since TB-22, world_counts.of_record; the report prints them)

O_DET = {'drop_detector': 'telemetry counts: a carried body left both finger pads',
         'collision_detector': 'telemetry counts: distinct (action, body) pairs'}
T_DET = {'drop_detector': 'cannot happen (kinematic carry)',
         'collision_detector': 'not detected (their execution reports no collision)'}


def _r18(row, drops, collisions, det):
    row.update(drops=drops, collisions=collisions, clean_success=None, **det)
    return row


def _r18_rows():
    # O: seeds 1 to 4 succeed (seed 3 only without the action limit), seed 5 fails;
    # seed 2 drops once, seed 4 has two collisions, seed 5 drops twice
    o = {1: (True, True, 0, 0), 2: (True, True, 1, 0), 3: (True, False, 0, 0),
         4: (True, True, 0, 2), 5: (False, False, 2, 0)}
    rows = []
    for s, (ok, capped, drops, coll) in o.items():
        rows.append(_r18(_crow('O', s, ok, capped=capped, t=30 if ok and not capped else 10, carries=1, losses=0),
                         drops, coll, O_DET))
        rows.append(_r18(_crow('T', s, s <= 2, reward=s <= 2), 0, None, T_DET))
    return rows


def _r18_block(text):
    return text.split('drops and collisions (rule 18', 1)[1].split('\n\n')[0]


def test_report_prints_drops_collisions_and_clean_success_per_view(tmp_path):
    _write_rows(tmp_path / 'j1', _r18_rows())
    block = _r18_block(gse.report([str(tmp_path / 'j1')]))
    # O: 2 episodes with a drop (3 drops), 1 with a collision (2 collisions)
    assert re.search(r'^O\s+5\s+2\s+3\s+1\s+2$', block, re.M)
    # T: its carry is kinematic and nothing detects its collisions: words, never 0
    assert re.search(r'^T\s+5\s+cannot happen\s+-\s+not detected\s+-$', block, re.M)
    assert '  T drop_detector (5): cannot happen (kinematic carry)' in block
    assert '  O collision_detector (5): telemetry counts: distinct (action, body) pairs' in block
    # clean success per view: within the limit 3 successes, 1 clean (seed 1); without it 4 and 2
    lo, hi = gse.wilson(1, 5)
    assert re.search(rf'^O\s+within 20 actions \(headline\)\s+5\s+3\s+1\s+\[{lo:.2f}, {hi:.2f}\]\s+0$', block, re.M)
    assert re.search(r'^O\s+without the action limit\s+5\s+4\s+2\s+\[', block, re.M)
    # T's successes have no collision count: clean success is not measured, 2 unknown
    assert re.search(r'^T\s+within 20 actions \(headline\)\s+5\s+2\s+not measured\s+-\s+2$', block, re.M)
    assert ('paired O against T on clean success (within 20 actions (headline)): not printed, 2 of 5 pairs '
            'hold a success whose drops or collisions nothing could count') in block
    # the counts above the block are untouched: O 3 of 5 within the limit
    _, capped, _, _ = _views(gse.report([str(tmp_path / 'j1')]))
    assert re.search(r'^O\s+5\s+3\s', capped, re.M)


def test_report_pairs_two_measured_arms_on_clean_success(tmp_path):
    rows = []
    for s, (o_drops, o2_drops) in {1: (1, 0), 2: (0, 0), 3: (2, 0), 4: (0, 1)}.items():
        rows += [_r18(_crow('O', s, True, t=10, carries=1, losses=0), o_drops, 0, O_DET),
                 _r18(_crow('O2', s, True, t=10, carries=1, losses=0), o2_drops, 0, O_DET),
                 _r18(_crow('T', s, False, reward=False), 0, None, T_DET)]
    _write_rows(tmp_path / 'j1', rows)
    block = _r18_block(gse.report([str(tmp_path / 'j1')]))
    # O clean on seeds 2 and 4, O2 clean on seeds 1, 2 and 3
    assert ('paired O2 against O on clean success (within 20 actions (headline)): 4 pairs; both clean 1, '
            'only O2 2, only O 1, neither 0; exact McNemar p = 1') in block
    # T failed everywhere, so its clean success is known (never clean) and its pairs print
    assert 'paired O2 against T on clean success (without the action limit): 4 pairs; both clean 0, only O2 3' in block


def test_report_of_an_episode_nothing_counted_is_a_lower_bound_not_a_zero(tmp_path):
    rows = [_r18(_crow('O', 1, True, t=10, carries=1, losses=0), 0, 0, O_DET),
            _r18(_crow('O', 2, True, t=10, carries=1, losses=0), None, None,
                 {'drop_detector': 'not detected (no summary and no counts file)',
                  'collision_detector': 'not detected (no summary and no counts file)'}),
            _r18(_crow('T', 1, False, reward=False), 0, None, T_DET),
            _r18(_crow('T', 2, False, reward=False), 0, None, T_DET)]
    _write_rows(tmp_path / 'j1', rows)
    block = _r18_block(gse.report([str(tmp_path / 'j1')]))
    assert re.search(r'^O\s+2\s+0\s+0\s+0\s+0$', block, re.M)
    assert '  O drops: 1 of 2 episodes without a count' in block
    assert re.search(r'^O\s+within 20 actions \(headline\)\s+2\s+2\s+at least 1\s+-\s+1$', block, re.M)


def test_report_of_rows_from_before_the_fields_says_so(tmp_path):
    rows = [_crow('T', 1, True, reward=True), _crow('O', 1, True, t=10, carries=1, losses=0)]
    _write_rows(tmp_path / 'j1', rows)
    assert 'these rows carry no such fields (they were recorded before TB-22)' in gse.report([str(tmp_path / 'j1')])
    # the old uncapped block too (BF#63 run 2's rows)
    _write_rows(tmp_path / 'j2', [_row('T', 1, True), _row('O', 1, True, carries=1, losses=0)])
    assert 'these rows carry no such fields' in gse.report([str(tmp_path / 'j2')])


def test_clean_of_never_reads_a_missing_count_as_clean():
    assert gse.clean_of({'drops': 0, 'collisions': 0}, True) is True
    assert gse.clean_of({'drops': 1, 'collisions': 0}, True) is False
    assert gse.clean_of({'drops': 0, 'collisions': None}, True) is None
    assert gse.clean_of({}, True) is None
    assert gse.clean_of({'drops': 0, 'collisions': None}, False) is False


# ---------------------------------------------------------------------------
# R's read of 9feee81 (tracks/review/validity/HARNESS_9feee81.md): early hangs, failed gates, old rows,
# common cells, planned cells and the start marker

def _scene(seed):
    return f'find_dice_gen_s{seed}.json'


def _o_rec(seed, status='success', timed_out=False, scene='auto', gates=None, error=None, save_dir=None):
    rec = {'timed_out': timed_out, 'bridge_status': status, 'save_dir': save_dir, 'gate_failures': gates or {},
           'bridge_outcome_error': error, 'metrics': {'outcome': 'success' if status == 'success' else 'failure',
                                                       'picks': 2, 'places': 1, 'senses': 0, 'observes': 0}}
    if scene == 'auto' and status is not None:
        rec['scene_file'] = None
    if scene not in (None, 'auto'):
        rec['scene_file'] = scene
    elif scene == 'auto' and status is not None:
        rec['scene_file'] = _scene(seed)
    if status is None:
        rec['bridge_error'] = 'FileNotFoundError: bridge_episode.json'
        rec['metrics'] = None
    return rec


def _t_rec(seed, status='success', **kw):
    rec = {'status': status, 'scene_ok': True, 'scene_file': _scene(seed), 'standard_read': True,
           'standard_success': status == 'success', 'history_read': {'history': True}}
    rec.update(kw)
    return rec


def _real_row(arm, seed, rec, rep=0, attempt=1, **override):
    """A row as run_one writes it (the class from score_rec), then the stored fields overridden: an old row."""
    ok, why, success, timed_out, t_reward, te, capped = gse.score_rec(arm, rec, _scene(seed))
    row = {'arm': arm, 'seed': seed, 'rep': rep, 'attempt': attempt, 'scene': _scene(seed), 'n_cups': 3,
           'counts': ok, 'why': why, 'success': success, 'capped_success': capped, 't_equiv': te,
           't_reward_success': t_reward, 'timed_out': timed_out, 'wall_s': 30.0, 'loop_s': 30.0, 'host': 'n',
           'finished': 'x', 'rec': rec}
    row.update(override)
    return row


def test_an_early_hang_of_arm_o_before_the_scene_line_is_a_counted_failure_and_old_rows_are_scored_again(tmp_path):
    # TB-15's kind: arm O hung before "Loading scene from" (no scene seen, killed at the cap).  The OLD rule
    # stored it as counts False, why "scene None"; today's rule is a timeout, a failure of arm O.
    hang = _o_rec(136, status=None, timed_out=True, save_dir=str(tmp_path / 'nowhere'))
    assert gse.classify_o(hang, _scene(136)) == (True, 'timeout')
    stored_old = _real_row('O', 136, hang, rep=1, counts=False, why='scene None', success=False)
    # an old row that trusted a stored success the record does not bear out
    liar = _real_row('O', 137, _o_rec(137, status='failure'), success=True)
    rows = [stored_old, _real_row('T', 136, _t_rec(136), rep=1), liar, _real_row('T', 137, _t_rec(137))]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert "rows classified again from their stored records by today's rule (never from the stored counts and " \
           "success): 2 of 4 changed class" in text
    assert re.search(r'^O\s+2\s+0\s', text, re.M)             # both O rows count, neither is a success; no cell is left out
    assert 'failures that count' in text and '1 timeout' in text
    assert 'harness faults, first attempts that do not count' in text and ': 0\n' in text
    assert 'stored counts False success False, now counts True success False' in text
    assert 'stored counts True success True, now counts True success False' in text


def test_a_failed_gate_other_than_g19_is_a_counted_failure_of_arm_o_and_trips_the_stop_rule():
    g21 = _real_row('O', 140, _o_rec(140, status='gate_failed', gates={'G21': 'moved a body'}))
    assert (g21['counts'], g21['success']) == (True, False) and gse.gate_names(g21) == ['G21']
    assert gse.failure_kind(g21) == 'gate'
    # G19 and G19h alone: the scene is not the declared one, our fault, does not count, flagged
    g19 = _real_row('O', 141, _o_rec(141, status='gate_failed', gates={'G19': 'scene', 'G19h': 'hash'}))
    assert g19['counts'] is False and gse.failure_kind(g19) is None
    rows = [g21, _real_row('O', 142, _o_rec(142, status='gate_failed', gates={'G21': 'x'})),
            _real_row('O', 143, _o_rec(143, status='gate_failed', gates={'G21': 'x', 'G3': 'y'}))]
    assert gse.stop_reached(gse.stop_counts(rows)) == {'rule': 'HARNESS_STOP', 'arm': 'O', 'gate': 'G21', 'count': 3}


def test_the_report_flags_our_faults_and_names_a_failed_gate(tmp_path):
    rows = [_real_row('O', 141, _o_rec(141, status='gate_failed', gates={'G19': 'scene'})), _real_row('T', 141, _t_rec(141)),
            _real_row('O', 142, _o_rec(142, status='gate_failed', gates={'G21': 'moved a body'})), _real_row('T', 142, _t_rec(142))]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert '  O seed 141 rep 0: gate_failed G19: ' in text and '(ours: needs a BUGS.md entry)' in text
    assert '  O seed 142 rep 0 gate: gate_failed G21: ' in text and '1 gate' in text
    assert 'seed 141 rep 0 (O did not count)' in text            # the headline leaves the fault's cell out for every arm
    assert re.search(r'^O\s+1\s+0\s', text, re.M) and re.search(r'^T\s+1\s+1\s', text, re.M)


def test_the_headline_is_over_the_cells_where_every_arm_counts(tmp_path):
    rows = []
    for seed in (1, 2, 3, 4):
        rows.append(_real_row('T', seed, _t_rec(seed)))
        rows.append(_real_row('O', seed, _o_rec(seed) if seed != 3 else _o_rec(seed, scene='find_dice_gen_s999.json')))
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert re.search(r'^O\s+3\s+3\s', text, re.M) and re.search(r'^T\s+3\s+3\s', text, re.M)     # the same 3 cells
    assert 'left out of the headline table for every arm (named): 1 seed 3 rep 0 (O did not count)' in text
    assert '  O seed 3 rep 0: scene find_dice_gen_s999.json' in text


def test_arm_t_a_pickle_our_reader_could_not_read_does_not_count_but_no_pickle_is_their_crash():
    their = {'status': 'crashed', 'scene_ok': True, 'scene_file': 's', 'error': 'rc 1, no RolloutHistory ()',
             'history_read': {'history': False}}
    assert gse.classify_t(their) == (True, 'crashed: rc 1, no RolloutHistory ()')
    ours = dict(their, history_read={'history': False, 'read_error': 'Traceback: EOFError'})
    counts, why = gse.classify_t(ours)
    assert not counts and why.startswith('our read failed: their pickle exists and our reader could not read it')
    # a hang before the scene line is a counted timeout for arm T too; a seen, other scene is a harness fault
    assert gse.classify_t({'status': 'killed', 'scene_ok': None, 'scene_file': None}) == (True, 'timeout')
    assert not gse.classify_t({'status': 'killed', 'scene_ok': False, 'scene_file': 'other.json'})[0]


def test_both_arms_crashing_on_one_cell_is_named(tmp_path):
    rows = [_real_row('T', 150, _t_rec(150, status='crashed', error='rc 1, no RolloutHistory ()')),
            _real_row('O', 150, _o_rec(150, status=None)), _real_row('T', 151, _t_rec(151)), _real_row('O', 151, _o_rec(151))]
    _write_rows(tmp_path / 'j1', rows)
    text = gse.report([str(tmp_path / 'j1')])
    assert 'cells where both arms crashed: 1 [(150, 0)]: candidates for a shared-code cause' in text


def test_slip_eval_run_episode_carries_the_outcomes_gates_and_error(tmp_path, monkeypatch):
    se = gse.se

    class FakeProc:
        outcome = {}

        def __init__(self, cmd, cwd=None, env=None, stdout=None, stderr=None, start_new_session=None):
            save = cmd[cmd.index('--save-dir') + 1]
            with open(os.path.join(save, 'bridge_episode.json'), 'w') as f:
                json.dump({'scene_file': '/s/' + _scene(140), 'rewards': [0.0], 'outcome': dict(self.outcome)}, f)
            self.pid = 1

        def wait(self, timeout=None):
            return 0
    monkeypatch.setattr(se.subprocess, 'Popen', FakeProc)
    a = SimpleNamespace(out=str(tmp_path), python='py', snapshot='/w/sb', cwd=str(tmp_path), cap=10)
    FakeProc.outcome = {'status': 'gate_failed', 'gate_failures': {'G21': 'x'}, 'error': None}
    rec = se.run_episode(a, gse.ARM_O, 140, 0)
    assert rec['gate_failures'] == {'G21': 'x'} and rec['bridge_outcome_error'] is None
    assert gse.classify_o(rec, _scene(140)) == (True, 'gate_failed G21: ')
    FakeProc.outcome = {'status': 'crashed', 'gate_failures': {}, 'error': 'ValueError: boom'}
    rec = se.run_episode(a, gse.ARM_O, 140, 1)
    assert rec['bridge_outcome_error'] == 'ValueError: boom'
    assert gse.classify_o(rec, _scene(140)) == (True, 'crashed: ValueError: boom')       # the crash keeps its cause


def test_run_writes_a_start_marker_before_the_episode_and_removes_it_after(tmp_path, monkeypatch):
    a = _run_setup(tmp_path, monkeypatch, [140])
    seen = []

    def fake(a_, arm, seed, rep, attempt, scene, order):
        seen.append((arm, os.path.isfile(gse.marker_path(a.out, arm, seed, rep))))
        return _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0, reward=True)
    monkeypatch.setattr(gse, 'run_one', fake)
    assert gse.run(a) == 0
    assert seen == [('T', True), ('O', True)]                                  # the marker was there during each episode
    assert not os.listdir(os.path.join(a.out, 'started'))                      # and is gone once the rows are written


def test_a_started_and_cut_episode_is_a_counted_failure_and_not_run_again(tmp_path, monkeypatch, capsys):
    a = _run_setup(tmp_path, monkeypatch, [140, 141])
    marker = gse.marker_path(a.out, 'T', 140, 0)
    os.makedirs(os.path.dirname(marker))
    with open(marker, 'w') as f:
        json.dump({'arm': 'T', 'seed': 140, 'rep': 0, 'started': '2026-11-15 10:00:00', 'host': 'cn-101'}, f)
    calls = []

    def fake(a_, arm, seed, rep, attempt, scene, order):
        calls.append((arm, seed))
        return _crow(arm, seed, True, attempt=attempt, rep=rep, t=10, carries=1, losses=0, reward=True)
    monkeypatch.setattr(gse, 'run_one', fake)
    assert gse.run(a) == 0
    assert ('T', 140) not in calls and calls == [('O', 140), ('T', 141), ('O', 141)]
    rows = [json.loads(l) for l in open(os.path.join(a.out, 'results.jsonl'))]
    cut = next(r for r in rows if (r['arm'], r['seed']) == ('T', 140))
    assert cut['counts'] is True and cut['success'] is False and cut['why'].startswith('cut: the episode started 2026-11-15 10:00:00')
    assert gse.failure_kind(cut) == 'cut' and not os.path.exists(marker)
    out = capsys.readouterr().out
    assert 'FAILURE (cut)' in out and 'failures that count' in out and '1 cut' in out
    assert 'full: every planned cell has one first attempt that counts' in out        # planned 4 cells, 4 rows, none missing
    # the report's re-classification leaves a cut row alone
    assert gse.reclassify_row(cut) is cut


def _bf63_folder(folder):
    rel = os.path.join('archive', 'tampura_bridge_plan_2026-10-25', 'bf', 'BF63_gen_scenes', folder)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for base in (repo, os.path.join(repo, '..', 'Semantic_Boxels')):
        if glob.glob(os.path.join(base, rel, 'results.jsonl')) or glob.glob(os.path.join(base, rel, '*', 'results.jsonl')):
            return os.path.join(base, rel)
    return None


@pytest.mark.parametrize('folder,o_ok,t_ok,t_crashed,both,o_only,t_only,neither', [
    ('eval', 56, 31, 7, 25, 31, 6, 18),
    ('eval2', 57, 46, 4, 37, 20, 9, 14),
    ('eval3', 69, 46, 4, 40, 29, 6, 5)])
def test_the_report_on_the_archived_bf63_rows_gives_rs_table(folder, o_ok, t_ok, t_crashed, both, o_only, t_only, neither):
    # R's count of the three BF#63 runs, first attempts only, a crash or a hang a failure, over the same 80 pairs
    path = _bf63_folder(folder)
    if path is None:
        pytest.skip('the archived BF#63 folders are not in this checkout')
    text = gse.report([path])
    assert re.search(rf'^O\s+80\s+{o_ok}\s', text, re.M) and re.search(rf'^T\s+80\s+{t_ok}\s', text, re.M)
    assert f"80 pairs; both succeed {both}, only O {o_only}, only T {t_only}, neither {neither};" in text
    assert f"{t_crashed} crashed" in text and 'planned cells 160 (arms x seeds x repetitions), rows for 160' in text
    assert 'left out of the headline table' not in text and 'cells where both arms crashed: 0' in text