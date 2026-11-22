"""The console's narration: what the robot says for a ledger row and for a
line of the pipeline's narration.

`ConsoleNarration` holds the methods of the Console that decide the words:
the line kinds (`warn`, `note`, `statement`), the header, the ledger's
events (`on_ledger_event` with the plan and step handlers) and `narration`,
which reads each line the pipeline prints against the rules of
`console_phrases`.  `Console.say` and `Console.summary` stay in
`console_ui`, beside `_short_path`.

`console_ui` imports `ConsoleNarration` and builds `Console` from it.
"""
import re
import time

from console.console_phrases import (
    _COMPLETED, _DEFAULT_REASON, _DISPOSAL, _GOAL_LINE, _KNOWN_LOC,
    _ORACLE_IN, _ORACLE_OUT, _PLAN_START, _PROGRESS, _RESULT_ROW, _SCENE,
    _SENSE_TEXT, _STATUS_TEXT, _TARGET_GIVEN_HIDDEN, _TARGET_HIDDEN,
    _TARGET_SEEN, _UNKNOWN, _WARN, _mission, _place, _plural, _secs, _symbols,
    intention)
from console.console_screen import _mark


class ConsoleNarration:
    """The speaking half of `console_ui.Console` (a mixin: `self` is the
    Console; every line goes out through `ConsoleScreen`'s methods)."""

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
