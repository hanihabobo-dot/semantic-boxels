"""class_uncertain's arm T for the cluster (Q42): tools/cu_eval.py (the harness), tools/cluster/cu_t.py
(their run_planner.py with one read after their rollout) and tools/cluster/cu_eval.sbatch (text only).
No simulator, no TAMPURA: their packages are stood in by small fakes."""
import json
import os
import subprocess
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(REPO, 'tools'), os.path.join(REPO, 'tools', 'cluster')):
    if p not in sys.path:
        sys.path.insert(0, p)
import cu_eval as ce  # noqa: E402
import cu_t  # noqa: E402
import memwatch as mw  # noqa: E402


def args(tmp_path, **kw):
    a = types.SimpleNamespace(snapshot=str(tmp_path / 'sb'), out=str(tmp_path / 'out' / '77'),
                              venv_t=str(tmp_path / 'tw' / '.venv'), tampura_work=str(tmp_path / 'tw'),
                              scratch=str(tmp_path / 'scratch'), hashseed='0', cap=5.0, reps=1,
                              seed_list=[0], min_avail_gb=0.0, peak_report_gb=0.0)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


FINAL_OK = {'ok': True, 'max_steps': 20, 'steps': 20, 'actions': ['inspect(o1)', 'pick(o1, g1, r0)', 'drop(o1, g1, r1)']
            + ['no-op()'] * 17, 'rewards': [0.0, 0.0] + [1.0] * 18, 'reward_t0': 0.0, 'success_first_goal': True,
            'first_goal_step': 3, 'reward_last': 1.0, 'n_noop': 17, 'first_noop_step': 4, 'broken': False,
            'broken_reports': [], 'world_success_end': True, 'world_rows': [{'body': 4, 'fruit': True, 'in_bowl': True}],
            'read_s': 0.002}
SPANS = [{'step': 0, 'get_action_s': 40.5, 'action': 'inspect(o1)'}, {'step': 1, 'get_action_s': 20.25, 'action': 'pick'}]


# ---- the harness's pieces ----------------------------------------------------------------------------

def test_seeds_are_parsed_and_a_seed_named_twice_is_refused():
    assert ce.parse_seeds('0-4') == [0, 1, 2, 3, 4]
    assert ce.parse_seeds('3, 7-8') == [3, 7, 8]
    for bad in ('', '2-1', '1,1', '0-2,2'):
        with pytest.raises(SystemExit):
            ce.parse_seeds(bad)


def test_the_episodes_environment_holds_their_two_packages_and_nothing_of_ours(tmp_path):
    base = {'PATH': '/usr/bin', 'PYTHONPATH': '/snap/sb:/w/pddlstream_lib', 'PYTHONHOME': '/x', 'PYTHONHASHSEED': '5'}
    env = ce.child_env(base, '/w/tw', '0')
    assert env['PYTHONPATH'].split(os.pathsep) == [os.path.join('/w/tw', 'tampura'),
                                                    os.path.join('/w/tw', 'tampura_environments')]
    assert env['PYTHONHASHSEED'] == '0' and env['MPLBACKEND'] == 'Agg' and env['PYTHONDONTWRITEBYTECODE'] == '1'
    assert 'PYTHONHOME' not in env and env['PATH'] == '/usr/bin'
    assert base['PYTHONPATH'] == '/snap/sb:/w/pddlstream_lib'          # the caller's is not edited
    assert 'PYTHONHASHSEED' not in ce.child_env(base, '/w/tw', 'unset')


def test_the_command_is_their_driver_through_cu_t_with_their_config_and_no_planner_argument(tmp_path):
    a = args(tmp_path)
    cmd = ce.command(a, 13, '/out/save')
    assert cmd[0] == os.path.join(a.venv_t, 'bin', 'python') and cmd[1] == '-u'
    assert cmd[2] == os.path.join(a.snapshot, 'tools', 'cluster', 'cu_t.py')
    assert cmd[cmd.index('--run-planner') + 1] == os.path.join(a.tampura_work, 'tampura_environments', 'run_planner.py')
    assert cmd[cmd.index('--world-test-dir') + 1] == os.path.join(a.snapshot, 'tasks_probe')
    assert cmd[cmd.index('--config') + 1] == './env_configs/class_uncertain.yml'
    assert cmd[cmd.index('--global-seed') + 1] == '13' and cmd[cmd.index('--save-dir') + 1] == '/out/save'
    assert '--planner' not in cmd and '--vis' not in cmd and '--max-steps' not in cmd
    # their own arguments pass cu_t.py's splitter untouched
    own, rest = cu_t.split_args(cmd[3:])
    assert rest == ['--config', './env_configs/class_uncertain.yml', '--global-seed', '13', '--save-dir', '/out/save']


def test_a_row_of_a_finished_episode_carries_the_world_test_and_rule_18s_words_never_a_zero():
    row = ce.build_row(13, 2, 5, 0, False, 612.345, dict(FINAL_OK), SPANS, '0')
    assert (row['task'], row['seed'], row['rep'], row['arm'], row['order']) == ('class_uncertain', 13, 2, 'T', 5)
    assert row['counts'] is True and row['success'] is True and row['world_success_end'] is True and row['why'] is None
    assert row['success_first_goal'] is True and row['first_goal_step'] == 3
    assert row['return'] == pytest.approx(0.98 ** 3)
    assert row['world_first_steps'] is None and row['world_return'] is None
    assert row['get_action_s'] == 60.75 and row['get_action_spans'] == [40.5, 20.25] and row['wall_s'] == 612.35
    assert row['drops'] is None and row['collisions'] is None and row['clean_success'] is None
    assert row['drop_detector'].startswith('cannot happen') and row['collision_detector'].startswith('not detected')
    assert row['pythonhashseed'] == 0 and ce.build_row(1, 0, 0, 0, False, 1.0, dict(FINAL_OK), [], 'unset')['pythonhashseed'] is None


def test_their_reward_without_the_world_test_is_not_a_success():
    final = dict(FINAL_OK, world_success_end=False)          # CU-15: their reward reached, no fruit in the bowl
    row = ce.build_row(14, 0, 0, 0, False, 500.0, final, SPANS, '0')
    assert row['success_first_goal'] is True and row['world_success_end'] is False
    assert row['counts'] is True and row['success'] is False


def test_a_timeout_and_a_crash_count_as_failures_and_a_missing_read_does_not_count():
    t = ce.build_row(1, 0, 0, -9, True, 3600.0, None, SPANS[:1], '0')
    assert t['counts'] is True and t['success'] is False and t['timed_out'] is True and 'timeout' in t['why']
    assert t['world_success_end'] is None and t['return'] is None
    c = ce.build_row(1, 0, 0, 1, False, 90.0, {'ok': False, 'crash': {'error': 'IndexError()', 'trace': 'x'}}, SPANS, '0')
    assert c['counts'] is True and c['success'] is False and 'CU-14' in c['why'] and c['crash']['error'] == 'IndexError()'
    n = ce.build_row(1, 0, 0, 1, False, 3.0, None, [], '0')
    assert n['counts'] is False and n['success'] is None and 'rc 1' in n['why']
    r = ce.build_row(1, 0, 0, 0, False, 600.0, {'ok': False, 'read_error': "KeyError('regions')", 'actions': ['a']}, SPANS, '0')
    assert r['counts'] is False and r['success'] is None and 'read after their rollout failed' in r['why']
    assert r['actions'] == ['a']                                          # what their history gave stays in the row


def test_the_scratch_directory_holds_only_the_two_links_and_one_that_exists_is_refused(tmp_path):
    tw = tmp_path / 'tw'
    (tw / 'tampura_environments' / 'env_configs').mkdir(parents=True)
    (tw / 'tampura_environments' / 'tampura_environments' / 'class_uncertain' / 'problems').mkdir(parents=True)
    (tw / 'tampura_environments' / 'env_configs' / 'class_uncertain.yml').write_text('task: class_uncertain\n')
    d = str(tmp_path / 'scratch' / 'ep')
    try:
        ce.make_scratch(d, str(tw))
    except OSError:
        pytest.skip('this account may not make symbolic links')
    assert os.path.islink(os.path.join(d, 'env_configs'))
    assert os.path.isfile(os.path.join(d, 'env_configs', 'class_uncertain.yml'))
    assert os.path.islink(os.path.join(d, 'tampura_environments', 'class_uncertain', 'problems'))
    with pytest.raises(SystemExit):
        ce.make_scratch(d, str(tw))


class FakeProc:
    """Stands in for the episode's process: writes what cu_t.py would leave in the save folder."""

    def __init__(self, log, final=FINAL_OK, rc=0, hang=False):
        self.log, self.final, self.rc, self.hang, self.pid, self.killed = log, final, rc, hang, 999999, False

    def __call__(self, cmd, cwd=None, env=None, stdout=None, stderr=None, start_new_session=None):
        self.log.append({'cmd': cmd, 'cwd': cwd, 'env': env, 'cwd_existed': os.path.isdir(cwd),
                         'new_session': start_new_session})
        save = cmd[cmd.index('--save-dir') + 1]
        if self.final is not None and not self.hang:
            with open(os.path.join(save, ce.FINAL_NAME), 'w') as f:
                json.dump(self.final, f)
            with open(os.path.join(save, ce.SPANS_NAME), 'w') as f:
                f.write('\n'.join(json.dumps(s) for s in SPANS) + '\n')
        return self

    def wait(self, timeout=None):
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired('x', timeout)
        return -9 if self.killed else self.rc

    def kill(self):
        self.killed = True


@pytest.fixture
def plain_scratch(monkeypatch):
    """make_scratch without the links (Windows accounts may not make them); the directory is real."""
    def make(path, tampura_work):
        if os.path.lexists(path):
            raise SystemExit('exists')
        os.makedirs(path)
        return path
    monkeypatch.setattr(ce, 'make_scratch', make)
    monkeypatch.setattr(ce, 'end_group', lambda proc: proc.kill())


def test_one_episode_runs_in_its_own_scratch_which_is_gone_afterwards(tmp_path, plain_scratch):
    a = args(tmp_path)
    log = []
    row = ce.run_one(a, 7, 1, 3, base_env={'PATH': 'p'}, popen=FakeProc(log))
    call = log[0]
    assert call['cwd_existed'] and not os.path.exists(call['cwd']) and call['new_session'] is True
    assert os.path.basename(call['cwd']) == 'cu_T_77_seed7_rep1'
    assert os.path.dirname(call['cwd']) == a.scratch
    assert call['env']['PYTHONHASHSEED'] == '0' and 'tampura_environments' in call['env']['PYTHONPATH']
    ep = os.path.join(a.out, 'T', 'seed7_rep1')
    assert os.path.isfile(os.path.join(ep, 'console.txt')) and os.path.isfile(os.path.join(ep, 'save', ce.FINAL_NAME))
    assert row['seed'] == 7 and row['rep'] == 1 and row['order'] == 3 and row['success'] is True and row['rc'] == 0
    assert row['get_action_s'] == 60.75


def test_an_episode_past_the_cap_is_ended_and_recorded_as_a_timeout(tmp_path, plain_scratch):
    a = args(tmp_path, cap=0.01)
    log = []
    proc = FakeProc(log, hang=True)
    row = ce.run_one(a, 2, 0, 0, base_env={}, popen=proc)
    assert proc.killed and row['timed_out'] is True and row['counts'] is True and row['success'] is False
    assert not os.path.exists(log[0]['cwd'])


def _ready(tmp_path, a):
    for rel in (('sb', 'tools', 'cluster', 'cu_t.py'), ('sb', 'tasks_probe', 'cu_rand.py'),
                ('tw', 'tampura_environments', 'run_planner.py'),
                ('tw', 'tampura_environments', 'env_configs', 'class_uncertain.yml'), ('tw', '.venv', 'bin', 'python')):
        p = tmp_path.joinpath(*rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('')


def test_a_job_runs_repetitions_outside_seeds_inside_and_resumes_without_running_a_row_twice(tmp_path, plain_scratch, monkeypatch, capsys):
    a = args(tmp_path, reps=2, seed_list=[0, 13])
    _ready(tmp_path, a)
    log = []

    def one(a_, seed, rep, order):
        log.append((seed, rep))
        return ce.build_row(seed, rep, order, 0, False, 1.0, dict(FINAL_OK), SPANS, '0')
    monkeypatch.setattr(ce, 'run_one', one)
    assert ce.run(a) == 0
    assert log == [(0, 0), (13, 0), (0, 1), (13, 1)]
    rows = ce.load_rows(os.path.join(a.out, ce.ROWS))
    assert [(r['seed'], r['rep'], r['order']) for r in rows] == [(0, 0, 0), (13, 0, 1), (0, 1, 2), (13, 1, 3)]
    assert all('mem' in r and 'peak_over_6gb' in r for r in rows)
    meta = json.load(open(os.path.join(a.out, 'cu_eval.json')))
    assert meta['seeds'] == [0, 13] and meta['reps'] == 2 and meta['hashseed'] == '0'
    del log[:]
    a.reps = 3
    assert ce.run(a) == 0
    assert log == [(0, 2), (13, 2)]                       # only the new repetition ran
    out = capsys.readouterr().out
    assert 'world-state test at the end (primary): 6 of 6' in out


def test_a_missing_file_stops_the_job_before_the_first_episode(tmp_path, plain_scratch, monkeypatch, capsys):
    a = args(tmp_path)
    _ready(tmp_path, a)
    os.remove(os.path.join(a.snapshot, 'tasks_probe', 'cu_rand.py'))
    monkeypatch.setattr(ce, 'run_one', lambda *x: pytest.fail('an episode ran'))
    assert ce.run(a) == 2
    assert 'cu_rand.py is missing: nothing run' in capsys.readouterr().out
    assert not os.path.exists(os.path.join(a.out, ce.ROWS))


def test_low_memory_stops_the_job_with_exit_code_4_and_starts_nothing(tmp_path, plain_scratch, monkeypatch):
    a = args(tmp_path, min_avail_gb=4.0, seed_list=[0, 1])
    _ready(tmp_path, a)
    monkeypatch.setattr(mw, 'mem_available_kb', lambda *x, **k: 3 * mw.KB_PER_GB)
    monkeypatch.setattr(ce, 'run_one', lambda *x: pytest.fail('an episode ran under the limit'))
    assert ce.run(a) == mw.EXIT_LOW_MEMORY
    assert os.path.isfile(os.path.join(a.out, mw.STOP_FILE))


def test_the_report_counts_the_folders_together_and_names_what_does_not_count(tmp_path):
    d1, d2 = tmp_path / 'j1', tmp_path / 'j2'
    d1.mkdir()
    d2.mkdir()
    ce.append_row(str(d1 / ce.ROWS), ce.build_row(0, 0, 0, 0, False, 600.0, dict(FINAL_OK), SPANS, '0'))
    ce.append_row(str(d1 / ce.ROWS), ce.build_row(1, 0, 1, 0, False, 800.0, dict(FINAL_OK, world_success_end=False, broken=True), SPANS, '0'))
    ce.append_row(str(d2 / ce.ROWS), ce.build_row(2, 0, 0, -9, True, 3600.0, None, [], '0'))
    ce.append_row(str(d2 / ce.ROWS), ce.build_row(3, 0, 1, 1, False, 2.0, None, [], '0'))
    text = ce.report([str(d1), str(d2)])
    assert '4 episode(s), 3 counted' in text
    assert 'world-state test at the end (primary): 1 of 3' in text and 'their reward reached: 2 of 3' in text
    assert 'timeouts 1' in text and 'episodes with a `broken` report 1' in text and 'not counted 1' in text
    assert 'NOT COUNTED seed 3 rep 0' in text and 'clean success: not measured' in text
    assert 'WARNING' not in text
    ce.append_row(str(d2 / ce.ROWS), ce.build_row(0, 0, 2, 0, False, 600.0, dict(FINAL_OK), SPANS, '0'))
    assert 'appear more than once: [(0, 0)]' in ce.report([str(d1), str(d2)])


def test_the_dry_run_prints_every_episode_and_runs_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ce, 'run', lambda a: pytest.fail('the dry run ran'))
    rc = ce.main(['--snapshot', '/w/sb_1', '--out', '/w/out/5', '--seeds', '0-1', '--reps', '2', '--venv-t', '/w/tw/.venv',
                  '--tampura-work', '/w/tw', '--dry-run'])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0 and out[0].startswith('4 episode(s), cap 3600 s each') and 'PYTHONHASHSEED=0' in out[0]
    assert [line.split(':')[0] for line in out[1:]] == ['rep 0 seed 0', 'rep 0 seed 1', 'rep 1 seed 0', 'rep 1 seed 1']
    assert all('--global-seed' in line and 'cu_t.py' in line for line in out[1:])


# ---- cu_t.py: what is read from their history, and the one read after their rollout ---------------------

class Obs:
    def __init__(self, broken=None):
        self.broken = broken


def test_their_history_gives_the_reward_after_each_step_and_the_break_reports():
    actions = ['inspect(o1)', 'pick(o1, g, r)', 'no-op()', None]
    obs = [Obs(), Obs(broken='o1'), None, None]
    rewards = [0.0, 0.0, 0.0, 1.0]                    # before steps 0, 1, 2 and after the last
    f = cu_t.history_facts(actions, obs, rewards, 3)
    assert f['actions'] == ['inspect(o1)', 'pick(o1, g, r)', 'no-op()'] and f['steps'] == 3
    assert f['rewards'] == [0.0, 0.0, 1.0] and f['reward_t0'] == 0.0 and f['reward_last'] == 1.0
    assert f['success_first_goal'] is True and f['first_goal_step'] == 3
    assert f['broken'] is True and f['broken_reports'] == ['o1']
    assert f['n_noop'] == 1 and f['first_noop_step'] == 3
    g = cu_t.history_facts(['a', None], [Obs(), None], [0.0, 0.0], 1)
    assert g['success_first_goal'] is False and g['first_goal_step'] is None and g['broken'] is False


def test_the_planner_argument_is_refused_and_the_rest_goes_to_their_parser():
    own, rest = cu_t.split_args(['--run-planner', '/tw/run_planner.py', '--world-test-dir', '/sb/tasks_probe',
                                 '--config', 'c.yml', '--global-seed', '3'])
    assert own.run_planner == '/tw/run_planner.py' and rest == ['--config', 'c.yml', '--global-seed', '3']
    for bad in (['--planner', 'x'], ['--planner=x']):
        with pytest.raises(SystemExit):
            cu_t.split_args(['--run-planner', 'a', '--world-test-dir', 'b'] + bad)


class History:
    def __init__(self):
        self.config = {'max_steps': 2}
        self.actions = ['pick(o1, g, r)', 'drop(o1, g, bowl)', None]
        self.observations = [Obs(), Obs(), None]
        self.rewards = [0.0, 0.0, 1.0]


class World:
    regions = ['floor', 'bowl']


def test_the_read_after_the_rollout_writes_the_world_test_and_a_failing_read_is_recorded_not_raised(tmp_path):
    seen = []

    def world_test(world, bowl, broken_any):
        seen.append((world, bowl, broken_any))
        return True, [{'body': 4, 'in_bowl': True}]
    w = World()
    rec = cu_t.record_after_rollout(w, History(), str(tmp_path), world_test)
    assert seen == [(w, 'bowl', False)]
    on_disk = json.load(open(tmp_path / cu_t.FINAL_NAME))
    assert rec['ok'] is True and on_disk['ok'] is True and on_disk['world_success_end'] is True
    assert on_disk['world_rows'] == [{'body': 4, 'in_bowl': True}] and on_disk['first_goal_step'] == 2

    def broken_test(world, bowl, broken_any):
        raise RuntimeError('no client')
    rec = cu_t.record_after_rollout(w, History(), str(tmp_path), broken_test)
    assert rec['ok'] is False and 'no client' in rec['read_error'] and rec['actions'] == ['pick(o1, g, r)', 'drop(o1, g, bowl)']
    assert 'world_success_end' not in rec


@pytest.fixture
def fake_tampura(monkeypatch):
    """Their three modules, stood in: a TampuraPolicy whose rollout sets env.state to None (CU-15) and
    returns a history, and a registry."""
    events = []
    registry = {}

    class TampuraPolicy:
        def __init__(self, config, problem_spec, **kwargs):
            self.config = config

        def get_action(self, belief, store):
            events.append('their get_action')
            return ('no-op()', {}, store)

        def rollout(self, env, b, store):
            events.append('their rollout')
            self.get_action(b, store)
            if getattr(env, 'boom', False):
                raise IndexError('inside their execute_fn')
            env.state = None
            return History(), store

    mods = {'tampura': types.ModuleType('tampura'), 'tampura.config': types.ModuleType('tampura.config'),
            'tampura.config.config': types.ModuleType('tampura.config.config'),
            'tampura.policies': types.ModuleType('tampura.policies'),
            'tampura.policies.tampura_policy': types.ModuleType('tampura.policies.tampura_policy'),
            'tampura_environments': types.ModuleType('tampura_environments')}
    mods['tampura'].__file__ = os.path.join('tw', 'tampura', 'tampura', '__init__.py')
    mods['tampura_environments'].__file__ = os.path.join('tw', 'te', 'tampura_environments', '__init__.py')
    mods['tampura.config.config'].register_planner = lambda name, cls: registry.__setitem__(name, cls)
    mods['tampura.policies.tampura_policy'].TampuraPolicy = TampuraPolicy
    for k, v in mods.items():
        monkeypatch.setitem(sys.modules, k, v)
    return events, registry, TampuraPolicy


class Env:
    def __init__(self, world):
        self.state = types.SimpleNamespace(world=world)


def test_the_registered_policy_is_theirs_with_three_overrides_and_reads_once_after_their_rollout(tmp_path, fake_tampura):
    events, registry, Theirs = fake_tampura
    w = World()

    def world_test(world, bowl, broken_any):
        events.append('our read')
        assert world is w                     # the handle taken before their rollout set env.state to None
        return False, []
    cls = cu_t.register(world_test)
    assert registry == {cu_t.PLANNER_NAME: cls} and cls.__mro__[1] is Theirs
    assert sorted(k for k, v in vars(cls).items() if callable(v)) == sorted(cu_t.OVERRIDES)
    policy = cls({'save_dir': str(tmp_path), 'planner': cu_t.PLANNER_NAME, 'max_steps': 2}, None)
    runtime = json.load(open(tmp_path / cu_t.RUNTIME_NAME))
    assert runtime['overrides'] == runtime['overrides_expected'] and runtime['base'].endswith('TampuraPolicy')
    assert runtime['tampura'].endswith(os.path.join('tampura', 'tampura')) and 'save_dir' not in runtime['config']
    env = Env(w)
    out = policy.rollout(env, 'b', 'store')
    assert events == ['their rollout', 'their get_action', 'our read'] and isinstance(out[0], History)
    final = json.load(open(tmp_path / cu_t.FINAL_NAME))
    assert final['ok'] is True and final['world_success_end'] is False
    spans = [json.loads(x) for x in open(tmp_path / cu_t.SPANS_NAME)]
    assert len(spans) == 1 and spans[0]['step'] == 0 and spans[0]['action'] == 'no-op()'


def test_a_rollout_that_raises_is_recorded_and_raised_again(tmp_path, fake_tampura):
    events, registry, Theirs = fake_tampura
    cls = cu_t.register(lambda *x: pytest.fail('the world was read after a crash'))
    policy = cls({'save_dir': str(tmp_path), 'planner': cu_t.PLANNER_NAME}, None)
    env = Env(World())
    env.boom = True
    with pytest.raises(IndexError):
        policy.rollout(env, 'b', 'store')
    final = json.load(open(tmp_path / cu_t.FINAL_NAME))
    assert final['ok'] is False and 'inside their execute_fn' in final['crash']['error']
    assert final['crash']['get_action_calls'] == 1
    row = ce.build_row(0, 0, 0, 1, False, 5.0, final, [], '0')
    assert row['counts'] is True and row['success'] is False


# ---- the job script, as text ---------------------------------------------------------------------------

def test_the_job_script_is_marked_not_run_and_calls_the_harness_as_declared():
    path = os.path.join(REPO, 'tools', 'cluster', 'cu_eval.sbatch')
    raw = open(path, 'rb').read()
    assert b'\r' not in raw                                   # LF: bash on the cluster rejects CRLF
    text = raw.decode('utf-8')
    assert 'PREPARED, NOT RUN' in text and "Hani's yes" in text
    assert '--partition=rleap_cpu' in text and '--cpus-per-task=8' in text and '--mem=24G' in text
    calls = [line for line in text.splitlines() if 'tools/cu_eval.py --snapshot' in line]
    assert len(calls) == 2                                    # the dry run and the run
    assert all('--seeds $SEEDS --reps $REPS --cap $CAP' in c for c in calls)
    assert text.count('--hashseed $HASHSEED') == 2 and text.count('--scratch $LD') == 2
    assert 'TREE CHANGED' in text and 'tree_hash tree_before.txt' in text and 'tree_hash tree_after.txt' in text
    assert 'prune_work.sh --apply' in text and 'STOPPED_LOW_MEMORY' in text
    assert 'bridge_gates' not in text                         # find_dice's gates do not apply to this task
    assert 'sbatch -w cn-1xx' in text and 'pkill' not in text and 'killall' not in text
