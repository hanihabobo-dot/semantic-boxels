"""The words, drawings and sounds of a Wumpus run on the curated console.

console_ui writes the story of a run in the robot's own first-person voice;
this module is how it tells the Wumpus world: wumpus/narrate.py writes the
ledger rows, console_ui.set_task(WumpusTask()) lets this class phrase them.
Every method answers None (or False) for what the shared words already say
well; nothing here reads or changes the env, and nothing feeds a decision.

Sprites (console_art, made by tools/sprite_tool.py from tools/sprites):
  move -> drive, perceive -> look_down, grab -> grab; while a perceive is on,
  its drawing becomes stench / breeze / glitter for what it found; a move
  into a pit becomes fall, into the wumpus wumpus.  The existing think and
  startup sprites are the shared ones.
Sounds (console_audio): the shared music and effects; breeze and stench are
  `warn`, the glitter `found`, the held gold `gold`, a death `death`.

Pace: the env is fast (a move takes 0.02 s headless, 0.2 s in the GUI) and
console_ui draws an activity only when it lasts 0.3 s, so no drawing would
ever be seen.  `pace` seconds is the least time an action's drawing stays on
screen: a presentation pause on a terminal that can animate (never in a
captured console), counted in `paced` so wall times can be corrected.
"""
import re
import time

from console_ui import _mark, _plural, _secs, _short_path

_CELL = re.compile(r'\bp(\d+)-(\d+)\b')


def cells_in(args):
    return [a for a in (args or []) if isinstance(a, str)]


def describe(action, args):
    """One action as the robot announces it, or None for an action that is
    not a Wumpus one."""
    cells = cells_in(args)
    if action == 'move':
        return f'Moving to `{cells[0]}`' if cells else 'Moving'
    if action == 'perceive':
        return f'Looking around `{cells[0]}`' if cells else 'Looking around'
    if action == 'grab':
        return 'Grabbing the gold'
    return None


def _go(run):
    """A run of consecutive moves as one phrase."""
    *via, last = run
    if not via:
        return f'go to `{last}`'
    if len(via) > 3:
        through = f'`{via[0]}`, `{via[1]}` and {len(via) - 2} more cells'
    elif len(via) == 1:
        through = f'`{via[0]}`'
    else:
        through = ', '.join(f'`{c}`' for c in via[:-1]) + f' and `{via[-1]}`'
    return f'go to `{last}` through {through}'


def plan_sentence(actions):
    """A plan's actions as one sentence of intent: 'go to `p1-2`, look
    around, go to `p2-2`, then grab the gold'.  Consecutive moves are one
    phrase."""
    phrases, run = [], []
    for a in actions:
        name, args = str(a[0]), cells_in(a[1:])
        if name == 'move':
            run.append(args[0] if args else '?')
            continue
        if run:
            phrases.append(_go(run))
            run = []
        if name == 'perceive':
            phrases.append('look around')
        elif name == 'grab':
            phrases.append('grab the gold')
        else:
            phrases.append(' '.join([name] + args))
    if run:
        phrases.append(_go(run))
    if len(phrases) > 8:
        phrases = phrases[:7] + [f'and {len(phrases) - 7} more steps']
    if not phrases:
        return ''
    if len(phrases) == 1:
        return phrases[0]
    return ', '.join(phrases[:-1]) + ', then ' + phrases[-1]


# (key, sentence, drawing, effect) in the order the percepts are told
_PERCEPTS = (
    ('stench', 'I smell the wumpus', 'stench', 'warn'),
    ('breeze', 'I feel a breeze', 'breeze', 'warn'),
    ('glitter', 'Something glitters here', 'glitter', 'found'),
)
ALL_QUIET = 'All quiet: no breeze, no stench, no glitter'


def percept_notes(stench=False, breeze=False, glitter=False):
    """[(sentence, drawing, effect)] for what was perceived, [] for nothing."""
    got = {'stench': stench, 'breeze': breeze, 'glitter': glitter}
    return [(text, art, fx) for key, text, art, fx in _PERCEPTS if got[key]]


def knowledge_lines(k):
    """The two dim lines of a thinking block from a wumpus_think row."""
    v, n, s = k.get('visited'), k.get('cells'), k.get('safe')
    p, w = k.get('maybe_pit'), k.get('maybe_wumpus')
    first = []
    if v is not None:
        first.append(f'I have been to {v} of {n} cells' if n else f'I have been to {_plural(v, "cell")}')
    if s is not None:
        first.append(f'{s} {"is" if s == 1 else "are"} known safe')
    second = []
    if p is not None:
        second.append(f'a pit may lie in {_plural(p, "cell")}')
    if w is not None:
        second.append(f'the wumpus in {w}')
    second.append('I know where the gold is' if k.get('gold_known') else 'no sign of the gold yet')
    return ', '.join(first), ', '.join(second)


class WumpusTask:
    def __init__(self, pace=0.0):
        self.pace = max(0.0, float(pace))
        self.paced = 0.0              # seconds the pace has held the run
        self.world = {}
        self.know = {}
        self.result = None            # the open step's wumpus_action_result row
        self.pending = []             # [(sentence, important)] told once the step line is closed
        self.final = {}
        self._held = 0.0              # pace seconds spent inside the open step

    # ----- the pace ------------------------------------------------------------

    @staticmethod
    def _animated(console):
        live = console._live
        return live is not None and live.get('mode') == 'block'

    def _hold(self, console, seconds):
        if seconds > 0 and self.pace > 0 and self._animated(console):
            time.sleep(seconds)
            self.paced += seconds
            self._held += seconds

    @staticmethod
    def _show_now(console):
        """With a pace the drawing is held for seconds, so it is drawn at
        once instead of after console_ui's 0.3 s grace for quick steps."""
        live = console._live
        if live is not None:
            live['show_at'] = live['t0']

    def _hold_until_pace(self, console):
        live = console._live
        if live is not None:
            self._hold(console, live['t0'] + self.pace - time.perf_counter())

    # ----- the words console_ui asks for ---------------------------------------

    def describe_step(self, console, action, args):
        return describe(action, args)

    def intention(self, console, actions):
        return plan_sentence(actions)

    def sprite_for(self, console, action, args):
        return {'move': 'drive', 'perceive': 'look_down', 'grab': 'grab'}.get(action)

    def think_lines(self, console, plan_no):
        gold = bool(self.know.get('gold_known'))
        head = ([(console.g('think') + ' ', 'magenta')]
                + _mark(f"Thinking{console.g('ell')} how to {'reach' if gold else 'find'} the gold"))
        first, second = knowledge_lines(self.know)
        return head, [t for t in (first, second) if t]      # a controller may tell no numbers

    def step_end(self, console, row, action, args, text, style, dt):
        res = self.result
        ok = (row.get('status') == 'ok') if res is None else bool(res.get('ok'))
        dead = res.get('dead') if res else None
        why = (res.get('why') or '') if res else ''
        if dead:
            art = 'fall' if dead == 'pit' else 'wumpus'
            console._set_sprite(art)
            console._sfx('death')
            sprite = console._art.get(art) or {}
            cycle = len(sprite.get('frames', ())) * int(sprite.get('period_ms', 150)) / 1000.0
            self._hold(console, max(self.pace, cycle))
            text = 'I fell into a pit' if dead == 'pit' else 'The wumpus got me'
            style = 'red'
        elif not ok:
            self._hold_until_pace(console)
            text, style = (f'failed: {why}' if why else 'failed'), 'red'
        else:
            self._hold_until_pace(console)
            if action == 'grab':
                console._sfx('gold')
                text, style = 'done', 'green'
        wall = res.get('wall_s') if res else None
        if isinstance(wall, (int, float)):
            dt = float(wall)
        elif dt is not None:
            dt = max(0.0, dt - self._held)
        return text, style, dt

    def summary_done(self, console, rows):
        return 'I am holding the gold'

    def summary_failed(self, console, exit_reason):
        f = self.final
        out, why, cell = f.get('outcome'), f.get('reason') or '', f.get('cell')
        at = f' at {cell}' if cell else ''
        if out == 'death':
            return ('I fell into a pit' if why == 'pit' else 'The wumpus got me') + at
        if out == 'stuck':
            return f'I am stuck: {why}' if why else 'I am stuck'
        if out == 'step_limit':
            return f'I ran out of steps ({why})' if why else 'I ran out of steps'
        if out == 'error':
            return f'Something went wrong: {why}' if why else 'Something went wrong'
        return None

    def summary_stats(self, console, rows):
        v, n = self.final.get('visited'), self.final.get('cells')
        if v is None:
            return None
        return [f'{v} of {n} cells visited' if n else f'{_plural(v, "cell")} visited']

    def speech(self, console, text):
        return _CELL.sub(r'cell \1 \2', text)

    # ----- the rows of the Wumpus world ----------------------------------------

    def on_ledger_event(self, console, kind, row):
        if kind == 'plan':
            live = console._live
            if live is not None and live['kind'] == 'think':
                # a controller that plans in no time still gets its thinking seen
                self._hold(console, live['t0'] + self.pace - time.perf_counter())
            return False                      # console_ui ends the thinking with the plan
        if kind == 'step':
            self.result, self.pending, self._held, self.know = None, [], 0.0, {}
            if self.pace > 0:
                console._step_begin(row)      # as console_ui does, but drawn at once
                self._show_now(console)
                return True
            return False                      # console_ui starts the step
        if kind == 'wumpus_mission':
            self._mission(console, row)
            return True
        if kind == 'wumpus_think':
            self.know = dict(row)
            console._start_thinking(row.get('plan_no'))
            if self.pace > 0:
                self._show_now(console)
            return True
        if kind == 'wumpus_percept':
            self._percept(console, row)
            return True
        if kind == 'wumpus_action_result':
            self.result = dict(row)
            return True
        if kind == 'step_end':
            console._step_end(row)            # the step line, then what it found
            self._flush(console)
            return True
        if kind == 'wumpus_result':
            self.final = dict(row)
            return True
        if kind == 'wumpus_files':
            self._files(console, row)
            return True
        return False

    def _files(self, console, row):
        """The per-seed closing line, under the verdict like the bridge's outcome line."""
        cols = console._cols()
        where = _short_path(row.get('where') or '', max(24, cols - 48) if cols else None)
        said = [b for b in (f"seed {row['seed']}" if row.get('seed') is not None else None,
                            row.get('outcome'),
                            _plural(row['actions'], 'action') if row.get('actions') is not None else None) if b]
        console.note(f"{', '.join(said)} {console.g('dot')} episode files in {where}", style='dim')

    def _mission(self, console, row):
        self.world = dict(row)
        if console._live is not None and console._live['kind'] == 'startup':
            console._end_live([('ready', 'green'),
                               (f"  ({_secs(time.perf_counter() - console._t0)})", 'dim')])
            console._sfx('ready')
        n = row.get('size')
        console.statement('Mission: find the gold and grab it.')
        counts = []
        if row.get('wumpuses') is not None:
            counts.append(_plural(row['wumpuses'], 'wumpus', 'wumpuses'))
        if row.get('pits') is not None:
            counts.append(_plural(row['pits'], 'pit'))
        bits = [console.run_id or '', f"{n}x{n} world, seed {row.get('seed')}",
                ', '.join(counts), f"controller {row.get('controller')}"]
        console.note(f' {console.g("dot")} '.join(b for b in bits if b), style='dim')
        console.statement(f"I am at `{row.get('start')}` in a {n}x{n} world of {row.get('cells')} "
                          f"cells. A wumpus, pits and a bar of gold are hidden in it.")

    def _percept(self, console, row):
        notes = percept_notes(row.get('stench'), row.get('breeze'), row.get('glitter'))
        if not notes:
            self.pending.append((ALL_QUIET, False))
            return
        self._hold_until_pace(console)        # the scan gets its time first
        for text, art, fx in notes:
            if self._animated(console):
                console._set_sprite(art)
            console._sfx(fx)
            self._hold(console, self.pace)
            self.pending.append((text, art == 'glitter'))

    def _flush(self, console):
        notes, self.pending = self.pending, []
        for text, important in notes:
            console.note(text, style='dim' if text == ALL_QUIET else None)
            console._say(text, important=important)
