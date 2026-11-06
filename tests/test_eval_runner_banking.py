"""TB-8: eval_runner.py must never bank another cell's run as a cell's result.

Found 2026-10-24 by the shadow-oracle review (CB#113): a cell rejected by
the pre-flight exits 1 before the run logger opens a run directory, and the
old run_cell took the newest logs/run_*/timing_summary.json written within
1 s of its launch, so a rejected cell that followed a finished one banked
that one's summary (10 of CB#113's 43 rejected find-and-tray-stack cells
held the preceding holding run's success).  These tests stand a fake
test_full_pipeline.py in for subprocess.run: one cell that runs and writes
its summary, one that the pre-flight rejects, back to back.
"""
import json
import types
from pathlib import Path

import pytest

import eval_runner as er

HOLD = {'scene': 'random-pairs', 'n_occluders': 2, 'seed': 0,
        'goal': 'holding', 'unit_costs': True, 'baseline': 'semantic',
        'min_boxel_size': 0.05}
TRAY = dict(HOLD, goal='find-and-tray-stack')
REJECTION = '[pre-flight] seed 0 rejected: the tray-stack goal cannot be formed'


def _fake_pipeline(runs):
    """subprocess.run for run_cell: argv's --goal picks the behaviour."""
    n = {'i': 0}

    def fake_run(argv, capture_output, text, timeout, cwd):
        goal = argv[argv.index('--goal') + 1]
        if goal == 'holding':
            n['i'] += 1
            d = Path(cwd) / 'logs' / f"run_2026-10-24_00-00-0{n['i']}"
            d.mkdir(parents=True)
            run_config = {k: HOLD[k] for k in
                          ('scene', 'seed', 'goal', 'baseline', 'unit_costs',
                           'min_boxel_size')}
            (d / 'timing_summary.json').write_text(json.dumps(
                {'success': True, 'exit_reason': 'success', 'plan_count': 2,
                 'total_planning_time_s': 1.0, 'run_config': run_config}))
            runs.append(goal)
            return types.SimpleNamespace(returncode=0, stdout='ok\n', stderr='')
        runs.append(goal)
        return types.SimpleNamespace(returncode=1, stdout='',
                                     stderr=REJECTION + '\n')
    return fake_run


@pytest.fixture
def sweep(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs = []
    monkeypatch.setattr(er.subprocess, 'run', _fake_pipeline(runs))
    out = tmp_path / 'sweep'
    out.mkdir()
    return out, runs


def _banked_by_the_old_runner(out):
    """The holding cell runs; the tray cell's folder is then what the old
    runner left for such a cell in CB#113: the holding run's summary and
    run directory, beside its own output with the pre-flight's rejection."""
    er.run_cell(HOLD, out, 60, [], skip_existing=False)
    hold_dir = out / 'cells' / er.cell_tag(HOLD)
    tray_dir = out / 'cells' / er.cell_tag(TRAY)
    tray_dir.mkdir(parents=True)
    for name in ('timing_summary.json', 'run_dir.txt'):
        (tray_dir / name).write_text((hold_dir / name).read_text())
    (tray_dir / 'stdout.log').write_text('\n--- STDERR ---\n' + REJECTION + '\n')


def test_a_rejected_cell_right_after_a_success_is_not_banked_as_one(sweep):
    out, _ = sweep
    first = er.run_cell(HOLD, out, 60, [], skip_existing=False)
    second = er.run_cell(TRAY, out, 60, [], skip_existing=False)
    assert first['success'] is True
    assert second['success'] is False
    assert second['exit_reason'] == 'preflight_rejected'
    assert second.get('preflight_message') == REJECTION
    stored = json.loads((out / 'cells' / er.cell_tag(TRAY) /
                         'timing_summary.json').read_text())
    assert stored['exit_reason'] == 'preflight_rejected'


def test_skip_existing_reruns_a_cell_that_holds_another_cells_summary(sweep):
    out, runs = sweep
    _banked_by_the_old_runner(out)
    again = er.run_cell(TRAY, out, 60, [], skip_existing=True)
    assert runs[-1] == 'find-and-tray-stack'      # it ran again
    assert again['exit_reason'] == 'preflight_rejected'
    # A stored result that is its own is resumed, not re-run.
    n = len(runs)
    er.run_cell(HOLD, out, 60, [], skip_existing=True)
    assert len(runs) == n


def test_aggregate_relabels_a_banked_cell_of_an_old_sweep(sweep):
    out, _ = sweep
    _banked_by_the_old_runner(out)
    (out / 'matrix.json').write_text(json.dumps({'cells': [HOLD, TRAY]}))
    er.aggregate(out)
    rows = [json.loads(line) for line in
            (out / 'aggregated.jsonl').read_text().splitlines()]
    by_goal = {r['goal']: r for r in rows}
    assert by_goal['holding']['success'] is True
    assert by_goal['find-and-tray-stack']['success'] is False
    assert by_goal['find-and-tray-stack']['exit_reason'] == 'preflight_rejected'
