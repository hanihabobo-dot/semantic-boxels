"""BF#68: tools/draw_equiv_compare.py judges two bridge runs.  Its verdicts are
the evidence that drawing changes nothing the run sees, so it is tested on
runs built here: equal runs are SAME; a planner that answers differently on
identical inputs is reported, not judged; a difference in the executing world
(a step, a render) is DIFF; a missing file or a pair in which nothing was
drawn cannot pass."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))
import draw_equiv_compare as cmp  # noqa: E402


def _plan(pid, actions):
    return {'kind': 'plan', 'plan_id': pid, 'actions': actions, 'plan_time_s': 3.0 + pid,
            't': 1.0 * pid}


def _step(plan, step, name):
    return {'kind': 'step', 'plan': plan, 'step': step, 'action': name,
            'args': [name], 't': 1.0 * step}


def _ledger(second_plan_target='q_kin_8', second_step_target=None):
    """Two plans.  Plan 2's first action is a move to second_plan_target (the
    planner's answer); the step the run takes from it moves to
    second_step_target (default: the same, as it should)."""
    tgt = second_step_target or second_plan_target
    return [
        {'kind': 'ledger_open'},
        {'kind': 'episode', 'seed': 0, 'scene_file': 's.json'},
        {'kind': 'gate_info', 'note': 'wrist_robot', 'client': 2},
        {'kind': 'render', 'camera': 'eye', 'client': 0, 'matched': True},
        {'kind': 'plan_call', 'goal': ['and'], 'targets': ['die'], 'problems': []},
        {'kind': 'render', 'camera': 'wrist', 'client': 2, 'matched': True},
        _plan(1, [['move', 'a', 'b'], ['observe', 'x']]),
        _step(1, 1, 'move'), {'kind': 'step_end', 'plan': 1, 'step': 1, 'status': 'ok'},
        _step(1, 2, 'observe'), {'kind': 'step_end', 'plan': 1, 'step': 2, 'status': 'ok'},
        {'kind': 'plan_call', 'goal': ['and'], 'targets': ['die'], 'problems': []},
        {'kind': 'render', 'camera': 'wrist', 'client': 2, 'matched': True},
        _plan(2, [['move', 'b', second_plan_target], ['pick', 'die']]),
        {'kind': 'render', 'camera': 'eye', 'client': 0, 'matched': True},
        {'kind': 'step', 'plan': 2, 'step': 1, 'action': 'move', 'args': ['b', tgt],
         't': 2.0},
        {'kind': 'step_end', 'plan': 2, 'step': 1, 'status': 'ok'},
        {'kind': 'ledger_close'},
    ]


def _write(path, rows):
    with open(path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')


def make_run(root, name, ledger, text=0, lines=100, eye_tags=None, bodies=12,
             renders=None, outcome='success', skip=(), problem=None,
             rng=('n', 'r'), log=None):
    run = os.path.join(root, name)
    ours = os.path.join(run, 'ep', 'ours', 'run_2026-11-06_10-00-00')
    os.makedirs(ours)
    if problem is not None:
        with open(os.path.join(ours, 'problem_initial.pddl'), 'w', encoding='utf-8') as f:
            f.write(problem)
    if log is not None:
        with open(os.path.join(ours, 'run_2026-11-06_10-00-00.log'), 'w',
                  encoding='utf-8') as f:
            f.write(log)
    if 'ledger' not in skip:
        _write(os.path.join(ours, 'ledger.jsonl'), ledger)
    if 'eye' not in skip:
        _write(os.path.join(ours, 'eye.jsonl'),
               [{'tag': t, 'bodies': {'die': [0.5, 0.0, 0.05]}} for t in
                (eye_tags or ['initial', 'plan#1 before action 1/2 move(x)',
                              'plan#2 before action 1/2 move(y)'])])
    # the harness sees one render more than the ledger (TAMPURA's own first image)
    clients = [0] + [r['client'] for r in ledger if r['kind'] == 'render']
    hashes = renders or [f"h{i}" for i in range(len(clients))]
    _write(os.path.join(run, 'render_hashes.jsonl'),
           [{'i': i, 'client': c, 'w': 8, 'h': 8, 'renderer': 65536, 'tiny': i > 0,
             'view': 'v', 'proj': 'p', 'rgb': hashes[i], 'depth': 'd', 'seg': 's'}
            for i, c in enumerate(clients)])
    with open(os.path.join(run, 'ep', 'bridge_episode.json'), 'w', encoding='utf-8') as f:
        json.dump({'outcome': {'status': outcome}, 'rewards': [0.0, 1.0],
                   'gates': {'counts': {}, 'info': {'executing_bodies_at_install': bodies,
                                                    'executing_bodies_now': bodies}},
                   'ledger_gates': [['G3', 'PASS', 'x']], 'seed': 0,
                   'scene_file': 's.json', 'settle': {}, 'switches': {},
                   'readback_identical': True}, f)
    with open(os.path.join(run, 'probe_final.json'), 'w', encoding='utf-8') as f:
        json.dump({'clients': {'0': {'bodies': bodies}}, 'exit_code': 0,
                   'numpy_state': rng[0], 'random_state': rng[1], 'renders': len(clients),
                   'debug_calls': {'line': lines, 'text': text, 'remove': 0,
                                   'remove_all': 1}}, f)
    return run


def verdict(a, b, drawing=None):
    A, B = cmp.load(a), cmp.load(b)
    A['label'], B['label'] = 'A', 'B'
    return {n: (s, d) for n, s, d in cmp.compare(A, B, drawing)}


def test_equal_runs_are_the_same(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger())
    b = make_run(str(tmp_path), 'b', _ledger())
    v = verdict(a, b, 'none')
    assert v['diverge'][0] == 'SAME'
    assert not [n for n, (s, _) in v.items() if s in cmp.BAD], v


def test_a_planner_that_answers_differently_is_reported_and_not_judged(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger('q_kin_8'), text=0, lines=100)
    b = make_run(str(tmp_path), 'b', _ledger('q_kin_6'), text=5, lines=160)
    v = verdict(a, b, 'b')
    assert v['diverge'][0] == 'info' and 'planner' in v['diverge'][1], v['diverge']
    # everything before the planner's answer agrees, and the checks that do
    # not depend on the plan still run
    for name in ('plans', 'steps', 'ledger', 'eye', 'renders', 'gates', 'bodies', 'final',
                 'rng'):
        assert v[name][0] == 'SAME', (name, v[name])
    assert v['drew'][0] == 'ok'
    assert not [n for n, (s, _) in v.items() if s in cmp.BAD], v


def test_a_step_that_differs_from_the_same_plan_is_a_world_difference(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger('q_kin_8', 'q_kin_8'))
    b = make_run(str(tmp_path), 'b', _ledger('q_kin_8', 'q_kin_9'))
    v = verdict(a, b)
    assert v['diverge'][0] == 'DIFF', v['diverge']


def test_a_body_count_or_a_gate_count_that_differs_is_judged_after_a_divergence(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger('q_kin_8'), bodies=12)
    b = make_run(str(tmp_path), 'b', _ledger('q_kin_6'), bodies=13)
    v = verdict(a, b)
    assert v['diverge'][0] == 'info'
    assert v['bodies'][0] == 'DIFF' and v['final'][0] == 'DIFF'


def test_a_differing_render_before_the_divergence_is_judged(tmp_path):
    led = _ledger('q_kin_8')
    n = 1 + sum(1 for r in led if r['kind'] == 'render')
    hashes = [f"h{i}" for i in range(n)]
    other = list(hashes)
    other[2] = 'changed'            # a render long before the planner's answer
    a = make_run(str(tmp_path), 'a', led, renders=hashes)
    b = make_run(str(tmp_path), 'b', _ledger('q_kin_6'), renders=other)
    v = verdict(a, b)
    assert v['diverge'][0] == 'info'
    assert v['renders'][0] == 'DIFF', v['renders']


def test_the_planner_inputs_are_compared_byte_for_byte(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger('q_kin_8'), problem='(define (problem p))')
    b = make_run(str(tmp_path), 'b', _ledger('q_kin_6'), problem='(define (problem p))')
    c = make_run(str(tmp_path), 'c', _ledger('q_kin_6'), problem='(define (problem q))')
    d = make_run(str(tmp_path), 'd', _ledger('q_kin_6'))
    assert verdict(a, b)['inputs'][0] == 'SAME'
    assert verdict(a, c)['inputs'][0] == 'DIFF'
    assert verdict(a, d)['inputs'][0] == 'info'          # nothing recorded to compare


def test_a_missing_file_does_not_compare_as_empty_and_equal(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger())
    b = make_run(str(tmp_path), 'b', _ledger(), skip=('ledger',))
    v = verdict(a, b)
    assert v['floor'][0] == 'FAIL' and 'ledger.jsonl' in v['floor'][1]


# What streams.plan_motion logs, in the planner's own wording (its em dash too): a
# move that is clear, and one that needs the RRT-Connect search (which draws from
# the global RNG).
_CLEAR = ("10:00:01 [DEBUG  ] streams: plan_motion: q_home -> q_a  endpoint_ignored=[0] held={}\n"
          "10:00:01 [INFO   ] streams: plan_motion: direct path clear — linear trajectory\n")
_SEARCH = ("10:00:02 [DEBUG  ] streams: plan_motion: q_a -> q_b  endpoint_ignored=[0] held=[13]\n"
           "10:00:02 [INFO   ] streams: plan_motion: direct path blocked — running RRT-Connect\n"
           "10:00:02 [INFO   ] streams: plan_motion: RRT path 7 wps -> smoothed 3 wps\n")


def test_the_planners_rrt_searches_are_read_from_the_run_log():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'run.log')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(_CLEAR + _SEARCH + _CLEAR
                    + "11:00:00 [DEBUG  ] streams: plan_motion: q_b -> q_c  endpoint_ignored=[0] held={}\n"
                      "11:00:00 [INFO   ] streams: plan_motion: direct path blocked — running RRT-Connect\n"
                      "11:00:09 [WARNING] streams: plan_motion: RRT-Connect failed (2000 iters)\n")
        assert cmp.rrt_runs(path) == [('q_a -> q_b', 'RRT path 7 wps -> smoothed 3 wps'),
                                      ('q_b -> q_c', 'RRT-Connect failed (2000 iters)')]


def test_the_global_rng_states_are_judged_when_the_planners_searched_alike(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger(), rng=('n1', 'r1'), log=_CLEAR + _SEARCH)
    b = make_run(str(tmp_path), 'b', _ledger(), rng=('n1', 'r1'), log=_CLEAR + _SEARCH)
    c = make_run(str(tmp_path), 'c', _ledger(), rng=('n2', 'r1'), log=_CLEAR + _SEARCH)
    assert verdict(a, b)['rng'][0] == 'SAME'
    # the same searches and another state: something else drew a random number
    assert verdict(a, c)['rng'][0] == 'DIFF'
    # no search in either run: the same
    d = make_run(str(tmp_path), 'd', _ledger(), rng=('n1', 'r1'), log=_CLEAR)
    e = make_run(str(tmp_path), 'e', _ledger(), rng=('n2', 'r1'), log=_CLEAR)
    assert verdict(d, e)['rng'][0] == 'DIFF'
    # no run log to read the searches from: judged, as before
    f = make_run(str(tmp_path), 'f', _ledger(), rng=('n1', 'r1'))
    g = make_run(str(tmp_path), 'g', _ledger(), rng=('n2', 'r1'))
    assert verdict(f, g)['rng'][0] == 'DIFF'


def test_a_different_rrt_search_explains_a_different_rng_state(tmp_path):
    # seed 106 of BF#68: the planner of one run searched round a blocked path, the
    # other's went by direct moves; the states differ, and that is reported
    a = make_run(str(tmp_path), 'a', _ledger('q_kin_8'), rng=('n1', 'r1'), log=_CLEAR + _SEARCH)
    b = make_run(str(tmp_path), 'b', _ledger('q_kin_6'), rng=('n2', 'r2'), log=_CLEAR)
    v = verdict(a, b)
    assert v['rng'][0] == 'info' and 'RRT-Connect' in v['rng'][1] and 'q_a -> q_b' in v['rng'][1]
    assert not [n for n, (s, _) in v.items() if s in cmp.BAD], v
    # the world is still judged: another body count fails whatever the searches were
    c = make_run(str(tmp_path), 'c', _ledger('q_kin_6'), rng=('n2', 'r2'), log=_CLEAR, bodies=13)
    assert verdict(a, c)['final'][0] == 'DIFF'
    # and equal states after different searches are fine
    d = make_run(str(tmp_path), 'd', _ledger('q_kin_6'), rng=('n1', 'r1'), log=_CLEAR)
    assert verdict(a, d)['rng'][0] == 'SAME'


def test_a_pair_in_which_nothing_was_drawn_cannot_pass(tmp_path):
    a = make_run(str(tmp_path), 'a', _ledger(), text=0, lines=100)
    b = make_run(str(tmp_path), 'b', _ledger(), text=0, lines=100)
    assert verdict(a, b, 'b')['drew'][0] == 'FAIL'
    c = make_run(str(tmp_path), 'c', _ledger(), text=5, lines=160)
    assert verdict(a, c, 'b')['drew'][0] == 'ok'
    assert verdict(a, c, 'none')['drew'][0] == 'FAIL'      # one of them drew
