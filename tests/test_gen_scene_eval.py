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
    assert gse.classify_t({'scene_ok': True, 'status': 'success'}) == (True, '')
    assert gse.classify_t({'scene_ok': True, 'status': 'failure'}) == (True, '')
    assert gse.classify_t({'scene_ok': True, 'status': 'killed'}) == (True, 'timeout')
    assert not gse.classify_t({'scene_ok': True, 'status': 'crashed', 'error': 'rc 1'})[0]
    assert not gse.classify_t({'scene_ok': True, 'status': 'gate_failed'})[0]
    assert not gse.classify_t({'scene_ok': False, 'status': 'success'})[0]


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
