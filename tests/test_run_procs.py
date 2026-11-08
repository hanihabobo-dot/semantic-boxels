"""TB-17: `run kill` ends only what run.ps1 started.

run.ps1 exports SB_RUN in every run's command, so a run and its children
carry it in their environment.  tools/run_procs.sh `kill` ends the pipeline
processes that carry it and names the others without touching them (a
track's locked episode, a probe, path 5's run_planner.py); `ps` lists them
and what holds or waits for the pipeline lock.  The process tests start
their own dummy pythons under a pattern and a lock file of their own
(RUN_PROCS_PAT, RUN_PROCS_LOCK), so they never see a real run, and they end
only their own children.
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


def _token() -> str:
    return 'tb17' + uuid.uuid4().hex[:12]


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


# run.ps1's dry runs, through WSL's interop as in test_run_launcher.py.
_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None


@pytest.mark.skipif(_PWSH is None, reason='needs pwsh.exe through WSL '
                    'interop and a checkout on a Windows drive')
def test_a_dry_run_starts_with_the_marker():
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
    assert all(c.startswith('export SB_RUN=1; ') for c in cmds), cmds
