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

# Parts of the console live in files of their own (the console_* imports
# below); every name is imported back, so that callers and tests keep
# reading it from this module.
from console_phrases import (  # noqa: F401
    _plural, _secs, _symbols, _is_home, _SHADOW_OF, _INTERIOR_OF, _place,
    _move_phrase, _where, describe_step, intention, _found_in, _mission,
    _WARN, _STDERR_SHOW, _STDERR_WARN, _reason_rules, _f20_role, _INTEGRITY,
    _note_rules, _SCENE, _TARGET_GIVEN_HIDDEN, _TARGET_SEEN, _TARGET_HIDDEN,
    _ORACLE_IN, _ORACLE_OUT, _GOAL_LINE, _PLAN_START, _UNKNOWN, _KNOWN_LOC,
    _PROGRESS, _DISPOSAL, _RESULT_ROW, _SENSE_TEXT, _COMPLETED, _STATUS_TEXT,
    _DEFAULT_REASON, _GATE_ROW, _OUTCOME)
from console_screen import (  # noqa: F401
    BLOCK_MIN_COLS, BLOCK_MIN_ROWS, FRAME_S, SHOW_AFTER_S, BANNER_COLS,
    _GLYPHS, _STARS, _STARS_ASCII, _CUBE, _CUBE_ASCII, _CUBE_LOOP,
    _CUBE_INNER, _CUBE_W, _LIGHT_LEN, _CODES, _CODES_256, _PALETTE, _Style,
    _color_depth, _load_art, _start_audio, _color_wanted, _unicode_wanted,
    _mark, _plain, _wrap, _clip, ConsoleScreen)

DEBUG_NAME = 'console_debug.log'
# Where the debug file lives until a run directory exists (a start that
# stops before its RunLogger, an argparse error, a crash during set-up,
# keeps it there and names it): the user's cache directory, since WSL's
# /tmp does not survive between sessions.
EARLY_DIR = os.path.join(os.path.expanduser('~'), '.cache', 'semantic_boxels')
REPO = os.path.dirname(os.path.abspath(__file__))

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


def set_task(task):
    """Plug in another task's words (the Wumpus world: wumpus/console_words.py).
    `task` is an object whose optional methods take the console first and
    answer None to leave the default words in place (see Console._tw); the
    ledger rows it names itself (on_ledger_event returning True) are its
    own.  boxels and tampura never set one, and then nothing here changes."""
    _call(Console.set_task, task)


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

class Console(ConsoleScreen):
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
        self._task = None             # another task's words (set_task); None for boxels and tampura

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

    # ----- another task's words (set_task) ------------------------------------

    def set_task(self, task):
        self._task = task

    def _tw(self, name, *args):
        """What the task says for `name` (its method of that name called with
        this console and `args`), or None: no task, no such method, a None
        answer or an error all leave the default words in place."""
        task = self._task
        if task is None:
            return None
        fn = getattr(task, name, None)
        if fn is None:
            return None
        try:
            return fn(self, *args)
        except Exception:
            return None

    def _describe(self, action, args):
        """describe_step, or the task's words for the action."""
        text = self._tw('describe_step', action, args)
        return text if text is not None else describe_step(action, args)

    def _set_sprite(self, key):
        """Change the drawing of the activity that is live now (the task shows
        what a step found while the step is still on)."""
        with self._lock:
            if self._live is not None:
                self._live['sprite'] = key
                self._live['frame0'] = self._frame
                self._redraw_live()

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
                if self._task is not None:
                    what = self._tw('summary_done', rows) or what
                self._emit([(self.g('ok') + ' ', 'bgreen'), ('Done. ', 'bgreen')]
                           + _mark(what + '.'))
                self._sfx('success')
                self._say(f'Done. {what}.', important=True)
            else:
                text = self._result[1] if self._result and self._result[0] == 'failed' else ''
                if self._task is not None:
                    text = self._tw('summary_failed', exit_reason) or text
                self._emit([(self.g('bad') + ' ', 'bred'), ('Failed. ', 'bred'),
                            (text, None), (f'  ({exit_reason})' if exit_reason else '', 'dim')])
                self._sfx('failure')
                self._say(f'Failed. {text}', important=True)
            stats = []
            if self._task is not None:
                stats.extend(self._tw('summary_stats', rows) or [])
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
            if self._task is not None:
                # another task's own rows come first (its on_ledger_event answers
                # True for a row it has dealt with); the shared kinds fall through
                # to the words below, which ask the task for its phrasing
                handler = getattr(self._task, 'on_ledger_event', None)
                if handler is not None and handler(self, kind, row):
                    return
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
        if self._task is not None:
            custom = self._tw('think_lines', plan_no)     # (head parts, info lines) or None
            if custom is not None:
                self._start_live('think', custom[0], list(custom[1]))
                self._music('think')
                self._sfx('plan')
                return
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
            plan_text = self._tw('intention', actions)
            if plan_text is None:
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
        text = self._describe(action, row.get('args'))
        head = ([(self.g('bullet') + ' ', 'cyan')] + _mark(text) + [(f' {self.g("ell")}', 'dim')])
        sprite = self._tw('sprite_for', action, row.get('args'))
        self._start_live('act', head, [where],
                         sprite=sprite or self._sprite_for(action, row.get('args')))
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
        if self._task is not None:
            custom = self._tw('step_end', row, action, self._step.get('args'), text, style, dt)
            if custom is not None:
                text, style, dt = custom
        if style == 'green':
            self._sfx('found' if text == 'found it' else 'done')
            if text == 'found it':
                self._say('Found it.', important=True)
        else:
            self._sfx('fail' if style == 'red' else 'warn')
            self._say(f'{self._describe(action, self._step.get("args"))}: {text}', important=True)
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
