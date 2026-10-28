"""#P4 B0: the ledger reader (tools/bridge_gates.py) fails on every
tampering it is there to catch, and passes a clean ledger."""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location(
    'bridge_gates', os.path.join(REPO, 'tools', 'bridge_gates.py'))
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)

PLAN = [['move', 'cfg:q0', 'cfg:q1', 'free_1', 'Trajectory@1'],
        ['pick', 'cup_a', 'cup_a', 'Grasp@2', 'cfg:q1'],
        ['place', 'cup_a', 'free_2', 'Grasp@2', 'cfg:q2'],
        ['sense', 'die', 'shadow_3']]


def clean():
    rows = [{'kind': 'ledger_open'},
            {'kind': 'plan', 'plan_id': 1, 'call': 'mission',
             'actions': PLAN, 'plan_obj': 77}]
    for k, a in enumerate(PLAN, 1):
        rows.append({'kind': 'step', 'plan': 1, 'step': k, 'action': a[0],
                     'args': a[1:], 'plan_obj': 77})
        if a[0] == 'place':
            rows.append({'kind': 'place_target', 'plan': 1, 'step': k,
                         'boxel': 'free_2', 'target_xy': [0.4, 0.1],
                         'boxel_center_xy': [0.4, 0.1]})
        if a[0] == 'sense':
            rows.append({'kind': 'belief', 'plan': 1, 'step': k,
                         'region': 'shadow_3', 'op': 'status',
                         'status': 'not_here',
                         'channel': 'planned_sense_render'})
            rows.append({'kind': 'sense_result', 'plan': 1, 'step': k,
                         'reason': 'sense_clear_but_empty'})
        rows.append({'kind': 'step_end', 'plan': 1, 'step': k,
                     'status': 'sense_outcome' if a[0] == 'sense' else 'ok'})
    rows.append({'kind': 'ledger_close', 'write_errors': 0})
    return rows


def run(tmp_path, rows, m7='on'):
    with open(tmp_path / 'ledger.jsonl', 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    rep = bg.Report()
    bg.run_ledger(rep, str(tmp_path), m7)
    return {g: s for g, s, _ in rep.rows}


def test_clean_ledger_passes(tmp_path):
    res = run(tmp_path, clean())
    assert res['ledger'] == res['G3'] == res['G4'] == res['G5'] == \
        res['G15'] == 'PASS'


def _edit(pred, change):
    rows = clean()
    for r in rows:
        if pred(r):
            change(r)
    return rows


@pytest.mark.parametrize('name,rows,gate', [
    ('changed args', _edit(lambda r: r['kind'] == 'step' and r['step'] == 3,
                           lambda r: r['args'].__setitem__(1, 'free_9')), 'G3'),
    ('other list object', _edit(lambda r: r['kind'] == 'step' and r['step'] == 2,
                                lambda r: r.update(plan_obj=78)), 'G3'),
    ('unlabelled exit', _edit(lambda r: r['kind'] == 'step_end' and r['step'] == 4,
                              lambda r: r.update(status='unlabelled')), 'G3'),
    ('place off centre', _edit(lambda r: r['kind'] == 'place_target',
                               lambda r: r.update(target_xy=[0.45, 0.1])), 'G4'),
    ('belief without channel', _edit(lambda r: r['kind'] == 'belief',
                                     lambda r: r.update(channel=None)), 'G5'),
    ('sense render of another region',
     _edit(lambda r: r['kind'] == 'belief',
           lambda r: r.update(region='shadow_8')), 'G5'),
])
def test_tampering_fails(tmp_path, name, rows, gate):
    assert run(tmp_path, rows)[gate] == 'FAIL', name


def test_skipped_step_fails_g3(tmp_path):
    rows = [r for r in clean()
            if not (r.get('plan') == 1 and r.get('step') == 2)]
    assert run(tmp_path, rows)['G3'] == 'FAIL'


def test_silent_early_end_fails_g3(tmp_path):
    rows = [r for r in clean()
            if not (r.get('plan') == 1 and r.get('step') == 4)]
    assert run(tmp_path, rows)['G3'] == 'FAIL'


def test_ok_then_more_steps_is_fine_but_trigger_mid_plan_fails(tmp_path):
    rows = _edit(lambda r: r['kind'] == 'step_end' and r['step'] == 2,
                 lambda r: r.update(status='pick_failure'))
    assert run(tmp_path, rows)['G3'] == 'FAIL'


def test_incomplete_ledger_fails(tmp_path):
    rows = [r for r in clean() if r['kind'] != 'ledger_close']
    assert run(tmp_path, rows)['ledger'] == 'FAIL'


def test_unrendered_rediscovery_depends_on_m7(tmp_path):
    extra = {'kind': 'belief', 'plan': 1, 'step': 4, 'region': 'shadow_5',
             'op': 'remove', 'status': None,
             'channel': 'superseded_unrendered'}
    rows = clean()
    rows.insert(-1, extra)
    assert run(tmp_path, rows, m7='on')['G5'] == 'FAIL'
    assert run(tmp_path, rows, m7='off')['G5'] == 'PASS'


def test_scene_map_g19(tmp_path):
    rows = clean()
    rows.insert(1, {'kind': 'episode', 'seed': 0,
                    'scene_file': 'problems/1747173591.json'})
    assert run(tmp_path, rows)['G19'] == 'PASS'
    rows[1]['scene_file'] = 'problems/1747173590.json'
    assert run(tmp_path, rows)['G19'] == 'FAIL'


def test_scene_map_g19_is_the_cluster_map(tmp_path):
    # BF#8, option A: on the cluster seed 1 loads 1747173593; the laptop
    # run's 1747173590 for seed 1 now fails G19.
    rows = clean()
    rows.insert(1, {'kind': 'episode', 'seed': 1,
                    'scene_file': '1747173593.826745.json'})
    assert run(tmp_path, rows)['G19'] == 'PASS'
    rows[1]['scene_file'] = '1747173590.312597.json'
    assert run(tmp_path, rows)['G19'] == 'FAIL'
    assert bg.SCENE_MAP_LAPTOP_2026_05_26[1] == '1747173590'
    assert len(bg.SCENE_MAP) == len(bg.SCENE_MAP_LAPTOP_2026_05_26) == 20


def test_runtime_counts_reach_g11_and_g21(tmp_path):
    rows = clean()
    rows.insert(-1, {'kind': 'gate_record', 'counts': {'G14': 1},
                     'solve_calls': 2, 'steps': {}})
    res = run(tmp_path, rows)
    assert res['G21'] == 'FAIL'
    assert res['G11'] == 'FAIL'
    rows[-2] = {'kind': 'gate_record', 'counts': {}, 'solve_calls': 1,
                'steps': {}}
    res = run(tmp_path, rows)
    assert res['G21'] == 'PASS' and res['G11'] == 'PASS'


# ----- GF5: G18, G19's seed hygiene, the outcome field ---------------------

def bridge():
    """clean() as a bridge episode: stamped rows, the episode and
    driver_clock rows, a gate_record."""
    rows = clean()
    rows.insert(1, {'kind': 'episode', 'seed': 0,
                    'scene_file': '1747173591.json'})
    rows.insert(2, {'kind': 'driver_clock', 'seed': 0,
                    'events': [[n, float(k)] for k, n in enumerate(bg.G18_EVENTS)],
                    'rng_untouched': {'random': True, 'numpy': True},
                    'pythonhashseed': '0'})
    rows.insert(-1, {'kind': 'gate_record', 'counts': {}, 'solve_calls': 1,
                     'steps': {}})
    start = len(bg.G18_EVENTS) - 1
    for k, r in enumerate(rows):
        r['t'] = start + 1.0 + k
    return rows


def test_clean_bridge_ledger_passes(tmp_path):
    res = run(tmp_path, bridge())
    assert all(s == 'PASS' for s in res.values()), res
    assert res['G18'] == res['G19h'] == 'PASS'


def _clock(change):
    rows = bridge()
    change(rows[2])
    return rows


def _swap_events(ck):
    ev = ck['events']
    ev[4][0], ev[5][0] = ev[5][0], ev[4][0]


@pytest.mark.parametrize('name,rows,gate', [
    ('extra driver work', _clock(lambda ck: ck['events'].insert(
        3, ['plan_warmup', 2.5])), 'G18'),
    ('stamps reordered', _clock(_swap_events), 'G18'),
    ('stamps out of time', _clock(lambda ck: ck['events'][4].__setitem__(1, 0.5)),
     'G18'),
    ('random consumed', _clock(lambda ck: ck['rng_untouched'].update(
        random=False)), 'G19h'),
    ('numpy consumed', _clock(lambda ck: ck['rng_untouched'].update(
        numpy=False)), 'G19h'),
    ('other seed', _clock(lambda ck: ck.update(seed=3)), 'G19h'),
    ('hash seed unset', _clock(lambda ck: ck.update(pythonhashseed=None)), 'G19h'),
])
def test_driver_clock_tampering_fails(tmp_path, name, rows, gate):
    assert run(tmp_path, rows)[gate] == 'FAIL', name


def test_bridge_work_before_rollout_start_fails_g18(tmp_path):
    rows = bridge()
    rows[4]['t'] = 1.0           # a row written before their first step
    assert run(tmp_path, rows)['G18'] == 'FAIL'


def test_bridge_run_without_clock_or_gate_record_fails(tmp_path):
    rows = [r for r in bridge() if r['kind'] not in ('driver_clock', 'gate_record')]
    res = run(tmp_path, rows)
    assert res['G18'] == res['G19h'] == res['G21'] == 'FAIL'


def test_outcome_field(tmp_path):
    ok, bad = bg.Report(), bg.Report()
    ok.add('G3', 'PASS')
    ok.add('G21', 'N/A')
    bad.add('G3', 'PASS')
    bad.add('G18', 'FAIL', 'stamps out of time order')
    assert bg.episode_outcome([0.0, 1.0], None, ok)['status'] == 'success'
    assert bg.episode_outcome([0.0, 0.0], None, ok)['status'] == 'failure'
    # a gate failure outranks a reward of 1.0, a crash outranks both
    out = bg.episode_outcome([0.0, 1.0], None, bad)
    assert out['status'] == 'gate_failed' and not out['success']
    assert out['gate_failures'] == {'G18': 'stamps out of time order'}
    out = bg.episode_outcome([0.0, 1.0], 'RuntimeError: x', bad)
    assert out['status'] == 'crashed' and not out['success']
    assert bg.episode_outcome([], None, ok)['status'] == 'failure'
