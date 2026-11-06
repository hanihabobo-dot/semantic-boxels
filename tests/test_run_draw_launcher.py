"""BF#68: run.ps1's -Draw, through the launcher's own -DryRun (it prints the
command instead of running it, so nothing starts).

  run tampura -Draw boxels   the driver gets `--draw boxels`
  without -Draw              no `--draw` anywhere: the command is the stable
                             base's
  -Headless / run boxels     the flag is dropped with a note
  a kind it does not know    exit 2 and no command
  -D, -Dr                    still mean -DryRun (adding -Draw made them
                             ambiguous; the aliases on -DryRun keep them)

All calls share one PowerShell 7 call through WSL's interop (pwsh.exe, with
-NoProfile) and skip without it, like tests/test_run_launcher.py (TB-16).
Every call names -DryRun or an abbreviation that is only ever an alias of it
or an error: none of them can start a run.
"""
import platform
import re
import shutil
import subprocess
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
    'plain': 'tampura -Seed 0 -DryRun',
    'draw': 'tampura -Seed 0 -Draw boxels -DryRun',
    'case': 'tampura -Seed 0 -Draw Boxels,boxels -DryRun',
    'headless': 'tampura -Seed 0 -Draw boxels -Headless -DryRun',
    'boxels': 'boxels -Seed 3 -Draw boxels -DryRun',
    'bad': 'tampura -Seed 0 -Draw boxles -DryRun',
    'gen': 'tampura -Seed 106 -Gen -Draw boxels -DryRun',
    'list': 'tampura -Seed 7,8 -Draw boxels -DryRun',
    'dr': 'tampura -Seed 0 -Dr',
    'd': 'tampura -Seed 0 -D',
    'dry': 'tampura -Seed 0 -Dry',
}


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
    return [ln for ln in text.splitlines() if '--global-seed' in ln or 'test_full_pipeline' in ln]


@needs_pwsh
def test_without_draw_the_command_has_no_draw_flag(out):
    assert _commands(out['plain']) and '--draw' not in out['plain'], out['plain']


@needs_pwsh
def test_draw_boxels_reaches_the_driver_and_only_there(out):
    (cmd,) = _commands(out['draw'])
    assert cmd.endswith(' --draw boxels') and '--vis 1' in cmd, cmd
    # the base command and the drawing one differ by that flag alone
    (base,) = _commands(out['plain'])
    stamp = re.compile(r'(watch|headless)_s\d+_[\d_-]+')
    assert stamp.sub('X', cmd.replace(' --draw boxels', '')) == stamp.sub('X', base)


@needs_pwsh
def test_case_and_repeats_are_normalised(out):
    (cmd,) = _commands(out['case'])
    assert cmd.count('--draw') == 1 and cmd.endswith(' --draw boxels'), cmd


@needs_pwsh
def test_a_seed_list_and_a_generated_scene_carry_it_too(out):
    assert len(_commands(out['list'])) == 2
    assert all(c.endswith(' --draw boxels') for c in _commands(out['list']))
    assert '--draw boxels' in out['gen'] and 'BRIDGE_SCENE_MANIFEST' in out['gen']


@needs_pwsh
def test_headless_and_run_boxels_drop_it_with_a_note(out):
    assert '--draw' not in out['headless'] and 'ignored with -Headless' in out['headless']
    assert _commands(out['headless'])
    assert '--draw' not in out['boxels'] and 'draws its boxels in the GUI' in out['boxels']
    assert _commands(out['boxels'])


@needs_pwsh
def test_an_unknown_kind_exits_2_and_prints_no_command(out):
    assert 'exit=2' in out['bad'] and 'boxles' in out['bad'], out['bad']
    assert not _commands(out['bad'])


@needs_pwsh
def test_the_dry_run_abbreviations_still_work(out):
    for name in ('dr', 'd', 'dry'):
        assert _commands(out[name]) and 'exit=0' in out[name], (name, out[name])
