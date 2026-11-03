"""BF#63: the generated-scene eval.  G19's manifest pins seeds outside the
campaign's map and never re-pins the campaign's twenty; the committed
scenes match their manifest; an episode counts only on its own scene with
an outcome (the declared validity rule); the tables' statistics."""
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
_spec.loader.exec_module(bg)
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


def test_statistics():
    lo, hi = gse.wilson(40, 60)
    assert 0.53 < lo < 0.55 and 0.77 < hi < 0.79
    assert gse.mcnemar_exact(0, 0) == 1.0
    assert abs(gse.mcnemar_exact(10, 0) - 2 / 2 ** 10) < 1e-12
    assert gse.mcnemar_exact(3, 3) == 1.0
