"""TB-17: `run kill` ends only what run.ps1 started.

run.ps1 exports SB_RUN in every run's command, so a run and its children
carry it in their environment.  tools/run_procs.sh `kill` ends the pipeline
processes that carry it and names the others without touching them (a
track's locked episode, a probe, path 5's run_planner.py); `ps` lists them
and what holds or waits for the pipeline lock.  The process tests start
their own dummy pythons under a pattern and a lock file of their own
(RUN_PROCS_PAT, RUN_PROCS_LOCK), so they never see a real run, and they end
only their own children.

TB-17's second part (Go, 2026-11-08): only a run that run started refuses a
new one (`busy`); every run takes the pipeline lock (rule 7) as `flock
<lock> bash -c '<run>'`, waits while a track's episode holds it and prints
`ps` meanwhile; `kill` and `kill-mine` also end a run that still waits.
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_PS1 = ROOT / 'run.ps1'
PROCS = ROOT / 'tools' / 'run_procs.sh'
MARK = "$cmd = 'export SB_RUN=1; ' + $cmd"

on_linux = pytest.mark.skipif(
    not Path('/proc/self/environ').exists() or shutil.which('pgrep') is None
    or shutil.which('flock') is None,
    reason='needs Linux /proc, pgrep and flock (WSL)')


def test_every_run_command_gets_the_marker_last():
    src = RUN_PS1.read_text()
    assert src.count(MARK) == 1
    new_run = src[src.index('function New-Run'):src.index('if ($DryRun)')]
    # After every branch that builds $cmd, so no target is left out.
    assert new_run.index(MARK) > new_run.rindex('$cmd = "')
    assert '"$PROCS ps"' in src           # run ps shows the locked jobs too
    assert '"$PROCS kill"' in src
    # The refusal counts run's own runs only; the lock wrapper comes before
    # the marker, so the marker still opens the command.
    assert '"$PROCS busy"' in src and '"$PROCS list"' not in src
    assert new_run.index('exec flock') < new_run.index(MARK)


def _token() -> str:
    return 'tb17' + uuid.uuid4().hex[:12]


def _env(marked: bool) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ('SB_RUN', 'RUN_PROCS_PAT', 'RUN_PROCS_LOCK')}
    if marked:
        env['SB_RUN'] = '1'
    return env


def _dummy(name: str, marked: bool, lock: Path = None) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if k != 'SB_RUN'}
    if marked:
        env['SB_RUN'] = '1'
    cmd = [sys.executable, '-c', 'import time;time.sleep(99)', name]
    if lock is not None:
        cmd = ['flock', str(lock)] + cmd
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def _procs(args, pattern: str, lock: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, RUN_PROCS_PAT=pattern, RUN_PROCS_LOCK=str(lock))
    env.pop('SB_RUN', None)
    return subprocess.run(['bash', str(PROCS)] + list(args), env=env,
                          capture_output=True, text=True, timeout=60)


def _end(*procs):
    """End this test's own children (and a flock's child) and reap them."""
    for p in procs:
        if p.poll() is None:
            kids = subprocess.run(['pgrep', '-P', str(p.pid)],
                                  capture_output=True, text=True).stdout.split()
            for k in kids:
                try:
                    os.kill(int(k), 9)
                except ProcessLookupError:
                    pass
            p.kill()
        p.wait(timeout=10)


def _line(out: str, pid: int) -> str:
    lines = [ln for ln in out.splitlines() if re.match(rf'^pid {pid}\s', ln)]
    assert len(lines) == 1, out
    return lines[0]


@on_linux
def test_list_says_which_process_run_started(tmp_path):
    t = _token()
    mine, other = _dummy(t + 'a', True), _dummy(t + 'b', False)
    try:
        time.sleep(0.5)
        out = _procs(['list'], t, tmp_path / 'lock').stdout
        assert 'not run' not in _line(out, mine.pid)
        assert ' run ' in _line(out, mine.pid)
        assert 'not run' in _line(out, other.pid)
    finally:
        _end(mine, other)


@on_linux
def test_kill_ends_what_run_started_and_names_the_rest(tmp_path):
    t = _token()
    mine, other = _dummy(t + 'a', True), _dummy(t + 'b', False)
    try:
        time.sleep(0.5)
        res = _procs(['kill'], t, tmp_path / 'lock')
        assert res.returncode == 0, res.stdout + res.stderr
        mine.wait(timeout=10)                     # ended (TERM)
        assert other.poll() is None, 'kill ended a process run did not start'
        assert f'ending pid {mine.pid}:' in res.stdout
        assert f'left alone, not started by run: pid {other.pid}:' in res.stdout
    finally:
        _end(mine, other)


@on_linux
def test_ps_shows_the_lock_holder_and_a_waiter_and_kill_leaves_them(tmp_path):
    t = _token()
    lock = tmp_path / 'lock'
    holder = _dummy(t + 'h', False, lock=lock)
    try:
        time.sleep(0.5)                           # flock holds it, the python runs
        waiter = subprocess.Popen(['flock', str(lock), 'true'])
        try:
            time.sleep(0.5)
            out = _procs(['ps'], t, lock).stdout
            assert 'under the pipeline lock' in out, out
            assert re.search(rf'holds the lock:\s.*{t}h', out), out
            assert re.search(rf'^pid {waiter.pid}\s.*waiting for the lock:',
                             out, re.M), out
            res = _procs(['kill'], t, lock)
            assert res.returncode == 0, res.stdout + res.stderr
            assert holder.poll() is None and waiter.poll() is None
            assert 'left alone, not started by run' in res.stdout
        finally:
            _end(holder)
            waiter.wait(timeout=10)               # takes the lock, runs true
    finally:
        _end(holder)


@on_linux
def test_busy_counts_only_what_run_started(tmp_path):
    t = _token()
    other = _dummy(t + 'b', False)
    try:
        time.sleep(0.5)
        assert _procs(['busy'], t, tmp_path / 'lock').stdout.strip() == ''
        mine = _dummy(t + 'a', True)
        try:
            time.sleep(0.5)
            out = _procs(['busy'], t, tmp_path / 'lock').stdout
            assert ' run ' in _line(out, mine.pid)
            assert f'pid {other.pid} ' not in out, out
        finally:
            _end(mine)
    finally:
        _end(other)


def _waiting_run(name: str, lock: Path) -> subprocess.Popen:
    """A run as run.ps1 starts it, still waiting for the lock: a flock that
    carries SB_RUN and names the run in its command line."""
    return subprocess.Popen(['flock', str(lock), sys.executable, '-c',
                             'import time;time.sleep(99)', name],
                            env=_env(True), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


@on_linux
def test_kill_ends_a_run_that_waits_for_the_lock_and_leaves_the_holder(tmp_path):
    t = _token()
    lock = tmp_path / 'lock'
    holder = _dummy(t + 'h', False, lock=lock)    # a track's locked episode
    waiter = None
    try:
        time.sleep(0.5)
        waiter = _waiting_run(t + 'w', lock)
        time.sleep(0.5)
        out = _procs(['ps'], t, lock).stdout
        assert re.search(rf'^pid {waiter.pid}\s+\S+ old\s+run\s+waiting for '
                         rf'the lock:', out, re.M), out
        assert re.search(rf'not run\s+holds the lock:\s.*{t}h', out), out
        assert _procs(['busy'], t, lock).stdout.strip() == ''
        res = _procs(['kill'], t, lock)
        assert res.returncode == 0, res.stdout + res.stderr
        waiter.wait(timeout=10)
        assert holder.poll() is None, 'kill ended the lock holder run did not start'
        assert (f'ending pid {waiter.pid}: ' in res.stdout
                and '(its flock on the pipeline lock)' in res.stdout), res.stdout
    finally:
        _end(*[p for p in (waiter, holder) if p is not None])


@on_linux
def test_kill_mine_ends_a_waiting_run_by_its_text(tmp_path):
    t = _token()
    lock = tmp_path / 'lock'
    holder = _dummy(t + 'h', False, lock=lock)
    waiter = None
    try:
        time.sleep(0.5)
        waiter = _waiting_run(t + 'w', lock)
        time.sleep(0.5)
        res = _procs(['kill-mine', t + 'w', '600'], t, lock)
        assert res.returncode == 0, res.stdout + res.stderr
        waiter.wait(timeout=10)
        assert holder.poll() is None
    finally:
        _end(*[p for p in (waiter, holder) if p is not None])


# run.ps1's dry runs, through WSL's interop as in test_run_launcher.py.
_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason='needs pwsh.exe '
                                'through WSL interop and a checkout on a '
                                'Windows drive')


@pytest.fixture(scope='module')
def dry_runs():
    """One pwsh.exe call (it starts slowly): a -Gen tampura and a boxels dry run."""
    win = subprocess.run(['wslpath', '-w', str(RUN_PS1)], capture_output=True,
                         text=True, check=True).stdout.strip()
    script = (f"& '{win}' tampura -Seed 118 -Gen -Headless -Music -DryRun; "
              f"& '{win}' boxels -Seed 3 -Headless -DryRun")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command',
                           script], capture_output=True, text=True,
                          timeout=180, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    cmds = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(cmds) == 2, proc.stdout
    return cmds


@needs_pwsh
def test_a_dry_run_starts_with_the_marker(dry_runs):
    assert all(c.startswith('export SB_RUN=1; ') for c in dry_runs), dry_runs
    # The run goes under the lock, its own command line on the flock, and no
    # double quote reaches wsl.exe's command line.
    for c in dry_runs:
        assert re.search(r"; exec flock \$L bash -c '.*'$", c), c
        assert '"' not in c, c


def _wrapped(dry_run: str, payload: str) -> str:
    """The dry run's command with the run inside the lock replaced."""
    out, n = re.subn(r"exec flock \$L bash -c '.*'$",
                     lambda m: f"exec flock $L bash -c '{payload}'", dry_run)
    assert n == 1, dry_run
    return out


@needs_pwsh
@on_linux
def test_a_run_waits_for_the_lock_and_says_who_holds_it(tmp_path, dry_runs):
    """The dry run's own wrapper, its run swapped for an echo, under a test
    lock: free, it runs at once and silently; held by a track's episode, it
    prints who holds it, waits, and runs when the lock is free."""
    boxels = dry_runs[1]
    t = _token()
    lock = tmp_path / 'lock'
    env = dict(_env(False), RUN_PROCS_LOCK=str(lock))
    cmd = _wrapped(boxels, 'echo RAN-$SB_RUN')
    free = subprocess.run(['bash', '-c', cmd], env=env, capture_output=True,
                          text=True, timeout=60)
    assert free.returncode == 0, free.stdout + free.stderr
    assert free.stdout.strip() == 'RAN-1', free.stdout
    holder = _dummy(t + 'h', False, lock=lock)
    run = None
    try:
        time.sleep(0.5)
        run = subprocess.Popen(['bash', '-c', cmd], env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(2.0)
        assert run.poll() is None, 'the run did not wait for the lock'
        _end(holder)
        out, _ = run.communicate(timeout=30)
        assert run.returncode == 0, out
        assert out.index('run: waiting for the pipeline lock') < out.index('RAN-1'), out
        assert re.search(rf'holds the lock:\s.*{t}h', out), out
    finally:
        _end(*[p for p in (run, holder) if p is not None])
