"""Hani, 2026-11-22: "can you make them stick together and look like one
window and move together?"  The holder of the page beside our own window
(tools/page_dock.ps1, tools/page_dock.cs), as far as it can be tested
without a window on the desktop (tracks rule 13):

  the arithmetic   PageDock.Place, compiled and called through pwsh.exe: where
                   the page's window goes for a simulator window at the left
                   edge, in the middle, at the right edge, as wide as the
                   screen, and that the page keeps its side while it serves
  which window     PageDock.Choose, the same way: which of the simulator
                   windows open is this run's, and when it takes none
  what it touches  the Windows calls the source names: it places, shows and
                   cuts a window and reads; nothing is sent to a program
  the names        the windows it looks for are the ones the page and
                   PyBullet open, and the ones the launcher watches
  the launcher     run boxels starts it for a run with the page and gives it
                   a log, -LoosePage leaves it out, and it changes nothing of
                   the run's command
  its ends         the real script without a page to find: the run gone, no
                   run to watch, a parameter it cannot read (the log says so)

Holding two real windows together is tried on a desktop that is not shown
(tracks/dbgcams/checks/dock_trial.ps1); how the pair looks, and how the real
simulator window behaves, only a look at a real run can say.
"""
import platform
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_PS1 = ROOT / 'run.ps1'
DOCK_PS1 = ROOT / 'tools' / 'page_dock.ps1'
DOCK_CS = ROOT / 'tools' / 'page_dock.cs'

_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None
needs_pwsh = pytest.mark.skipif(
    _PWSH is None, reason='needs pwsh.exe through WSL interop and a checkout '
                          'on a Windows drive')

RIGHT, LEFT, OVER_RIGHT, OVER_LEFT = 1, 2, 3, 4
WORK = (0, 0, 1920, 1008)               # a 1920x1080 screen without its taskbar
MARGINS = (11, 45, 14, 14)              # the page inside its browser window, as the trial measured it
WANT, MIN = 600, 360                    # 400 and 240 at 150 % scaling

# name: (the simulator's window, the page's margins, the side it is on, then what is expected:
#        side, width, the page's whole window, the cut inside it)
CASES = {
    'room on the right':
        ((0, 40, 1296, 800), MARGINS, 0, RIGHT, 600, (1285, -5, 1910, 814), (11, 45, 611, 805)),
    'less room on the right than wanted':
        ((200, 100, 1496, 860), MARGINS, 0, RIGHT, 424, (1485, 55, 1934, 874), (11, 45, 435, 805)),
    'room on the left only':
        ((624, 40, 1920, 800), MARGINS, 0, LEFT, 600, (13, -5, 638, 814), (11, 45, 611, 805)),
    'too little room on both sides':
        ((300, 40, 1596, 800), MARGINS, 0, OVER_RIGHT, 360, (1549, -5, 1934, 814), (11, 45, 371, 805)),
    'too little room on both sides, coming from the left':
        ((300, 40, 1596, 800), MARGINS, LEFT, OVER_LEFT, 360, (-11, -5, 374, 814), (11, 45, 371, 805)),
    'the simulator as wide as the screen':
        ((0, 0, 1920, 1008), MARGINS, 0, OVER_RIGHT, 360, (1549, -45, 1934, 1022), (11, 45, 371, 1053)),
    'on the left while the left serves, though the right has room too':
        ((500, 40, 1400, 800), MARGINS, LEFT, LEFT, 500, (-11, -5, 514, 814), (11, 45, 511, 805)),
    'on the right while the right serves, though the left has more room':
        ((700, 40, 1520, 800), MARGINS, RIGHT, RIGHT, 400, (1509, -5, 1934, 814), (11, 45, 411, 805)),
    'a window without a page found inside it is not cut':
        ((0, 40, 1296, 800), (0, 0, 0, 0), 0, RIGHT, 600, (1296, 40, 1896, 800), (0, 0, 600, 760)),
}


# name: (the simulator windows open now, the topmost first; the ones open at the holder's kept
#        look; whether the run has drawn its window; the window taken, 0 none yet, -1 it cannot tell)
CHOICES = {
    'one opened since the look':
        ((7, 3), (3,), False, 7),
    'the topmost of two that opened since':
        ((9, 7, 3), (3,), False, 9),
    'none opened since and the run has not drawn its window: none yet':
        ((3,), (3,), False, 0),
    'none opened since, the run has drawn its window, one is open: that one':
        ((3,), (3,), True, 3),
    'none opened since, the run has drawn its window, two are open: it cannot tell':
        ((3, 4), (3, 4), True, -1),
    'one that opened since is taken whatever else is open':
        ((5, 3, 4), (3, 4), True, 5),
    'no simulator window at all':
        ((), (), True, 0),
}


def _win(path):
    return subprocess.run(['wslpath', '-w', str(path)], capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture(scope='module')
def placed():
    """Every case through the compiled PageDock.Place, in one pwsh call."""
    lines = ["$ErrorActionPreference = 'Stop'",
             f"Add-Type -Path '{_win(DOCK_CS)}' -IgnoreWarnings",
             # (not named R: that is PowerShell's own short name for Invoke-History)
             "function New-Rect($l, $t, $r, $b) { $x = New-Object PageDock+RECT; "
             "$x.L = $l; $x.T = $t; $x.R = $r; $x.B = $b; $x }",
             "$work = New-Rect %d %d %d %d" % WORK,
             "'consts|' + [PageDock]::Right + '|' + [PageDock]::Left + '|' + "
             "[PageDock]::OverRight + '|' + [PageDock]::OverLeft"]
    for i, (sim, m, side_now, *_expected) in enumerate(CASES.values()):
        lines.append(
            "$p = [PageDock]::Place((New-Rect %d %d %d %d), $work, %d, %d, %d, %d, %d, %d, %d); "
            "'%d|' + $p.Side + '|' + $p.Width + '|' + $p.Window + '|' + $p.Region"
            % (*sim, *m, WANT, MIN, side_now, i))
    for i, (now, before, drawn, _taken) in enumerate(CHOICES.values()):
        lines.append("'choose%d|' + [PageDock]::Choose([long[]]@(%s), [long[]]@(%s), $%s)"
                     % (i, ', '.join(map(str, now)), ', '.join(map(str, before)), str(drawn).lower()))
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', '\n'.join(lines)],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    rows = [ln.strip().split('|') for ln in proc.stdout.splitlines() if '|' in ln]
    return {row[0]: row[1:] for row in rows}


@needs_pwsh
def test_the_sides_have_the_numbers_this_file_uses(placed):
    assert placed['consts'] == [str(RIGHT), str(LEFT), str(OVER_RIGHT), str(OVER_LEFT)]


@needs_pwsh
@pytest.mark.parametrize('name', list(CASES))
def test_where_the_page_goes(placed, name):
    sim, margins, _side_now, side, width, window, cut = CASES[name]
    got = placed[str(list(CASES).index(name))]
    assert got == [str(side), str(width), ','.join(map(str, window)), ','.join(map(str, cut))], name
    # what is seen of the page: the cut, on the screen
    seen = (window[0] + cut[0], window[1] + cut[1], window[0] + cut[2], window[1] + cut[3])
    assert (seen[1], seen[3]) == (sim[1], sim[3]), 'the simulator\'s top and height'
    if side == RIGHT:
        assert seen[0] == sim[2], 'flush against its right edge'
    elif side == LEFT:
        assert seen[2] == sim[0], 'flush against its left edge'
    elif side == OVER_RIGHT:
        assert seen[2] == WORK[2] and seen[2] - seen[0] == MIN
    else:
        assert seen[0] == WORK[0] and seen[2] - seen[0] == MIN
    assert WORK[0] <= seen[0] and seen[2] <= WORK[2], 'what is seen stays on the screen'


@needs_pwsh
@pytest.mark.parametrize('name', list(CHOICES))
def test_which_simulator_window_is_this_runs(placed, name):
    """A window that opened since the holder's kept look is the run's.  With
    none, the holder may have looked late: only once the run has drawn its
    window is a window from before taken, and only when it is the one there
    is.  No waiting decides it (review r4: a window was taken after 20 s)."""
    assert placed['choose%d' % list(CHOICES).index(name)] == [str(CHOICES[name][3])], name
    cs = DOCK_CS.read_text(encoding='utf-8')
    assert 'OldAfterMs' not in cs and cs.count('Choose(sims, before, ') == 2


def test_the_holder_places_shows_and_cuts_a_window_and_sends_nothing():
    """The Windows calls the source names, all of them: reading windows,
    placing, showing and cutting one, the reports of Windows about the two
    programs' windows, the holder's own message loop and timer.  No call
    that sends a message, a key or a click to a program is among them."""
    names = set(re.findall(r'static extern [\w\[\]]+ (\w+)\(', DOCK_CS.read_text(encoding='utf-8')))
    assert names == {
        'EnumWindows', 'EnumChildWindows', 'IsWindow', 'IsWindowVisible', 'IsIconic', 'IsZoomed',
        'GetWindowText', 'GetClassName', 'GetWindowThreadProcessId', 'GetWindowRect',
        'GetWindowRgnBox', 'GetWindowPlacement', 'MonitorFromWindow', 'GetMonitorInfo',
        'GetDpiForWindow', 'DwmGetWindowAttribute', 'GetWindowLongPtr',
        'SetWindowPos', 'ShowWindow', 'SetWindowRgn', 'SetWindowPlacement',
        'CreateRectRgn', 'DeleteObject',
        'SetThreadDpiAwarenessContext', 'SetWinEventHook', 'UnhookWinEvent',
        'GetMessage', 'TranslateMessage', 'DispatchMessage', 'SetTimer', 'KillTimer',
        'PostQuitMessage'}


def _default(name):
    return re.search(r"\[string\]\$%s = '([^']*)'" % name, DOCK_PS1.read_text(encoding='utf-8')).group(1)


def test_the_holder_looks_for_the_windows_the_page_and_pybullet_open():
    from console import gui_page
    import pybullet
    page = gui_page.Page(None, 0)
    try:
        assert page.title.startswith(_default('PageTitle'))
    finally:
        page.close()
    # the simulator's title is PyBullet's own (it takes none from us): read from the library
    with open(pybullet.__file__, 'rb') as f:
        assert (_default('SimTitle') + ' ExampleBrowser').encode() in f.read()
    # and the launcher watches the same window of the same program
    ps = RUN_PS1.read_text(encoding='utf-8')
    assert f"Get-Process -Name {_default('SimProcess')} " in ps
    assert f"-like '*{_default('SimTitle')}*'" in ps


def test_the_launcher_starts_the_holder_for_a_run_with_the_page_and_never_ends_it():
    ps = RUN_PS1.read_text(encoding='utf-8')
    code = '\n'.join(ln for ln in ps.splitlines() if not ln.lstrip().startswith('#'))
    assert code.count('tools/page_dock.ps1') == 1
    start = code.index('if ($r.Page -and -not $LoosePage) {')
    block = code[start:code.index('if ($r.Cameras) {', start)]
    assert "'tools/page_dock.ps1'" in block and "'-WatchPid', $p.Id" in block
    # this run's word and the launcher's own ports: the holder takes this run's page and no other
    assert "'-PageWord', $r.Page, '-PortFrom', $pagePorts[0], '-PortTo', $pagePorts[-1]" in block
    assert '-WindowStyle Hidden' in block
    assert 'try {' in block and 'catch {' in block                           # a failure never touches the run
    assert code.index('$p = [System.Diagnostics.Process]::Start($psi)') < start
    # it writes a log the launcher can name (one file in the checkout's logs folder, which
    # git ignores), with every report of Windows about the two windows
    assert "'-Log', ('\"' + $holderLog + '\"'), '-Trace'" in block
    assert "$holderLog = Join-Path $PSScriptRoot 'logs\\page_dock.log'" in code
    assert 'logs/' in (ROOT / '.gitignore').read_text(encoding='utf-8').split()
    # the process is kept only to be asked whether it has ended; nothing here ends it
    assert '$holder = Start-Process' in block and '-PassThru' in block
    assert not re.search(r'(Stop-Process|taskkill|Kill\(\))[^\n]*holder', code)
    assert not re.search(r'\$holder\.(Kill|Close|CloseMainWindow)', code)


def test_the_launcher_says_so_when_the_holder_ends_while_the_run_goes_on():
    """A holder that has ended with anything but 0 (it held, the page's
    window was closed) or 2 (the run ended first) left a loose page: the
    launcher's loop says it once, with the holder's exit code and its log,
    and only while the run goes on."""
    ps = RUN_PS1.read_text(encoding='utf-8')
    loop = ps[ps.index('while (-not $p.HasExited)'):]
    block = loop[loop.index('if ($holder -and $holder.HasExited) {'):loop.index('if ($pageWord -and $seenAt')]
    assert 'if ($holder.ExitCode -notin 0, 2 -and -not $p.HasExited) {' in block
    assert 'Write-Host' in block and '$holder.ExitCode' in block and '$holderLog' in block
    assert block.rstrip().endswith('$holder = $null\n            }')       # said once
    # the codes it names are the holder's own
    cs = DOCK_CS.read_text(encoding='utf-8')
    for code in re.findall(r'^\s+(\d) \{ ', block, re.M):
        assert re.search(r'^\s+///\s+%s  ' % code, cs, re.M), code
    assert set(re.findall(r'^\s+(\d) \{ ', block, re.M)) == {'5', '6', '7'}
    assert 'return pick > 0 ? 7 : pick < 0 ? 5 : 6;' in cs


def test_the_holder_finds_this_runs_page_as_the_launcher_does_and_names_it_as_the_page_does():
    """With the run's word the holder asks the page servers for it (the
    launcher's Find-Page) and takes the window named by that server's port,
    in the page's own words; its ports are the page's."""
    from console import gui_page
    ps = DOCK_PS1.read_text(encoding='utf-8')
    assert '/state' in ps and '$state.run.token -eq $PageWord' in ps
    head, tail = re.search(r"\$PageTitle = '([^']*)' \+ \$port \+ '([^']*)'", ps).groups()
    page = gui_page.Page(None, 0)
    try:
        assert page.title == f'{head}{page.port}{tail}'
    finally:
        page.close()
    first = int(re.search(r'\[int\]\$PortFrom = (\d+)', ps).group(1))
    last = int(re.search(r'\[int\]\$PortTo = (\d+)', ps).group(1))
    assert (first, last) == (gui_page.DEFAULT_PORT, gui_page.DEFAULT_PORT + gui_page.PORT_TRIES - 1)
    # The simulator windows are looked at before every ask of the page servers, and the look
    # is kept when no page gave the word back: this run's window was not open at it, since
    # the run starts its page before it opens its window (tests/test_window_page.py pins that
    # order in the pipeline's entry).  A page that answers at the first ask: the look is kept
    # all the same and the run is asked whether it has drawn its window (PageDock.Choose).
    loop = ps[ps.index('while (-not $port) {'):ps.index("$PageTitle = 'Semantic Boxels (page ' + $port")]
    assert (loop.index('[PageDock]::Look($SimTitle, $SimProcess)') < loop.index('Invoke-RestMethod')
            < loop.index('if (-not $port) {') < loop.index('[PageDock]::Keep()')
            < loop.index('if (-not $kept) { [PageDock]::Keep() }'))
    assert ps.index('[PageDock]::RunWindowOpen = [Func[bool]] {') < ps.index('[PageDock]::Run(')
    asked = ps[ps.index('[PageDock]::RunWindowOpen = '):ps.index('}.GetNewClosure()')]
    assert '$stateUrl' in asked and ').camera' in asked and 'catch { $false }' in asked
    # and only a window whose WHOLE title is the page's is taken: a browser window with tabs
    # that shows the page ("... - Microsoft Edge") is a person's own and is never cut or moved
    assert ps.index("$PageTitle = '") < ps.index('[PageDock]::WholeTitle = $true') < ps.index('[PageDock]::Run(')
    cs = DOCK_CS.read_text(encoding='utf-8')
    assert 'WholeTitle ? t == titleStart : t.StartsWith(titleStart, StringComparison.Ordinal)' in cs


@needs_pwsh
def test_the_holder_ends_by_itself_when_no_page_gives_the_word_back():
    """The real script, up to the point where it would look for windows: a
    run that is gone (exit 2), and no run to watch and no page (exit 3).  It
    reads the list of windows and touches none."""
    win = _win(DOCK_PS1)
    script = ("$me = Join-Path $PSHOME 'pwsh.exe'; "
              f"& $me -NoProfile -File '{win}' -WatchPid 4194300 -PageWord nosuchword; \"gone=$LASTEXITCODE\"; "
              f"& $me -NoProfile -File '{win}' -WaitSeconds 1 -PageWord nosuchword -PortFrom 8799 -PortTo 8799; "
              "\"nopage=$LASTEXITCODE\"")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    assert 'gone=2' in proc.stdout and 'nopage=3' in proc.stdout, proc.stdout + proc.stderr


@needs_pwsh
def test_an_error_of_the_holder_is_in_its_log_and_in_its_exit_code(tmp_path):
    """The launcher starts the holder hidden, so what stops it must be in its
    log: here a -SimInset it cannot read.  The log is started anew by every
    holder."""
    log = tmp_path / 'sub' / 'page_dock.log'
    log.parent.mkdir()
    log.write_text('a line of the run before\n', encoding='utf-8')
    script = ("$me = Join-Path $PSHOME 'pwsh.exe'; "
              f"& $me -NoProfile -File '{_win(DOCK_PS1)}' -WaitSeconds 1 -PageWord nosuchword -PortFrom 8799 "
              f"-PortTo 8799 -SimInset '1,2,3' -Log '{_win(log)}'; \"bad=$LASTEXITCODE\"")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    assert 'bad=4' in proc.stdout, proc.stdout + proc.stderr
    said = log.read_text(encoding='utf-8-sig')
    assert 'a line of the run before' not in said
    assert 'the holder of the page starts' in said and "word 'nosuchword'" in said
    assert 'ERROR, the holder ends: -SimInset takes four whole numbers' in said


@needs_pwsh
def test_loose_page_changes_nothing_of_the_runs_command():
    """-LoosePage is the launcher's own: the run asks for the page as before."""
    win = _win(RUN_PS1)
    script = (f"& '{win}' boxels -Seed 3 -LoosePage -DryRun *>&1 | Out-String; '@@'; "
              f"& '{win}' boxels -Seed 3 -DryRun *>&1 | Out-String; '@@'; & '{win}' help | Out-String")
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    loose, held, help_text = proc.stdout.split('@@')
    word = re.compile(r'SB_GUI_PAGE_TOKEN=[0-9a-f]{12}')
    assert word.search(loose) and ' --gui-page on' in loose
    assert word.sub('', loose).strip() == word.sub('', held).strip()
    assert '-LoosePage' in help_text and 'held against it' in help_text
