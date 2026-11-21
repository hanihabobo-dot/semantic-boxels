"""run.ps1's `wumpus` target (path 4), through the launcher's own -DryRun (it
prints the command instead of running it, so nothing starts), and what
tools/run_procs.sh makes of a wumpus run.

  run wumpus -Seed 3 -Size 10 -Headless   cd to this checkout, run_wumpus.py with
                                          --size 10 --seed 3 --vis 0, saved in
                                          tracks/wumpus/runs/wumpus_headless_n10_s3_<stamp>
  run wumpus -Seed [3, 4]                 one command per seed, in the GUI, size 5
  run wumpus -Draw boxels                 the flag is dropped with the wumpus note
  run help                                the header, down to its 'run help' line
  run ps, kill-mine                       a run_wumpus.py is listed as 'wumpus N=10
                                          seed 3, headless' and ended by the text of
                                          its save folder

The launcher calls share one PowerShell 7 call through WSL's interop
(pwsh.exe, with -NoProfile) and skip without it, like
tests/test_run_draw_launcher.py; each names -DryRun or help, so none of them
can start a run.  The run_procs.sh test starts a stand-in run_wumpus.py (a
sleep) and ends it by its own text, as tests/test_draw_equiv_run.py does.
"""
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_PS1 = ROOT / 'run.ps1'

_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None
needs_pwsh = pytest.mark.skipif(
    _PWSH is None, reason='needs pwsh.exe through WSL interop and a checkout '
                          'on a Windows drive')

CALLS = {
    'headless': 'wumpus -Seed 3 -Size 10 -Headless -DryRun',
    'list': 'wumpus -Seed [3, 4] -DryRun',
    'draw': 'wumpus -Seed 3 -Draw boxels -DryRun',
    'help': 'help',
}
STAMP = r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}'     # run.ps1's Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'


@pytest.fixture(scope='module')
def out():
    win = subprocess.run(['wslpath', '-w', str(RUN_PS1)], capture_output=True,
                         text=True, check=True).stdout.strip()
    script = '; '.join(
        f"$global:LASTEXITCODE = 0; & '{win}' {args} *>&1 | Out-String; "
        f"\"exit=$LASTEXITCODE\"; '@@{name}'"
        for name, args in CALLS.items())
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    parts = re.split(r'@@(\w+)', proc.stdout)      # text, name, text, name ...
    return {name: parts[i] for i, name in zip(range(0, len(parts) - 1, 2),
                                              parts[1::2])} | {'raw': proc.stdout}


def _commands(text):
    return [ln.strip() for ln in text.splitlines() if 'run_wumpus.py' in ln]


def _own(cmd):
    """The run's own command.  Since TB-17 the launcher's line is
    `export SB_RUN=1; ...; exec flock $L bash -c '<the run's command>'` (the
    run waits for the pipeline lock, rule 7), as in
    tests/test_run_draw_launcher.py; before TB-17 the line was the command."""
    m = re.search(r"; exec flock \$L bash -c '(.*)'$", cmd)
    return m.group(1).replace("'\\''", "'") if m else cmd


@needs_pwsh
def test_a_headless_run_names_this_checkout_its_size_seed_and_folder(out):
    (cmd,) = _commands(out['headless'])
    assert _own(cmd).startswith(f'cd {ROOT} && '), cmd
    assert ' --size 10 --seed 3 --vis 0 ' in cmd, cmd
    runs = re.escape(f'{ROOT}/archive/tampura_bridge_plan_2026-10-25/tracks/wumpus/runs/')
    assert re.search(rf' --save-dir {runs}wumpus_headless_n10_s3_{STAMP}$', _own(cmd)), cmd
    assert 'exit=0' in out['headless']


@needs_pwsh
def test_a_seed_list_gives_one_gui_command_per_seed(out):
    cmds = _commands(out['list'])
    assert len(cmds) == 2, out['list']
    for seed, cmd in zip((3, 4), cmds):
        assert f' --size 5 --seed {seed} --vis 1 ' in cmd, cmd
        assert re.search(rf'/wumpus_watch_n5_s{seed}_{STAMP}$', _own(cmd)), cmd


@needs_pwsh
def test_draw_is_dropped_with_the_wumpus_note(out):
    assert len(_commands(out['draw'])) == 1, out['draw']
    assert '--draw' not in out['draw'], out['draw']
    assert 'run wumpus paints what the robot knows' in out['draw'], out['draw']
    assert 'draws its boxels' not in out['draw'], out['draw']
    assert 'exit=0' in out['draw']


@needs_pwsh
def test_help_prints_the_header_down_to_its_run_help_line(out):
    lines = [ln.strip() for ln in out['help'].splitlines() if ln.strip()]
    assert lines[-1] == 'exit=0', lines[-3:]
    assert lines[-2].startswith('run help'), lines[-3:]
    assert lines[0].startswith('run: the pipeline in one word'), lines[0]
    assert any(ln.startswith('run wumpus -Seed 3') for ln in lines), lines
    assert any(ln.startswith('run tampura -Draw boxels') for ln in lines), lines


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='run_procs.sh reads /proc')
def test_run_procs_lists_and_ends_a_wumpus_run(tmp_path):
    # run.ps1 feeds the file to bash through tr -d '\r'
    with open(ROOT / 'tools' / 'run_procs.sh', encoding='utf-8') as f:
        procs = f.read().replace('\r', '')
    script = tmp_path / 'run_wumpus.py'
    script.write_text('import time\ntime.sleep(120)\n')
    p = subprocess.Popen([sys.executable, str(script), '--size', '10', '--seed', '3', '--vis', '0',
                          '--save-dir', str(tmp_path / 'wumpus_headless_n10_s3_OUTW')])
    try:
        def run_procs(*args):
            return subprocess.run(['bash', '-s', '--', *args], input=procs,
                                  capture_output=True, text=True, timeout=60).stdout
        line = ''
        for _ in range(50):
            mine = [ln for ln in run_procs('list').splitlines() if ln.startswith(f'pid {p.pid} ')]
            if mine:
                line = mine[0]
                break
            time.sleep(0.2)
        assert line.endswith('wumpus N=10 seed 3, headless'), line
        run_procs('kill-mine', 'OUTW', '100')
        assert p.wait(timeout=20) is not None
    finally:
        if p.poll() is None:
            p.kill()
