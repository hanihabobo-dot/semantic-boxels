"""TB-22: every eval record carries the fields of tracks rule 18.

The places a record is built: the pipeline's own summary (run_logger.
report_run_outcome), the runner's rows and its stub rows (eval_runner.py),
the find_dice harnesses' records of both arms (tools/slip_eval.py,
tools/_bridge_campaign.py, tools/gen_scene_eval.py), and the hooks the
counts hang on (robot_utils' gripper commands, execution's notices, the
--world-counts switch).  No simulator and no episode: fakes stand in for
the subprocesses, and the hooks are read from the source.
"""
import ast
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

import eval_runner as er
import run_logger
import world_counts as wc

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import _bridge_campaign as bc  # noqa: E402
import gen_scene_eval as gse  # noqa: E402
import slip_eval as se  # noqa: E402

DROP = {'object': 'green_object', 'phase': 'move', 't': 12.5,
        'how': 'left the finger pads before the gripper was opened'}
KNOCK = {'object': 'red_object', 'phase': 'move', 't': 12.4, 'moved_mm': 8.0}
WATCHED_CLEAN = {'drops': [], 'collisions': []}
ONE_DROP = {'drops': [DROP], 'collisions': []}
COUNTS_FILE = {'drops': [DROP], 'collisions': [KNOCK], 'mode': 'counts',
               'steps': 900, 'closed': False}
SCENE = 'scene_7.json'


# ----- the pipeline's summary (run_logger.report_run_outcome) -----------

def _summary(tmp_path, success=True, **kw):
    belief = types.SimpleNamespace(get_unknown_shadows=lambda: [],
                                   get_parked_shadows=lambda: [])
    run_logger.report_run_outcome(
        success=success,
        exit_reason='success' if success else 'planner_failed',
        goal_kind='stack', goal=[], target_name=None, on_relations={},
        belief=belief, plan_count=1, shadows=[],
        blocked_giveup_shadows=set(), plan_times=[0.5], total_plan_time=0.5,
        physical_failures=[], physics_failures=[], run_config={'seed': 0},
        run_logger=types.SimpleNamespace(run_dir=tmp_path, log_path=None),
        **kw)
    return json.loads((tmp_path / wc.SUMMARY_FILE).read_text())


def test_a_summary_nothing_watched_says_not_detected(tmp_path):
    s = _summary(tmp_path)
    assert set(wc.FIELDS) <= set(s)
    assert s['drops'] is None and s['collisions'] is None       # never a 0
    assert s['drop_detector'] == s['collision_detector'] == wc.NOT_DETECTED
    assert s['clean_success'] is None
    assert s['drops_noticed'] is None and s['drops_noticed_by'] == {}


def test_a_watched_summary_without_events_is_a_clean_success(tmp_path):
    s = _summary(tmp_path, observer_counts=dict(WATCHED_CLEAN, check_s=0.42),
                 drops_noticed={'entry': 0, 'lift': 0, 'carry': 0},
                 collisions_reported=0)
    assert (s['drops'], s['collisions'], s['clean_success']) == (0, 0, True)
    assert s['counts_cost_s'] == 0.42        # what the counting cost the run
    assert s['drop_detector'] == wc.DROP_DETECTOR
    assert s['collision_detector'] == wc.COLLISION_DETECTOR
    assert (s['drops_noticed'], s['collisions_reported']) == (0, 0)
    assert s['drops_noticed_by'] == {'entry': 0, 'lift': 0, 'carry': 0}


def test_a_success_with_a_drop_or_a_knock_is_not_clean(tmp_path):
    s = _summary(tmp_path, observer_counts={'drops': [DROP],
                                            'collisions': [KNOCK]},
                 drops_noticed={'entry': 0, 'lift': 0, 'carry': 1},
                 collisions_reported=2)
    assert s['success'] is True
    assert (s['drops'], s['collisions'], s['clean_success']) == (1, 1, False)
    assert s['drop_events'] == [DROP] and s['collision_events'] == [KNOCK]
    # what the robot itself saw stands beside the counts, apart from them
    assert (s['drops_noticed'], s['collisions_reported']) == (1, 2)


def test_a_failure_is_never_clean(tmp_path):
    s = _summary(tmp_path, success=False, observer_counts=WATCHED_CLEAN)
    assert (s['drops'], s['collisions'], s['clean_success']) == (0, 0, False)


def test_the_monitors_knocked_off_table_body_is_a_collision(tmp_path):
    s = _summary(tmp_path, observer_counts=WATCHED_CLEAN, integrity_events=[
        {'kind': 'knocked_off_table', 'object': 'blue_object',
         'label': 'move'}])
    assert (s['collisions'], s['clean_success']) == (1, False)
    assert s['collision_events'][0]['source'] == 'knocked_off_table'


# ----- the switch -------------------------------------------------------

def test_the_counts_are_on_in_every_headless_run_by_default():
    assert run_logger.parse_pipeline_args(['--no-gui']).world_counts == 'auto'
    args = run_logger.parse_pipeline_args(['--no-gui', '--no-telemetry'])
    assert args.world_counts == 'auto'      # --no-telemetry does not lose them
    assert wc.wanted('auto', gui=False) and not wc.wanted('auto', gui=True)
    assert wc.wanted('on', gui=True) and not wc.wanted('off', gui=False)
    off = run_logger.parse_pipeline_args(['--no-gui', '--world-counts', 'off'])
    assert off.world_counts == 'off'


def _functions(path):
    tree = ast.parse((REPO / path).read_text(encoding='utf-8'))
    return {n.name: n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)}


def _calls(node, name):
    """The calls of a function or attribute called ``name`` under node."""
    return [c for c in ast.walk(node) if isinstance(c, ast.Call)
            and getattr(c.func, 'attr', getattr(c.func, 'id', None)) == name]


def test_the_pipeline_arms_the_counts_where_the_recorder_is_off():
    src = (REPO / 'test_full_pipeline.py').read_text(encoding='utf-8')
    main = _functions('test_full_pipeline.py')['main']
    armed = [c for c in _calls(main, 'enable')
             if any(k.arg == 'counts_only'
                    and getattr(k.value, 'value', None) is True
                    for k in c.keywords)]
    assert len(armed) == 1
    assert "elif world_counts.wanted(getattr(args, 'world_counts', 'auto'), gui):" in src
    # a run nothing watches drops an observer left armed by an earlier run in
    # the process (its counts are not this run's), and every run starts the
    # robot's own notices at zero
    assert len([c for c in _calls(main, 'disable')
                if getattr(c.func.value, 'id', None) == 'telemetry']) == 1
    assert len(_calls(main, 'run_reset')) == 1
    # and the run's record gets the observer's counts and the robot's notices
    out = _calls(main, 'report_run_outcome')
    assert len(out) == 1
    assert {'observer_counts', 'drops_noticed', 'collisions_reported'} <= {
        k.arg for k in out[0].keywords}


# ----- the hooks the counts hang on -------------------------------------

def test_every_gripper_command_tells_the_observer():
    fns = _functions('robot_utils.py')
    opened = _calls(fns['open_gripper'], 'gripper_command')
    assert len(opened) == 1
    assert opened[0].args[0].value is True
    assert opened[0].args[1].id == 'placing'
    for name in ('close_gripper', 'close_gripper_until_contact'):
        closed = _calls(fns[name], 'gripper_command')
        assert len(closed) == 1 and closed[0].args[0].value is False


def test_only_the_release_of_a_place_opens_as_placing():
    """An open that is no release of a place lets a carried body fall: the
    observer counts it.  The one function that releases on purpose is
    _release_and_verify_drop (place and stack)."""
    fns = _functions('execution.py')
    placing = {name for name, fn in fns.items()
               for c in _calls(fn, 'open_gripper')
               if any(k.arg == 'placing' for k in c.keywords)}
    assert placing == {'_release_and_verify_drop'}
    for c in _calls(fns['_release_and_verify_drop'], 'open_gripper'):
        assert [k.value.value for k in c.keywords if k.arg == 'placing'] == [True]


def test_the_robots_three_checks_count_what_they_notice():
    wc.run_reset()
    assert wc.noticed_drops() == {'entry': 0, 'lift': 0, 'carry': 0}
    wc.notice_drop('carry')
    wc.notice_drop('carry')
    wc.notice_drop('lift')
    assert wc.noticed_drops() == {'entry': 0, 'lift': 1, 'carry': 2}
    wc.noticed_drops()['carry'] = 5                         # a copy
    assert wc.noticed_drops()['carry'] == 2
    wc.run_reset()                                          # a new run starts at zero
    assert sum(wc.noticed_drops().values()) == 0
    # each of execution.py's three checks counts once, under its own name
    tree = ast.parse((REPO / 'execution.py').read_text(encoding='utf-8'))
    counted = sorted(c.args[0].value for c in _calls(tree, 'notice_drop'))
    assert counted == ['carry', 'entry', 'lift']


def test_the_executors_contact_report_is_counted_where_it_is_made():
    wc.run_reset()
    assert wc.collisions_reported() == 0
    wc.report_collision()
    wc.report_collision()
    assert wc.collisions_reported() == 2
    wc.run_reset()
    assert wc.collisions_reported() == 0
    # robot_utils.detect_execution_collisions counts a report that names a
    # contact, once, where it prints it
    fn = _functions('robot_utils.py')['detect_execution_collisions']
    named = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and getattr(n.test, 'id', None) == 'collisions']
    assert len(named) == 1 and len(_calls(named[0], 'report_collision')) == 1
    assert len(_calls(fn, 'report_collision')) == 1
    # so the pipeline's two calls of it stay plain statements: nothing
    # branches on the report
    main = _functions('test_full_pipeline.py')['main']
    plain = [n for n in ast.walk(main) if isinstance(n, ast.Expr)
             and isinstance(n.value, ast.Call)
             and getattr(n.value.func, 'id', None) == 'detect_execution_collisions']
    assert len(plain) == len(_calls(main, 'detect_execution_collisions')) == 2


def test_a_contact_report_that_names_a_contact_counts_once(monkeypatch):
    pytest.importorskip('pybullet')
    import robot_utils

    class Sim:
        contacts = []

        def performCollisionDetection(self, physicsClientId=0):
            pass

        def getContactPoints(self, bodyA=None, physicsClientId=0):
            return list(self.contacts)
    sim = Sim()
    monkeypatch.setattr(robot_utils, 'p', sim)
    wc.run_reset()
    assert robot_utils.detect_execution_collisions(0, body_names={5: 'box'}) == []
    assert wc.collisions_reported() == 0                    # a clean report
    sim.contacts = [(0, 0, 5, 7, -1), (0, 0, 5, 8, -1)]     # two links on one body
    found = robot_utils.detect_execution_collisions(0, body_names={5: 'box'})
    assert found == ['robot link 7 <-> box', 'robot link 8 <-> box']
    assert wc.collisions_reported() == 1                    # one report, not two
    wc.run_reset()


# ----- the runner's rows (eval_runner.py) -------------------------------

CELL = {'scene': 'random-pairs', 'n_occluders': 2, 'seed': 0,
        'goal': 'holding', 'unit_costs': True, 'baseline': 'semantic',
        'min_boxel_size': 0.05}
REJECTION = '[pre-flight] seed 0 rejected: the tray-stack goal cannot be formed'


def _new_run_dir(cwd, name='run_2026-11-12_00-00-01'):
    d = Path(cwd) / 'logs' / name
    d.mkdir(parents=True)
    return d


def _cell_summary(fields):
    run_config = {k: CELL[k] for k in ('scene', 'seed', 'goal', 'baseline',
                                       'unit_costs', 'min_boxel_size')}
    return {'success': True, 'exit_reason': 'success', 'plan_count': 1,
            'total_planning_time_s': 1.0, 'run_config': run_config, **fields}


@pytest.fixture
def sweep(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'sweep'
    out.mkdir()

    def launch(behaviour):
        def fake_run(argv, capture_output, text, timeout, cwd):
            return behaviour(argv, timeout, cwd)
        monkeypatch.setattr(er.subprocess, 'run', fake_run)
        return er.run_cell_counted(CELL, out, 60, [], skip_existing=False)
    return out, launch


def _stored(out):
    return json.loads((out / 'cells' / er.cell_tag(CELL) /
                       'timing_summary.json').read_text())


def test_the_sweep_runs_its_cells_through_the_counted_runner():
    main = _functions('eval_runner.py')['main']
    assert len(_calls(main, 'run_cell_counted')) == 1
    assert _calls(main, 'run_cell') == []


def test_a_finished_cell_carries_its_runs_fields(sweep):
    out, launch = sweep

    def finished(argv, timeout, cwd):
        (_new_run_dir(cwd) / wc.SUMMARY_FILE).write_text(json.dumps(
            _cell_summary(wc.episode_fields(True, ONE_DROP))))
        return types.SimpleNamespace(returncode=0, stdout='ok\n', stderr='')
    row = launch(finished)
    assert row['success'] is True
    assert (row['drops'], row['collisions'], row['clean_success']) == (1, 0, False)
    assert row['drop_detector'] == wc.DROP_DETECTOR


def test_a_cell_killed_at_the_budget_keeps_its_counts(sweep):
    out, launch = sweep

    def killed(argv, timeout, cwd):
        (_new_run_dir(cwd) / wc.COUNTS_FILE).write_text(json.dumps(COUNTS_FILE))
        raise subprocess.TimeoutExpired(argv, timeout)
    row = launch(killed)
    assert row['exit_reason'] == 'timeout'
    assert (row['drops'], row['collisions'], row['clean_success']) == (1, 1, False)
    assert 'the run wrote no summary' in row['drop_detector']
    assert _stored(out)['drops'] == 1          # the stored stub has them too


def test_a_crashed_cell_keeps_its_counts(sweep):
    out, launch = sweep

    def crashed(argv, timeout, cwd):
        (_new_run_dir(cwd) / wc.COUNTS_FILE).write_text(json.dumps(COUNTS_FILE))
        return types.SimpleNamespace(returncode=139, stdout='', stderr='')
    row = launch(crashed)
    assert row['exit_reason'] == 'crash_exit139'
    assert (row['drops'], row['collisions']) == (1, 1)


def test_a_killed_cell_never_takes_an_older_runs_counts(sweep):
    out, launch = sweep
    old = _new_run_dir(Path.cwd(), 'run_2026-11-11_00-00-01')
    (old / wc.COUNTS_FILE).write_text(json.dumps(COUNTS_FILE))

    def killed_before_its_run_directory(argv, timeout, cwd):
        raise subprocess.TimeoutExpired(argv, timeout)
    row = launch(killed_before_its_run_directory)
    assert row['drops'] is None and row['collisions'] is None
    assert row['drop_detector'].startswith(wc.NOT_DETECTED)
    assert row['clean_success'] is False


def test_a_rejected_cell_says_no_episode_ran(sweep):
    out, launch = sweep

    def rejected(argv, timeout, cwd):
        return types.SimpleNamespace(returncode=1, stdout='',
                                     stderr=REJECTION + '\n')
    row = launch(rejected)
    assert row['exit_reason'] == 'preflight_rejected'
    assert row['drops'] is None and row['collisions'] is None
    assert 'no episode ran' in row['drop_detector']
    assert row['clean_success'] is False
    assert 'no episode ran' in _stored(out)['drop_detector']


def test_a_resumed_row_from_before_the_counts_is_not_rewritten(sweep, monkeypatch):
    out, launch = sweep

    def finished_before_the_counts(argv, timeout, cwd):
        (_new_run_dir(cwd) / wc.SUMMARY_FILE).write_text(json.dumps(
            _cell_summary({})))
        return types.SimpleNamespace(returncode=0, stdout='ok\n', stderr='')
    monkeypatch.setattr(er.subprocess, 'run',
                        lambda argv, capture_output, text, timeout, cwd:
                        finished_before_the_counts(argv, timeout, cwd))
    er.run_cell(CELL, out, 60, [], skip_existing=False)   # the old runner's cell
    path = out / 'cells' / er.cell_tag(CELL) / 'timing_summary.json'
    before = path.read_text()
    row = er.run_cell_counted(CELL, out, 60, [], skip_existing=True)
    assert row['success'] is True
    assert row['drops'] is None and row['clean_success'] is None
    assert row['drop_detector'] == 'not detected (the record has no counts)'
    assert path.read_text() == before          # an old sweep's file stays as it is


def test_aggregate_gives_every_row_the_fields_and_the_csv_its_columns(sweep, monkeypatch):
    out, launch = sweep
    assert {'clean_success', 'drops', 'collisions'} <= set(er.PRIMARY_COLUMNS)
    assert {'drop_events', 'collision_events'} <= er.LIST_VALUED

    def finished_before_the_counts(argv, timeout, cwd):
        (_new_run_dir(cwd) / wc.SUMMARY_FILE).write_text(json.dumps(
            _cell_summary({})))                  # a summary of an old sweep
        return types.SimpleNamespace(returncode=0, stdout='ok\n', stderr='')
    monkeypatch.setattr(er.subprocess, 'run',
                        lambda argv, capture_output, text, timeout, cwd:
                        finished_before_the_counts(argv, timeout, cwd))
    er.run_cell(CELL, out, 60, [], skip_existing=False)   # the old runner's cell
    (out / 'matrix.json').write_text(json.dumps({'cells': [CELL]}))
    er.aggregate(out)
    row = json.loads((out / 'aggregated.jsonl').read_text().splitlines()[0])
    assert row['success'] is True
    assert row['drops'] is None and row['clean_success'] is None
    assert row['drop_detector'] == 'not detected (the record has no counts)'
    header, line = (out / 'aggregated.csv').read_text().splitlines()[:2]
    cols = header.split(',')
    assert {'clean_success', 'drops', 'collisions', 'drop_detector'} <= set(cols)
    assert line.split(',')[cols.index('drops')] == ''      # empty, never 0


# ----- the find_dice harnesses: our arm ---------------------------------

def _bridge_file(success=True, counts=ONE_DROP):
    return {'rewards': [1.0 if success else 0.0], 'time_deltas': [5.0],
            'scene_file': '/scenes/' + SCENE, 'run_dir': None,
            'outcome': {'status': 'success' if success else 'failure',
                        'success': success},
            **wc.episode_fields(success, counts)}


def test_a_bridge_episode_gives_its_fields_under_the_harness_test(tmp_path):
    f = wc.from_bridge_episode(_bridge_file(counts=WATCHED_CLEAN),
                               str(tmp_path), True)
    assert (f['drops'], f['collisions'], f['clean_success']) == (0, 0, True)
    # the harness's own success test decides clean_success, not the file's
    f = wc.from_bridge_episode(_bridge_file(counts=WATCHED_CLEAN),
                               str(tmp_path), False)
    assert (f['drops'], f['clean_success']) == (0, False)


def test_a_bridge_episode_killed_at_the_cap_keeps_its_counts(tmp_path):
    run = tmp_path / 'ours' / 'run_2026-11-12_00-00-01'
    run.mkdir(parents=True)
    (run / wc.COUNTS_FILE).write_text(json.dumps(COUNTS_FILE))
    f = wc.from_bridge_episode(None, str(tmp_path), False)
    assert (f['drops'], f['collisions'], f['clean_success']) == (1, 1, False)
    assert 'the run wrote no summary' in f['collision_detector']
    # the pipeline's summary, when the run got that far, comes first
    (run / wc.SUMMARY_FILE).write_text(json.dumps(
        {'success': True, **wc.episode_fields(True, WATCHED_CLEAN)}))
    f = wc.from_bridge_episode(None, str(tmp_path), False)
    assert (f['drops'], f['collisions'], f['clean_success']) == (0, 0, False)


def test_a_bridge_episode_that_left_nothing_is_not_detected(tmp_path):
    f = wc.from_bridge_episode(None, str(tmp_path), False)
    assert f['drops'] is None and f['collisions'] is None
    assert f['drop_detector'].startswith(wc.NOT_DETECTED)
    # a driver file from before the counts reads the same
    f = wc.from_bridge_episode({'outcome': {'success': True}},
                               str(tmp_path), True)
    assert f['drops'] is None and f['clean_success'] is None


class _Driver:
    """The bridge driver's process for slip_eval.run_episode: it writes
    what a run leaves in --save-dir, then ends or hangs until the cap."""
    pid = 4321

    def __init__(self, cmd, leave, hang):
        self.save_dir = cmd[cmd.index('--save-dir') + 1]
        self.leave, self.hang = leave, hang

    def wait(self, timeout=None):
        if self.leave:
            self.leave(Path(self.save_dir))
            self.leave = None
        if self.hang and timeout is not None:
            raise subprocess.TimeoutExpired('driver', timeout)
        return 0


def _slip_episode(tmp_path, monkeypatch, leave, hang=False, outcome='success'):
    monkeypatch.setattr(se.subprocess, 'Popen',
                        lambda cmd, **kw: _Driver(cmd, leave, hang))
    monkeypatch.setattr(se.os, 'killpg', lambda pid, sig: None, raising=False)
    monkeypatch.setattr(se.episode_metrics, '_find_run_dir', lambda d: d)
    monkeypatch.setattr(se.episode_metrics, 'metrics',
                        lambda d: {'outcome': outcome, 'wall_s': 10.0})
    a = types.SimpleNamespace(out=str(tmp_path), python='python',
                              snapshot=str(REPO), cwd=str(tmp_path), cap=5)
    return se.run_episode(a, 'base', 7, 0)


def test_slip_evals_record_carries_the_drivers_fields(tmp_path, monkeypatch):
    def leave(save_dir):
        (save_dir / 'bridge_episode.json').write_text(json.dumps(_bridge_file()))
    rec = _slip_episode(tmp_path, monkeypatch, leave)
    assert set(wc.FIELDS) <= set(rec)
    assert (rec['drops'], rec['collisions'], rec['clean_success']) == (1, 0, False)
    assert rec['drop_events'] == [DROP]


def test_slip_evals_record_of_a_killed_run_keeps_the_counts(tmp_path, monkeypatch):
    def leave(save_dir):
        run = save_dir / 'ours' / 'run_2026-11-12_00-00-01'
        run.mkdir(parents=True)
        (run / wc.COUNTS_FILE).write_text(json.dumps(COUNTS_FILE))
    rec = _slip_episode(tmp_path, monkeypatch, leave, hang=True, outcome=None)
    assert rec['timed_out'] is True and rec['bridge_status'] is None
    assert (rec['drops'], rec['collisions'], rec['clean_success']) == (1, 1, False)


def _campaign_args(tmp_path):
    return types.SimpleNamespace(
        out=str(tmp_path), venv_t='/venv_t', venv_o='/venv_o',
        snapshot=str(REPO), mode='full', cap=60.0, their_envs=str(tmp_path),
        pythonhashseed='0', tampura_work='/tampura-work',
        pddlstream_lib='/pddlstream_lib', drop_t_history=False)


def test_the_campaigns_arm_o_record_carries_the_drivers_fields(tmp_path, monkeypatch):
    def run_capped(cmd, cwd, env, cap, console):
        save_dir = Path(cmd[cmd.index('--save-dir') + 1])
        (save_dir / 'bridge_episode.json').write_text(json.dumps(_bridge_file()))
        return 0, 12.0, 12.0, False
    monkeypatch.setattr(bc, 'run_capped', run_capped)
    rec = bc.episode_o(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])
    assert rec['success'] is True
    assert (rec['drops'], rec['collisions'], rec['clean_success']) == (1, 0, False)


def test_the_campaigns_arm_o_record_of_a_killed_run_keeps_the_counts(tmp_path, monkeypatch):
    def run_capped(cmd, cwd, env, cap, console):
        run = Path(cmd[cmd.index('--save-dir') + 1]) / 'ours' / 'run_x'
        run.mkdir(parents=True)
        (run / wc.COUNTS_FILE).write_text(json.dumps(COUNTS_FILE))
        return None, 60.0, 60.0, True
    monkeypatch.setattr(bc, 'run_capped', run_capped)
    rec = bc.episode_o(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])
    assert rec['status'] == 'killed' and rec['success'] is False
    assert (rec['drops'], rec['collisions'], rec['clean_success']) == (1, 1, False)


# ----- the find_dice harnesses: TAMPURA's arm ---------------------------

def _episode_t(tmp_path, monkeypatch, rewards):
    monkeypatch.setattr(bc, 'run_capped', lambda *k: (0, 30.0, 30.0, False))
    monkeypatch.setattr(bc, 'read_text',
                        lambda path: f'Loading scene from /scenes/{SCENE}\n')
    monkeypatch.setattr(bc, 'read_history_t', lambda a, d: {
        'history': True, 'rewards': rewards,
        'time_deltas': [float(i + 1) for i in range(len(rewards))],
        'actions': ['look'] * len(rewards)})
    return bc.episode_t(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])


def test_their_arm_cannot_drop_and_its_collisions_are_not_detected(tmp_path, monkeypatch):
    rec = _episode_t(tmp_path, monkeypatch, [0.0, 1.0])
    assert rec['success'] is True
    assert rec['drops'] == 0
    assert rec['drop_detector'].startswith(wc.CANNOT_HAPPEN)
    assert rec['collisions'] is None                         # never a 0
    assert rec['collision_detector'].startswith(wc.NOT_DETECTED)
    assert rec['clean_success'] is None      # a success nobody could vouch for
    rec = _episode_t(tmp_path, monkeypatch, [0.0, 0.0])
    assert rec['success'] is False and rec['clean_success'] is False


# ----- the generated-scene eval's rows (both arms) ----------------------

needs_uname = pytest.mark.skipif(not hasattr(os, 'uname'),
                                 reason='run_one names its host with os.uname')


def _gen_row(tmp_path, monkeypatch, arm, rec):
    def episode_cwd(a, arm, seed, rep, attempt, scene):
        d = tmp_path / 'cwd' / f'{arm}_{seed}'
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    monkeypatch.setattr(gse, 'episode_cwd', episode_cwd)
    monkeypatch.setattr(gse.bc, 'machine_check', lambda: [])
    monkeypatch.setattr(gse.bc, 'episode_t', lambda *k, **kw: dict(rec))
    monkeypatch.setattr(gse.se, 'run_episode', lambda *k, **kw: dict(rec))
    a = types.SimpleNamespace(
        out=str(tmp_path), venv_t='/venv_t', snapshot=str(REPO), cap=60.0,
        tampura_work='/tampura-work', python_o='python', shots='none',
        cups={'7': 3})
    return gse.run_one(a, arm, 7, 0, 1, SCENE, 0)


@needs_uname
def test_a_generated_scene_row_of_our_arm_carries_the_fields(tmp_path, monkeypatch):
    rec = {'scene_file': SCENE, 'timed_out': False, 'bridge_status': 'success',
           'metrics': {'outcome': 'success', 'wall_s': 10.0},
           'process_wall_s': 12.0, 'save_dir': str(tmp_path),
           **wc.episode_fields(True, ONE_DROP)}
    row = _gen_row(tmp_path, monkeypatch, 'O', rec)
    assert row['success'] is True and set(wc.FIELDS) <= set(row)
    assert (row['drops'], row['collisions'], row['clean_success']) == (1, 0, False)
    # a run that loaded another scene does not count: no success, never clean
    other = dict(rec, scene_file='scene_8.json',
                 **wc.episode_fields(True, WATCHED_CLEAN))
    row = _gen_row(tmp_path, monkeypatch, 'O', other)
    assert row['success'] is False and row['clean_success'] is False
    assert (row['drops'], row['collisions']) == (0, 0)


@needs_uname
def test_a_generated_scene_row_of_their_arm_carries_the_fields(tmp_path, monkeypatch):
    # DV-1 (track/eval, path 6): arm T's success is the standard test, read from their final world by the
    # reviewed rollout wrapper (episode_t's 'final_world', 'standard_read', 'standard_success'); their own
    # reward stays beside it as t_reward_success
    rec = {'scene_ok': True, 'status': 'success', 'wall_s': 30.0,
           'loop_s': 25.0, 'save_dir': str(tmp_path),
           'final_world': {'ok': True, 'standard_success': True},
           'standard_read': True, 'standard_success': True,
           **wc.kinematic_arm_fields(True)}
    row = _gen_row(tmp_path, monkeypatch, 'T', rec)
    assert row['success'] is True and row['t_reward_success'] is True
    assert row['drops'] == 0 and row['collisions'] is None
    assert row['drop_detector'].startswith(wc.CANNOT_HAPPEN)
    assert row['collision_detector'].startswith(wc.NOT_DETECTED)
    assert row['clean_success'] is None
    # their reward with no readable final world counts as a non-success under DV-1 (R2 of the G13
    # review, classify_t's UNREAD_WHY; 1580c85): no success, never clean, the detector words stay
    unread = dict(rec, final_world=None, standard_read=False, standard_success=False)
    row = _gen_row(tmp_path, monkeypatch, 'T', unread)
    assert row['counts'] is True and row['success'] is False and row['t_reward_success'] is True
    assert row['drop_detector'].startswith(wc.CANNOT_HAPPEN) and row['clean_success'] is False
