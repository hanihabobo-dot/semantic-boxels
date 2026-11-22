"""Hani, 2026-11-22: run.ps1 and the page beside our own window (gui_page),
through the launcher's own -DryRun (it prints the commands and starts
nothing; as tests/test_run_draw_launcher.py does for -Draw):

  run boxels             a window run asks the pipeline for the page
                         (--gui-page on) and carries a word of its own
                         (SB_GUI_PAGE_TOKEN), by which the launcher finds
                         this run's page
  run boxels -Headless   no window, no page
  run boxels -NoPage     PyBullet's own window as it was
  run tampura, wumpus    never (TAMPURA's window has no panels to take off)

Opening the browser is not tested here: a dry run never reaches it, and a
real run would put a window on the desktop (tracks rule 13).
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
    'boxels': 'boxels -Seed 3 -DryRun',
    'again': 'boxels -Seed 3 -DryRun',
    'headless': 'boxels -Seed 3 -Headless -DryRun',
    'nopage': 'boxels -Seed 3 -NoPage -DryRun',
    'flags': "boxels -Seed 3 -Look boxel -Squeeze 1 -Args '--n-extra-distractors 1' -DryRun",
    'list': 'boxels -Seed 3,4 -DryRun',
    'tampura': 'tampura -Seed 0 -DryRun',
    'wumpus': 'wumpus -Seed 3 -DryRun',
    'help': 'help',
}
TOKEN = re.compile(r'export SB_GUI_PAGE_TOKEN=([0-9a-f]{12}); ')


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
    return {name: parts[i] for i, name in zip(range(0, len(parts) - 1, 2), parts[1::2])}


def _commands(text):
    return [ln for ln in text.splitlines()
            if 'test_full_pipeline' in ln or '--global-seed' in ln or 'run_wumpus' in ln]


def _own(cmd):
    """The run's own command inside the launcher's line (see
    tests/test_run_draw_launcher.py)."""
    m = re.search(r"; exec flock \$L bash -c '(.*)'$", cmd)
    return m.group(1).replace("'\\''", "'") if m else cmd


@needs_pwsh
def test_a_window_run_of_boxels_asks_for_the_page_and_carries_its_word(out):
    (cmd,) = _commands(out['boxels'])
    own = _own(cmd)
    assert TOKEN.search(own), own
    assert own.endswith('test_full_pipeline.py --scene random-pairs --seed 3 --goal holding '
                        '--n-occluders 2 --gui-page on'), own
    assert 'exit=0' in out['boxels']


@needs_pwsh
def test_every_run_has_a_word_of_its_own(out):
    words = [TOKEN.search(_own(c)).group(1)
             for name in ('boxels', 'again', 'list') for c in _commands(out[name])]
    assert len(words) == 4 and len(set(words)) == 4


@needs_pwsh
def test_without_the_page_the_command_is_the_one_before(out):
    """-NoPage and -Headless: no flag and no word; the window run's command
    is that command plus the two."""
    (plain,) = _commands(out['nopage'])
    assert '--gui-page' not in plain and 'SB_GUI_PAGE' not in plain
    assert _own(plain).endswith('test_full_pipeline.py --scene random-pairs --seed 3 --goal holding '
                                '--n-occluders 2')
    (paged,) = _commands(out['boxels'])
    assert TOKEN.sub('', paged).replace(' --gui-page on', '') == plain
    (headless,) = _commands(out['headless'])
    assert '--gui-page' not in headless and 'SB_GUI_PAGE' not in headless
    assert ' --no-gui ' in headless


@needs_pwsh
def test_the_flag_follows_the_runs_own_text_and_the_others_follow_it(out):
    """run kill finds a run by the text up to --n-occluders; the page's flag
    comes right after it and the other switches after that."""
    (cmd,) = _commands(out['flags'])
    assert _own(cmd).endswith('--n-occluders 2 --gui-page on --look boxel --grip-squeeze-mm 1 '
                              '--n-extra-distractors 1'), cmd


@needs_pwsh
def test_the_other_targets_never_ask_for_the_page(out):
    for name in ('tampura', 'wumpus'):
        assert _commands(out[name]), out[name]
        assert '--gui-page' not in out[name] and 'SB_GUI_PAGE' not in out[name]


@needs_pwsh
def test_the_help_text_names_the_switch_and_still_ends_at_run_help(out):
    text = out['help']
    assert 'run boxels -NoPage' in text and 'gui_page.py' in text
    assert 'prints the command instead of running it' in text      # the header's last line
    assert 'Every run takes the pipeline lock' not in text         # and not one line more


def test_the_launcher_and_the_page_know_the_same_ports_and_title():
    from console import gui_page
    ps = RUN_PS1.read_text(encoding='utf-8')
    first, last = map(int, re.search(r'^\$pagePorts = (\d+)\.\.(\d+)$', ps, re.M).groups())
    assert first == gui_page.DEFAULT_PORT and last == first + gui_page.PORT_TRIES - 1
    title = re.search(r"\$title = '([^']*)' \+ \(\[uri\]\$url\)\.Port \+ '([^']*)'", ps).groups()
    page = gui_page.Page(None, 0)
    try:
        assert page.title == f'{title[0]}{page.port}{title[1]}'
    finally:
        page.close()
    assert "/state" in ps and '.run.token' in ps and 'SB_GUI_PAGE_TOKEN' in ps


def test_the_page_is_looked_for_only_where_a_run_has_one():
    """The launcher's loop looks for the page only for a run that carries a
    word, and a failure there never ends the loop."""
    ps = RUN_PS1.read_text(encoding='utf-8')
    assert '$pageWord = $r.Page' in ps
    loop = ps[ps.index('while (-not $p.HasExited)'):]
    block = loop[loop.index('if ($pageWord) {'):loop.index('if ($Headless -or $ended)')]
    assert 'try {' in block and 'catch { $pageWord = $null }' in block
    assert 'Find-Page $pageWord' in block and 'Open-Page $pageUrl' in block
