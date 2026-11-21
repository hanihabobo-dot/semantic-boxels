"""BF#68: run.ps1's -Draw, through the launcher's own -DryRun (it prints the
command instead of running it, so nothing starts).

  run tampura -Draw boxels   the driver gets `--draw boxels`
  run tampura -Draw cameras  `--draw cameras` (the camera window starts with a
                             real run, never with -DryRun); `boxels,cameras`
                             both, in the order typed
  -Draw boxels cameras       kinds with only spaces between them join like a
                             comma list does
  without -Draw              no `--draw` anywhere: the command is the stable
                             base's
  -Headless / run boxels     the flag is dropped with a note
  a kind it does not know    exit 2 and no command
  a dry run                  starts no camera window (no process names the dry
                             run's folder afterwards)
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
    'cameras': 'tampura -Seed 0 -Draw Cameras -DryRun',
    'both': 'tampura -Seed 0 -Draw boxels,cameras -DryRun',
    'cams_headless': 'tampura -Seed 0 -Draw cameras -Headless -DryRun',
    'cams_boxels_run': 'boxels -Seed 3 -Draw cameras -DryRun',
    'badmix': 'tampura -Seed 0 -Draw boxels,camras -DryRun',
    'spaced': 'tampura -Seed 0 -Draw boxels cameras -DryRun',
    'spaced_case': 'tampura -Seed 0 -Draw Cameras Boxels -DryRun',
    'help': 'help',
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
    # After the calls: every camera window process alive (a dry run must have
    # started none).  This pwsh itself is left out: its own command line names
    # camera_view.ps1 and holds every @@ marker above.
    script += ("; Get-CimInstance Win32_Process -Filter \"Name='pwsh.exe'\" | "
               "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like '*camera_view.ps1*' } | "
               "ForEach-Object { 'viewer: ' + $_.CommandLine }; '@@viewers'")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    parts = re.split(r'@@(\w+)', proc.stdout)      # text, name, text, name ...
    return {name: parts[i] for i, name in zip(range(0, len(parts) - 1, 2),
                                              parts[1::2])} | {'raw': proc.stdout}


def _commands(text):
    return [ln for ln in text.splitlines() if '--global-seed' in ln or 'test_full_pipeline' in ln]


def _own(cmd):
    """The run's own command.  Since TB-17 the launcher's line is
    `export SB_RUN=1; ...; exec flock $L bash -c '<the run's command>'` (the
    run waits for the pipeline lock, rule 7), so the driver's last flag is
    followed by the closing quote; before TB-17 the line was the command."""
    m = re.search(r"; exec flock \$L bash -c '(.*)'$", cmd)
    return m.group(1).replace("'\\''", "'") if m else cmd


@needs_pwsh
def test_without_draw_the_command_has_no_draw_flag(out):
    assert _commands(out['plain']) and '--draw' not in out['plain'], out['plain']


@needs_pwsh
def test_draw_boxels_reaches_the_driver_and_only_there(out):
    (cmd,) = _commands(out['draw'])
    assert _own(cmd).endswith(' --draw boxels') and '--vis 1' in cmd, cmd
    # the base command and the drawing one differ by that flag alone
    (base,) = _commands(out['plain'])
    stamp = re.compile(r'(watch|headless)_s\d+_[\d_-]+')
    assert stamp.sub('X', cmd.replace(' --draw boxels', '')) == stamp.sub('X', base)


@needs_pwsh
def test_case_and_repeats_are_normalised(out):
    (cmd,) = _commands(out['case'])
    assert cmd.count('--draw') == 1 and _own(cmd).endswith(' --draw boxels'), cmd


@needs_pwsh
def test_a_seed_list_and_a_generated_scene_carry_it_too(out):
    assert len(_commands(out['list'])) == 2
    assert all(_own(c).endswith(' --draw boxels') for c in _commands(out['list']))
    assert '--draw boxels' in out['gen'] and 'BRIDGE_SCENE_MANIFEST' in out['gen']


@needs_pwsh
def test_headless_and_run_boxels_drop_it_with_a_note(out):
    assert '--draw' not in out['headless'] and 'ignored with -Headless' in out['headless']
    assert _commands(out['headless'])
    assert '--draw' not in out['boxels'] and 'run boxels has its own display' in out['boxels']
    assert _commands(out['boxels'])


@needs_pwsh
def test_an_unknown_kind_exits_2_and_prints_no_command(out):
    assert 'exit=2' in out['bad'] and 'boxles' in out['bad'], out['bad']
    assert not _commands(out['bad'])
    # one bad kind in a list refuses the whole call and names the kinds there are
    assert 'exit=2' in out['badmix'] and 'camras' in out['badmix'], out['badmix']
    assert 'boxels, cameras' in out['badmix'] and not _commands(out['badmix'])


@needs_pwsh
def test_draw_cameras_reaches_the_driver_and_starts_no_window_in_a_dry_run(out):
    (cmd,) = _commands(out['cameras'])           # any case: Cameras
    assert _own(cmd).endswith(' --draw cameras') and '--vis 1' in cmd, cmd
    (both,) = _commands(out['both'])
    assert _own(both).endswith(' --draw boxels,cameras'), both
    assert 'exit=0' in out['cameras']


@needs_pwsh
def test_a_dry_run_starts_no_camera_window(out):
    # A hidden window prints nothing, so the check is on the processes: after
    # the calls, no pwsh runs camera_view.ps1 for a folder a dry run named.
    # (Other sessions' real runs name their own folders.)
    names = set(re.findall(r'(?:watch|headless)_s\d+_[\d_-]+', out['raw']))
    assert names, out['raw']
    viewers = [ln for ln in out['viewers'].splitlines() if ln.startswith('viewer:')]
    started = [ln for ln in viewers if any(n in ln for n in names)]
    assert not started, started


@needs_pwsh
def test_kinds_with_only_spaces_between_them_join_like_a_comma_list(out):
    for name in ('spaced', 'spaced_case'):
        (cmd,) = _commands(out[name])
        assert cmd.count('--draw') == 1, (name, cmd)
        assert _own(cmd).endswith((' --draw boxels,cameras', ' --draw cameras,boxels')), (name, cmd)
        assert ' boxels cameras' not in cmd and 'exit=0' in out[name], (name, out[name])
    assert _own(cmd).endswith(' --draw cameras,boxels')            # in the order typed (any case)


def test_the_launcher_and_the_policy_know_the_same_draw_kinds():
    ps = RUN_PS1.read_text(encoding='utf-8')
    py = (ROOT / 'tampura_bridge' / 'policy.py').read_text(encoding='utf-8')
    here = re.search(r"^\$drawKinds = (.+)$", ps, re.M).group(1)
    there = re.search(r"^DRAW_KINDS = \(([^)]*)\)", py, re.M).group(1)
    assert re.findall(r"'([^']+)'", here) == re.findall(r"'([^']+)'", there) != []


def test_the_camera_window_reads_the_folder_the_driver_writes():
    ps = RUN_PS1.read_text(encoding='utf-8')
    save = re.search(r'\$save = "\$S/(archive/[^"]*/gui_runs)/\$mine"', ps)
    cams = re.search(r'\$cameras = Join-Path \$PSScriptRoot "(archive/[^"]*/gui_runs)/\$mine/cameras"', ps)
    assert save and cams and save.group(1) == cams.group(1)
    # and the driver writes <save-dir>/cameras (pinned in tampura_bridge/tests/test_draw_cameras.py)
    driver = (ROOT / 'tampura_bridge' / 'run_bridge_on_finddice.py').read_text(encoding='utf-8')
    assert "os.path.join(config['save_dir'], 'cameras')" in driver


@needs_pwsh
def test_the_help_text_names_both_kinds_and_still_ends_at_run_help(out):
    text = out['help']
    assert 'run tampura -Draw boxels' in text and 'run tampura -Draw cameras' in text
    assert 'prints the command instead of running it' in text      # the header's last line
    assert 'Never two pipeline runs at once' not in text            # and not one line more


@needs_pwsh
def test_draw_cameras_is_dropped_like_boxels_without_a_gui_or_on_run_boxels(out):
    assert '--draw' not in out['cams_headless'] and 'ignored with -Headless' in out['cams_headless']
    assert _commands(out['cams_headless'])
    assert '--draw' not in out['cams_boxels_run'] and 'run boxels has its own display' in out['cams_boxels_run']
    assert _commands(out['cams_boxels_run'])


@needs_pwsh
def test_the_dry_run_abbreviations_still_work(out):
    for name in ('dr', 'd', 'dry'):
        assert _commands(out[name]) and 'exit=0' in out[name], (name, out[name])
