"""Hani, 2026-11-25: "i want the view to be spilt between the two thing
completly. so one part of the screen is the browser thing entierly, an the
other part is the sim. you should measure the widtith of the screen when it
starts and sets the sizes accordingly."  The split of the screen between the
page and the simulator's window, as far as it can be tested without a window
on the desktop (tracks rule 13):

  the arithmetic   PageDock.Split, compiled and called through pwsh.exe: the
                   share, the page's least width, several screens, a scaling
                   of 100, 125, 150, 200 and 300 %; the two parts touch, lie
                   inside the screen and leave nothing over
  the margin       PageDock.MarginOf: how far what is seen of the simulator's
                   window lies inside its rectangle, computed from the
                   rectangle, and when it is only assumed
  the page         PageDock.Place with the split's numbers: the page fills
                   its part when the simulator stands in its own, and takes
                   the room beside the simulator where it stands elsewhere
  the launcher     run.ps1 -DryRun: the size is in the run's command for a
                   held page and for no other run, and it is the size of the
                   screen measured
  the run          boxel_env reads the size in one place, for a window of its
                   own only, and a value that is no size changes nothing
  the holder       the simulator's window is asked to move in one place, once,
                   for its place only

Whether the real simulator window follows that one request only a look at a
real run can say (tools/page_dock.cs, MoveSimOnce); a stand-in window does,
on a desktop that is not shown (tracks/dbgcams/checks/split_trial.ps1).
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from world import boxel_env

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

SHARE = (1, 3)                          # the page's share of the width
LEAST_WIDTH, LEAST_INSIDE = 240, 320    # the page's least width at 100 %; the simulator's least inside
BORDER, TITLE, MARGIN = 6, 27, 32       # the frame WSL draws around an X window, its own pixels

# name: (the screen without its taskbar, its dots per inch, then what is expected: the scale of
#        an X window, the page's part, the simulator's part, the rectangle Windows has for the
#        simulator's window, the window's inside; None where the screen is too small)
SCREENS = {
    "Hani's screen, 1920x1080 at 150 % with the taskbar below":
        ((0, 0, 1920, 1008), 144, 1, (0, 0, 640, 1008), (640, 0, 1920, 1008), (608, -32, 1952, 1040), (1268, 975)),
    '100 %':
        ((0, 0, 1920, 1040), 96, 1, (0, 0, 640, 1040), (640, 0, 1920, 1040), (608, -32, 1952, 1072), (1268, 1007)),
    '125 %':
        ((0, 0, 1920, 1032), 120, 1, (0, 0, 640, 1032), (640, 0, 1920, 1032), (608, -32, 1952, 1064), (1268, 999)),
    '200 %':
        ((0, 0, 3840, 2064), 192, 2, (0, 0, 1280, 2064), (1280, 0, 3840, 2064), (1216, -64, 3904, 2128), (1268, 999)),
    '200 %, a width and a height the scale does not divide':
        ((0, 0, 2560, 1601), 192, 2, (0, 0, 854, 1600), (854, 0, 2560, 1600), (790, -64, 2624, 1664), (841, 767)),
    '300 %':
        ((0, 0, 5760, 3096), 288, 3, (0, 0, 1920, 3096), (1920, 0, 5760, 3096), (1824, -96, 5856, 3192), (1268, 999)),
    'a second screen, to the right and higher up':
        ((1920, -200, 4480, 1200), 96, 1, (1920, -200, 2773, 1200), (2773, -200, 4480, 1200),
         (2741, -232, 4512, 1232), (1695, 1367)),
    'the taskbar on the left':
        ((64, 0, 1920, 1080), 96, 1, (64, 0, 682, 1080), (682, 0, 1920, 1080), (650, -32, 1952, 1112), (1226, 1047)),
    'a narrow screen: the page keeps its least width':
        ((0, 0, 1000, 700), 144, 1, (0, 0, 360, 700), (360, 0, 1000, 700), (328, -32, 1032, 732), (628, 667)),
    'too small for a split':
        ((0, 0, 800, 600), 192, 2, None, None, None, None),
}

# The scale WSL shows an X window at: the screen's scaling rounded down to a whole number.
SCALES = {96: 1, 120: 1, 144: 1, 168: 1, 191: 1, 192: 2, 240: 2, 287: 2, 288: 3}

# name: (the rectangle Windows has for the simulator's window, the inside the run was asked to
#        open, the scale; then the margin taken and whether the rectangle gave it)
MARGINS = {
    "Hani's window of 2026-11-25: 1356x817 for an inside of 1280x720":
        ((335, -9, 1691, 808), (1280, 720), 1, 32, True),
    "the split's window on his screen":
        ((608, -32, 1952, 1040), (1268, 975), 1, 32, True),
    'at 200 % the margin is twice as wide':
        ((1216, -64, 3904, 2128), (1268, 999), 2, 64, True),
    'a window host that sends no shadow: no margin':
        ((0, 0, 1292, 753), (1280, 720), 1, 0, True),
    'another margin than the one assumed is taken as it is':
        ((0, 0, 1312, 773), (1280, 720), 1, 10, True),
    'the width and the height do not give one margin: the assumed one':
        ((0, 0, 1300, 800), (1280, 720), 1, 32, False),
    'an odd number of pixels cannot be two margins: the assumed one':
        ((0, 0, 1357, 818), (1280, 720), 1, 32, False),
    'a window smaller than the inside asked: the assumed one':
        ((0, 0, 1200, 700), (1280, 720), 1, 32, False),
}

RIGHT, LEFT, OVER_RIGHT, OVER_LEFT = 1, 2, 3, 4
WORK = (0, 0, 1920, 1008)
PAGE_MARGINS = (11, 45, 14, 14)         # the page inside its browser window, as the trial measured it
PART, MIN = 640, 360                    # the page's part of that screen, and 240 at 150 %

# name: (what is seen of the simulator's window, then what is expected of the page that starts
#        on the left: side, width, its whole window, the cut inside it)
PLACES = {
    'the simulator stands in its part: the page fills the other':
        ((640, 0, 1920, 1008), LEFT, 640, (-11, -45, 654, 1022), (11, 45, 651, 1053)),
    'the simulator did not move and stands further left: the room on its left':
        ((500, 0, 1780, 1008), LEFT, 500, (-11, -45, 514, 1022), (11, 45, 511, 1053)),
    'too little room on its left: the room on its right':
        ((100, 0, 1380, 1008), RIGHT, 540, (1369, -45, 1934, 1022), (11, 45, 551, 1053)),
    'too little room on either side: at the left edge, over the simulator':
        ((300, 0, 1580, 1008), OVER_LEFT, 360, (-11, -45, 374, 1022), (11, 45, 371, 1053)),
    'dragged down and to the right afterwards: the page keeps against it, as wide as its part':
        ((700, 100, 1980, 1108), LEFT, 640, (49, 55, 714, 1122), (11, 45, 651, 1053)),
}


def _win(path):
    return subprocess.run(['wslpath', '-w', str(path)], capture_output=True,
                          text=True, check=True).stdout.strip()


def _pwsh(script, timeout=300):
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture(scope='module')
def computed():
    """Every case through the compiled code, in one pwsh call."""
    lines = ["$ErrorActionPreference = 'Stop'",
             f"Add-Type -Path '{_win(DOCK_CS)}' -IgnoreWarnings",
             "function New-Rect($l, $t, $r, $b) { $x = New-Object PageDock+RECT; "
             "$x.L = $l; $x.T = $t; $x.R = $r; $x.B = $b; $x }",
             "'consts|' + [PageDock]::ShareOfPage + '|' + [PageDock]::ShareOutOf + '|' + [PageDock]::LeastWidth + '|' + "
             "[PageDock]::LeastInside + '|' + [PageDock]::FrameBorder + '|' + [PageDock]::FrameTitle + '|' + "
             "[PageDock]::FrameMargin"]
    for i, (work, dpi, *_expected) in enumerate(SCREENS.values()):
        lines.append(
            "$h = [PageDock]::Split((New-Rect %d %d %d %d), %d, [PageDock]::LeastWidth); "
            "'split%d|' + $h.Ok + '|' + $h.Scale + '|' + $h.Page + '|' + $h.Sim + '|' + $h.SimWindow + '|' + "
            "$h.ClientW + ',' + $h.ClientH + '|' + $h.Work + '|' + $h.Dpi" % (*work, dpi, i))
    for dpi in SCALES:
        lines.append("'scale%d|' + [PageDock]::WslScale(%d)" % (dpi, dpi))
    for i, (rect, inside, scale, *_expected) in enumerate(MARGINS.values()):
        lines.append("$m = [PageDock]::MarginOf((New-Rect %d %d %d %d), %d, %d, %d); "
                     "'margin%d|' + $m.Pixels + '|' + $m.Computed" % (*rect, *inside, scale, i))
    for i, (sim, *_expected) in enumerate(PLACES.values()):
        lines.append(
            "$p = [PageDock]::Place((New-Rect %d %d %d %d), (New-Rect %d %d %d %d), %d, %d, %d, %d, %d, %d, "
            "[PageDock]::Left); '%s|' + $p.Side + '|' + $p.Width + '|' + $p.Window + '|' + $p.Region"
            % (*sim, *WORK, *PAGE_MARGINS, PART, MIN, 'place%d' % i))
    # the screen of this machine, measured as the launcher measures it (read only)
    lines.append("$h = [PageDock]::SplitOfPrimary(); 'primary|' + $h.Ok + '|' + $h.Work + '|' + $h.Dpi + '|' + "
                 "$h.Page + '|' + $h.Sim + '|' + $h.ClientW + ',' + $h.ClientH")
    rows = [ln.strip().split('|') for ln in _pwsh('\n'.join(lines)).splitlines() if '|' in ln]
    return {row[0]: row[1:] for row in rows}


def _rect(text):
    return tuple(int(v) for v in text.split(','))


@needs_pwsh
def test_the_share_the_least_width_and_the_frame_are_the_numbers_this_file_uses(computed):
    assert computed['consts'] == [str(v) for v in (*SHARE, LEAST_WIDTH, LEAST_INSIDE, BORDER, TITLE, MARGIN)]
    # one place: the launcher and the holder's script name no share and no frame of their own
    cs = DOCK_CS.read_text(encoding='utf-8')
    assert cs.count('public const int ShareOfPage = 1, ShareOutOf = 3;') == 1
    assert cs.count('public const int FrameBorder = 6, FrameTitle = 27, FrameMargin = 32;') == 1
    for script in (RUN_PS1, DOCK_PS1):
        text = script.read_text(encoding='utf-8')
        code = '\n'.join(ln for ln in text.splitlines() if not ln.lstrip().startswith('#'))
        assert 'ShareOfPage' not in code and 'FrameMargin' not in code and '/ 3' not in code, script.name
    # the page's least width is the holder's own
    assert re.search(r'\[int\]\$MinWidth = (\d+)', DOCK_PS1.read_text(encoding='utf-8')).group(1) == str(LEAST_WIDTH)


@needs_pwsh
@pytest.mark.parametrize('name', list(SCREENS))
def test_the_split_of_a_screen(computed, name):
    work, dpi, scale, page, sim, window, inside = SCREENS[name]
    ok, got_scale, got_page, got_sim, got_window, got_inside, got_work, got_dpi = computed[
        'split%d' % list(SCREENS).index(name)]
    assert (int(got_scale), _rect(got_work), int(got_dpi)) == (scale, work, dpi)
    if page is None:
        assert ok == 'False'
        w, h = _rect(got_inside)
        assert w < LEAST_INSIDE or h < LEAST_INSIDE
        return
    assert ok == 'True'
    assert (_rect(got_page), _rect(got_sim), _rect(got_window), _rect(got_inside)) == (page, sim, window, inside)
    # the two parts divide the screen: side by side, touching, nothing over the screen's edges
    assert page[0] == work[0] and sim[2] == work[2], 'from the left edge to the right edge'
    assert page[2] == sim[0], 'no gap between them and nothing overlapping'
    assert page[1] == sim[1] == work[1] and page[3] == sim[3], 'the same top and the same height'
    assert 0 <= work[3] - sim[3] < scale, 'the whole height, but for under one step of the scale'
    # the share, never under the least width
    least = round(LEAST_WIDTH * dpi / 96)
    third = (work[2] - work[0]) * SHARE[0] // SHARE[1]
    width = page[2] - page[0]
    assert width >= least
    assert 0 <= width - max(third, least) < scale, 'the page takes only what the rounding leaves over'
    # the simulator's part is its window as seen: the inside, the border and the title bar,
    # at the scale of an X window; the rectangle for Windows is the margin larger all round
    assert sim[2] - sim[0] == (inside[0] + 2 * BORDER) * scale
    assert sim[3] - sim[1] == (inside[1] + TITLE + BORDER) * scale
    m = MARGIN * scale
    assert window == (sim[0] - m, sim[1] - m, sim[2] + m, sim[3] + m)
    assert inside[0] >= LEAST_INSIDE and inside[1] >= LEAST_INSIDE


@needs_pwsh
def test_an_x_window_is_shown_at_a_whole_number_scale(computed):
    assert {dpi: int(computed['scale%d' % dpi][0]) for dpi in SCALES} == SCALES


@needs_pwsh
@pytest.mark.parametrize('name', list(MARGINS))
def test_the_margin_is_computed_from_the_rectangle(computed, name):
    """What is seen of the simulator's window lies a margin inside the
    rectangle Windows has for it (the window host's shadow).  The holder does
    not just assume it: the rectangle less the inside asked, its border and
    its title bar leaves twice the margin, once in the width and once in the
    height.  Only where the two do not agree is the assumed margin taken (and
    the holder's log says ASSUMED)."""
    rect, inside, scale, margin, computed_it = MARGINS[name]
    assert computed['margin%d' % list(MARGINS).index(name)] == [str(margin), str(computed_it)], name
    if not computed_it:
        assert margin == MARGIN * scale
    cs = DOCK_CS.read_text(encoding='utf-8')
    assert 'margin = m.Pixels;' in cs and 'the margin is ASSUMED' in cs and 'is COMPUTED from that' in cs


@needs_pwsh
@pytest.mark.parametrize('name', list(PLACES))
def test_where_the_page_goes_in_a_split(computed, name):
    """The page starts on the left and is as wide as its part.  With the
    simulator in its part that is all the room there is; where the simulator
    stands elsewhere (its window did not follow the one request, or it was
    dragged later) the page takes the room beside it, as without a split."""
    sim, side, width, window, cut = PLACES[name]
    got = computed['place%d' % list(PLACES).index(name)]
    assert got == [str(side), str(width), ','.join(map(str, window)), ','.join(map(str, cut))], name
    seen = (window[0] + cut[0], window[1] + cut[1], window[0] + cut[2], window[1] + cut[3])
    assert (seen[1], seen[3]) == (sim[1], sim[3]), "the simulator's top and height"
    if side == LEFT:
        assert seen[2] == sim[0], 'no gap and nothing overlapping'
    elif side == RIGHT:
        assert seen[0] == sim[2]
    if name.startswith('the simulator stands in its part'):
        assert seen == (WORK[0], WORK[1], sim[0], WORK[3]), 'the whole of its part'


@needs_pwsh
def test_this_machines_screen_is_measured_in_real_pixels(computed):
    """SplitOfPrimary, read only: a work area and a scaling come back, and
    the split is the arithmetic's for them."""
    ok, work, dpi, page, sim, inside = computed['primary']
    work, dpi = _rect(work), int(dpi)
    assert work[2] > work[0] and work[3] > work[1] and dpi >= 96
    if ok == 'True':
        page, sim = _rect(page), _rect(sim)
        assert page[0] == work[0] and page[2] == sim[0] and sim[2] == work[2]
        assert page[1] == sim[1] == work[1]
    cs = DOCK_CS.read_text(encoding='utf-8')
    measuring = cs[cs.index('public static Halves SplitOfPrimary()'):cs.index('static string More(')]
    # real pixels for the one call, and the thread's own setting back after it
    assert measuring.index('SetThreadDpiAwarenessContext(new IntPtr(-4))') < measuring.index('MonitorFromPoint(')
    assert 'finally { if (was != IntPtr.Zero) SetThreadDpiAwarenessContext(was); }' in measuring
    assert 'return Split(info.rcWork, DpiOf(monitor), LeastWidth);' in measuring


# ----- the launcher ---------------------------------------------------------------------------

# name: (the screen given in place of the measured one, or None for this machine's; the call)
CALLS = {
    'hani': ('0,0,1920,1008,144', 'boxels -Seed 3 -DryRun'),
    'at100': ('0,0,1920,1040,96', 'boxels -Seed 3 -DryRun'),
    'at125': ('0,0,1920,1032,120', 'boxels -Seed 3 -DryRun'),
    'at200': ('0,0,3840,2064,192', 'boxels -Seed 3 -DryRun'),
    'second': ('1920,-200,4480,1200,96', 'boxels -Seed 3 -DryRun'),
    'narrow': ('0,0,1000,700,144', 'boxels -Seed 3 -DryRun'),
    'small': ('0,0,800,600,192', 'boxels -Seed 3 -DryRun'),
    'list': ('0,0,1920,1008,144', 'boxels -Seed 3,4 -DryRun'),
    'flags': ('0,0,1920,1008,144', "boxels -Seed 3 -Look boxel -Args '--n-extra-distractors 1' -DryRun"),
    'loose': ('0,0,1920,1008,144', 'boxels -Seed 3 -LoosePage -DryRun'),
    'nopage': ('0,0,1920,1008,144', 'boxels -Seed 3 -NoPage -DryRun'),
    'headless': ('0,0,1920,1008,144', 'boxels -Seed 3 -Headless -DryRun'),
    'tampura': ('0,0,1920,1008,144', 'tampura -Seed 0 -DryRun'),
    'wumpus': ('0,0,1920,1008,144', 'wumpus -Seed 3 -DryRun'),
    'real': (None, 'boxels -Seed 3 -DryRun'),
}
SIZES = {'hani': '1268x975', 'at100': '1268x1007', 'at125': '1268x999', 'at200': '1268x999',
         'second': '1695x1367', 'narrow': '628x667'}
WINDOW = re.compile(r'export SB_GUI_WINDOW=(\d+x\d+); ')
TOKEN = re.compile(r'export SB_GUI_PAGE_TOKEN=[0-9a-f]{12}; ')


@pytest.fixture(scope='module')
def out():
    win = _win(RUN_PS1)
    parts = []
    for name, (screen, args) in CALLS.items():
        given = (f"$env:SB_SPLIT_SCREEN = '{screen}'" if screen
                 else "Remove-Item Env:SB_SPLIT_SCREEN -ErrorAction SilentlyContinue")
        parts.append(f"{given}; $global:LASTEXITCODE = 0; & '{win}' {args} *>&1 | Out-String; "
                     f"\"exit=$LASTEXITCODE\"; '@@{name}'")
    parts.append(f"Add-Type -Path '{_win(DOCK_CS)}' -IgnoreWarnings; $h = [PageDock]::SplitOfPrimary(); "
                 "'primary=' + $h.Ok + '=' + $h.ClientW + 'x' + $h.ClientH; '@@primary'")
    text = _pwsh('; '.join(parts))
    pieces = re.split(r'@@(\w+)', text)             # text, name, text, name ...
    return {name: pieces[i] for i, name in zip(range(0, len(pieces) - 1, 2), pieces[1::2])}


def _commands(text):
    return [ln for ln in text.splitlines()
            if 'test_full_pipeline' in ln or '--global-seed' in ln or 'run_wumpus' in ln]


def _own(cmd):
    """The run's own command inside the launcher's line (see
    tests/test_run_draw_launcher.py)."""
    m = re.search(r"; exec flock \$L bash -c '(.*)'$", cmd)
    return m.group(1).replace("'\\''", "'") if m else cmd


def _said(text):
    return [ln for ln in text.splitlines() if ln.startswith('run: ')]


@needs_pwsh
@pytest.mark.parametrize('name', list(SIZES))
def test_a_held_page_run_is_asked_for_the_size_of_the_screen_measured(out, name):
    """The size is known before the run starts: it is in the run's own
    command, as an environment variable beside the page's word, once."""
    (cmd,) = _commands(out[name])
    assert WINDOW.findall(cmd) == [SIZES[name]], cmd
    own = _own(cmd)
    assert own.startswith(f'export SB_GUI_WINDOW={SIZES[name]}; export SB_GUI_PAGE_TOKEN='), own
    assert own.endswith('--n-occluders 2 --gui-page on')
    assert 'exit=0' in out[name] and not _said(out[name])


@needs_pwsh
def test_the_size_is_all_the_split_adds_to_the_command(out):
    """No new flag: the command of a held page is the loose page's command
    plus the size, and PyBullet's own window's plus the size, the word and
    the page's flag.  Every seed of a list is asked for it, and the other
    switches follow as before."""
    (held,) = _commands(out['hani'])
    (loose,) = _commands(out['loose'])
    (plain,) = _commands(out['nopage'])
    assert 'SB_GUI_WINDOW' not in loose and 'SB_GUI_WINDOW' not in plain
    assert TOKEN.sub('', WINDOW.sub('', held)) == TOKEN.sub('', loose)
    assert TOKEN.sub('', WINDOW.sub('', held)).replace(' --gui-page on', '') == plain
    both = _commands(out['list'])
    assert len(both) == 2 and [WINDOW.findall(c) for c in both] == [['1268x975'], ['1268x975']]
    (flags,) = _commands(out['flags'])
    assert WINDOW.findall(flags) == ['1268x975']
    assert _own(flags).endswith('--n-occluders 2 --gui-page on --look boxel --n-extra-distractors 1')


@needs_pwsh
def test_no_other_run_is_asked_for_a_size(out):
    """-LoosePage and -NoPage stay as they are (a 1280x720 window), and a
    headless run, run tampura and run wumpus never carry the size."""
    for name in ('loose', 'nopage', 'headless', 'tampura', 'wumpus'):
        assert _commands(out[name]), out[name]
        assert 'SB_GUI_WINDOW' not in out[name], name
        assert not [ln for ln in _said(out[name]) if 'split' in ln], name


@needs_pwsh
def test_a_screen_too_small_gets_no_split_and_the_launcher_says_so(out):
    (cmd,) = _commands(out['small'])
    assert 'SB_GUI_WINDOW' not in cmd and TOKEN.search(cmd) and ' --gui-page on' in cmd
    assert _said(out['small']) == [
        "run: no split of the screen (the screen is too small for it: 800x600 at 200 %); the simulator's "
        "window opens 1280x720 and the page beside it"]


@needs_pwsh
def test_without_a_screen_given_this_machines_screen_is_measured(out):
    ok, size = re.search(r'primary=(\w+)=(-?\d+x-?\d+)', out['primary']).groups()
    (cmd,) = _commands(out['real'])
    if ok == 'True':
        assert WINDOW.findall(cmd) == [size] and not _said(out['real'])
    else:
        assert 'SB_GUI_WINDOW' not in cmd and len(_said(out['real'])) == 1


def test_the_launcher_measures_before_the_run_starts_and_tells_the_holder():
    ps = RUN_PS1.read_text(encoding='utf-8')
    code = '\n'.join(ln for ln in ps.splitlines() if not ln.lstrip().startswith('#'))
    # measured where the run's command is built, for a page that is held only
    build = code[code.index('function New-Run('):code.index('function Get-SplitWindow')]
    held = build[build.index('if (-not $Headless -and -not $NoPage) {'):build.index('$cmd = "cd $S && PYTHONHASHSEED=0 $PY $mine$pageFlag$sw$extra"')]
    assert 'if (-not $LoosePage) {' in held and '$window = Get-SplitWindow' in held
    assert build.count('Get-SplitWindow') == 1
    assert 'if ($window) { $cmd = "export SB_GUI_WINDOW=$window; " + $cmd }' in build
    assert code.index('function New-Run(') < code.index('$p = [System.Diagnostics.Process]::Start($psi)')
    # the arithmetic is the holder's file's, not the launcher's
    measure = code[code.index('function Get-SplitWindow'):code.index('$pagePorts = ')]
    assert "[PageDock]::SplitOfPrimary()" in measure and "[PageDock]::Split($work, " in measure
    assert 'catch { $script:noSplit = $_.Exception.Message }' in measure     # a failure never stops the run
    # and the holder is told the same size, only when there is one
    start = code.index('if ($r.Page -and -not $LoosePage) {')
    block = code[start:code.index('if ($r.Cameras) {', start)]
    assert "if ($r.Window) { $holdArgs += '-SimClient', $r.Window }" in block
    assert block.index("$holdArgs += '-SimClient'") < block.index('$holder = Start-Process')


# ----- the run --------------------------------------------------------------------------------

@pytest.mark.parametrize('given, size', [
    (None, (1280, 720)),                    # unset: as before
    ('1268x975', (1268, 975)),
    (' 1268x975 ', (1268, 975)),
    ('628x667', (628, 667)),
    ('', (1280, 720)),
    ('1268', (1280, 720)),
    ('1268x', (1280, 720)),
    ('x975', (1280, 720)),
    ('1268X975', (1280, 720)),
    ('1268x975x2', (1280, 720)),
    ('-1268x975', (1280, 720)),
    ('12.5x975', (1280, 720)),
    ('99x975', (1280, 720)),                # under a hundred pixels: no window size
    ('1268x99999', (1280, 720)),
    ('on', (1280, 720)),
])
def test_the_window_takes_the_launchers_size_and_nothing_that_is_no_size(monkeypatch, given, size):
    if given is None:
        monkeypatch.delenv('SB_GUI_WINDOW', raising=False)
    else:
        monkeypatch.setenv('SB_GUI_WINDOW', given)
    assert boxel_env._own_window_size(1280, 720) == size


def test_the_size_is_read_in_one_place():
    """Over the whole checkout, tests and records aside, one file names the
    variable, and names it once in its code."""
    readers = []
    for folder, folders, files in os.walk(ROOT):
        folders[:] = [d for d in folders
                      if not d.startswith('.') and d not in ('tests', 'archive', 'logs', 'pddlstream_lib',
                                                               '__pycache__', 'eval_results', 'thesis', 'report')]
        for name in files:
            if name.endswith('.py'):
                with open(os.path.join(folder, name), encoding='utf-8', errors='replace') as f:
                    if 'SB_GUI_WINDOW' in f.read():
                        readers.append(os.path.relpath(os.path.join(folder, name), ROOT).replace(os.sep, '/'))
    assert readers == ['world/boxel_env.py']
    source = (ROOT / 'world' / 'boxel_env.py').read_text(encoding='utf-8')
    assert source.count("os.environ.get('SB_GUI_WINDOW'") == 1
    assert source.count('_own_window_size(') == 2          # the function and its one call


# A window that opens with and without the launcher's size, without a window: as in
# test_window_panes.py a GUI connection is handed a DIRECT client in a process of its own, and
# every connection is written down with the options it was asked with.
_OPENING = r'''
import json
import pybullet as p

real_connect = p.connect
log = []


def connect(mode, *args, **kwargs):
    log.append(['window' if mode == p.GUI else 'no window', kwargs.get('options', '')])
    return real_connect(p.DIRECT)


p.connect = connect
from world import boxel_env

own = boxel_env.BoxelTestEnv(gui=True)
seen = own.get_camera_observation()
shape = list(seen.rgb_image.shape)
headless = boxel_env.BoxelTestEnv(gui=False)


class Stop(Exception):
    pass


class Adopted(boxel_env.BoxelTestEnv):
    def _adopt_scene(self):
        raise Stop()


world = real_connect(p.DIRECT)
try:
    Adopted(gui=True, adopt_client=world)
except Stop:
    pass
print(json.dumps({'connections': log, 'image': shape, 'camera': [own.image_width, own.image_height]}))
'''


def _opening(size):
    env = {k: v for k, v in os.environ.items() if k != 'SB_GUI_WINDOW'}
    if size is not None:
        env['SB_GUI_WINDOW'] = size
    done = subprocess.run([sys.executable, '-c', _OPENING], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_our_own_window_opens_with_the_size_and_nothing_else_differs():
    """The size reaches PyBullet's options of the one connection that opens a
    window.  The plan twin, a headless env and an adopted world connect as
    before, and the robot's camera image keeps its own size."""
    plain, split = _opening(None), _opening('1268x975')
    assert plain['connections'][0] == ['window', '--width=1280 --height=720']
    assert split['connections'][0] == ['window', '--width=1268 --height=975']
    # the plan twin, the headless env and its plan twin, the adopted world's plan twin
    assert plain['connections'][1:] == split['connections'][1:] == [['no window', '']] * 4
    assert plain['image'] == split['image'] == [480, 640, 3]
    assert plain['camera'] == split['camera'] == [640, 480]


# ----- the holder -----------------------------------------------------------------------------

def test_the_simulators_window_is_asked_to_move_in_one_place_once_for_its_place_only():
    """The holder touches the simulator's window in two places: its place in
    the stacking order when the page is clicked (as before), and ONE request
    to move into its part of the screen when the pair is taken: position
    only (no size, no stacking order, no activation), posted and not waited
    for.  It is made before the page is first placed and never again: no
    report of Windows and no look of the timer leads to it."""
    cs = DOCK_CS.read_text(encoding='utf-8')
    assert cs.count('SetWindowPos(sim, ') == 2
    assert cs.count('SetWindowPos(sim, page, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);') == 1       # RaiseSim
    move = 'bool posted = SetWindowPos(sim, IntPtr.Zero, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010 | 0x4000);'
    assert cs.count(move) == 1
    once = cs[cs.index('static void MoveSimOnce()'):cs.index('static void CheckMove()')]
    assert move in once
    assert "if (!placeSim) {" in once and once.index("if (!placeSim) {") < once.index(move)
    assert 'if (IsZoomed(sim) || IsIconic(sim)) {' in once
    # called once, in Run, after the windows are described and before the first placing
    assert cs.count('MoveSimOnce()') == 2                   # the function and its one call
    run = cs[cs.index('public static int Run('):]
    assert (run.index('if (askedW > 0) TakeMargin();') < run.index('Note("  simulator: "')
            < run.index('if (askedW > 0) MoveSimOnce();') < run.index('Sync("first");'))
    for later in ('static void Sync(', 'static void Tick()', 'static void OnEvent(', 'static void CheckMove()'):
        body = cs[cs.index(later):cs.index('\n    }\n', cs.index(later))]
        assert 'MoveSimOnce' not in body and 'SetWindowPos(sim, IntPtr.Zero' not in body, later
    # what is read back is written down, whichever way it went
    for said in ('was asked ONCE to move from', 'Windows has it there after', 'It is NOT asked again',
                 'Windows refused the move', 'is in its part already'):
        assert said in once, said


def test_without_a_size_the_holder_is_the_one_before():
    """No -SimClient (the trial's stand-ins, a run without a split): no
    margin, no move, the page beside the simulator on the side with room."""
    cs = DOCK_CS.read_text(encoding='utf-8')
    assert 'static int askedW, askedH, margin;' in cs and 'static bool placeSim = true;' in cs
    assert 'margin = 0; moveOpen = false;' in cs
    assert 'if (askedW > 0) side = Left;' in cs
    assert cs.count('if (askedW > 0)') == 4                 # the side, the margin, the move, the width wanted
    ps = DOCK_PS1.read_text(encoding='utf-8')
    assert "[string]$SimClient = ''," in ps and "[string]$SimPlace = 'move'," in ps
    assert ps.index('if ($SimClient) {') < ps.index("[PageDock]::SetSplit($inside[0], $inside[1], $SimPlace -eq 'move')") \
        < ps.index('exit [PageDock]::Run(')


@needs_pwsh
def test_a_size_or_a_place_the_holder_cannot_read_is_in_its_log(tmp_path):
    """The launcher starts the holder hidden, so what stops it must be in its
    log (exit 4), as for -SimInset."""
    logs = [tmp_path / 'size.log', tmp_path / 'place.log']
    script = ("$me = Join-Path $PSHOME 'pwsh.exe'; "
              f"& $me -NoProfile -File '{_win(DOCK_PS1)}' -WaitSeconds 1 -PageWord nosuchword -PortFrom 8799 "
              f"-PortTo 8799 -SimClient 1268by975 -Log '{_win(logs[0])}'; \"size=$LASTEXITCODE\"; "
              f"& $me -NoProfile -File '{_win(DOCK_PS1)}' -WaitSeconds 1 -PageWord nosuchword -PortFrom 8799 "
              f"-PortTo 8799 -SimClient 1268x975 -SimPlace there -Log '{_win(logs[1])}'; \"place=$LASTEXITCODE\"")
    said = _pwsh(script)
    assert 'size=4' in said and 'place=4' in said, said
    assert "-SimClient takes the simulator window's inside as <width>x<height>, not '1268by975'" in logs[0].read_text(
        encoding='utf-8-sig')
    assert "-SimPlace takes move or leave, not 'there'" in logs[1].read_text(encoding='utf-8-sig')
