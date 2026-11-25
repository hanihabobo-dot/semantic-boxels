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
  -NoPage, -LoosePage    where a run has no page they change nothing, and
                         the launcher says so

Opening the browser is not tested here: a dry run never reaches it, and a
real run would put a window on the desktop (tracks rule 13).  Whether a
page's window is open already is asked of all windows (read only).
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
    'tampura_switches': 'tampura -Seed 0 -NoPage -LoosePage -DryRun',
    'headless_loose': 'boxels -Seed 3 -Headless -LoosePage -DryRun',
    'loose': 'boxels -Seed 3 -LoosePage -DryRun',
    'help': 'help',
}
TOKEN = re.compile(r'export SB_GUI_PAGE_TOKEN=([0-9a-f]{12}); ')
# The split of the screen (Hani, 2026-11-25): a run whose page is held is also asked for a window
# of the size measured, in front of the word (tests/test_page_split.py holds that); none where
# this machine's screen is too small for a split.
WINDOW = re.compile(r'export SB_GUI_WINDOW=\d+x\d+; ')


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
    """-NoPage and -Headless: no flag, no word and no window size; the
    window run's command is that command plus the word, the flag and, for
    the split of the screen, at most one window size."""
    (plain,) = _commands(out['nopage'])
    assert '--gui-page' not in plain and 'SB_GUI_' not in plain
    assert _own(plain).endswith('test_full_pipeline.py --scene random-pairs --seed 3 --goal holding '
                                '--n-occluders 2')
    (paged,) = _commands(out['boxels'])
    assert len(WINDOW.findall(paged)) <= 1
    assert TOKEN.sub('', WINDOW.sub('', paged)).replace(' --gui-page on', '') == plain
    (headless,) = _commands(out['headless'])
    assert '--gui-page' not in headless and 'SB_GUI_' not in headless
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
        assert '--gui-page' not in out[name] and 'SB_GUI_' not in out[name]


@needs_pwsh
def test_the_pages_switches_say_so_where_a_run_has_no_page(out):
    """-NoPage and -LoosePage with a run that has no page (tampura, wumpus,
    -Headless): one line, as -Draw has it for run boxels, and the command is
    the one without the switch."""
    said = [ln for ln in out['tampura_switches'].splitlines() if ln.startswith('run: ')]
    assert said == ['run: -NoPage and -LoosePage ignored: only a window run of boxels has the page '
                    'beside its window (run tampura has none)']
    strip = lambda text: [re.sub(r'_\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d', '', c) for c in _commands(text)]
    assert strip(out['tampura_switches']) == strip(out['tampura'])
    said = [ln for ln in out['headless_loose'].splitlines() if ln.startswith('run: ')]
    assert said == ['run: -LoosePage ignored: only a window run of boxels has the page beside its '
                    'window (this run has no window)']
    assert _commands(out['headless_loose']) == _commands(out['headless'])
    # and where the run has a page, or -NoPage takes it away, nothing is said
    for name in ('boxels', 'nopage', 'loose'):
        assert not [ln for ln in out[name].splitlines() if ln.startswith('run: ')], out[name]


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


def test_the_ports_are_asked_no_more_once_the_window_has_stood_without_a_page():
    """A run whose window has been open for 20 s and whose page never
    answered has none: the launcher stops asking the ten ports, which slows
    its watch of the window (BF#51)."""
    ps = RUN_PS1.read_text(encoding='utf-8')
    loop = ps[ps.index('while (-not $p.HasExited)'):]
    assert 'if ($open -gt 0) { $seen = $true; if (-not $seenAt) { $seenAt = Get-Date } }' in loop
    stop = loop.index('if ($pageWord -and $seenAt -and ((Get-Date) - $seenAt).TotalSeconds -ge 20) {')
    assert stop < loop.index('if ($pageWord) {')
    assert '$pageWord = $null' in loop[stop:loop.index('if ($pageWord) {')]


def test_nothing_is_written_to_the_console_while_the_run_draws_in_it():
    """The run's console redraws its live rows ten times a second by going up
    from where the cursor stands and clearing to the end of the screen
    (console_screen.py).  A line the launcher writes in between is wiped at
    once and leaves stale rows of the block above it (review r4, post-review
    finding A).  So the launcher's loop writes nothing, and neither does a
    function of the launcher that the loop calls (Open-Page wrote one line
    itself when no browser started: the third read's finding 5): what there
    is to say (the page was not held, the camera window ended at once, the
    page did not open) is kept and said in the finally, after the run."""
    ps = RUN_PS1.read_text(encoding='utf-8')
    start = ps.index('while (-not $p.HasExited) {')
    loop = ps[start:ps.index('} finally {', start)]
    writers = ('Write-Host', '[Console]::', 'Write-Output', 'Write-Warning', 'Write-Error', 'Write-Information')
    for writer in writers:
        assert writer not in loop, writer
    assert loop.count('$late.Add(') == 3
    assert 'the camera window ended at once' in loop and 'the page was not held against the window' in loop
    # the launcher's own functions that the loop reaches, through one another too
    names = re.findall(r'^function ([\w-]+)\(', ps, re.M)

    def body(name):
        at = ps.index('function %s(' % name)
        return ps[at:ps.index('\n}\n', at)]

    reached, texts = set(), [loop]
    while texts:
        text = texts.pop()
        for name in names:
            if name not in reached and re.search(r'(?<![\w-])%s(?![\w-])' % re.escape(name), text):
                reached.add(name)
                texts.append(body(name))
    assert reached == {'Find-Page', 'Open-Page', 'Test-PageShown'}
    for name in sorted(reached):
        for writer in writers:
            assert writer not in body(name), (name, writer)
    # Open-Page's one sentence is handed back and kept
    assert 'return "run: the page did not open (' in body('Open-Page')
    assert '$said = Open-Page $pageUrl ([bool]$holder)' in loop and 'if ($said) { $late.Add("$said") }' in loop
    closing = ps[ps.index('} finally {', start):ps.index('$code = $p.ExitCode', start)]
    assert 'foreach ($line in $late) { [Console]::Out.WriteLine(' in closing
    # the console's way of redrawing, which this rests on
    screen = (ROOT / 'console' / 'console_screen.py').read_text(encoding='utf-8')
    assert "\\033[{live['drawn']}A\\033[1G\\033[J" in screen
    assert re.search(r'^FRAME_S = 0\.1\b', screen, re.M)


def _function(name):
    """One function of run.ps1 as text, with the checkout's folder in place of
    $PSScriptRoot (which a function typed into a shell does not have)."""
    ps = RUN_PS1.read_text(encoding='utf-8')
    start = ps.index('function %s(' % name)
    end = ps.index('\n}\n', start) + 3
    win = subprocess.run(['wslpath', '-w', str(ROOT)], capture_output=True, text=True, check=True).stdout.strip()
    return ps[start:end].replace('$PSScriptRoot', "'%s'" % win)


def test_a_page_window_left_open_is_looked_for_among_all_windows():
    """Open-Page opens no second window for a page that is open.  A browser
    is one process with many windows, so a process's main window does not
    tell (review r4): the windows are looked through as the holder does it.
    For the holder only a window of the page's own counts; without Edge a
    tab that shows the page counts too, so that tabs do not pile up."""
    ps = RUN_PS1.read_text(encoding='utf-8')
    opener = ps[ps.index('function Open-Page('):ps.index('if ($DryRun) {')]
    assert 'MainWindowTitle' not in opener
    assert 'if (Test-PageShown $title $own) { return }' in opener
    assert opener.index('Start-Process -FilePath $edge') < opener.index(
        'if ($own -and (Test-PageShown $title $false)) { return }') < opener.index('Start-Process $url')
    shown = ps[ps.index('function Test-PageShown('):ps.index('function Open-Page(')]
    assert "Add-Type -Path (Join-Path $PSScriptRoot 'tools/page_dock.cs')" in shown
    assert "[PageDock]::WholeTitle = $whole" in shown and "[PageDock]::FindPage($title, '') -ne 0" in shown
    assert 'catch { return $false }' in shown
    assert 'Open-Page $pageUrl ([bool]$holder)' in ps


@needs_pwsh
def test_open_page_hands_its_sentence_back_and_writes_nothing():
    """Open-Page itself, with stand-ins for what it calls, so that no browser
    starts and no window opens: when neither Edge nor a default browser
    starts, the one sentence is what it gives back and nothing reaches the
    console (all streams are read); when a browser starts it gives nothing
    back."""
    script = (
        "function Test-PageShown { $false }; "
        "function Get-ItemProperty { throw 'no Edge here' }; "
        "function Start-Process { if ($script:starts) { $script:asked = \"$args\" } else { throw 'no browser here' } }; "
        + _function('Open-Page') +
        "; $script:starts = $false; $a = Open-Page 'http://127.0.0.1:8765/' $true; \"none=[$a]\""
        "; $script:starts = $true; $b = Open-Page 'http://127.0.0.1:8765/' $true; \"some=[$b] asked=[$script:asked]\"")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ''
    assert proc.stdout.splitlines() == [
        'none=[run: the page did not open (no browser here); it is at http://127.0.0.1:8765/]',
        'some=[] asked=[http://127.0.0.1:8765/]']


@needs_pwsh
def test_no_window_carries_a_title_nobody_gave():
    """Test-PageShown itself, on the real list of windows (read only): no
    window is named like a page of a port no page has."""
    script = (_function('Test-PageShown') +
              "; 'whole=' + (Test-PageShown 'Semantic Boxels (page 1)' $true)"
              "; 'start=' + (Test-PageShown 'Semantic Boxels (page 1)' $false)")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    assert 'whole=False' in proc.stdout and 'start=False' in proc.stdout, proc.stdout + proc.stderr
