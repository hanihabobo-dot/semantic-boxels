"""M7's F9 give-up as a suspension (Hani, 2026-11-20: "make it a timer thing.
its suspended for 1 - 3 minutes ... make sure the smart consle and evals
capture this correctly. fail and why").

The belief's suspend and release, the run summary's FAILED line and record,
the eval row's metrics and the console's wording.  No simulator: the sense
handler's side is in test_m7_rediscovery.py.
"""
import json
import os
import sys
import types
from pathlib import Path

import pytest

import console_ui
import run_logger
from belief import BeliefState

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import episode_metrics  # noqa: E402

S = 'shadow_026'


def _suspended(now=100.0, seconds=120.0):
    b = BeliefState([S, 'shadow_027'], 'die')
    b.suspend(S, bodies={'e_cups_ud': 3}, now=now, seconds=seconds)
    return b


# ----- the belief ------------------------------------------------------------

def test_a_suspension_parks_until_its_time_is_up():
    b = _suspended()
    assert b.shadow_status[S] == 'unresolved'
    assert b.get_parked_shadows() == [S] and b.get_suspended_shadows() == [S]
    assert S not in b.get_unknown_shadows()
    assert b.release_suspended(219.9) == [] and b.get_suspended_shadows() == [S]
    assert b.release_suspended(220.0) == [S]
    assert b.shadow_status[S] == 'unknown' and S in b.get_unknown_shadows()
    assert not b.suspended and not b.get_parked_shadows()
    row, = b.suspensions
    assert (row['start'], row['until'], row['end'], row['ended_by']) == (
        100.0, 220.0, 220.0, 'released')


@pytest.mark.parametrize('change,ended_by', [
    (lambda b: b.mark_sensed(S, found=False), 'not_here'),   # a sweep saw it empty
    (lambda b: b.remove_shadow(S), 'forgotten'),
])
def test_a_region_that_changed_meanwhile_ends_without_a_release(change, ended_by):
    b = _suspended()
    change(b)
    assert b.get_suspended_shadows() == []
    assert b.release_suspended(500.0) == []
    assert b.suspensions[0]['ended_by'] == ended_by
    assert b.shadow_status.get(S) != 'unknown'


def test_a_found_region_is_not_suspended():
    b = BeliefState([S], 'die')
    b.mark_sensed(S, found=True)
    b.suspend(S, bodies={'e_cups_ud': 3}, now=1.0, seconds=120.0)
    assert b.shadow_status[S] == 'found' and not b.suspended and not b.suspensions


def test_a_second_give_up_after_the_release_suspends_again():
    b = _suspended()
    assert b.release_suspended(220.0) == [S]
    b.suspend(S, bodies={'e_cups_ud': 4}, now=230.0, seconds=120.0)
    assert [r['bodies'] for r in b.suspensions] == [{'e_cups_ud': 3}, {'e_cups_ud': 4}]
    assert b.suspended[S]['until'] == 350.0


def test_a_suspension_renewed_while_open_ends_the_first(tmp_path):
    # third review: no path is known to suspend a region still suspended;
    # if one does, the first row ends as resuspended rather than stay open
    run_logger.ledger_open(tmp_path)
    try:
        b = _suspended(now=100.0)
        b.suspend(S, bodies={'e_cups_ud': 4}, now=150.0, seconds=120.0)
    finally:
        run_logger.ledger_close()
    first, second = b.suspensions
    assert (first['end'], first['ended_by']) == (150.0, 'resuspended')
    assert (second['start'], second['until'], second['end']) == (150.0, 270.0, None)
    assert b.suspended == {S: second} and b.get_suspended_shadows() == [S]
    rows = [json.loads(line) for line in open(tmp_path / 'ledger.jsonl')]
    assert [(r['op'], r.get('ended_by')) for r in rows
            if r['kind'] == 'm7_suspension'] == [
        ('start', None), ('end', 'resuspended'), ('start', None)]


def test_the_ledger_rows(tmp_path):
    run_logger.ledger_open(tmp_path)
    try:
        with run_logger.provenance('strike_park'):
            b = _suspended(now=run_logger._ledger_t0 + 5.0)
        with run_logger.provenance('suspension_over'):
            b.release_suspended(b.suspended[S]['until'])
    finally:
        run_logger.ledger_close()
    rows = [json.loads(line) for line in open(tmp_path / 'ledger.jsonl')]
    belief = [(r['region'], r['status'], r['channel']) for r in rows
              if r['kind'] == 'belief']
    assert belief == [(S, 'unresolved', 'strike_park'),
                      (S, 'unknown', 'suspension_over')]
    susp = [(r['op'], r.get('bodies'), r.get('seconds'), r.get('ended_by'))
            for r in rows if r['kind'] == 'm7_suspension']
    assert susp == [('start', {'e_cups_ud': 3}, 120.0, None),
                    ('end', None, None, 'released')]


# ----- the run summary: the FAILED line and the record -----------------------

def _report(tmp_path, capsys, belief, exit_reason, m7_suspend_s=120.0,
            blocked=(), integrity_events=None):
    run_logger.report_run_outcome(
        success=False, exit_reason=exit_reason, goal_kind='holding', goal=None,
        target_name='die', on_relations={}, belief=belief, plan_count=8,
        shadows=[S, 'shadow_027'], blocked_giveup_shadows=set(blocked),
        m7_suspend_s=m7_suspend_s, integrity_events=integrity_events,
        plan_times=[0.5], total_plan_time=0.5,
        physical_failures=[], physics_failures=[], run_config={'seed': 293},
        run_logger=types.SimpleNamespace(run_dir=tmp_path, log_path=None))
    out = capsys.readouterr().out
    return out, json.loads((tmp_path / 'timing_summary.json').read_text())


def test_only_suspended_regions_left_fails_and_says_why(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(run_logger, '_ledger_t0', 90.0)
    b = _suspended()
    b.mark_sensed('shadow_027', found=False)
    out, s = _report(tmp_path, capsys, b, 'rediscovery_giveup')
    failed, = [ln for ln in out.splitlines() if ln.startswith('FAILED')]
    assert failed == ('FAILED: the only shadows left to search are suspended at '
                      'the F9 give-up (M7): shadow_026 (e_cups_ud rediscovered 3 '
                      'times); the target may be inside')
    assert s['success'] is False and s['exit_reason'] == 'rediscovery_giveup'
    assert s['m7_suspend_s'] == 120.0
    assert s['m7_suspensions'] == [{'region': S, 'bodies': {'e_cups_ud': 3},
                                    'start_s': 10.0, 'until_s': 130.0,
                                    'end_s': None, 'ended_by': 'open_at_end'}]


def test_a_planner_failure_names_the_suspended_regions(tmp_path, capsys):
    out, _ = _report(tmp_path, capsys, _suspended(), 'planner_failed')
    failed, = [ln for ln in out.splitlines() if ln.startswith('FAILED')]
    assert failed == ('FAILED: Planner returned no plan (1 unsearched shadows '
                      'remaining; suspended at the F9 give-up (M7): shadow_026 '
                      '(e_cups_ud rediscovered 3 times))')


def test_the_give_up_line_also_names_the_blocked_views(tmp_path, capsys):
    # third review: blocked views given up (audit #21) are unsearched too
    b = _suspended()
    b.mark_unresolved('shadow_027')
    out, _ = _report(tmp_path, capsys, b, 'rediscovery_giveup',
                     blocked=['shadow_027'])
    failed, = [ln for ln in out.splitlines() if ln.startswith('FAILED')]
    assert failed == ('FAILED: the only shadows left to search are suspended at '
                      'the F9 give-up (M7): shadow_026 (e_cups_ud rediscovered 3 '
                      'times); the target may be inside; 1 more given up after '
                      'repeated still_blocked outcomes (audit #21), not observed '
                      "empty: ['shadow_027']")


def test_a_lost_target_names_the_suspended_regions(tmp_path, capsys):
    b = _suspended()
    b.mark_sensed('shadow_027', found=False)
    lost = [{'kind': 'lost', 'object': 'die'}]
    out, s = _report(tmp_path, capsys, b, 'target_lost', integrity_events=lost)
    failed, = [ln for ln in out.splitlines() if ln.startswith('FAILED')]
    assert failed == ("FAILED: the target was seen, then lost from view (['die']) "
                      'and never re-detected (#P2 monitor; 0 unsearched shadows '
                      'remaining; suspended at the F9 give-up (M7): shadow_026 '
                      '(e_cups_ud rediscovered 3 times))')
    assert s['exit_reason'] == 'target_lost'
    assert s['m7_suspensions'][0]['ended_by'] == 'open_at_end'
    # with nothing suspended the line is as before
    out, _ = _report(tmp_path, capsys, BeliefState([S], 'die'), 'target_lost',
                     m7_suspend_s=None, integrity_events=lost)
    failed, = [ln for ln in out.splitlines() if ln.startswith('FAILED')]
    assert failed == ("FAILED: the target was seen, then lost from view (['die']) "
                      'and never re-detected (#P2 monitor; 1 unsearched shadows '
                      'remaining)')


# ----- the ending's relabel at the end of main() (third review) ---------------

def _relabel():
    """The relabel statement before report_run_outcome, by ast: a statement
    of report_episode(), which main() calls at its end."""
    import ast
    src = REPO / 'test_full_pipeline.py'
    tree = ast.parse(src.read_text(encoding='utf-8'))
    report, = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'report_episode']
    stmt, = [n for n in report.body if isinstance(n, ast.If)
             and 'target_lost_seen' in ast.unparse(n.test)]
    return compile(ast.Module(body=[stmt], type_ignores=[]), str(src), 'exec')


@pytest.mark.parametrize('reason,seen,after', [
    ('rediscovery_giveup', True, 'target_lost'),   # the target was seen, then lost
    ('rediscovery_giveup', False, 'rediscovery_giveup'),
    ('all_searched', True, 'target_lost'),         # as before
    ('all_searched', False, 'all_searched'),
    ('planner_failed', True, 'planner_failed'),
])
def test_a_target_seen_then_lost_keeps_that_reason(reason, seen, after):
    names = {'st': types.SimpleNamespace(ending=types.SimpleNamespace(
        success=False, exit_reason=reason, target_lost_seen=seen))}
    exec(_relabel(), names)
    assert names['st'].ending.exit_reason == after


def test_with_m7_off_the_summary_and_the_lines_are_as_before(tmp_path, capsys):
    b = BeliefState([S], 'die')
    out, s = _report(tmp_path, capsys, b, 'planner_failed', m7_suspend_s=None)
    assert 'm7_suspend_s' not in s and 'm7_suspensions' not in s
    failed, = [ln for ln in out.splitlines() if ln.startswith('FAILED')]
    assert failed == 'FAILED: Planner returned no plan (1 unsearched shadows remaining)'


# ----- the eval row (episode_metrics, read into every find_dice record) -------

def _run_dir(tmp_path, rows, summary, name='run_x'):
    d = tmp_path / name
    d.mkdir()
    with open(d / 'ledger.jsonl', 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    (d / 'timing_summary.json').write_text(json.dumps(summary))
    return str(d)


def test_the_eval_row_carries_each_suspensions_start_and_end(tmp_path):
    rows = [{'kind': 'ledger_open', 't': 50.0},
            {'kind': 'm7_suspension', 't': 92.5, 'plan': 8, 'step': 1,
             'op': 'start', 'region': S, 'bodies': {'e_cups_ud': 3},
             'seconds': 120.0},
            {'kind': 'm7_suspension', 't': 213.0, 'op': 'end', 'region': S,
             'ended_by': 'released'},
            {'kind': 'ledger_close', 't': 300.0}]
    m = episode_metrics.metrics(_run_dir(tmp_path, rows, {
        'success': False, 'exit_reason': 'rediscovery_giveup', 'm7_suspend_s': 120.0}))
    assert m['outcome'] == 'failure (rediscovery_giveup)'
    assert m['m7_suspend_s'] == 120.0
    assert m['m7_suspensions'] == [{'region': S, 'bodies': {'e_cups_ud': 3},
                                    'plan': 8, 'start_s': 42.5, 'seconds': 120.0,
                                    'end_s': 163.0, 'ended_by': 'released'}]


def test_an_eval_row_with_m7_on_and_no_suspension_says_so(tmp_path):
    rows = [{'kind': 'ledger_open', 't': 0.0}, {'kind': 'ledger_close', 't': 9.0}]
    m = episode_metrics.metrics(_run_dir(tmp_path, rows, {
        'success': True, 'm7_suspend_s': 120.0, 'm7_suspensions': []}))
    assert m['m7_suspensions'] == []
    m_off = episode_metrics.metrics(_run_dir(tmp_path, rows, {'success': True},
                                             name='run_off'))
    assert 'm7_suspensions' not in m_off


# ----- the smart console --------------------------------------------------------

def _note(line):
    for pat, fn in console_ui._note_rules():
        m = pat.match(line.strip())
        if m:
            return fn(m)
    return None


def test_the_console_words_the_suspension_and_its_end():
    assert _note(f'    {S}: a body found in it reaches the F9 give-up, so nothing '
                 f're-covers what it hides; suspending {S} for 120 s instead of '
                 f'marking it empty (M7): e_cups_ud rediscovered 3 times') == (
        f'I keep finding the same thing in `{S}` (e_cups_ud rediscovered 3 '
        f'times), so I set that space aside for 120 s')
    assert _note(f'  [M7] {S} is back in the search: its 120 s suspension at the '
                 f'F9 give-up is over') == (
        f'`{S}` is back on my list: its time aside is over')
