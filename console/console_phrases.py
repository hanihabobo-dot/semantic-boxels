"""The console's words: how a name, a step, a plan and a pipeline line
become a sentence.

Three kinds of thing live here.  The phrases (`describe_step`, `intention`
and the helpers they use) turn ledger rows into the robot's first-person
sentences.  The rules (`_WARN`, `_reason_rules`, `_note_rules` and the
patterns below them) say which lines of the pipeline's narration the
console listens to and what it says for each.  The status texts
(`_SENSE_TEXT`, `_STATUS_TEXT`, `_DEFAULT_REASON`) say how a step's end
reads.

Nothing here draws or holds state.  `console_ui` imports every name of this
file back, and callers and tests read them from there.  The Wumpus world
has words of its own in `wumpus/console_words.py`.
"""
import re


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
# BF#65 option 1: the region under a cover (interior_regions.py); its
# suffixes (__NN a carve's part, __rK a second region of one object) are not
# part of the name.
_INTERIOR_OF = re.compile(r'interior_of_(.+?)(?:__(?:\d{2,}|r\d+))*$')


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
    m = _INTERIOR_OF.match(name)
    if m:
        return f'the space under `{m.group(1)}`'
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
    m = _INTERIOR_OF.match(dest)
    if m:
        return f'Moving to the space under `{m.group(1)}`'
    return f'Moving over `{dest}`'


def _where(dest):
    """'on a free spot' / 'in the space behind x' / 'at <place>'."""
    dest = str(dest)
    if re.match(r'free_\d+$', dest):
        return 'on a free spot'
    if dest.startswith('shadow_of_') or dest.startswith('interior_of_'):
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
        if src != obj and (src.startswith('shadow_of_')
                           or src.startswith('interior_of_')):
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
        # M7 (Hani, 2026-11-20): the F9 give-up's suspension and its end
        (re.compile(r'^(\S+): a body found in it reaches the F9 give-up.*?'
                    r'suspending \S+ for (\d+) s.*?: (.*)$'),
         lambda m: f'I keep finding the same thing in `{m.group(1)}` '
                   f'({m.group(3)}), so I set that space aside for '
                   f'{m.group(2)} s'),
        (re.compile(r'^\[M7\] (\S+) is back in the search'),
         lambda m: f'`{m.group(1)}` is back on my list: its time aside is over'),
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
