"""Rule 16 of the dev tracks: tools/memwatch.py (what path 6's harnesses measure and decide
about memory), the guard around the tabletop runner's cells (tools/cluster/p6_run.py) and
the find_dice harness's stop (tools/gen_scene_eval.py).

Everything runs on Windows: the /proc readers take a fake tree, MemAvailable is a value the
tests set, the children's high-water mark is a function.  What needs Linux (the real
/proc, a real child's resident set) is not run here."""
import json
import os
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, os.path.join(REPO, 'tools'), os.path.join(REPO, 'tools', 'cluster')):
    if p not in sys.path:
        sys.path.insert(0, p)
import memwatch as mw  # noqa: E402

GB = mw.KB_PER_GB


def _proc(root, pid, comm, state, ppid, rss_kb, cmd=''):
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / 'stat').write_text(f"{pid} ({comm}) {state} {ppid} 1 1 0 -1\n")
    (d / 'status').write_text(f"Name:\t{comm}\nVmRSS:\t{rss_kb} kB\n")
    (d / 'cmdline').write_bytes(cmd.replace(' ', '\0').encode() + b'\0')


def _meminfo(path, avail_kb):
    path.write_text(f"MemTotal:       16000000 kB\nMemFree:          100000 kB\nMemAvailable:   {avail_kb} kB\n")
    return str(path)


def test_the_readers_parse_proc_text(tmp_path):
    assert mw.parse_meminfo("MemTotal:  1000 kB\nMemAvailable:  600 kB\nHugePages_Total:  0\nbad line\n") == {
        'MemTotal': 1000, 'MemAvailable': 600, 'HugePages_Total': 0}
    assert mw.mem_available_kb(_meminfo(tmp_path / 'mi', 5 * GB)) == 5 * GB
    assert mw.mem_available_kb(str(tmp_path / 'missing')) is None
    assert mw.status_kb("Name:\tx\nVmRSS:\t 1234 kB\nVmHWM:\t 4321 kB\n") == 1234
    assert mw.status_kb("Name:\tx\nVmRSS:\t 1234 kB\nVmHWM:\t 4321 kB\n", 'VmHWM') == 4321
    assert mw.status_kb("Name:\tx\n") is None
    # a command name with spaces and parentheses: the fields are counted from the last ')'
    assert mw.stat_fields("42 (tmux: server (x)) S 7 42 42 0 -1") == {'comm': 'tmux: server (x)', 'state': 'S', 'ppid': 7}
    assert mw.stat_fields("garbage") is None


def test_the_processes_below_a_root_by_the_parent_chain(tmp_path):
    root = tmp_path / 'proc'
    _proc(root, 100, 'python', 'S', 1, 300_000)               # the harness
    _proc(root, 101, 'python', 'S', 100, 900_000)             # the episode
    _proc(root, 102, 'downward', 'R', 101, 400_000)           # its planner
    _proc(root, 103, 'bash', 'S', 1, 50_000)                  # not ours
    _proc(root, 104, 'python', 'Z', 100, 0)                   # a zombie holds nothing
    (root / 'self').mkdir()
    stats = mw.scan_stats(str(root))
    assert mw.below(stats, 100) == [101, 102, 104]
    procs = mw.snapshot_below(100, str(root))
    assert [(p['pid'], p['rss_kb']) for p in procs] == [(101, 900_000), (102, 400_000)]
    assert mw.snapshot_below(999, str(root)) == []


def test_strays_are_pipeline_programs_that_are_not_us_or_our_parents(tmp_path):
    root = tmp_path / 'proc'
    _proc(root, 10, 'bash', 'S', 1, 1000, 'bash job.sbatch')
    _proc(root, 100, 'python', 'S', 10, 300_000, 'python p6_run.py --arm A')
    _proc(root, 200, 'downward', 'S', 1, 400_000, '/x/downward --search ...')            # an orphan planner
    _proc(root, 201, 'python', 'S', 1, 800_000, 'python test_full_pipeline.py --scene stack')
    _proc(root, 202, 'python', 'S', 1, 100_000, 'python something_else.py')
    found = mw.strays(str(root), own_pid=100)
    assert [(s['pid'], s['comm']) for s in found] == [(200, 'downward'), (201, 'python')]
    assert all('rss_kb' in s and 'cmd' in s for s in found)


def test_limits_zero_is_off_and_an_unreadable_meminfo_is_not_a_stop():
    assert mw.low_memory(3 * GB, 4 * GB) and not mw.low_memory(5 * GB, 4 * GB)
    assert not mw.low_memory(None, 4 * GB)
    assert not mw.low_memory(1, 0) and not mw.low_memory(1, None)
    assert mw.limit_kb(4.0) == 4 * GB and mw.EXIT_LOW_MEMORY == 4


def _watch(tmp_path, avail, peak_limit_gb=6, hwm=(100_000, 100_000), root_procs=(), min_gb=4):
    """An EpisodeWatch over a fake /proc, a meminfo file and a fake high-water mark (before, after)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    proc = tmp_path / 'proc'
    proc.mkdir(exist_ok=True)
    for args in root_procs:
        _proc(proc, *args)
    marks = iter(hwm)
    return mw.EpisodeWatch(mw.limit_kb(min_gb), mw.limit_kb(peak_limit_gb), poll_s=0.01, root_pid=100,
                           proc_root=str(proc), meminfo=_meminfo(tmp_path / 'mi', avail),
                           shm_path=str(tmp_path / 'shm'), rusage=lambda: next(marks))


def test_an_episode_whose_high_water_mark_rose_has_its_exact_peak(tmp_path):
    w = _watch(tmp_path, 8 * GB, hwm=(500_000, 1_200_000),
               root_procs=[(100, 'python', 'S', 1, 300_000), (101, 'python', 'S', 100, 700_000)])
    with w:
        w.sample()
    row = w.as_row()
    assert row['peak_rss_kb'] == 1_200_000 and row['peak_exact'] is True and row['children_hwm_kb'] == 1_200_000
    assert row['avail_start_kb'] == row['avail_end_kb'] == row['avail_min_kb'] == 8 * GB
    assert row['group_peak_kb'] == 700_000 and row['polls'] >= 1
    assert row['peak_over_limit'] is False and row['min_avail_limit_kb'] == 4 * GB and row['peak_limit_kb'] == 6 * GB
    assert mw.row_fields(row) == {'mem': row, 'peak_over_6gb': False}


def test_an_episode_under_the_high_water_mark_reports_the_polled_peak_as_such(tmp_path):
    w = _watch(tmp_path, 8 * GB, hwm=(2_000_000, 2_000_000),
               root_procs=[(100, 'python', 'S', 1, 300_000), (101, 'python', 'S', 100, 700_000)])
    with w:
        w.sample()
    row = w.as_row()
    assert row['peak_exact'] is False and row['peak_rss_kb'] == 700_000 and row['children_hwm_kb'] == 2_000_000
    assert 'at a poll' in w.end_lines('x')[0]


def test_a_peak_over_the_limit_is_flagged_and_zero_switches_the_flag_off(tmp_path):
    w = _watch(tmp_path, 8 * GB, hwm=(1_000_000, 7 * GB))
    with w:
        pass
    assert w.over() and mw.row_fields(w.as_row())['peak_over_6gb'] is True
    assert 'OVER 6 GB' in w.end_lines('cell')[0]
    w0 = _watch(tmp_path / 'z', 8 * GB, peak_limit_gb=0, hwm=(1_000_000, 7 * GB))
    with w0:
        pass
    assert not w0.over()


def test_the_lowest_reading_decides_the_stop(tmp_path):
    w = _watch(tmp_path, 3 * GB)                  # under the 4 GB limit from the start
    with w:
        pass
    assert w.low() and w.as_row()['avail_min_kb'] == 3 * GB
    ok = _watch(tmp_path / 'ok', 5 * GB)
    with ok:
        pass
    assert not ok.low()
    off = _watch(tmp_path / 'off', 3 * GB, min_gb=0)
    with off:
        pass
    assert not off.low()                           # a limit of 0 only records


def test_new_shm_names_and_leftover_pipeline_processes_are_reported_not_ended(tmp_path):
    shm = tmp_path / 'shm'
    shm.mkdir()
    (shm / 'old').write_text('')
    w = _watch(tmp_path, 8 * GB, root_procs=[(100, 'python', 'S', 1, 300_000)])
    with w:
        (shm / 'psm_abc').write_text('')
        _proc(tmp_path / 'proc', 300, 'downward', 'S', 1, 250_000, '/x/downward --search')   # appears during the episode
    row = w.as_row()
    assert row['shm_new'] == ['psm_abc']
    assert [(p['pid'], p['comm']) for p in row['leftover']] == [(300, 'downward')]
    lines = w.end_lines('cell')
    assert any('NEW in /dev/shm' in ln for ln in lines) and any('LEFTOVER (reported, not ended)' in ln for ln in lines)
    assert (tmp_path / 'proc' / '300').exists()       # nothing here ends a process or deletes a name
    assert (shm / 'psm_abc').exists()


def test_the_poll_thread_never_ends_an_episode(tmp_path, monkeypatch):
    w = _watch(tmp_path, 8 * GB)
    monkeypatch.setattr(w, 'sample', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    with w:
        import time
        time.sleep(0.05)                               # several polls, all failing
    assert w.as_row()['avail_end_kb'] == 8 * GB


def test_write_stop_prints_the_line_and_writes_the_file(tmp_path, capsys):
    e = mw.LowMemory('end', 3 * GB, 4 * GB, 'randpairs_occ2_seed2')
    path = mw.write_stop(str(tmp_path / 'out'), e, extra='slot 3')
    out = capsys.readouterr().out
    assert out.startswith('[mem] STOPPED_LOW_MEMORY: randpairs_occ2_seed2 end: MemAvailable 3.00 GB under the limit 4.00 GB')
    text = open(path, encoding='utf-8').read().splitlines()
    assert os.path.basename(path) == mw.STOP_FILE and text[0].startswith('STOPPED_LOW_MEMORY')
    assert 'where end' in text[1] and text[2] == 'slot 3'
    assert not isinstance(e, Exception) and isinstance(e, BaseException)     # a runner's `except Exception` cannot swallow it


def test_the_summary_lines_name_every_flagged_episode():
    rows = [{'label': 'A s1', 'peak_over_6gb': False, 'mem': {'avail_min_kb': 6 * GB, 'avail_end_kb': 7 * GB,
                                                              'peak_rss_kb': 1 * GB, 'group_peak_kb': 2 * GB,
                                                              'batch_rss_kb': 100_000, 'leftover': [], 'shm_new': []}},
            {'label': 'A s2', 'peak_over_6gb': True, 'mem': {'avail_min_kb': 5 * GB, 'avail_end_kb': 5 * GB,
                                                             'peak_rss_kb': 7 * GB, 'group_peak_kb': 7 * GB,
                                                             'batch_rss_kb': 110_000,
                                                             'leftover': [{'pid': 9, 'comm': 'downward'}],
                                                             'shm_new': ['psm_x']}}]
    text = '\n'.join(mw.summary_lines(rows))
    assert 'memory: 2 episodes recorded; lowest MemAvailable 5.00 GB' in text and 'highest peak RSS of one process 7.00 GB' in text
    assert 'OVER the peak limit: A s2' in text and 'A s2 left 1 pipeline process(es)' in text and 'A s2: new in /dev/shm' in text
    assert 'A s1' not in text.split('\n', 1)[1]
    assert mw.summary_lines([]) == ['memory: no episode recorded']


# ---------------------------------------------------------------------------
# the guard around the tabletop runner's cells
# ---------------------------------------------------------------------------

def _fake_runner(tmp_path, state, drop_in=None):
    """A runner module with the runner's own shape: cell_tag, run_cell (writes the cell's summary and returns a
    row), aggregate, and a main that loops over the cells calling run_cell through the module global."""
    ran, aggregated = [], []

    def cell_tag(cell):
        return f"cell{cell['seed']}"

    def run_cell(cell, sweep_dir, timeout_s, extra_args, skip_existing):
        tag = cell_tag(cell)
        ran.append(tag)
        d = os.path.join(str(sweep_dir), 'cells', tag)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'timing_summary.json'), 'w') as f:
            f.write('{}')
        if tag == drop_in:
            state['avail'] = 3 * GB                    # memory falls during this cell
        return {'tag': tag, 'success': True}

    mod = SimpleNamespace(cell_tag=cell_tag, run_cell=run_cell, aggregate=lambda p: aggregated.append(str(p)))

    def main(cells, sweep_dir):
        for c in cells:
            mod.run_cell(c, sweep_dir, 1800.0, [], True)
        mod.aggregate(sweep_dir)
        return 0
    mod.main = main
    return mod, ran, aggregated


@pytest.fixture
def avail(monkeypatch):
    state = {'avail': 8 * GB}
    monkeypatch.setattr(mw, 'mem_available_kb', lambda path='/proc/meminfo': state['avail'])
    return state


def test_the_guard_records_each_cell_and_leaves_a_skipped_cell_alone(tmp_path, avail):
    mod, ran, _ = _fake_runner(tmp_path, avail)
    out = tmp_path / 'out'
    logs = []
    mw.install_run_cell_guard(mod, str(out), 4 * GB, 6 * GB, log=logs.append, poll_s=0.01,
                              proc_root=str(tmp_path / 'noproc'), shm_path=str(tmp_path / 'noshm'))
    mod.main([{'seed': 1}, {'seed': 2}], out)
    recs = mw.read_jsonl(str(out / 'mem_cells.jsonl'))
    assert [r['tag'] for r in recs] == ['cell1', 'cell2']
    assert all(r['peak_over_6gb'] is False and r['mem']['avail_start_kb'] == 8 * GB for r in recs)
    assert recs[0]['started_epoch'] <= recs[0]['ended_epoch'] <= recs[1]['ended_epoch']
    assert any(ln.startswith('mem cell1 start: MemAvailable 8.00 GB') for ln in logs)
    assert any(ln.startswith('mem cell2 end: MemAvailable 8.00 GB') for ln in logs)
    # a rerun with the cells banked is not an episode: nothing is recorded for it
    mod.main([{'seed': 1}], out)
    assert len(mw.read_jsonl(str(out / 'mem_cells.jsonl'))) == 2 and ran == ['cell1', 'cell2', 'cell1']


def test_low_memory_before_a_cell_starts_nothing(tmp_path, avail):
    mod, ran, aggregated = _fake_runner(tmp_path, avail)
    avail['avail'] = 3 * GB
    mw.install_run_cell_guard(mod, str(tmp_path / 'o'), 4 * GB, 6 * GB, log=lambda s: None, poll_s=0.01,
                              proc_root=str(tmp_path / 'noproc'), shm_path=str(tmp_path / 'noshm'))
    with pytest.raises(mw.LowMemory) as e:
        mod.main([{'seed': 1}], tmp_path / 'o')
    assert e.value.where == 'start' and ran == []


def test_low_memory_during_a_cell_stops_after_that_cells_record(tmp_path, avail):
    mod, ran, _ = _fake_runner(tmp_path, avail, drop_in='cell2')
    out = tmp_path / 'o'
    mw.install_run_cell_guard(mod, str(out), 4 * GB, 6 * GB, log=lambda s: None, poll_s=0.01,
                              proc_root=str(tmp_path / 'noproc'), shm_path=str(tmp_path / 'noshm'))
    with pytest.raises(mw.LowMemory) as e:
        mod.main([{'seed': 1}, {'seed': 2}, {'seed': 3}], out)
    assert e.value.where == 'end' and ran == ['cell1', 'cell2']             # cell 3 never started
    recs = mw.read_jsonl(str(out / 'mem_cells.jsonl'))
    assert [r['tag'] for r in recs] == ['cell1', 'cell2'] and recs[1]['mem']['avail_end_kb'] == 3 * GB


FAKE_LOOP_RUNNER = '''
import os
import p6_slots
from pathlib import Path
MATRIX_PRESETS = {}
RAN = []
AGG = []
DROP_AT = 2


def iterate_matrix(matrix):
    for sub in matrix:
        c = {k: v[0] for k, v in sub.items() if not k.startswith('_')}
        c['n_hidden'] = 0
        yield c


def cell_tag(c):
    return p6_slots.expected_tag(c)


def cell_to_argv(c, extra):
    return ['python', 'test_full_pipeline.py'] + list(extra)


def run_cell(cell, sweep_dir, timeout_s, extra_args, skip_existing):
    tag = cell_tag(cell)
    RAN.append(tag)
    d = Path(sweep_dir) / 'cells' / tag
    d.mkdir(parents=True, exist_ok=True)
    (d / 'timing_summary.json').write_text('{}')
    if len(RAN) == DROP_AT:
        import memwatch
        memwatch.DROP[0] = True
    return {'success': True}


def aggregate(sweep_dir):
    AGG.append(str(sweep_dir))


def main(argv=None):
    out = Path(argv[argv.index('--output') + 1])
    for c in iterate_matrix(MATRIX_PRESETS['p6-slot']):
        run_cell(c, out, 1800.0, [], True)
    aggregate(out)
    return 0
'''


@pytest.fixture
def isolated_runner(tmp_path, monkeypatch):
    """A code directory holding the fake eval_runner, as the working directory.  p6_run imports `eval_runner` from
    the working directory, so the fake module must not outlive the test: another test file may import the real
    one afterwards (tests/test_p6_view.py runs p6_run's dry run).  Whatever `eval_runner` was in sys.modules before
    is put back at the end; the path entry p6_run adds goes with the copy of sys.path."""
    code = tmp_path / 'codeB'
    code.mkdir()
    (code / 'eval_runner.py').write_text(FAKE_LOOP_RUNNER)
    monkeypatch.chdir(code)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    before = sys.modules.pop('eval_runner', None)
    yield code
    sys.modules.pop('eval_runner', None)
    if before is not None:
        sys.modules['eval_runner'] = before


def test_p6_run_stops_with_exit_4_aggregates_and_leaves_the_stop_file(tmp_path, monkeypatch, avail, isolated_runner):
    import p6_run
    monkeypatch.setattr(mw, 'DROP', [False], raising=False)
    monkeypatch.setattr(mw, 'mem_available_kb',
                        lambda path='/proc/meminfo': 3 * GB if mw.DROP[0] else 8 * GB)
    out = tmp_path / 'out' / 'B' / 'slot_3'
    rc = p6_run.main(['--arm', 'B', '--slot', '3', '--out', str(out)])
    fake = sys.modules['eval_runner']
    assert rc == mw.EXIT_LOW_MEMORY == 4
    assert len(fake.RAN) == 2 and fake.AGG == [str(out)]                   # the cells that ran were aggregated
    assert (out / mw.STOP_FILE).read_text().startswith('STOPPED_LOW_MEMORY')
    meta = json.loads((out / 'p6_run.json').read_text())
    assert meta['stopped'] == 'STOPPED_LOW_MEMORY' and meta['min_avail_limit_kb'] == 4 * GB
    assert meta['peak_limit_kb'] == 6 * GB and meta['runner_rc'] is None
    recs = mw.read_jsonl(str(out / 'mem_cells.jsonl'))
    assert len(recs) == 2 and recs[1]['mem']['avail_end_kb'] == 3 * GB


def test_p6_run_with_the_limits_at_zero_only_records(tmp_path, monkeypatch, isolated_runner):
    import p6_run
    monkeypatch.setattr(mw, 'DROP', [True], raising=False)
    monkeypatch.setattr(mw, 'mem_available_kb', lambda path='/proc/meminfo': 1 * GB)
    out = tmp_path / 'out'
    assert p6_run.main(['--arm', 'A', '--slot', '0', '--out', str(out),
                        '--min-avail-gb', '0', '--peak-report-gb', '0']) == 0
    assert len(sys.modules['eval_runner'].RAN) == 9 and not (out / mw.STOP_FILE).exists()
    assert len(mw.read_jsonl(str(out / 'mem_cells.jsonl'))) == 9


def test_the_fake_runner_does_not_outlive_the_p6_run_tests():
    """The two tests above leave no `eval_runner` in sys.modules and no fake directory on sys.path (the order
    test_memwatch, then test_p6_view failed on this at fdd77ab)."""
    leaked = sys.modules.get('eval_runner')
    assert leaked is None or 'codeB' not in os.path.dirname(os.path.realpath(leaked.__file__))
    assert not [p for p in sys.path if 'codeB' in p]
