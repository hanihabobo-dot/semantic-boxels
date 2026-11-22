"""Phase 0 pin 27, group "console" (R's pin list row 27, PLAN 5.2 row 27, R's
plan review S-d): recorded runs and made tapes played through the real
Console by tools/readable/console_replay.py.

The unit tests at the top import no pipeline module (they run on Windows
too): reading a run log, the anchors that place the ledger rows among the
log's lines, the header and summary derivation, the made tapes' form, the
masks, the group's pin list.

The tests below them play tapes through console_ui's Console, each in its
own child interpreter (the Console takes over file descriptors 1 and 2), so
they run in WSL only, with the arm-O venv, under the pipeline lock:

    PYTHONHASHSEED=0 flock /root/sb_pipeline.lock /root/armO-venvA/bin/python \\
        -m pytest -q tests/readable/test_pin_console.py

READABLE_TAPES=<folder written by record_episode.py --record-set> adds the
pins of pin 47's live runs.  No golden output is stored before tag
refactor-checkpoint-2 (R's condition): with READABLE_GOLDEN=<folder written
by pin_outputs.py --group console> each pin is compared with it.
Pin 26 (the pure console functions) is p26_console_pure in group low.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name, path):
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


cr = _load('readable_console_replay', REPO / 'tools' / 'readable' / 'console_replay.py')
sys.path.insert(0, str(REPO / 'tools' / 'readable'))
import pin_outputs as po  # noqa: E402

GOLDEN = po.readable_path(po.GOLDEN_VAR)   # absolute, or None when unset (SPEC D11)
TAPES = os.environ.get('READABLE_TAPES')
PINS = [p for p in po.GROUPS['console'] if TAPES or not p.startswith('p27_tape_')]
MADE_PINS = [p for p in PINS if p.startswith('p27_made_')]
RUN_PINS = [p for p in PINS if not p.startswith('p27_made_')]

in_wsl = pytest.mark.skipif(os.name == 'nt', reason='plays console_ui (a pipeline module): WSL, the arm-O '
                                                    'venv, under the pipeline lock')
needs_golden = pytest.mark.skipif(
    not GOLDEN, reason='READABLE_GOLDEN is not set: no stored golden output exists before tag '
                       'refactor-checkpoint-2 (R\'s condition)')

# The exit code each made tape ends with: finish(code) as the tape says, a
# SystemExit with a message 1, a crash 1, an interrupt 130 (Console._excepthook).
MADE_EXIT = {'holding': 0, 'stack': 1, 'tray': 0, 'plain_goal': 0, 'bridge': 1, 'g19_stop': 1,
             'crash': 1, 'interrupt': 130}
# Rules no tape reaches, each with its reason (R's S-d: the record lists
# them).  Empty: the made tapes reach every rule of console_ui at the
# checkpoint (record phase0/build/console_replay.md).
KNOWN_UNREACHED_RULES = {}


# ---------------------------------------------------------------------------
# Unit tests: no pipeline import
# ---------------------------------------------------------------------------

def _events(*lines):
    return [{'m': 'line', 'a': [t]} for t in lines]


def _texts(calls):
    out = []
    for c in calls:
        if c['m'] == 'line':
            out.append(c['a'][0])
        elif c['m'] == 'ledger':
            row = c['a'][1]
            out.append(f"<{c['a'][0]}:{row.get('status') or row.get('action') or row.get('plan_id') or ''}>")
        else:
            out.append(f"<{c['m']}>")
    return out


def test_read_run_log_splits_stdout_lines_from_logging_lines(tmp_path):
    p = tmp_path / 'run_x.log'
    p.write_bytes(b'17:25:48 [INFO   ] root: Run started  : x\n'
                  b'=== PLAN #1 ===\n'
                  b'17:25:50 [ERROR  ] streams: plan_motion: no path\n'
                  b'  Executing: move\r\n'
                  b'no newline at the end')
    events, partial = cr.read_run_log(p)
    assert [e['m'] for e in events] == ['log', 'line', 'log', 'line']
    assert events[0]['a'] == ['INFO', 'root', 'Run started  : x']
    assert events[2]['a'] == ['ERROR', 'streams', 'plan_motion: no path']
    assert events[3]['a'] == ['  Executing: move\r']       # the tee splits on \n only
    assert partial == 'no newline at the end'


def test_merge_places_plan_step_and_step_end_by_the_anchors():
    ev = _events('', '=== PLAN #1 ===', 'Unknown shadows remaining: 2', 'Stream plan (1)',
                 '    [eye #2] plan#1 planned (2 actions) | held=none',
                 '  [timing] planner.plan() #1: 1.0s (cumulative 1.0s)', 'Plan: 2 actions',
                 '', '  Executing: move', '    -> Arrived at x', '    [integrity] after plan#1 move(x): ok',
                 '', '  Executing: sense', '    Sensing s...', '', '=== PLAN #2 ===')
    rows = [{'kind': 'ledger_open'}, {'kind': 'plan', 'plan_id': 1, 'call': 'mission'},
            {'kind': 'step', 'action': 'move'}, {'kind': 'move_resolve'}, {'kind': 'step_end', 'status': 'ok'},
            {'kind': 'step', 'action': 'sense'}, {'kind': 'sense_result', 'reason': 'sense_clear_but_empty'},
            {'kind': 'step_end', 'status': 'sense_outcome'}]
    calls, rep = cr.merge(ev, rows)
    t = _texts(calls)
    assert t.index('<ledger_open:>') < t.index('<plan:1>') < t.index('    [eye #2] plan#1 planned (2 actions) | held=none')
    assert t.index('Stream plan (1)') < t.index('<plan:1>')
    # step before the blank line ahead of its Executing line
    i = t.index('<step:move>')
    assert t[i + 1] == '' and t[i + 2] == '  Executing: move'
    # step_end ok after the step's last line, before the next step; the
    # unanchored move_resolve right before it (the next anchored row)
    j = t.index('<step_end:ok>')
    assert t[j - 1] == '<move_resolve:>' and t[j - 2] == '    [integrity] after plan#1 move(x): ok'
    assert t[j + 1] == '<step:sense>'
    k = t.index('<step_end:sense_outcome>')
    assert t[k - 1] == '<sense_result:>' and t[k - 2] == '    Sensing s...' and t[k + 2] == '=== PLAN #2 ==='
    assert rep['missed'] == [] and rep['anchored'] == {'plan': 1, 'step': 2, 'step_end': 2}


def test_merge_mission_and_disposal_plan_rows():
    ev = _events('=== PLAN #3 ===', '    [eye #9] plan#3 planned (no plan) | held=dice',
                 '  no mission plan with dice held: planning a disposal place instead',
                 'Iteration: 1', '  [timing] planner.plan() #3: 2.0s (cumulative 9.0s)')
    rows = [{'kind': 'plan', 'plan_id': 3, 'call': 'mission', 'actions': None},
            {'kind': 'plan', 'plan_id': 3, 'call': 'disposal', 'actions': [['move']]}]
    calls, rep = cr.merge(ev, rows)
    t = _texts(calls)
    assert t.index('<plan:3>') == 1
    assert t[t.index('Iteration: 1') + 1] == '<plan:3>'
    assert rep['missed'] == []


def test_merge_without_eye_line_uses_the_timing_line():
    ev = _events('=== PLAN #1 ===', 'Summary: x', '  [timing] planner.plan() #1: 1.0s (cumulative 1.0s)')
    calls, _ = cr.merge(ev, [{'kind': 'plan', 'plan_id': 1, 'call': 'mission'}])
    assert _texts(calls) == ['=== PLAN #1 ===', 'Summary: x', '<plan:1>',
                             '  [timing] planner.plan() #1: 1.0s (cumulative 1.0s)']


def test_merge_at_home_test_before_its_d7_line_and_the_report_tail():
    ev = _events('  Executing: move', '    [D7] at-home test FAILED: max |dq| 3e-3 rad', '    -> Arrived at q_home',
                 '  PHYSICAL_FAILURE (goal): x', '    [eye #7] final (FAILED: x)', '', cr.BANNER,
                 'FAILED: x', '  Plans executed: 1', '--- Planning timing summary ---', cr.BANNER, 'after')
    rows = [{'kind': 'step', 'action': 'move'}, {'kind': 'at_home_test', 'passed': False},
            {'kind': 'step_end', 'status': 'ok'}, {'kind': 'belief', 'op': 'status'},
            {'kind': 'ledger_close'}]
    calls, rep = cr.merge(ev, rows, header=None, summary={'success': False})
    t = _texts(calls)
    assert t[t.index('<at_home_test:>') + 1].startswith('    [D7] at-home test')
    assert t[t.index('<step_end:ok>') + 1] == '  PHYSICAL_FAILURE (goal): x'
    # rows after the last anchor: before the report's opening rule (and its blank line)
    assert t[t.index('<belief:>') + 1] == '' and t[t.index('<belief:>') + 2] == cr.BANNER
    s = t.index('<summary>')
    assert t[s - 1] == cr.BANNER and t[s + 1] == '<ledger_close:>' and t[s + 2] == 'after'
    assert rep['report_block'] is True


def test_merge_header_after_model_tweaks_and_a_missed_anchor_is_reported():
    ev = _events('x', "  model tweaks: {'M8': True}; domain d.pddl", 'y')
    calls, rep = cr.merge(ev, [{'kind': 'step', 'action': 'pick', 'plan': 1, 'step': 1}], header={'goal': 'g'})
    t = _texts(calls)
    assert t[t.index('<header>') - 1].startswith('  model tweaks:')
    assert rep['missed'] == [{'kind': 'step', 'plan': 1, 'step': 1, 'placed_at_event': 0}]


def test_derive_header_boxels_passes_no_target_and_bridge_does():
    lines = ["  model tweaks: {'M8': True, 'M9': False}; domain domain_pddlstream_m8.pddl"]
    rc = {'scene': 'random-pairs', 'seed': '0', 'n_occluders': '2', 'n_targets': '1', 'n_hidden': '1',
          'goal': 'holding', 'planner': 'ff-astar2', 'grip_squeeze_mm': '0.5',
          'slip_fixes': 'solver_iters,force_hold'}
    rows = [{'kind': 'plan', 'goal': ['holding', 'orange_object']}]
    h, _ = cr.derive_header(lines, rows, rc, None)
    assert h == {'scene': 'random-pairs seed 0, 2 occluders, 1 targets, 1 hidden', 'goal': 'holding',
                 'switches': 'M8 on, M9 off, grip squeeze 0.5 mm, planner ff-astar2, '
                             'slip fixes force_hold,solver_iters'}
    rows = [{'kind': 'plan', 'goal': ['and', ['holding', 'dice'], ['at_config', 'q_home']]}]
    h, src = cr.derive_header(lines, rows, {}, {'switches': {'grip_squeeze_mm': '0.5', 'slip_fixes': ''}})
    assert h == {'scene': None, 'goal': 'holding dice at home',
                 'switches': 'M8 on, M9 off, grip squeeze 0.5 mm, planner ff-astar2, slip fixes none'}
    assert 'default' in src['planner']


def test_made_tapes_are_well_formed_and_cover_every_call_kind():
    kinds = set()
    for name in cr.MADE:
        tape = cr.made_tape(name)
        assert cr.check_tape(tape) == [], name
        assert tape['calls'][-1]['m'] in ('finish', 'raise'), name
        kinds |= {c['m'] for c in tape['calls']}
    assert kinds == set(cr.CALL_KINDS)
    assert set(MADE_EXIT) == set(cr.MADE)


def test_masks_replace_paths_and_random_names():
    tape = {'source': '/data/runs/run_1', 'save_dir': '/data/runs'}
    root = Path('/tmp/console_replay_ab/plain')
    m = cr.masks_for(root, tape)
    s = m(f'{root}/run_1 /data/runs/run_1/x /data/runs/y '
          f'{cr.REPO}/z console_debug_k2_x9.log File "a/console_replay.py", line 812')
    assert s == ('<RUN>/run_1 <SRC>/x <SAVE>/y <REPO>/z console_debug_<X>.log '
                 'File "a/console_replay.py", line <N>')


def test_group_console_registers_pin_27():
    pins = po.GROUPS['console']
    assert [p for p in pins if p.startswith('p27_made_')] == [f'p27_made_{n}' for n in cr.MADE]
    assert [p for p in pins if p.startswith('p27_run_')] == [f'p27_run_{k}' for k in po.CONSOLE_RUNS]
    assert [p for p in pins if p.startswith('p27_tape_')] == [f'p27_tape_{e}' for e in po.CONSOLE_TAPE_RUNS]
    for k, rel in po.CONSOLE_RUNS.items():
        d = REPO / rel
        assert (d / 'ledger.jsonl').exists() and list(d.glob('run_*.log')), k


# ---------------------------------------------------------------------------
# Played through the real Console (WSL)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def fresh(tmp_path_factory):
    if os.name == 'nt':
        pytest.skip('WSL only')
    out = tmp_path_factory.mktemp('pins_console')
    po.run_group('console', out, only=PINS, log=lambda s: None)
    return out


def _run_json(fresh, pid, variant):
    return json.loads((fresh / pid / variant / 'run.json').read_text(encoding='utf-8'))


def _ok(fresh, pid):
    manifest = json.loads((fresh / 'MANIFEST.json').read_text(encoding='utf-8'))
    err = fresh / pid / 'ERROR.txt'
    assert manifest['pins'][pid]['status'] == 'ok', err.read_text(encoding='utf-8') if err.exists() else pid


@in_wsl
@pytest.mark.parametrize('pin_id', PINS)
def test_pin_plays_its_whole_tape_in_every_set(fresh, pin_id):
    _ok(fresh, pin_id)
    for variant in cr.ENV_SETS:
        r = _run_json(fresh, pin_id, variant)
        assert r['status'] == 'ended', (variant, r)
        assert r['played_to'] == r['tape_calls'] - 1, (variant, r)     # the last call ended it
        if pin_id.startswith('p27_made_'):
            assert r['exit_code'] == MADE_EXIT[pin_id[len('p27_made_'):]], (variant, r)
        else:
            assert r['exit_code'] in (0, 1), (variant, r)
        assert r['stderr_pipe'] == '', (variant, r)


@in_wsl
@pytest.mark.parametrize('pin_id', PINS)
def test_console_lines_do_not_depend_on_colour(fresh, pin_id):
    _ok(fresh, pin_id)
    read = lambda v, f: (fresh / pin_id / v / f).read_text(encoding='utf-8')  # noqa: E731
    lines = read('plain', 'console.txt').splitlines()
    assert lines[0].startswith('[console] ') and len(lines) > 3
    assert read('plain', 'console.txt') == read('color', 'console.txt')
    assert read('ascii', 'console.txt') == read('color_ascii', 'console.txt')
    assert read('plain', 'console.txt') != read('ascii', 'console.txt')
    assert '\x1b[' not in read('plain', 'terminal.txt') and '\x1b[' not in read('ascii', 'terminal.txt')
    assert '\x1b[' in read('color', 'terminal.txt')
    # the static layout: what the pipe got is the committed lines, the mirror's text
    plain_term = [ln for ln in read('plain', 'terminal.txt').splitlines() if ln.strip()]
    mirrored = [ln[len('[console] '):] for ln in lines if ln[len('[console] '):].strip()]
    assert plain_term == mirrored


@in_wsl
@pytest.mark.parametrize('pin_id', RUN_PINS)
def test_runs_place_every_anchored_row(fresh, pin_id):
    _ok(fresh, pin_id)
    inputs = json.loads((fresh / pin_id / 'inputs.json').read_text(encoding='utf-8'))
    assert inputs['anchors']['missed'] == [], inputs['anchors']['missed'][:3]
    assert inputs['anchors']['report_block'] is True
    console = (fresh / pin_id / 'plain' / 'console.txt').read_text(encoding='utf-8')
    assert 'Mission: ' in console and ('Done. ' in console or 'Failed. ' in console)


@in_wsl
def test_made_tapes_reach_every_rule_kind_and_status():
    sys.path.insert(0, str(REPO))
    from console import console_ui
    from console import run_logger
    cov = cr.coverage([cr.made_tape(n) for n in cr.MADE], cu=console_ui,
                      statuses=run_logger.STEP_END_STATUSES)
    unreached = [r for r in cov['rules_not_reached'] if r not in KNOWN_UNREACHED_RULES]
    assert not unreached, f'rules no made tape reaches: {unreached}'
    assert cov['statuses_not_reached'] == []
    assert cov['sense_texts_not_reached'] == []
    # every ledger kind of pin 40 (p40_ledger_schema kinds.json), read from the code as pin 40
    # reads it (SPEC D14 (d), PLAN rule 3: counted from the code, never typed)
    kinds = po.ledger_kinds()
    assert kinds, "no ledger_event call found in the AST pins' scope"
    missing = sorted(set(kinds) - set(cov['ledger_kinds']))
    assert not missing, f'ledger kinds no made tape feeds: {missing}'


@in_wsl
def test_two_plays_of_a_tape_are_equal(tmp_path):
    tape = cr.made_tape('holding')
    cr.play(tape, tmp_path / 'a', ('plain', 'ascii'))
    cr.play(tape, tmp_path / 'b', ('plain', 'ascii'))
    for v in ('plain', 'ascii'):
        for f in ('console.txt', 'terminal.txt', 'debug.txt', 'run.json'):
            assert (tmp_path / 'a' / v / f).read_bytes() == (tmp_path / 'b' / v / f).read_bytes(), (v, f)


@needs_golden
@in_wsl
@pytest.mark.parametrize('pin_id', PINS)
def test_pin_equals_golden(fresh, pin_id):
    import difflib
    golden = Path(GOLDEN) / pin_id
    assert golden.is_dir(), f'the golden folder {GOLDEN} has no {pin_id}'
    _ok(fresh, pin_id)
    want, have = po.pin_files(golden), po.pin_files(fresh / pin_id)
    assert sorted(want) == sorted(have), f'file sets differ: golden {sorted(want)}, fresh {sorted(have)}'
    for name in sorted(want):
        if want[name].read_bytes() != have[name].read_bytes():
            a = want[name].read_text(encoding='utf-8', errors='replace').splitlines()
            b = have[name].read_text(encoding='utf-8', errors='replace').splitlines()
            pytest.fail(f'{pin_id}/{name} differs from the golden copy:\n'
                        + '\n'.join(list(difflib.unified_diff(a, b, 'golden', 'fresh', lineterm='', n=2))[:40]))
