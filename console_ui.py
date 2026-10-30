"""The console of a pipeline run: Semantic Boxels narrating its own episode
(2026-10-30).

What the terminal shows: a banner, then the robot speaking in the first
person: what it is starting, what it sees, what it is thinking about before
each plan and what the plan intends, one line per step with how the step
went, the notable observations under the step, warnings, and a closing
verdict.  While the robot is busy (starting up, planning, executing a
step) an animated colour pictogram of the action (a sprite from
console_art, the boxel cube when none fits) is drawn beside a status line;
the block is erased when the activity ends, so a captured console (a file,
the campaign's console.txt) holds only the committed lines.  Everything else the process
writes goes to files: our narration keeps landing in the run log through
run_logger's stdout tee, and the raw stdout and stderr of the whole process
(pybullet's b3Printf and b3Warning lines, TAMPURA's logger, PDDLStream's
iteration and summary dumps, FastDownward) land in
<run_dir>/console_debug.log, next to the run log.  At start-up the
terminal's own descriptor is duplicated, then file descriptors 1 and 2 are
pointed at the debug file, so C-level prints cannot reach the terminal any
more; the console's lines go out through the duplicate and are mirrored
into the debug file as "[console] ..." lines.  Nothing is lost: a line
that reached the terminal before is in one of the two files now.

Installed by the entry points (test_full_pipeline.py and the bridge driver
tampura_bridge/run_bridge_on_finddice.py) at their module top, before
pybullet is imported, when --log-level is smart, the default.  The raw
levels (normal, quiet, verbose) keep the raw terminal and nothing here
runs for them.  Events reach the console from run_logger: the ledger's
plan, step, step_end, sense_result and observe_result rows, the tee's
narration lines and report_run_outcome's numbers; the pipeline's planning,
execution, perception, the ledger and the gates are not touched, and
nothing here feeds a decision.

Layouts: the full view (a terminal of at least BLOCK_MIN_COLS columns and
BLOCK_MIN_ROWS rows) draws the animated block; a narrower terminal gets a
one-line status with the same animation; a captured console (not a
terminal) gets plain text, no animation and no colour.
"""
import argparse
import atexit
import io
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
from contextlib import contextmanager

DEBUG_NAME = 'console_debug.log'
# Where the debug file lives until a run directory exists (a start that
# stops before its RunLogger, an argparse error, a crash during set-up,
# keeps it there and names it): the user's cache directory, since WSL's
# /tmp does not survive between sessions.
EARLY_DIR = os.path.join(os.path.expanduser('~'), '.cache', 'semantic_boxels')
REPO = os.path.dirname(os.path.abspath(__file__))

# The full view (the animated block beside the status) needs this much
# terminal (a split view of some 56 columns gets it); below it the status
# is one line.  The full view comes first (Hani, 2026-10-30); the mini view
# gets its own layout later.
BLOCK_MIN_COLS = 48
BLOCK_MIN_ROWS = 12
FRAME_S = 0.1          # the animation's tick
SHOW_AFTER_S = 0.3     # an activity shorter than this never shows its drawing
BANNER_COLS = 60       # the banner's widest rule

_console = None        # the installed Console; None means nothing here runs


# ---------------------------------------------------------------------------
# installation
# ---------------------------------------------------------------------------

class _ArgvError(Exception):
    pass


class _PreParser(argparse.ArgumentParser):
    """argparse's own rules (prefix abbreviations, the last value wins) on
    the two options the early install depends on; it never prints and
    never exits, the entry point's parser reports the errors."""

    def error(self, message):
        raise _ArgvError(message)


def _pre_parse(argv, default='smart'):
    pre = _PreParser(add_help=False)      # allow_abbrev on, like both entry points
    pre.add_argument('--log-level', default=default)
    pre.add_argument('-h', '--help', action='store_true')
    return pre.parse_known_args(argv)[0]


def argv_log_level(argv=None, default='smart'):
    """The --log-level value as the entry point's parser will read it
    (abbreviations such as --log quiet, the last of repeated flags), or
    the default; None when the command line does not parse."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return _pre_parse(argv, default).log_level
    except Exception:
        return None


def install_early(module_name, argv=None):
    """At an entry point's module top, before pybullet is imported: install
    the console when the module runs as the script and the console level
    is smart.  A no-op for an import, for --help, for the raw levels and
    for a command line that does not parse."""
    if module_name != '__main__' or _console is not None:
        return False
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        ns = _pre_parse(argv)
    except Exception:
        return False
    if ns.help or ns.log_level != 'smart':
        return False
    return install() is not None


def install(debug_path=None):
    """Install the console; the debug file is a temporary one until
    attach() moves it next to the run log.  None when the console cannot
    be installed: the constructor rolled back what it had changed and the
    terminal stays as it is."""
    global _console
    if _console is None:
        try:
            _console = Console(debug_path)
        except Exception:
            return None
    return _console


def installed():
    return _console is not None


def uninstall():
    """Restore the terminal descriptors and streams (tests, lazy installs)."""
    global _console
    c, _console = _console, None
    if c is not None:
        try:
            c.close()
        except Exception:
            pass


def attach(run_dir, log_path):
    """RunLogger's hook for a smart run: the debug file moves next to the
    run log and the console learns the run id.  Installs the console when
    the entry point did not (a RunLogger made by other code); that console
    is then owned by the RunLogger and goes away with detach()."""
    target = os.path.join(str(run_dir), DEBUG_NAME)
    owned = _console is None
    c = install(target)
    if c is None:
        return None
    try:
        c.attach(run_dir, log_path, owned=owned)
    except Exception:
        pass
    return c


def detach():
    """RunLogger.close()'s hook."""
    if _console is not None:
        try:
            _console.detach()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# the event API (every call is a no-op without an installed console)
# ---------------------------------------------------------------------------

def set_context(**fields):
    """Header fields an entry point knows before main() runs (the bridge's
    scene and seed)."""
    if _console is not None:
        _console.context.update(fields)


def context():
    return dict(_console.context) if _console is not None else {}


def _call(method, *args, **kw):
    """The event API never raises into the pipeline."""
    if _console is None:
        return
    try:
        method(_console, *args, **kw)
    except Exception:
        pass


def startup(text):
    """One start-up note, verbatim, under the 'Starting up' line (the
    bridge's scene file: a console reader looks for 'Loading scene from')."""
    _call(Console.startup_note, text)


def header(scene=None, goal=None, switches=None):
    _call(Console.header, scene=scene, goal=goal, switches=switches)


def on_ledger_event(kind, row):
    """Called by run_logger.ledger_event after the row is written."""
    _call(Console.on_ledger_event, kind, row)


def summary(**kw):
    """Called by run_logger.report_run_outcome after its prints."""
    _call(Console.summary, **kw)


def say(text):
    """One line, verbatim (the bridge's gate table and outcome line)."""
    _call(Console.say, text)


def warn(text):
    _call(Console.warn, text)


def finish(code=0):
    """The entry points' exit in place of sys.exit(code).  With the console
    installed every file is flushed, the exit handlers run and the process
    ends with os._exit(code): pybullet's GUI teardown segfaults at
    interpreter exit after a GUI run, and bash then prints 'Segmentation
    fault' with the whole command under the console's last line.  Without
    the console (the raw levels) it is sys.exit(code)."""
    if _console is None:
        sys.exit(code)
    try:
        _console.finish()
    except Exception:
        pass
    os._exit(int(code) if isinstance(code, int) else (0 if code is None else 1))


@contextmanager
def terminal():
    """sys.stdout goes to the terminal (mirrored into the debug file) for
    the block: for code that prints curated output with print()."""
    if _console is None:
        yield
        return
    old = sys.stdout
    sys.stdout = _TerminalWriter(_console)
    try:
        yield
    finally:
        sys.stdout.flush()
        sys.stdout = old


# ---------------------------------------------------------------------------
# words: names, phrases and the rules over the narration
# ---------------------------------------------------------------------------

def _plural(n, word, words=None):
    n = int(n)
    return f"{n} {word if n == 1 else (words or word + 's')}"


def _secs(x):
    try:
        return f'{float(x):.1f} s'
    except (TypeError, ValueError):
        return '? s'


def _symbols(args):
    """The plain symbols of a ledger step row (names and boxel ids; the
    configurations and trajectories are 'cfg:...' and 'Type@id')."""
    return [a for a in (args or []) if isinstance(a, str)
            and not a.startswith('cfg:') and '@' not in a]


def _is_home(name):
    return name in ('home', 'q_home', 'view__q_home')


# A shadow's parent object; the registry's slab suffix (shadow_of_x__03,
# boxel_env: one shadow per slab) is not part of the name.
_SHADOW_OF = re.compile(r'shadow_of_(.+?)(?:__\d{2,})?$')


def _place(name):
    """A boxel or configuration name as a place in a sentence.  Object
    names are marked `like this` (rendered in bold)."""
    name = str(name)
    if _is_home(name):
        return 'home'
    if name.startswith('view__'):
        rest = name[len('view__'):]
        m = re.match(r'look_(.+?)_\d+$', rest)
        if m:
            return f'a look at `{m.group(1)}`'
        if rest.startswith('sense_retract'):
            return 'a step back'
        return f'the viewpoint {rest}'
    if re.match(r'free_\d+$', name):
        return 'a free spot'
    m = _SHADOW_OF.match(name)
    if m:
        return f'the space behind `{m.group(1)}`'
    return f'`{name}`'


def _move_phrase(dest):
    dest = str(dest)
    if _is_home(dest):
        return 'Going home'
    if dest.startswith('view__'):
        rest = dest[len('view__'):]
        m = re.match(r'look_(.+?)_\d+$', rest)
        if m:
            return f'Moving in for a look at `{m.group(1)}`'
        if rest.startswith('sense_retract'):
            return 'Stepping back for a clear view'
        return f'Moving to the viewpoint {rest}'
    if re.match(r'free_\d+$', dest):
        return 'Moving over a free spot'
    m = _SHADOW_OF.match(dest)
    if m:
        return f'Moving to the space behind `{m.group(1)}`'
    return f'Moving over `{dest}`'


def _where(dest):
    """'on a free spot' / 'in the space behind x' / 'at <place>'."""
    dest = str(dest)
    if re.match(r'free_\d+$', dest):
        return 'on a free spot'
    if dest.startswith('shadow_of_'):
        return f'in {_place(dest)}'
    return f'at {_place(dest)}' if dest else ''


def describe_step(action, args):
    """One action as the robot announces it (first person, present)."""
    s = _symbols(args)
    if action == 'move':
        return _move_phrase(s[0]) if s else 'Moving'
    if action == 'pick':
        obj = s[0] if s else '?'
        src = s[1] if len(s) > 1 else obj
        if src != obj and src.startswith('shadow_of_'):
            return f'Picking up `{obj}` from {_place(src)}'
        return f'Picking up `{obj}`'
    if action in ('place', 'place_hiding'):
        obj = s[0] if s else '?'
        dest = s[1] if len(s) > 1 else ''
        tail = " (out of the camera's view)" if action == 'place_hiding' else ''
        return f'Setting `{obj}` down {_where(dest)}'.rstrip() + tail
    if action == 'stack':
        return (f'Stacking `{s[0]}` on `{s[1]}`' if len(s) > 1
                else 'Stacking ' + ' '.join(s))
    if action == 'sense':
        return (f'Looking into {_place(s[1])} for `{s[0]}`' if len(s) > 1
                else 'Sensing ' + ' '.join(s))
    if action == 'observe':
        return f"Taking a closer look at `{s[0] if s else '?'}`"
    return ' '.join([str(action)] + s)


def intention(actions):
    """A plan's actions as one sentence of intent: 'pick up `x`, set it
    down on a free spot, come home, then look behind it for `t`'.  A move
    right before the action it serves is implied and left out."""
    phrases, last = [], None

    def ref(obj):
        return 'it' if obj == last else f'`{obj}`'

    n = len(actions)
    for i, a in enumerate(actions):
        name, s = str(a[0]), _symbols(a[1:])
        nxt = str(actions[i + 1][0]) if i + 1 < n else None
        if name == 'move':
            if nxt in ('pick', 'place', 'place_hiding', 'stack', 'sense', 'observe'):
                continue
            dest = s[0] if s else ''
            phrases.append('come home' if _is_home(dest) else f'go to {_place(dest)}')
        elif name == 'pick':
            obj = s[0] if s else '?'
            phrases.append('pick it up' if obj == last else f'pick up `{obj}`')
            last = obj
        elif name in ('place', 'place_hiding'):
            obj = s[0] if s else '?'
            dest = s[1] if len(s) > 1 else ''
            phrases.append(f'set {ref(obj)} down {_where(dest)}'.strip())
            last = obj
        elif name == 'stack':
            obj = s[0] if s else '?'
            phrases.append(f'stack {ref(obj)} on `{s[1]}`' if len(s) > 1
                           else f'stack {ref(obj)}')
            last = obj
        elif name == 'sense':
            if len(s) > 1:
                m = _SHADOW_OF.match(s[1])
                where = f'behind {ref(m.group(1))}' if m else f'into {_place(s[1])}'
                phrases.append(f'look {where} for `{s[0]}`')
            else:
                phrases.append('sense ' + ' '.join(s))
        elif name == 'observe':
            obj = s[0] if s else '?'
            phrases.append(f'look closer at {ref(obj)}')
            last = obj
        else:
            phrases.append(' '.join([name] + s))
    if len(phrases) > 8:
        phrases = phrases[:7] + [f'and {len(phrases) - 7} more steps']
    if not phrases:
        return ''
    if len(phrases) == 1:
        return phrases[0]
    return ', '.join(phrases[:-1]) + ', then ' + phrases[-1]


def _found_in(value):
    """A found region (the belief's status row) or belief.target_found_in
    as words; 'picked' (the pick's own overwrite) carries no place."""
    v = str(value)
    m = _SHADOW_OF.match(v)
    if m:
        return f'found behind `{m.group(1)}`'
    if re.match(r'free_\d+$', v):
        return 'found on a free spot'
    if v in ('None', '', 'picked'):
        return ''
    return 'found in plain view'


def _mission(goal):
    """The header's goal text ('holding dice at home', 'stack', ...) as
    the mission sentence."""
    g = (goal or '').strip()
    m = re.match(r'holding(?: (\S+))?( at home)?$', g)
    if m:
        target, home = m.group(1), bool(m.group(2))
        if target:
            return f'get hold of `{target}`' + (' and bring it home' if home else '')
        return 'find the hidden target and pick it up' + (', then come home' if home else '')
    if g.startswith('stack'):
        return 'build the tower'
    if g.startswith('find-and-tray-stack'):
        return 'find the hidden cube and stack it on the tray'
    return g or 'the mission'


def _short_path(path, limit):
    """A run directory for the closing line: relative to the repository,
    the middle elided to fit."""
    p = str(path).replace('\\', '/')
    repo = REPO.replace('\\', '/').rstrip('/') + '/'
    if p.startswith(repo):
        p = p[len(repo):]
    if limit is None or len(p) <= limit:
        return p
    parts = [x for x in p.split('/') if x]
    for cand in ('/'.join([parts[0], '...'] + parts[-2:]) if len(parts) > 3 else p,
                 '/'.join(['...'] + parts[-2:]) if len(parts) > 2 else p,
                 parts[-1] if parts else p):
        if len(cand) <= limit:
            return cand
    return parts[-1] if parts else p


# Narration lines shown as warnings, as printed.
_WARN = re.compile(
    r'^(ERROR\b|WARNING\b|PHYSICAL_FAILURE\b|NOTE:|\[warn\]'
    r'|\[pre-flight\]|\[D9\] the die is VISIBLE|\[eye\] snapshot .* failed)')

# sys.stderr lines mirrored to the terminal: argparse, the pre-flight and
# seed notes, the drivers' SystemExit messages.  Everything else written to
# stderr (Python warnings, TAMPURA's logging after our logger closed) stays
# in the debug file.
_STDERR_SHOW = re.compile(
    r'^(usage: |\S+: error: |\[pre-flight\]|\[warn\]|\[random-pairs'
    r'|G19:|G13 runtime check failed|ERROR\b|WARNING\b|PHYSICAL_FAILURE\b)')
_STDERR_WARN = re.compile(
    r'^(\[pre-flight\]|\[warn\]|G13 runtime check failed|ERROR\b|WARNING\b'
    r'|PHYSICAL_FAILURE\b)')


def _reason_rules():
    return (
        (re.compile(r'^IK failure during (place|stack)'),
         lambda m: f'no reachable arm pose for the {m.group(1)}'),
        (re.compile(r'^IK or grip failure during pick'),
         lambda m: 'no reachable grasp or the grip failed'),
        (re.compile(r'^drop-verify failed for (\S+)'),
         lambda m: 'the release did not verify'),
        (re.compile(r'^empty hand at (place|stack) entry'),
         lambda m: f'my hand was empty at the {m.group(1)}'),
        (re.compile(r'^pick failure (\d+)/3 for'),
         lambda m: f'pick failure {m.group(1)} of 3'),
        (re.compile(r'^transit loss (\d+)/3 for'),
         lambda m: f'I lost it on the way, loss {m.group(1)} of 3'),
        (re.compile(r'^stack failure (\d+)/3 for'),
         lambda m: f'stack failure {m.group(1)} of 3'),
        (re.compile(r'^\[M8\] (\S+) pose_radius .* outside its commit margin'),
         lambda m: f"`{m.group(1)}`'s pose is too uncertain, I should look first"),
        (re.compile(r'^ERROR: Cannot pick (\S+) .* gripper already holds (\S+)\.'),
         lambda m: f'I am still holding `{m.group(2)}`'),
        (re.compile(r'^ERROR: no registry estimate for (?:the held |the support )?(\S+)'),
         lambda m: f'I have no estimate where `{m.group(1)}` is'),
        (re.compile(r'^ERROR: Cannot resolve'),
         lambda m: 'a symbol did not resolve'),
    )


def _f20_role(role):
    if 'SEARCH TARGET' in role:
        return 'it is the target and I can pick it directly'
    m = re.search(r'with (\d+) shadow', role)
    return (f'it hides {_plural(m.group(1), "fragment")} of space behind it'
            if m else 'it is in the way of something')


_INTEGRITY = {
    'disturbed': 'was disturbed',
    'toppled': 'toppled over',
    'off_support': 'slid off its support',
    'knocked_off_table': 'was knocked off the table',
    'lost': 'is lost from view',
}


def _note_rules():
    return (
        (re.compile(r'^\[F20\] (\S+) is visible in this observation but had no '
                    r'boxel.*?\((\d+) px\); (.*)$'),
         lambda m: f'I can see `{m.group(1)}` now ({m.group(2)} px): '
                   f'{_f20_role(m.group(3))}'),
        (re.compile(r'^\[F20\] (\S+) is visible \((\d+) px\) but partly behind the arm'),
         lambda m: f'I can see `{m.group(1)}` but my arm is in the way, '
                   f'I will look again later'),
        (re.compile(r'^\[F20\] (\S+) is visible \((\d+) px\) but lies below the table'),
         lambda m: f'`{m.group(1)}` shows below the table, I am ignoring that'),
        (re.compile(r'^\[integrity\] (\w+): (\S+) after'),
         lambda m: f'`{m.group(2)}` '
                   f'{_INTEGRITY.get(m.group(1), m.group(1).replace("_", " "))}'),
        (re.compile(r'^\[integrity\] (\S+) disturbed (\d+) times in this plan'),
         lambda m: f'I have disturbed `{m.group(1)}` {m.group(2)} times this plan, '
                   f'I will not replan for it again'),
        (re.compile(r'^-> (\S+): object boxel \+ (\d+) shadow'),
         lambda m: f'I registered `{m.group(1)}`, with '
                   f'{_plural(m.group(2), "fragment")} of space behind it'),
        (re.compile(r'^Grip verified for (\S+):.*measured half-width ([\d.]+) mm '
                    r'vs estimate ([\d.]+) mm'),
         lambda m: f'I have a firm grip on `{m.group(1)}`: its half-width is '
                   f'{m.group(2)} mm, I expected {m.group(3)} mm'),
        (re.compile(r'^\[release-obs\] (\S+)(?: on \S+)?: observed (\d+) px.*shift ([\d.]+) mm'),
         lambda m: (f'`{m.group(1)}` is where I put it ({m.group(2)} px)'
                    if float(m.group(3)) < 0.5 else
                    f'`{m.group(1)}` shifted {m.group(3)} mm as I let go ({m.group(2)} px)')),
        (re.compile(r'^\[M10\] (\S+) touched by the pads'),
         lambda m: f'my pads touched `{m.group(1)}`, its pose is uncertain now'),
        (re.compile(r'^\[M8\] observe strike (\d+)/3 for (\S+); look (\S+) removed(.*)'),
         lambda m: f'that look did not show `{m.group(2)}` well, strike '
                   f'{m.group(1)} of 3' + (', I am giving up on looking at it'
                                           if 'PARKED' in m.group(4) else '')),
        (re.compile(r'^\[M8\] observe strikes of (\S+) reset'),
         lambda m: f'`{m.group(1)}` moved or was re-registered, I forget my '
                   f'strikes on it'),
        (re.compile(r'^giveup parole (\d+)/2: (\S+)'),
         lambda m: f'`{m.group(2)}` gets another chance after 4 replans '
                   f'(parole {m.group(1)} of 2)'),
        (re.compile(r'^stop_before_planning: returning'),
         lambda m: 'stopping before planning, as asked'),
        (re.compile(r'^\[D7\] initial arm readback is not at q_home(.*)$'),
         lambda m: f'my arm is not at home to begin with{m.group(1)}'),
    )


# Phase 3 and 4 narration: what the robot sees and is after.
_SCENE = re.compile(r'^(\d+) boxels, (\d+) shadows, (\d+) occluders$')
_TARGET_GIVEN_HIDDEN = re.compile(
    r'^Target: (\S+) \(given; not in the first observation; the robot must search\)')
_TARGET_SEEN = re.compile(r'^Target: (\S+) at boxel (\S+) \((?:given; in the first '
                          r'observation, direct pick|direct pick)\)')
_TARGET_HIDDEN = re.compile(r'^Target: (\S+)$')
_ORACLE_IN = re.compile(r'^ORACLE: Actually hidden in (\S+)')
_ORACLE_OUT = re.compile(r'^ORACLE: Actually hidden by camera-ray occlusion but inside NO shadow')
_GOAL_LINE = re.compile(r'^(Stack goal|Find-and-tray-stack goal|2-cube tray tower): (.*)$')

# The planning loop's narration: the thinking line's trigger and context.
_PLAN_START = re.compile(r'^=== PLAN #(\d+) ===$')
_UNKNOWN = re.compile(r'^Unknown shadows remaining: (\d+)$')
_KNOWN_LOC = re.compile(r'^no unknown shadows remain, but (\S+) is registered')
_PROGRESS = re.compile(r'^(Tray-stack progress|Stack progress): (.*)$')
_DISPOSAL = re.compile(r'^no mission plan with (\S+) held')

_RESULT_ROW = re.compile(r'^(Target|Found in|Shadows searched|Stack goal|'
                         r'Final on-relations|Plans executed): (.*)$')

_SENSE_TEXT = {
    'sense_found_target': 'found it',
    'sense_clear_but_empty': 'nothing there, replanning',
    'sense_contains_nontarget': 'something else is in there, replanning',
    'sense_still_blocked': 'I still cannot see in, replanning',
    'sense_missing_shadow': 'that space is gone, replanning',
    'sense_contains_unlocalizable': 'something I cannot place is in there, replanning',
}

# How a dispatched step ended (run_logger.STEP_END_STATUSES), as the
# console says it; the failure texts take the narration's reason.
_COMPLETED = frozenset(('ok', 'sense_outcome', 'observe_ok', 'observe_incomplete',
                        'integrity_replan'))
_STATUS_TEXT = {
    'ok': 'done',
    'sense_outcome': 'replanning on what I saw',
    'observe_ok': 'seen',
    'observe_incomplete': 'I could not see it well, replanning',
    'integrity_replan': 'done, but something moved: replanning',
    'motion_resolve_failed': 'no motion from where my arm is, replanning',
    'pick_failure': 'failed: {reason}, replanning',
    'place_failure': 'failed: {reason}, replanning',
    'stack_failure': 'failed: {reason}, replanning',
    'empty_hand': 'failed: {reason}, replanning',
    'stale_precondition': 'skipped: {reason}, replanning',
    'home_not_reached': 'not at home twice in a row, I am giving up',
    'unlabelled': 'ended without a label',
}
_DEFAULT_REASON = {
    'pick_failure': 'no reachable grasp or the grip failed',
    'place_failure': 'no reachable pose or the release did not verify',
    'stack_failure': 'no reachable pose or the release did not verify',
    'empty_hand': 'my hand was empty',
    'stale_precondition': 'a precondition no longer holds',
}
# The bridge's gate table (tools/bridge_gates.Report.show) and its outcome
# line: a captured console keeps them as printed, the terminal gets one
# verdict line and one tidy outcome line.
_GATE_ROW = re.compile(r'^(\w+)\s+(PASS|FAIL|SKIP|WARN|INFO)\b\s*(.*)$')
_OUTCOME = re.compile(r'^seed (\d+): outcome (\w+), their RolloutHistory rewards\[-1\] = (\S+); '
                      r'details in (.+)$')


# ---------------------------------------------------------------------------
# glyphs, colours and the drawing
# ---------------------------------------------------------------------------

_GLYPHS = {
    # name: (unicode, ascii)
    'bullet': ('●', '*'),        # ●
    'think': ('✻', '~'),         # ✻
    'sub': ('⎿', '|_'),          # ⎿
    'warn': ('⚠', '!'),          # ⚠
    'ok': ('✔', '+'),            # ✔
    'bad': ('✘', 'x'),           # ✘
    'ell': ('…', '...'),         # …
    'rule': ('─', '-'),          # ─
    'heavy': ('━', '='),         # ━
    'box': ('▣', '#'),           # ▣
    'dot': ('·', '.'),           # ·
}
_STARS = ('·', '✢', '✳', '✶', '✻', '✽')   # · ✢ ✳ ✶ ✻ ✽
_STARS_ASCII = ('.', '+', '*', 'x', '*', '+')

# The boxel: an isometric cube, 5 rows by 8 columns.  _CUBE_LOOP walks its
# silhouette (the running light follows it); _CUBE_INNER are the edges of
# the front face inside the silhouette.
_CUBE = (
    '  ╭────╮',
    ' ╱    ╱│',
    '╭────╮ │',
    '│    │╱ ',
    '╰────╯  ',
)
_CUBE_ASCII = (
    '  +----+',
    ' /    /|',
    '+----+ |',
    '|    |/ ',
    '+----+  ',
)
_CUBE_LOOP = ((2, 0), (1, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (0, 7),
              (1, 7), (2, 7), (3, 6), (4, 5), (4, 4), (4, 3), (4, 2), (4, 1),
              (4, 0), (3, 0))
_CUBE_INNER = frozenset(((1, 6), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (3, 5)))
_CUBE_W = 8
_LIGHT_LEN = 4

_CODES = {
    'bold': '1', 'dim': '2', 'red': '31', 'green': '32', 'yellow': '33',
    'blue': '34', 'magenta': '35', 'cyan': '36', 'white': '37',
    'bred': '91', 'bgreen': '92', 'byellow': '93', 'bblue': '94',
    'bmagenta': '95', 'bcyan': '96', 'bwhite': '97',
    'obj': '1', 'title': '1;97', 'brand': '1;96',
    'hi_blue': '1;94', 'hi_magenta': '1;95', 'hi_cyan': '1;96', 'hi_green': '1;92',
    'dim_blue': '2;34', 'dim_magenta': '2;35', 'dim_cyan': '2;36', 'dim_green': '2;32',
}
# The same styles on a 256-colour terminal: fixed palette indices (16 to
# 255 look the same in every terminal), so a terminal theme that hides some
# of its 16 ANSI colours (the app's terminal pane showed the cyan and green
# text as nothing, 2026-10-30) cannot hide the console.
_CODES_256 = {
    'bold': '1', 'dim': '2',
    'red': '38;5;167', 'green': '38;5;71', 'yellow': '38;5;178', 'blue': '38;5;68',
    'magenta': '38;5;133', 'cyan': '38;5;73', 'white': '38;5;252',
    'bred': '38;5;203', 'bgreen': '38;5;114', 'byellow': '38;5;221', 'bblue': '38;5;111',
    'bmagenta': '38;5;177', 'bcyan': '38;5;80', 'bwhite': '38;5;231',
    'obj': '1', 'title': '1;38;5;231', 'brand': '1;38;5;80',
    'hi_blue': '1;38;5;111', 'hi_magenta': '1;38;5;177', 'hi_cyan': '1;38;5;80',
    'hi_green': '1;38;5;114',
    'dim_blue': '2;38;5;68', 'dim_magenta': '2;38;5;133', 'dim_cyan': '2;38;5;73',
    'dim_green': '2;38;5;71',
}
# The activities' colours: the cube's edges, its inner edges, the light.
_PALETTE = {
    'startup': ('blue', 'dim_blue', 'hi_blue'),
    'think': ('magenta', 'dim_magenta', 'hi_magenta'),
    'act': ('cyan', 'dim_cyan', 'hi_cyan'),
}


class _Style:
    """ANSI colour, only on a terminal (NO_COLOR, FORCE_COLOR and TERM=dumb
    honoured); `extra` maps the sprites' colour keys to their SGR codes."""

    def __init__(self, enabled, extra=None, depth=16):
        self.enabled = enabled
        self.extra = extra or {}
        self.codes = _CODES_256 if depth >= 256 else _CODES

    def __call__(self, text, style):
        code = (self.extra.get(style) or self.codes.get(style)) if style else None
        if not self.enabled or not text or code is None:
            return text
        return f'\033[{code}m{text}\033[0m'


def _color_depth():
    """256 colours where the terminal says so (the sprites' palette), else
    the 16 ANSI colours."""
    term = os.environ.get('TERM', '')
    if (os.name == 'nt' or '256color' in term or 'truecolor' in term
            or os.environ.get('COLORTERM', '') in ('truecolor', '24bit')
            or os.environ.get('WT_SESSION')):
        return 256
    return 16


def _load_art():
    """console_art's sprites, palette and ASCII map, or empty ones (the
    boxel cube then stands in for every activity)."""
    try:
        import console_art
        return (dict(console_art.SPRITES), dict(console_art.PALETTE),
                dict(console_art.ASCII_MAP))
    except Exception:
        return {}, {}, {}


def _start_audio():
    """console_audio's Audio (8-bit music and effects that follow the run,
    and Windows' voice when asked; see there) when SB_AUDIO or SB_VOICE
    asks for it, else None."""
    try:
        import console_audio
        flags = console_audio.wanted()
        if not flags:
            return None
        return console_audio.Audio(music=flags[0], sfx=flags[1], speech=flags[2])
    except Exception:
        return None


def _color_wanted(fd):
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    try:
        if not os.isatty(fd):
            return False
    except OSError:
        return False
    return os.environ.get('TERM', '') != 'dumb'


def _unicode_wanted():
    if os.environ.get('SB_CONSOLE_ASCII'):
        return False
    if os.name == 'nt':
        return True
    loc = (os.environ.get('LC_ALL') or os.environ.get('LC_CTYPE')
           or os.environ.get('LANG') or '')
    return 'utf' in loc.lower()


def _mark(text, style=None):
    """Text with `object names` marked up, as (text, style) parts."""
    parts = []
    for i, seg in enumerate(str(text).split('`')):
        if seg:
            parts.append((seg, 'obj' if i % 2 else style))
    return parts


def _plain(parts):
    return ''.join(t for t, _ in parts)


def _wrap(parts, width, indent, hang):
    """Greedy word wrap of styled parts into rows; the first row is
    indented by `indent`, the others by `hang`.  width None: one row."""
    if width is None:
        return [[(' ' * indent, None)] + list(parts)]
    tokens = []
    for text, style in parts:
        for tok in re.findall(r'\S+\s*|\s+', text):
            tokens.append((tok, style))
    rows, cur, cur_len, first = [], [], 0, True
    for tok, style in tokens:
        avail = max(8, width - (indent if first else hang))
        if cur and cur_len + len(tok.rstrip()) > avail:
            rows.append(cur)
            cur, cur_len, first = [], 0, False
            tok = tok.lstrip()
            if not tok:
                continue
        cur.append((tok, style))
        cur_len += len(tok)
    if cur or not rows:
        rows.append(cur)
    out = []
    for i, row in enumerate(rows):
        out.append([(' ' * (indent if i == 0 else hang), None)] + row)
    return out


def _clip(parts, limit, ell):
    """Parts cut to `limit` columns, with an ellipsis when cut."""
    if limit is None or len(_plain(parts)) <= limit:
        return list(parts)
    out, used = [], 0
    for text, style in parts:
        room = limit - len(ell) - used
        if room <= 0:
            break
        if len(text) > room:
            out.append((text[:room], style))
            used += room
            break
        out.append((text, style))
        used += len(text)
    out.append((ell, 'dim'))
    return out


# ---------------------------------------------------------------------------
# streams
# ---------------------------------------------------------------------------

class _StderrTee:
    """sys.stderr while the console is installed: everything goes to the
    real stderr (the debug file), and the lines _STDERR_SHOW names are
    mirrored to the terminal, an argparse usage block as a whole."""

    def __init__(self, original, console):
        self._original = original
        self._console = console
        self._buf = ''
        self._in_usage = False

    def write(self, text):
        try:
            self._original.write(text)
        except Exception:
            pass
        self._buf += text
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            self._line(line.rstrip('\r'))
        return len(text)

    def _line(self, line):
        show = bool(_STDERR_SHOW.match(line))
        if line.startswith('usage: '):
            self._in_usage = True
        elif self._in_usage and line.startswith((' ', '\t')):
            show = True
        else:
            self._in_usage = False
        if not show:
            return
        if _STDERR_WARN.match(line):
            self._console.warn(line)
        else:
            self._console.say(line)

    def flush(self):
        if self._buf:
            self._line(self._buf)
            self._buf = ''
        try:
            self._original.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def fileno(self):
        return self._original.fileno()

    def __getattr__(self, name):
        return getattr(self._original, name)


class _TerminalWriter:
    """sys.stdout inside terminal(): complete lines go out as console lines."""

    def __init__(self, console):
        self._console = console
        self._buf = ''

    def write(self, text):
        self._buf += text
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            self._say(line.rstrip('\r'))
        return len(text)

    def flush(self):
        if self._buf:
            self._say(self._buf)
            self._buf = ''

    def _say(self, line):
        try:
            self._console.say(line)
        except Exception:
            pass

    def isatty(self):
        return False


class _ConsoleHandler(logging.Handler):
    """ERROR and above from the logging tree, one line each; WARNING
    records (the streams' per-call collision notes, dozens per plan) stay
    in the run log."""

    def __init__(self, console):
        super().__init__(level=logging.ERROR)
        self._console = console

    def emit(self, record):
        try:
            text = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                e = record.exc_info[1]
                text += f': {type(e).__name__}: {e} (traceback in the run log)'
            self._console.warn(f'{record.levelname.lower()}: {text}')
        except Exception:
            pass


def _c_stdio_line_buffered():
    """Best effort: C stdio's stdout line-buffered, so pybullet's printf
    lines reach the debug file in order and survive a crash (a file target
    would otherwise be fully buffered)."""
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        libc.fflush(None)
        libc.setvbuf(ctypes.c_void_p.in_dll(libc, 'stdout'), None, 1, 0)
    except Exception:
        pass


def _c_stdio_flush():
    try:
        import ctypes
        ctypes.CDLL(None).fflush(None)
    except Exception:
        pass


def _early_debug_path():
    try:
        os.makedirs(EARLY_DIR, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix='console_debug_', suffix='.log',
                                    dir=EARLY_DIR)
    except OSError:
        fd, path = tempfile.mkstemp(prefix='console_debug_', suffix='.log')
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# the console
# ---------------------------------------------------------------------------

class Console:
    def __init__(self, debug_path=None):
        self._in_run_dir = debug_path is not None
        self.debug_path = debug_path
        self.log_path = None
        self.run_id = None
        self.context = {}
        self._owned = False
        self._t0 = time.perf_counter()
        self._handler = None
        self._closed = False
        self._crash_reported = False
        self._lock = threading.RLock()
        # the terminal and the files, taken over in _take_over
        self._saved = None
        self._term_fd = None
        self._tty = False
        self.term = None
        self.debug = None
        self._orig_stderr = None
        self._orig_excepthook = None
        self._orig_sigint = None
        self._style = _Style(False)
        self._uni = _unicode_wanted()

        # the animation
        self._live = None             # the current activity, or None
        self._frame = 0
        self._anim = None
        self._anim_stop = threading.Event()
        self._cursor_hidden = False
        self._echo_was_on = False
        self._art, self._art_palette, self._ascii = _load_art()
        self._art_w = max([_CUBE_W] + [int(s.get('width', 0)) for s in self._art.values()])
        self._audio = None            # console_audio.Audio when SB_AUDIO or SB_VOICE asks for it

        # what the robot knows for its narration (nothing here feeds back)
        self._goal_text = None
        self._goal_kind = None
        self._goal_at_home = False
        self._target = None
        self._holding = None
        self._known_loc = False
        self._unknown = None
        self._progress = None
        self._reasons = []
        self._step = None             # the open step: dict(action, t0, args)
        self._sense_text = None
        self._observe_text = None
        self._plan_len = {}
        self._plan_no = None
        self._thinking = None         # dict(title parts, info) while a plan is thought about
        self._plans = 0
        self._plans_found = 0
        self._dispatched = 0
        self._completed = 0
        self._failed = 0
        self._in_result = False
        self._result = None           # ('success', None) or ('failed', text)
        self._result_rows = {}
        self._found_region = None     # the belief's 'found' region, when sensed
        self._gates = []              # the bridge's gate rows, held for one verdict line
        self._reason_rules = _reason_rules()
        self._note_rules = _note_rules()

        atexit.register(self._at_exit)
        # From here on the terminal is changed; a failure rolls that back
        # (close) and install() leaves the console out.
        try:
            self._take_over(debug_path)
            self._audio = _start_audio()
            self._banner()
            self._sfx('startup')
            self._say('Semantic Boxels, starting up.', important=True)
            self._start_live('startup', self._parts([(self.g('bullet') + ' ', 'cyan')]
                                                    + _mark(f"Starting up{self.g('ell')}")),
                             ['the simulator, the eye and the planner'])
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def _take_over(self, debug_path):
        """The terminal: a duplicate of fd 1 (restored on close) becomes the
        console's own stream; the debug file takes fds 1 and 2, so every
        later write to them, from Python or C, lands there; sys.stderr is
        teed and the excepthook replaced."""
        if debug_path is None:
            debug_path = _early_debug_path()
        self.debug_path = debug_path
        for s in (sys.stdout, sys.stderr):
            try:
                s.flush()
            except Exception:
                pass
        self._saved = (os.dup(1), os.dup(2))
        self._term_fd = os.dup(1)
        try:
            self._tty = os.isatty(self._term_fd)
        except OSError:
            self._tty = False
        self._style = _Style(_color_wanted(self._term_fd), self._art_codes(), _color_depth())
        self.term = io.open(self._term_fd, 'w', buffering=1, encoding='utf-8',
                            errors='replace', closefd=True)
        self.debug = open(debug_path, 'w', buffering=1, encoding='utf-8',
                          errors='replace')
        os.dup2(self.debug.fileno(), 1)
        os.dup2(self.debug.fileno(), 2)
        _c_stdio_line_buffered()
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(line_buffering=True)
            except Exception:
                pass
        self._orig_stderr = sys.stderr
        sys.stderr = _StderrTee(self._orig_stderr, self)
        self._orig_excepthook = sys.excepthook
        sys.excepthook = self._excepthook
        # Ctrl-C ends the process at once, at the kernel level (SIG_DFL),
        # instead of raising KeyboardInterrupt: a run whose GUI window was
        # closed busy-waits in PyBullet's C client and never runs Python
        # again, so Python's handler would never fire and the process would
        # outlive its terminal at full CPU (BF#51).  Under WSL the key never
        # reaches the Windows side either (wsl.exe forwards it as SIGINT), so
        # this is the one place that can make Ctrl-C reliable.  The files
        # are line buffered; an interrupted run needs no tidy ending.
        if threading.current_thread() is threading.main_thread():
            try:
                self._orig_sigint = signal.signal(signal.SIGINT, signal.SIG_DFL)
            except Exception:
                self._orig_sigint = None

    def _art_codes(self):
        """The sprites' colour keys as styles ('art_o' and so on)."""
        depth = _color_depth()
        codes = {}
        for key, (c256, c16) in self._art_palette.items():
            code = c256 if depth >= 256 else c16
            if code:
                codes['art_' + key] = code
        return codes

    # ----- glyphs and geometry ----------------------------------------------

    def g(self, name):
        return _GLYPHS[name][0 if self._uni else 1]

    def _star(self):
        stars = _STARS if self._uni else _STARS_ASCII
        return stars[(self._frame // 2) % len(stars)]

    def _geometry(self):
        """(columns, rows) of the terminal, or (None, None) for a captured
        console."""
        if not self._tty:
            return None, None
        try:
            sz = os.get_terminal_size(self._term_fd)
        except (OSError, ValueError):
            return None, None
        if sz.columns <= 0 or sz.lines <= 0:
            return None, None         # a pty whose size was never set
        return sz.columns, sz.lines

    def _cols(self):
        return self._geometry()[0]

    @staticmethod
    def _parts(parts):
        return list(parts)

    # ----- lifecycle -------------------------------------------------------

    def attach(self, run_dir, log_path, owned):
        with self._lock:
            self.run_id = os.path.basename(str(run_dir).rstrip('/\\'))
            self.log_path = str(log_path)
            self.run_dir = str(run_dir)
            self._owned = self._owned or owned
            target = os.path.join(str(run_dir), DEBUG_NAME)
            if os.path.abspath(target) != os.path.abspath(self.debug_path):
                self._relocate(target)
            self._handler = _ConsoleHandler(self)
            if self._live is not None and self._live['kind'] == 'startup':
                self._end_live([('ready', 'green'),
                                (f"  ({_secs(time.perf_counter() - self._t0)})", 'dim')])
                self._sfx('ready')

    def log_handler(self):
        """The ERROR-and-above handler for the root logger (RunLogger adds
        it after its own, since it resets the root's handlers)."""
        if self._handler is None:
            self._handler = _ConsoleHandler(self)
        return self._handler

    def _relocate(self, target):
        """Move the debug file (everything captured so far) next to the
        run log and point fds 1 and 2 at the new file."""
        old_path, old = self.debug_path, self.debug
        _c_stdio_flush()
        for s in (sys.stdout, old):
            try:
                s.flush()
            except Exception:
                pass
        new = open(target, 'wb')
        with open(old_path, 'rb') as src:
            shutil.copyfileobj(src, new)
            copied = src.tell()
        new.close()
        self.debug = open(target, 'a', buffering=1, encoding='utf-8',
                          errors='replace')
        os.dup2(self.debug.fileno(), 1)
        os.dup2(self.debug.fileno(), 2)
        # Anything written to the old file between the copy and the
        # redirect (another thread's print) follows.
        try:
            old.close()
            with open(old_path, 'rb') as src:
                src.seek(copied)
                tail = src.read()
            if tail:
                self.debug.flush()
                with open(target, 'ab') as dst:
                    dst.write(tail)
            os.unlink(old_path)
        except OSError:
            pass
        self.debug_path = target
        self._in_run_dir = True

    def _at_exit(self):
        """A start that never reached a run directory names its debug file
        (the crash line did so already when a crash ended it)."""
        if self._closed:
            return
        try:
            with self._lock:
                self._gate_verdict()
                self._end_live(None)
                self._show_cursor()
                if not self._in_run_dir and not self._crash_reported:
                    self._emit([(f'(raw stdout and stderr of this start: '
                                 f'{self.debug_path})', 'dim')])
        except Exception:
            pass

    def detach(self):
        """The run is over: the live activity is committed and the logging
        handler removed; a console the RunLogger installed itself goes
        away."""
        with self._lock:
            self._end_live(None)
            self._step = None
        if self._handler is not None:
            try:
                logging.getLogger().removeHandler(self._handler)
            except Exception:
                pass
            self._handler = None
        if self._owned:
            uninstall()

    def close(self):
        """Restore the terminal, the streams and the hook; safe on a console
        whose take-over stopped half way."""
        if self._closed:
            return
        self._anim_stop.set()
        if self._anim is not None and self._anim is not threading.current_thread():
            self._anim.join(timeout=1.0)
        with self._lock:
            self._closed = True
            try:
                self._gate_verdict()
                self._end_live(None)
                self._show_cursor()
            except Exception:
                pass
            try:
                self.term.flush()
            except Exception:
                pass
            # a bound method is a new object at every access: compare, never `is`
            if self._orig_excepthook is not None and sys.excepthook == self._excepthook:
                sys.excepthook = self._orig_excepthook
            if (self._orig_sigint is not None
                    and threading.current_thread() is threading.main_thread()):
                try:
                    if signal.getsignal(signal.SIGINT) is signal.SIG_DFL:
                        signal.signal(signal.SIGINT, self._orig_sigint)
                except Exception:
                    pass
                self._orig_sigint = None
            if isinstance(sys.stderr, _StderrTee) and sys.stderr._console is self:
                sys.stderr.flush()
                sys.stderr = self._orig_stderr
            try:
                sys.stdout.flush()
            except Exception:
                pass
            _c_stdio_flush()
            if self._saved is not None:
                os.dup2(self._saved[0], 1)
                os.dup2(self._saved[1], 2)
                for fd in self._saved:
                    os.close(fd)
                self._saved = None
            for f in (self.debug, self.term):
                try:
                    f.close()
                except Exception:
                    pass
            if self._audio is not None:
                try:
                    self._audio.drain(1.0)
                    self._audio.close()
                except Exception:
                    pass

    def finish(self):
        """Before os._exit (console_ui.finish): the verdict out, the live
        block ended, the exit handlers run (ours included), everything
        flushed; the voice gets to say its last sentence."""
        try:
            with self._lock:
                self._gate_verdict()
                self._end_live(None)
                self._show_cursor()
        except Exception:
            pass
        try:
            atexit._run_exitfuncs()
        except Exception:
            pass
        self._flush_all()
        if self._audio is not None:
            try:
                self._audio.drain(6.0)
                self._audio.close()
            except Exception:
                pass

    def _excepthook(self, exc_type, exc, tb):
        self._crash_reported = True
        try:
            with self._lock:
                self._end_live(None)
                if issubclass(exc_type, KeyboardInterrupt):
                    self._emit([(self.g('bad') + ' ', 'red'), ('Interrupted.', 'red')])
                else:
                    self._emit([(self.g('bad') + ' ', 'red'),
                                (f'Crashed: {exc_type.__name__}: {exc}', 'red')])
                    self._emit([(f'(traceback in {self.debug_path})', 'dim')], indent=2)
                self._show_cursor()
        except Exception:
            pass
        self._orig_excepthook(exc_type, exc, tb)
        if issubclass(exc_type, KeyboardInterrupt):
            # A Ctrl-C under the GUI used to end in pybullet's teardown
            # segfault (and bash's 'Segmentation fault' line with the whole
            # command); the files are flushed and the process ends here.
            self._flush_all()
            if self._audio is not None:
                try:
                    self._audio.close()
                except Exception:
                    pass
            os._exit(130)

    def _flush_all(self):
        for f in (sys.stdout, sys.stderr, self.debug, self.term):
            try:
                f.flush()
            except Exception:
                pass
        try:
            logging.shutdown()
        except Exception:
            pass
        _c_stdio_flush()

    # ----- writing ---------------------------------------------------------

    def _render(self, parts):
        return ''.join(self._style(t, s) for t, s in parts)

    def _write_raw(self, text):
        try:
            self.term.write(text)
            self.term.flush()
        except Exception:
            pass

    def _mirror(self, plain):
        try:
            self.debug.write('[console] ' + plain + '\n')
        except Exception:
            pass

    def _say(self, text, important=False):
        """The voice, when there is one: important sentences are always
        spoken, the others dropped while the robot is ahead of its voice."""
        if self._audio is not None:
            try:
                self._audio.say(text, important=important)
            except Exception:
                pass

    def _sfx(self, name):
        """An effect (console_audio.PIECES), when there is sound."""
        if self._audio is not None:
            try:
                self._audio.sfx(name)
            except Exception:
                pass

    def _music(self, name):
        """The loop for what the robot does now ('act', 'think', None)."""
        if self._audio is not None:
            try:
                self._audio.music(name)
            except Exception:
                pass

    def _hide_cursor(self):
        if self._tty and not self._cursor_hidden:
            self._write_raw('\033[?25l')
            self._cursor_hidden = True
            self._echo_off()

    def _show_cursor(self):
        if self._cursor_hidden:
            self._write_raw('\033[?25h')
            self._cursor_hidden = False
            self._echo_on()

    def _echo_off(self):
        """No keyboard echo while the block is drawn: an echoed Enter would
        move the cursor under the block and the erase would miss a row.
        Typed keys stay queued for the shell."""
        try:
            import termios
            fd = self._term_fd
            if os.tcgetpgrp(fd) != os.getpgrp():    # a background job must not touch it
                return
            attrs = termios.tcgetattr(fd)
            if attrs[3] & termios.ECHO:
                attrs[3] &= ~termios.ECHO
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
                self._echo_was_on = True
        except Exception:
            pass

    def _echo_on(self):
        if not self._echo_was_on:
            return
        self._echo_was_on = False
        try:
            import termios
            attrs = termios.tcgetattr(self._term_fd)
            attrs[3] |= termios.ECHO
            termios.tcsetattr(self._term_fd, termios.TCSANOW, attrs)
        except Exception:
            pass

    def _write_rows(self, rows):
        """Committed rows (each ends the line) to the terminal and, as one
        plain line, to the mirror."""
        for row in rows:
            self._write_raw(self._render(row) + '\n')

    def _emit(self, parts, indent=0, hang=None):
        """One committed line, wrapped to the terminal; parts are (text,
        style) pairs.  A live block steps aside and is redrawn below."""
        hang = indent + 2 if hang is None else hang
        with self._lock:
            self._stand_aside()
            cols = self._cols()
            rows = _wrap(parts, (cols - 1) if cols else None, indent, hang)
            self._write_rows(rows)
            self._mirror(' ' * indent + _plain(parts))
            self._redraw_live()

    def say(self, text):
        m = _GATE_ROW.match(text)
        if m:
            if not self._tty:
                self._emit([(text, None)], indent=2)     # the table as printed
                return
            # On the terminal the table becomes one verdict line (the next
            # other line flushes it); the rows stay in the record.
            self._gates.append((m.group(1), m.group(2), m.group(3).strip()))
            self._mirror('  ' + text)
            return
        self._gate_verdict()
        m = _OUTCOME.match(text)
        if m and self._tty:
            seed, status, reward, where = m.groups()
            cols = self._cols()
            self._mirror(text)
            self._emit([(self.g('sub') + ' ', 'dim'), ('TAMPURA scores the episode: ', None),
                        (status, 'bgreen' if status == 'success' else 'bred'),
                        (f', reward {reward}', None),
                        (f' {self.g("dot")} episode files in '
                         f'{_short_path(where, max(24, cols - 48) if cols else None)}', 'dim')],
                       indent=2, hang=4)
            return
        if text.startswith('G19:'):
            # Verbatim at the line start, and plain in a captured console
            # whatever FORCE_COLOR says: the campaign's console reader
            # looks for '^G19: seed'.
            self._emit([(text, 'yellow' if self._tty else None)])
        else:
            self._emit([(text, None)])

    def _gate_verdict(self):
        """The gate rows held back by say(), as one line: every gate
        passes, or the failing and warning ones named."""
        rows, self._gates = self._gates, []
        if not rows:
            return
        bad = [(g, s, d) for g, s, d in rows if s in ('FAIL', 'WARN')]
        if not bad:
            self.statement(f'My ledger passes all {_plural(len(rows), "gate")}.')
            return
        ell = self.g('ell')
        named = ', '.join(f'{g} {s.lower()}' + (f' ({d if len(d) <= 60 else d[:59] + ell})' if d else '')
                          for g, s, d in bad)
        n_ok = len(rows) - len(bad)
        text = f'My ledger: {named}; {_plural(n_ok, "gate")} {"passes" if n_ok == 1 else "pass"}.'
        self.warn(text)
        self._say(text, important=True)

    def warn(self, text):
        self._sfx('warn')
        if text.startswith('G19:'):
            self._emit([(text, 'yellow' if self._tty else None)])
            return
        self._emit([(self.g('warn') + ' ', 'yellow'), (text, 'yellow')])

    def note(self, text, style=None):
        """A sub line under the current step or statement."""
        self._emit([(self.g('sub') + ' ', 'dim')] + _mark(text, style), indent=2, hang=4)

    def statement(self, text, style=None):
        self._emit([(self.g('bullet') + ' ', 'cyan')] + _mark(text, style))
        self._say(text, important=True)

    def startup_note(self, text):
        # Their scene file, in words on the terminal; a captured console
        # keeps 'Loading scene from <file>' for the campaign's reader.
        m = (re.match(r'^Loading scene from (\S+?)(?:\.json)?(?:\s+(\(.*\)))?$', text)
             if self._tty else None)
        if m:
            text = f"loading TAMPURA's scene {m.group(1)}" + (f' {m.group(2)}' if m.group(2) else '')
        self.note(text)

    # ----- the live activity (the animated block) ---------------------------

    def _start_live(self, kind, head, info, sprite=None):
        """Begin an activity: the head line is committed (full view) or
        pending (narrow and captured views) and the status animates until
        _end_live.  `sprite` names the drawing (console_art); the kind's
        name by default, the boxel cube when no sprite fits."""
        with self._lock:
            self._end_live(None)
            cols, rows = self._geometry()
            if cols is None:
                mode = 'static'
            elif cols >= BLOCK_MIN_COLS and rows >= BLOCK_MIN_ROWS:
                mode = 'block'
            else:
                mode = 'line'
            head_plain = _plain(head)
            t0 = time.perf_counter()
            live = {'kind': kind, 'head': list(head), 'head_plain': head_plain,
                    'info': list(info), 't0': t0, 'mode': mode,
                    'sprite': sprite or kind, 'frame0': self._frame,
                    'drawn': 0, 'committed': False, 'intervened': False,
                    'fits': cols is not None and len(head_plain) <= cols - 1,
                    # the drawing appears only when the activity lasts (a
                    # quick step keeps its one line, no flicker)
                    'show_at': t0 + SHOW_AFTER_S}
            self._live = live
            if mode == 'block':
                self._write_rows(_wrap(head, cols - 1, 0, 2))
                self._mirror(head_plain)
                live['committed'] = True
            elif mode == 'line':
                # A head that leaves no room for the status is committed
                # and the status gets its own short row; otherwise the head
                # is the pending row the status is appended to.
                if len(head_plain) + 14 > cols - 1:
                    self._write_rows(_wrap(head, cols - 1, 0, 2))
                    self._mirror(head_plain)
                    live['committed'] = True
                else:
                    self._write_raw(self._render(head))
                    live['drawn'] = 1
            else:
                self._write_raw(self._render(head))
            if mode != 'static':
                self._hide_cursor()
                self._ensure_animator()

    def _update_live(self, info=None, head=None):
        with self._lock:
            if self._live is None:
                return
            if info is not None:
                self._live['info'] = list(info)
            if head is not None and not self._live['committed']:
                self._live['head'] = list(head)
                self._live['head_plain'] = _plain(head)
            self._redraw_live()

    def _commit_head(self, live):
        """A pending head line becomes a committed one.  In the captured
        view the head is on the terminal already (it only lacks its line
        end); in the narrow view its row was just erased."""
        if live['committed']:
            return
        if live['mode'] == 'static':
            self._write_raw('\n')
        else:
            self._write_raw(self._render(live['head']) + '\n')
        self._mirror(live['head_plain'])
        live['committed'] = True

    def _stand_aside(self):
        """Before a committed line is written: the live drawing is erased
        and a pending head is committed."""
        live = self._live
        if live is None:
            return
        self._erase_live()
        self._commit_head(live)
        live['intervened'] = True

    def _end_live(self, completion):
        """End the activity; `completion` (parts) is appended to the head
        line when nothing came between, else written as a sub line.  None
        commits the head without a completion."""
        with self._lock:
            live = self._live
            if live is None:
                return
            self._erase_live()
            self._live = None
            if completion is None:
                self._commit_head(live)
                self._show_cursor()
                return
            comp_plain = _plain(completion)
            cols = self._cols()
            joined = f"{live['head_plain']} {comp_plain}"
            # On a sub line of its own the result needs no leading ellipsis.
            sub = list(completion)
            if sub and sub[0][0].strip() == self.g('ell'):
                sub = sub[1:]
            if live['mode'] == 'block':
                if (not live['intervened'] and live['fits'] and cols
                        and len(joined) <= cols - 1):
                    self._write_raw(f"\033[1A\033[{len(live['head_plain']) + 2}G"
                                    + self._render(completion) + '\n')
                    self._mirror('  ' + self.g('sub') + ' ' + _plain(sub))
                else:
                    self._emit([(self.g('sub') + ' ', 'dim')] + sub, indent=2, hang=4)
            elif not live['committed']:
                # narrow and captured views: the head is still pending (the
                # narrow view's row was erased, the captured one is on the
                # terminal without its line end)
                if live['mode'] == 'line' and cols and len(joined) > cols - 1:
                    # no room on the row: the head gets its line end and
                    # the result its own sub line
                    self._commit_head(live)
                    self._emit([(self.g('sub') + ' ', 'dim')] + sub, indent=2, hang=4)
                else:
                    self._write_raw((self._render(live['head']) + ' ' if live['mode'] == 'line'
                                     else ' ') + self._render(completion) + '\n')
                    self._mirror(joined)
            else:
                self._emit([(self.g('sub') + ' ', 'dim')] + sub, indent=2, hang=4)
            self._show_cursor()

    def _erase_live(self):
        live = self._live
        if live is None or not live['drawn']:
            return
        # Column 1 by CHA (ESC[1G), never by a carriage return: WSL's pty
        # turns a CR into a line feed on the way out.
        if live['mode'] == 'block':
            self._write_raw(f"\033[{live['drawn']}A\033[1G\033[J")
        elif live['mode'] == 'line':
            self._write_raw('\033[1G\033[2K')
        live['drawn'] = 0

    def _redraw_live(self):
        if self._live is not None and self._live['mode'] != 'static':
            self._erase_live()
            self._draw_live()

    def _draw_live(self):
        live = self._live
        if live is None or live['mode'] == 'static' or self._closed:
            return
        cols, rows = self._geometry()
        if cols is None:
            return
        if live['mode'] == 'block' and (cols < BLOCK_MIN_COLS or rows < BLOCK_MIN_ROWS):
            live['mode'] = 'line'          # the terminal shrank: narrow view
        now = time.perf_counter()
        show = now >= live['show_at']
        elapsed = _secs(now - live['t0'])
        edge, inner, hi = _PALETTE[live['kind']]
        star = self._star()
        if live['mode'] == 'block':
            if not show:
                return
            text = {1: _mark(live['info'][0] if live['info'] else '', 'dim'),
                    2: [(star + ' ', hi), (elapsed, 'dim')]
                       + ([('  ' + live['info'][1], 'dim')] if len(live['info']) > 1 else [])}
            art = self._art_rows(live, edge, inner, hi)
            out = []
            for r in range(5):
                parts = [(' ', None)] + art[r] + [('   ', None)] + text.get(r, [])
                out.append(self._render(_clip(parts, cols - 1, self.g('ell'))))
            self._write_raw('\n'.join(out) + '\n')
            live['drawn'] = 5
        else:
            if live['committed']:
                if not show:
                    return
                parts = [('  ', None), (star + ' ', hi), (elapsed, 'dim')]
                if live['info']:
                    parts.append(('  ' + live['info'][0], 'dim'))
            else:
                parts = list(live['head'])
                if show:
                    parts += [(' ', None), (star + ' ', hi), (elapsed, 'dim')]
            self._write_raw('\033[1G\033[2K' + self._render(_clip(parts, cols - 1, self.g('ell'))))
            live['drawn'] = 1

    def _cube_row(self, r, edge, inner, hi):
        cube = _CUBE if self._uni else _CUBE_ASCII
        lit = {_CUBE_LOOP[(self._frame + k) % len(_CUBE_LOOP)] for k in range(_LIGHT_LEN)}
        parts = []
        for c, ch in enumerate(cube[r]):
            if ch == ' ':
                parts.append((ch, None))
            elif (r, c) in lit:
                parts.append((ch, hi))
            elif (r, c) in _CUBE_INNER:
                parts.append((ch, inner))
            else:
                parts.append((ch, edge))
        return parts

    def _art_rows(self, live, edge, inner, hi):
        """The activity's drawing as 5 rows of parts, every drawing padded
        to the widest sprite so the status text keeps its column; the
        boxel cube (the kind's hue) when no sprite fits."""
        sprite = self._art.get(live.get('sprite'))
        if sprite is None:
            rows = [self._cube_row(r, edge, inner, hi) for r in range(5)]
            width = _CUBE_W
        else:
            glyph_rows, mask_rows = self._sprite_frame(sprite, live)
            rows = [self._sprite_row(g, m) for g, m in zip(glyph_rows, mask_rows)]
            width = int(sprite['width'])
        pad = self._art_w - width
        if pad > 0:
            rows = [r + [(' ' * pad, None)] for r in rows]
        return rows

    def _sprite_frame(self, sprite, live):
        """The frame to show now: the sprite's period in animator ticks,
        looping, or back and forth for a pingpong sprite."""
        frames = sprite['frames']
        n = len(frames)
        ticks = max(1, int(round(int(sprite.get('period_ms', 200)) / (FRAME_S * 1000))))
        i = (self._frame - live.get('frame0', 0)) // ticks
        if sprite.get('pingpong') and n > 1:
            cycle = 2 * n - 2
            i %= cycle
            if i >= n:
                i = cycle - i
        else:
            i %= n
        return frames[i]

    def _sprite_row(self, glyphs, mask):
        """One sprite row as (text, style) parts, runs of one colour key
        joined; the glyphs through the ASCII map when the locale is not
        UTF-8."""
        if not self._uni:
            glyphs = ''.join(ch if ord(ch) < 0x7F else self._ascii.get(ch, '*')
                             for ch in glyphs)
        parts, cur, buf = [], ' ', ''
        for ch, key in zip(glyphs, mask):
            if key != cur:
                if buf:
                    parts.append((buf, None if cur == ' ' else 'art_' + cur))
                cur, buf = key, ''
            buf += ch
        if buf:
            parts.append((buf, None if cur == ' ' else 'art_' + cur))
        return parts

    def _sprite_for(self, action, args):
        """The sprite of a step: a move is going home, moving in for a look,
        stepping back, carrying or travelling empty-handed."""
        s = _symbols(args)
        if action == 'move':
            dest = s[0] if s else ''
            if _is_home(dest):
                return 'home'
            if dest.startswith('view__'):
                return ('retract' if dest[len('view__'):].startswith('sense_retract')
                        else 'look')
            return 'carry' if self._holding else 'move'
        return {'pick': 'pick', 'place': 'place', 'place_hiding': 'hide', 'stack': 'stack',
                'sense': 'sense', 'observe': 'observe'}.get(action, 'move')

    def _ensure_animator(self):
        if self._anim is None and self._tty:
            self._anim = threading.Thread(target=self._animate, name='console-anim',
                                          daemon=True)
            self._anim.start()

    def _animate(self):
        while not self._anim_stop.wait(FRAME_S):
            try:
                with self._lock:
                    if self._closed:
                        return
                    if self._live is not None and self._live['mode'] != 'static':
                        self._frame += 1
                        self._redraw_live()
            except Exception:
                pass

    # ----- the banner, the header and the summary -------------------------------

    def _rule(self, glyph, width):
        return self.g(glyph) * max(1, width)

    def _banner(self):
        cols = self._cols()
        width = min(cols - 1, BANNER_COLS) if cols else 44
        stamp = time.strftime('%Y-%m-%d %H:%M')
        box = self.g('box')
        if width >= 40:
            name = 'S E M A N T I C   B O X E L S'
            left = f'  {box}  {name}'
            gap = width - len(left) - len(stamp) - 2
            self._emit([(self._rule('heavy', width), 'cyan')])
            self._emit([(f'  {box}  ', 'brand'), (name, 'title'),
                        ((' ' * gap + stamp) if gap > 0 else '', 'dim')])
            self._emit([(self._rule('heavy', width), 'cyan')])
        else:
            self._emit([(self._rule('heavy', width), 'cyan')])
            self._emit([(f'{box} ', 'brand'), ('SEMANTIC BOXELS', 'title')])
            self._emit([(self._rule('heavy', width), 'cyan')])

    def header(self, scene=None, goal=None, switches=None):
        with self._lock:
            if self._live is not None and self._live['kind'] == 'startup':
                self._end_live([('ready', 'green'),
                                (f"  ({_secs(time.perf_counter() - self._t0)})", 'dim')])
                self._sfx('ready')
        self._goal_text = goal
        g = (goal or '').strip()
        self._goal_kind = ('holding' if g.startswith('holding') else
                           'tray' if g.startswith('find-and-tray-stack') else
                           'stack' if g.startswith('stack') else g)
        m = re.match(r'holding (\S+)', g)
        if m and m.group(1) != 'at':
            self._target = m.group(1)
        self._goal_at_home = g.endswith(' at home')
        self.statement(f'Mission: {_mission(goal)}.')
        bits = [self.run_id or '']
        scene = scene or self.context.get('scene')
        if scene:
            bits.append(str(scene))
        if switches:
            bits.append(str(switches).replace('_', ' '))
        self.note(f' {self.g("dot")} '.join(b for b in bits if b), style='dim')

    def summary(self, success=None, exit_reason=None, plan_count=0,
                plan_times=None, total_plan_time=0.0, log_path=None):
        with self._lock:
            self._end_live(None)
            self._step = None
            if log_path:
                self.log_path = str(log_path)
            cols = self._cols()
            self._emit([(self._rule('rule', min(cols - 1, BANNER_COLS) if cols else 44), 'dim')])
            self._music(None)
            rows = self._result_rows
            if success:
                if self._goal_kind == 'holding':
                    target = rows.get('Target') or self._target or 'the target'
                    what = f'I am holding `{target}`' + (' at home' if self._goal_at_home else '')
                elif rows.get('Stack goal'):
                    what = 'the tower stands as planned'
                else:
                    what = 'the mission is accomplished'
                self._emit([(self.g('ok') + ' ', 'bgreen'), ('Done. ', 'bgreen')]
                           + _mark(what + '.'))
                self._sfx('success')
                self._say(f'Done. {what}.', important=True)
            else:
                text = self._result[1] if self._result and self._result[0] == 'failed' else ''
                self._emit([(self.g('bad') + ' ', 'bred'), ('Failed. ', 'bred'),
                            (text, None), (f'  ({exit_reason})' if exit_reason else '', 'dim')])
                self._sfx('failure')
                self._say(f'Failed. {text}', important=True)
            stats = []
            found = _found_in(self._found_region or rows.get('Found in'))
            if found:
                stats.append(found)
            if 'Shadows searched' in rows:
                m = re.match(r'(\d+)(.*)', rows['Shadows searched'])
                if m:
                    stats.append(_plural(m.group(1), 'space') + ' searched'
                                 + m.group(2).replace('unresolved', 'unresolved'))
            calls = self._plans or len(plan_times or []) or plan_count
            stats.append(_plural(calls, 'plan') + (f', {self._plans_found} found'
                                                   if self._plans_found != calls else ''))
            stats.append(f'{_plural(self._dispatched, "step")}, {self._completed} done'
                         + (f', {self._failed} failed' if self._failed else ''))
            stats.append(f'planning {_secs(total_plan_time)}')
            stats.append(f'{_secs(time.perf_counter() - self._t0)} in all')
            self.note(f' {self.g("dot")} '.join(stats), style='dim')
            where = getattr(self, 'run_dir', None) or (
                os.path.dirname(self.log_path) if self.log_path else os.path.dirname(self.debug_path))
            limit = max(24, cols - 28) if cols else None
            self.note(f'log and raw stream in {_short_path(where, limit)}', style='dim')
            self._in_result = False

    # ----- the ledger's events ------------------------------------------------

    def on_ledger_event(self, kind, row):
        try:
            if kind == 'plan':
                self._plan(row)
            elif kind == 'step':
                self._step_begin(row)
            elif kind == 'step_end':
                self._step_end(row)
            elif kind == 'sense_result':
                reason = str(row.get('reason'))
                self._sense_text = _SENSE_TEXT.get(
                    reason, reason.replace('sense_', '', 1).replace('_', ' '))
            elif kind == 'observe_result':
                status = row.get('status')
                text = _STATUS_TEXT.get(status, str(status))
                if row.get('lost'):
                    text = f"`{row.get('obj')}` is gone from view, replanning"
                self._observe_text = text
            elif kind == 'at_home_test' and not row.get('passed'):
                err = row.get('max_abs_err')
                err_s = f'{err:.1e}' if isinstance(err, float) else str(err)
                self.note(f"not quite at home: the largest joint error is {err_s} rad "
                          f"after a {row.get('hold_steps')}-step hold")
            elif kind == 'gate_violation':
                self.warn(f"gate {row.get('gate')} violated in {row.get('fn')}: "
                          f"{row.get('detail')}")
            elif (kind == 'belief' and row.get('op') == 'status'
                  and row.get('status') == 'found'):
                # BeliefState.mark_sensed(found=True): the region the target
                # was sensed in (the pick overwrites target_found_in later)
                self._found_region = row.get('region')
        except Exception:
            pass

    def _think_head(self, disposal=None):
        ell = self.g('ell')
        if disposal:
            text = f'Thinking{ell} where to put `{disposal}` down'
        elif self._goal_kind == 'holding':
            target = self._target or 'the target'
            text = f'Thinking{ell} how to get hold of `{target}`'
        elif self._goal_kind in ('stack', 'tray'):
            text = f'Thinking{ell} how to build the tower'
        else:
            text = f'Thinking{ell}'
        return [(self.g('think') + ' ', 'magenta')] + _mark(text)

    def _think_info(self, disposal=None):
        bits = []
        if disposal:
            bits.append('no plan for the mission while I hold it')
        if self._holding:
            bits.append(f'holding `{self._holding}`')
        elif self._goal_kind == 'holding':
            bits.append('my hands are empty')
        if self._known_loc and self._target:
            bits.append(f'I know where `{self._target}` is')
        elif self._unknown is not None:
            bits.append(f'{_plural(self._unknown, "space")} still unchecked'
                        if self._unknown else 'every space is checked')
        if self._progress:
            bits.append(self._progress)
        return ', '.join(bits)

    def _start_thinking(self, plan_no, disposal=None):
        self._plan_no = plan_no
        self._thinking = {'disposal': disposal}
        self._start_live('think', self._think_head(disposal), [self._think_info(disposal)])
        self._music('think')
        self._sfx('plan')

    def _plan(self, row):
        pid = row.get('plan_id')
        actions = row.get('actions')
        dt = row.get('plan_time_s')
        self._plans += 1
        disposal = row.get('call') == 'disposal'
        if self._live is None or self._live['kind'] != 'think':
            self._start_thinking(pid, disposal=self._holding if disposal else None)
        ell = [(self.g('ell') + ' ', 'dim')]
        if actions is not None:
            self._plans_found += 1
            self._plan_len[pid] = len(actions)
            completion = ell + [(f'{_plural(len(actions), "step")} in {_secs(dt)}', 'green')]
        else:
            completion = ell + [('no plan', 'red'), (f' ({_secs(dt)})', 'dim')]
        self._end_live(completion)
        self._thinking = None
        self._known_loc = False
        self._progress = None
        if actions:
            plan_text = intention(actions)
            if plan_text:
                self.note(f'I will {plan_text}')
                self._say(f'I will {plan_text}.', important=True)
        elif actions is None:
            self._say('I found no plan.', important=True)

    def _step_begin(self, row):
        pid, idx = row.get('plan'), row.get('step')
        n = self._plan_len.get(pid)
        action = row.get('action')
        self._step = {'action': action, 't0': row.get('t'), 'args': row.get('args')}
        self._reasons = []
        self._sense_text = None
        self._observe_text = None
        self._dispatched += 1
        where = (f'step {idx} of {n}' if n else f'step {idx}') + f' in plan {pid}'
        text = describe_step(action, row.get('args'))
        head = ([(self.g('bullet') + ' ', 'cyan')] + _mark(text) + [(f' {self.g("ell")}', 'dim')])
        self._start_live('act', head, [where], sprite=self._sprite_for(action, row.get('args')))
        self._music('act')
        self._sfx('step')
        self._say(text)

    def _step_end(self, row):
        if self._step is None:
            return
        status = row.get('status')
        action = self._step['action']
        args = _symbols(self._step.get('args'))
        t0, t1 = self._step.get('t0'), row.get('t')
        dt = (t1 - t0) if isinstance(t0, float) and isinstance(t1, float) else None
        if action == 'sense' and self._sense_text:
            text = self._sense_text
        elif action == 'observe' and self._observe_text:
            text = self._observe_text
        else:
            reason = ', '.join(self._reasons) or _DEFAULT_REASON.get(status, '')
            text = _STATUS_TEXT.get(status, str(status)).format(reason=reason)
        if status in _COMPLETED:
            self._completed += 1
        else:
            self._failed += 1
        # What is in the hand now: a delivered step (ok, or an integrity
        # replan after the step was delivered) moves it; a failed pick, an
        # empty hand and a release that did not verify leave it empty.
        if status in ('ok', 'integrity_replan'):
            if action == 'pick' and args:
                self._holding = args[0]
            elif action in ('place', 'place_hiding', 'stack'):
                self._holding = None
        elif status in ('pick_failure', 'empty_hand'):
            self._holding = None
        elif (status in ('place_failure', 'stack_failure')
              and any('release did not verify' in r for r in self._reasons)):
            self._holding = None
        style = ('green' if text in ('done', 'found it', 'seen')
                 else 'red' if text.startswith(('failed', 'skipped', 'not at home', 'ended'))
                 else 'yellow')
        if style == 'green':
            self._sfx('found' if text == 'found it' else 'done')
            if text == 'found it':
                self._say('Found it.', important=True)
        else:
            self._sfx('fail' if style == 'red' else 'warn')
            self._say(f'{describe_step(action, self._step.get("args"))}: {text}', important=True)
        completion = _mark(text, style) + ([(f'  ({_secs(dt)})', 'dim')] if dt is not None else [])
        self._end_live(completion)
        self._step = None
        self._reasons = []

    # ----- the narration (run_logger's tee) ----------------------------------

    def narration(self, line):
        """One complete line printed by the pipeline (it is in the run log
        and the debug file already); a few kinds reach the terminal."""
        try:
            s = line.strip()
            if not s:
                return
            if self._in_result:
                m = _RESULT_ROW.match(s)
                if m:
                    self._result_rows[m.group(1)] = m.group(2).strip()
                    return
                if s.startswith('--- Planning timing summary'):
                    self._in_result = False
                    return
            if s == 'SUCCESS!':
                self._in_result, self._result, self._result_rows = True, ('success', None), {}
                return
            if s.startswith('FAILED'):
                self._in_result, self._result, self._result_rows = (
                    True, ('failed', s[len('FAILED:'):].strip() if s.startswith('FAILED:') else s), {})
                return
            m = _PLAN_START.match(s)
            if m:
                self._start_thinking(int(m.group(1)))
                return
            m = _UNKNOWN.match(s)
            if m:
                self._unknown = int(m.group(1))
                self._update_live(info=[self._think_info()])
                return
            m = _KNOWN_LOC.match(s)
            if m:
                self._known_loc = True
                self._update_live(info=[self._think_info()])
                return
            m = _PROGRESS.match(s)
            if m:
                self._progress = f'{m.group(1).lower()} {m.group(2)}'
                self._update_live(info=[self._think_info()])
                return
            m = _DISPOSAL.match(s)
            if m:
                self._end_live([(self.g('ell') + ' ', 'dim'), ('no plan', 'red')])
                self._start_thinking(self._plan_no, disposal=m.group(1))
                return
            for pat, fn in self._reason_rules:
                m = pat.match(s)
                if m:
                    self._reasons.append(fn(m))
                    break
            if _WARN.match(s):
                if self._live is not None and self._live['kind'] == 'think':
                    self._end_live([(self.g('ell') + ' ', 'dim'), ('nothing to plan', 'yellow')])
                self.warn(s)
                return
            m = _SCENE.match(s)
            if m:
                objects, spaces = int(m.group(3)), int(m.group(2))
                if spaces:
                    self.statement(f'I see {_plural(objects, "object")} on the table and '
                                   f'{_plural(spaces, "space")} hidden behind '
                                   f'{"it" if objects == 1 else "them"}.')
                else:
                    self.statement(f'I see {_plural(objects, "object")} on the table; '
                                   f'nothing is hidden from me.')
                return
            m = _TARGET_GIVEN_HIDDEN.match(s)
            if m:
                self._target = m.group(1)
                self.statement(f'I am after `{m.group(1)}`. It is not in view, so I will '
                               f'have to search.')
                return
            m = _TARGET_SEEN.match(s)
            if m:
                self._target = m.group(1)
                self.statement(f'I am after `{m.group(1)}`. I can see it, so I will go '
                               f'straight for it.')
                return
            m = _TARGET_HIDDEN.match(s)
            if m:
                self._target = m.group(1)
                self.statement(f'I am after `{m.group(1)}`. It is hidden somewhere I '
                               f'cannot see, so I will have to search.')
                return
            m = _ORACLE_IN.match(s)
            if m:
                self.note(f'(the oracle knows: it is in {_place(m.group(1))})', style='dim')
                return
            if _ORACLE_OUT.match(s):
                self.note('(the oracle knows: it is hidden outside every space I can '
                          'sense; I will find it once its cover is moved)', style='dim')
                return
            m = _GOAL_LINE.match(s)
            if m:
                self.statement(f'{m.group(1)}: {m.group(2)}')
                return
            for pat, fn in self._note_rules:
                m = pat.match(s)
                if m:
                    text = fn(m)
                    self.note(text)
                    self._say(text, important=text.startswith('I can see'))
                    return
        except Exception:
            pass
