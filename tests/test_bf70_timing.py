"""BF#70's timing check for a cluster node: tools/cluster/rusage_run.py (one command, its cost as
JSON) and tools/cluster/bf70_timing.sbatch (text only).  No simulator, no TAMPURA."""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(REPO, 'tools', 'cluster')
if p not in sys.path:
    sys.path.insert(0, p)
import rusage_run as rr  # noqa: E402


def test_the_arguments_are_out_timeout_console_then_the_command():
    out, timeout_s, console, cmd = rr.split_argv(['o.json', '960', 'c.txt', '--', 'python', '-u', 'x.py', '--save-dir', 'd'])
    assert (out, timeout_s, console) == ('o.json', 960.0, 'c.txt')
    assert cmd == ['python', '-u', 'x.py', '--save-dir', 'd']
    for bad in (['o.json', '960', 'c.txt'], ['o.json', '960', '--', 'python'], ['o.json', '960', 'c.txt', '--']):
        with pytest.raises(SystemExit):
            rr.split_argv(bad)


def test_the_childs_share_is_the_difference_of_the_counters_and_the_peak_as_it_is():
    before = {'user_s': 1.0, 'sys_s': 0.5, 'max_rss_kb': 100, 'inblock': 10, 'oublock': 1, 'majflt': 2, 'minflt': 50}
    after = {'user_s': 113.63, 'sys_s': 28.84, 'max_rss_kb': 1212460, 'inblock': 2581235, 'oublock': 9, 'majflt': 2288,
             'minflt': 950}
    d = rr.usage_delta(before, after)
    assert d == {'user_s': 112.63, 'sys_s': 28.34, 'max_rss_kb': 1212460, 'inblock': 2581225, 'oublock': 8,
                 'majflt': 2286, 'minflt': 900}
    none = rr.usage_delta(None, None)
    assert set(none) == set(d) and all(v is None for v in none.values())


def test_a_command_is_run_its_output_kept_and_its_record_written(tmp_path):
    out, console = str(tmp_path / 'rusage.json'), str(tmp_path / 'console.txt')
    rec = rr.run(out, 60.0, console, [sys.executable, '-c', "import sys; print('hello'); sys.exit(3)"])
    on_disk = json.load(open(out))
    assert rec['rc'] == 3 and on_disk['rc'] == 3 and on_disk['timed_out'] is False
    assert open(console).read().strip() == 'hello'
    assert on_disk['wall_s'] >= 0 and on_disk['cmd'][0] == sys.executable
    for k in ('user_s', 'sys_s', 'max_rss_kb', 'inblock', 'majflt', 'load_start', 'memavailable_kb_start',
              'cached_kb_start', 'load_end', 'memavailable_kb_end', 'start', 'end', 'cwd', 'timeout_s'):
        assert k in on_disk
    if rr.resource is not None:                       # Linux: the kernel's accounting is there
        assert on_disk['max_rss_kb'] > 0 and on_disk['user_s'] >= 0


def test_a_command_past_the_timeout_is_ended_and_recorded(tmp_path):
    out, console = str(tmp_path / 'rusage.json'), str(tmp_path / 'console.txt')
    rec = rr.run(out, 0.5, console, [sys.executable, '-c', 'import time; time.sleep(60)'])
    assert rec['timed_out'] is True and rec['wall_s'] < 30 and json.load(open(out))['timed_out'] is True


def test_main_returns_0_whatever_the_command_returned(tmp_path, capsys):
    out, console = str(tmp_path / 'r.json'), str(tmp_path / 'c.txt')
    assert rr.main([out, '60', console, '--', sys.executable, '-c', 'import sys; sys.exit(7)']) == 0
    assert 'rc 7' in capsys.readouterr().out


def test_the_job_script_runs_the_declared_order_and_touches_nothing_else_on_the_volume():
    raw = open(os.path.join(REPO, 'tools', 'cluster', 'bf70_timing.sbatch'), 'rb').read()
    assert b'\r' not in raw
    text = raw.decode('utf-8')
    assert '#SBATCH --job-name=C-bf70-time' in text          # job names start with the worker's letter
    assert '--partition=rleap_cpu' in text and '--cpus-per-task=8' in text and '--mem=24G' in text
    assert 'PREPARED, NOT RUN' in text
    assert 'ORDER=${BF70_ORDER:-00_W 01_N 02_W 03_N 04_N 05_W 06_W 07_N}' in text
    # the episode: the harness's arm T line, the snapshot alone on PYTHONPATH, the hash seed fixed
    assert 'PYTHONPATH=$SNAP PYTHONHASHSEED=0' in text
    assert '$SNAP/tools/run_tampura_timed.py --config ./env_configs/find_dice.yml' in text
    assert '--planner tampura_policy_timed --global-seed $SEED --save-dir $D/save' in text
    assert '$VA/python -I -B $SNAP_W/tools/cluster/rusage_run.py $D/rusage.json $CAP $D/console.txt --' in text
    # N must be a snapshot without the wrapper, and both must hold the same scene file
    assert 'holds tampura_bridge/final_world.py, so it has the wrapper too: nothing run' in text
    assert 'cmp -s $SNAP_W/$SCENE $SNAP_N/$SCENE' in text
    # nothing on the volume but its own tarball: no prune, no gates, no kill by name
    code = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
    assert 'prune_work' not in code and 'bridge_gates' not in code
    assert 'pkill' not in text and 'killall' not in text and 'srun' not in text
    assert "--exclude='*.pkl'" in text and 'OUT=$LD/p4bf70_$JOB' in text
