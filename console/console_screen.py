"""The console's screen: glyphs, colours and everything that writes to the
terminal.

The top of the file holds the sizes and timings of the animated block, the
glyph and colour tables, and the helpers over styled parts (`_mark`,
`_wrap`, `_clip`).  `ConsoleScreen` holds the methods of the Console that
draw: the committed lines (`_emit`), the live activity with its animated
block (`_start_live` to `_animate`) and the banner.

`console_ui` imports every name of this file back, and callers and tests
read them from there.
"""
import os
import re
import threading
import time

from console.console_phrases import _is_home, _secs, _symbols


# The full view (the animated block beside the status) needs this much
# terminal (a split view of some 56 columns gets it); below it the status
# is one line.  The full view comes first (Hani, 2026-10-30); the mini view
# gets its own layout later.
BLOCK_MIN_COLS = 48
BLOCK_MIN_ROWS = 12
FRAME_S = 0.1          # the animation's tick
SHOW_AFTER_S = 0.3     # an activity shorter than this never shows its drawing
BANNER_COLS = 60       # the banner's widest rule
PAGE_LINES = 500       # the committed lines kept for the page beside our own window (gui_page)


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
        from console import console_art
        return (dict(console_art.SPRITES), dict(console_art.PALETTE),
                dict(console_art.ASCII_MAP))
    except Exception:
        return {}, {}, {}


def _start_audio():
    """console_audio's Audio (8-bit music and effects that follow the run,
    and Windows' voice when asked; see there) when SB_AUDIO or SB_VOICE
    asks for it, else None."""
    try:
        from console import console_audio
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


class ConsoleScreen:
    """The drawing half of `console_ui.Console` (a mixin: `self` is the
    Console, with its one lock `self._lock` and the state that
    `Console.__init__` sets).  Glyphs and geometry, writing, the live
    activity, the banner."""

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

    # ----- writing ---------------------------------------------------------

    def _render(self, parts):
        return ''.join(self._style(t, s) for t, s in parts)

    def _write_raw(self, text):
        try:
            self.term.write(text)
            self.term.flush()
        except Exception:
            pass

    def _mirror(self, plain, parts=None):
        """A committed line into the debug file, as plain text; with `parts`
        (the line as the terminal shows it) it is kept for the page too.  A
        line the terminal does not show (a held gate row) has no parts."""
        try:
            self.debug.write('[console] ' + plain + '\n')
        except Exception:
            pass
        if parts is not None:
            self._page_seq += 1
            self._page_lines.append((self._page_seq, [(str(t), s) for t, s in parts if t]))

    def page_snapshot(self, after=0):
        """What the page beside our own window shows (gui_page asks from its
        own thread, a few times a second): the committed lines numbered
        above `after`, the live activity and the counts the narration keeps.
        Read only: nothing of the console changes."""
        with self._lock:
            live = self._live
            activity = None
            if live is not None:
                activity = {'id': live['t0'], 'kind': live['kind'],
                            'head': [list(part) for part in live['head']],
                            'info': [str(text) for text in live['info']],
                            'sprite': live.get('sprite'),
                            'elapsed': time.perf_counter() - live['t0']}
            return {'seq': self._page_seq,
                    'lines': [[n, [list(part) for part in parts]]
                              for n, parts in self._page_lines if n > after],
                    'live': activity,
                    'run_id': self.run_id,
                    'elapsed': time.perf_counter() - self._t0,
                    'counts': {'plans': self._plans, 'plans_found': self._plans_found,
                               'dispatched': self._dispatched, 'completed': self._completed,
                               'failed': self._failed, 'holding': self._holding,
                               'unknown': self._unknown}}

    def _say(self, text, important=False):
        """The voice, when there is one: important sentences are always
        spoken, the others dropped while the robot is ahead of its voice."""
        if self._audio is not None:
            try:
                if self._task is not None:
                    text = self._tw('speech', text) or text
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
            self._mirror(' ' * indent + _plain(parts), [(' ' * indent, None)] + list(parts))
            self._redraw_live()

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
                self._mirror(head_plain, head)
                live['committed'] = True
            elif mode == 'line':
                # A head that leaves no room for the status is committed
                # and the status gets its own short row; otherwise the head
                # is the pending row the status is appended to.
                if len(head_plain) + 14 > cols - 1:
                    self._write_rows(_wrap(head, cols - 1, 0, 2))
                    self._mirror(head_plain, head)
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
        self._mirror(live['head_plain'], live['head'])
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
                    self._mirror('  ' + self.g('sub') + ' ' + _plain(sub),
                                 [('  ', None), (self.g('sub') + ' ', 'dim')] + sub)
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
                    self._mirror(joined, list(live['head']) + [(' ', None)] + list(completion))
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
