"""
Pipeline run logging service.

Provides a RunLogger that:
  - Tees all stdout to a timestamped log file (captures PDDLStream print output)
  - Configures Python logging with file + console handlers
  - Copies input artefacts (boxel_data.json, problem PDDL) into the log directory
  - Supports four verbosity levels via a single parameter

Verbosity levels:
  - 'smart'   (default): the curated console (console_ui.py): a header,
                one line per planner call, per dispatched action with its
                outcome, per sense result and notable observation,
                warnings as single lines, a closing summary.  The raw
                stdout and stderr of the whole process go to
                <run_dir>/console_debug.log; our narration goes to the
                log file as before.
  - 'normal':   Console at INFO level, raw stdout untouched.
  - 'quiet':    Console at WARNING level, raw stdout untouched.
  - 'verbose':  Console at DEBUG level, raw stdout untouched.

Usage::

    logger = RunLogger(verbosity='smart')   # default; or 'normal', 'quiet', 'verbose'
    ...
    logger.save_artefact('boxel_data.json')
    logger.save_artefact('pddl/problem_debug.pddl')
    ...
    logger.close()

Or as a context manager::

    with RunLogger(verbosity='smart') as logger:
        ...
"""

import argparse
import functools
import json
import logging
import os
import random
import shutil
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import console_ui
import world_counts       # TB-22: the record's drop and collision fields
# The flag parser lives in pipeline_args.py since the readable migration (P8);
# tampura_bridge/policy.py, tests and tools import the name from run_logger.
from pipeline_args import parse_pipeline_args

if TYPE_CHECKING:
    from boxel_data import BoxelRegistry

QUIET = logging.WARNING
NORMAL = logging.INFO
VERBOSE = logging.DEBUG

# 'smart' is a console-presentation mode, not a filter level — the
# console handler still runs at INFO, into the raw stream (the debug
# file), so console_debug.log reads like the old raw terminal; the
# curated console takes ERROR and above through its own handler.
_LEVEL_MAP = {
    'quiet':   QUIET,
    'normal':  NORMAL,
    'smart':   NORMAL,
    'verbose': VERBOSE,
}

VALID_VERBOSITIES = ('smart', 'normal', 'quiet', 'verbose')


class _TeeStream:
    """Duplicates writes to both the original stream and a log file.  With
    a line hook (the curated console's narration reader) every complete
    line is handed over as well, after it is written."""

    def __init__(self, original, log_file, line_hook=None):
        self.original = original
        self.log_file = log_file
        self._line_hook = line_hook
        self._line_buf = ''

    def write(self, text):
        self.original.write(text)
        self.log_file.write(text)
        self.log_file.flush()
        if self._line_hook is not None and text:
            self._line_buf += text
            while '\n' in self._line_buf:
                line, self._line_buf = self._line_buf.split('\n', 1)
                self._line_hook(line)

    def flush(self):
        self.original.flush()
        self.log_file.flush()

    def fileno(self):
        return self.original.fileno()

    def isatty(self):
        return self.original.isatty()


class RunLogger:
    """
    Pipeline logging service with verbosity control and persistent output.

    Args:
        verbosity: One of ``'smart'`` (default), ``'normal'``, ``'quiet'``,
            ``'verbose'``.  Controls what appears on the console.  The log
            FILE always captures everything (DEBUG and above).
        log_dir: Directory for log files (created if absent).

    Attributes:
        log_path: Path to the current run's log file.
        run_dir:  Per-run subdirectory inside *log_dir* (holds artefacts).
    """

    def __init__(self, verbosity: str = 'smart', log_dir: str = 'logs'):
        if verbosity not in VALID_VERBOSITIES:
            raise ValueError(
                f"verbosity must be one of {VALID_VERBOSITIES}, "
                f"got {verbosity!r}")
        self._verbosity = verbosity
        self._timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

        self.run_dir = Path(log_dir) / f'run_{self._timestamp}'
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = self.run_dir / f'run_{self._timestamp}.log'

        self._log_file = open(self.log_path, 'w', encoding='utf-8')
        self._original_stdout = sys.stdout

        # In smart mode the curated console (console_ui) owns the terminal
        # and the raw stdout is the debug file next to this log; the tee's
        # line hook feeds it our narration.  Other modes keep the raw
        # stdout so PyBullet/PDDLStream output appears verbatim.  The tee
        # always forks a copy to the log file, untouched, for full fidelity.
        self._console_target = self._original_stdout
        if verbosity == 'smart':
            self._console = console_ui.attach(self.run_dir, self.log_path)
            line_hook = self._console.narration
        else:
            self._console = None
            line_hook = None
        sys.stdout = _TeeStream(self._console_target, self._log_file, line_hook)

        console_level = _LEVEL_MAP.get(verbosity, NORMAL)

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        for h in root.handlers[:]:
            root.removeHandler(h)

        fh = logging.StreamHandler(self._log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'))
        root.addHandler(fh)
        self._file_handler = fh

        ch = logging.StreamHandler(self._console_target)
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter('[%(levelname)-7s] %(message)s'))
        root.addHandler(ch)
        self._console_handler = ch
        if self._console is not None:
            root.addHandler(self._console.log_handler())

        logging.info('Run started  : %s', self._timestamp)
        logging.info('Log file     : %s', self.log_path)
        logging.info('Verbosity    : %s (console), DEBUG (file)', verbosity)
        ledger_open(self.run_dir)

    # ----- artefact saving ---------------------------------------------------

    def save_artefact(self, src_path: str, dest_name: str = None):
        """
        Copy *src_path* into the run directory for reproducibility.

        Args:
            src_path:  Path to the file to copy.
            dest_name: Optional filename override inside the run directory.
        """
        src = Path(src_path)
        if not src.exists():
            logging.warning('Artefact not found, skipping: %s', src)
            return
        dest = self.run_dir / (dest_name or src.name)
        shutil.copy2(src, dest)
        logging.debug('Saved artefact: %s -> %s', src, dest)

    # ----- lifecycle ---------------------------------------------------------

    def close(self):
        """Restore stdout, flush the log file, and remove handlers."""
        ledger_close()
        logging.info('Run finished : %s',
                     datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
        logging.info('Full log at  : %s', self.log_path)

        root = logging.getLogger()
        root.removeHandler(self._file_handler)
        root.removeHandler(self._console_handler)
        if self._console is not None:
            console_ui.detach()

        sys.stdout = self._original_stdout
        self._log_file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# ---------------------------------------------------------------------------
# #P4 B0: the run ledger and the dispatcher context
# ---------------------------------------------------------------------------
# The ledger is an append-only event stream, <run_dir>/ledger.jsonl, one
# JSON object per line: every plan() result, every dispatched step and how
# it ended, the runtime motion re-solve before a move, the commanded place
# target, and one provenance row per belief change of a SHADOW fragment.
# tools/bridge_gates.py reads it (gates G3, G4, G5, G11, G21); the bridge's
# runtime hooks read the dispatcher context.  Writing an event never feeds a
# decision: arguments are copied out as names and numbers.  A write that
# fails is counted, printed and recorded when the ledger closes, so the
# reader can refuse an incomplete ledger instead of passing it.

_ledger_file = None
_ledger_write_errors = 0
_dispatch = None
_provenance = []
_ledger_t0 = None     # time.perf_counter() at ledger_open (M7's suspension times)

# The ways a dispatched step may end.  'ok' is the only one that lets the
# dispatcher go on to the next step of the same plan; every other value is
# a logged early end (gate G3).  'unlabelled' is written only when the
# dispatcher left a step without saying why, and fails G3.
# 'home_not_reached' is D7 (vi)'s bound (#P4 B3(d)): the second
# consecutive planned move to q_home that fails the at-home test.
# 'action_failed' and 'dead' are the Wumpus world's (wumpus/narrate.py,
# 2026-11-06): an action that returned not ok, and a move into a pit or the
# wumpus's cell.  tools/bridge_gates.py keeps its own G3 list: a bridge run
# never writes them.
STEP_END_STATUSES = (
    'ok', 'sense_outcome', 'integrity_replan', 'motion_resolve_failed',
    'pick_failure', 'place_failure', 'stack_failure', 'empty_hand',
    'stale_precondition', 'home_not_reached', 'observe_ok',
    'observe_incomplete', 'look_outcome', 'unlabelled', 'action_failed', 'dead',
)


def ledger_open(run_dir) -> None:
    """Start <run_dir>/ledger.jsonl.  Called by RunLogger."""
    global _ledger_file, _ledger_write_errors, _dispatch, _ledger_t0
    ledger_close()
    _ledger_write_errors = 0
    _dispatch = None
    _provenance.clear()
    _ledger_file = open(Path(run_dir) / 'ledger.jsonl', 'w', encoding='utf-8')
    _ledger_t0 = time.perf_counter()
    ledger_event('ledger_open', pid=os.getpid())


def ledger_close() -> None:
    global _ledger_file
    if _ledger_file is None:
        return
    ledger_event('ledger_close', write_errors=_ledger_write_errors)
    _ledger_file.close()
    _ledger_file = None


def ledger_arg(value):
    """One action argument as the ledger records it: names stay names, a
    configuration is its name, anything else is its type and object id (so
    the reader can prove the dispatched object is the planned one)."""
    if isinstance(value, str):
        return value
    name = getattr(value, 'name', None)
    if isinstance(name, str) and hasattr(value, 'joint_positions'):
        return f"cfg:{name}"
    return f"{type(value).__name__}@{id(value)}"


def ledger_plan(plan):
    """A plan as the ledger records it: [[action, arg, ...], ...]."""
    if plan is None:
        return None
    return [[str(a[0])] + [ledger_arg(x) for x in a[1:]] for a in plan]


def _ledger_default(obj):
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    return repr(obj)


def ledger_event(kind: str, **fields) -> None:
    """Append one event.  The open dispatcher context, if any, is stamped
    on it."""
    global _ledger_write_errors
    if _ledger_file is None:
        return
    row = {'t': time.perf_counter(), 'wall': time.time(), 'kind': kind}
    if _dispatch is not None:
        row['plan'] = _dispatch['plan']
        row['step'] = _dispatch['step']
    row.update(fields)
    try:
        _ledger_file.write(json.dumps(row, default=_ledger_default) + '\n')
        _ledger_file.flush()
    except Exception as e:
        _ledger_write_errors += 1
        print(f"  WARNING: ledger write failed ({kind}): {e}")
    # The curated console reads the row after it is written (a no-op
    # without a console; it never raises and feeds no decision).
    console_ui.on_ledger_event(kind, row)


def dispatch_begin(plan_id, step, action, args, plan_obj=None) -> None:
    """Open the dispatcher context for step `step` (1-based) of plan
    `plan_id`.  The bridge's motion hook (gate G3) refuses motion
    commanded while no context is open."""
    global _dispatch
    if _dispatch is not None:
        dispatch_end('unlabelled')
    _dispatch = {'plan': plan_id, 'step': step, 'action': action}
    ledger_event('step', action=action, args=[ledger_arg(x) for x in args],
                 plan_obj=plan_obj)


def dispatch_end(status: str) -> None:
    """Close the dispatcher context with how the step ended (one of
    STEP_END_STATUSES).  A no-op when no context is open."""
    global _dispatch
    if _dispatch is None:
        return
    if status not in STEP_END_STATUSES:
        status = 'unlabelled'
    ledger_event('step_end', status=status)
    _dispatch = None


def current_dispatch():
    """The open dispatcher context as a dict, or None."""
    return None if _dispatch is None else dict(_dispatch)


@contextmanager
def provenance(channel: str, **detail):
    """Name the observation channel behind every belief change made inside
    the block (gate G5).  The innermost block wins."""
    _provenance.append(dict(detail, channel=channel))
    try:
        yield
    finally:
        _provenance.pop()


def provenance_channel(channel: str):
    """provenance() for a whole function, as a decorator."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with provenance(channel):
                return fn(*args, **kwargs)
        return wrapper
    return deco


def ledger_belief(region: str, op: str, status=None) -> None:
    """One G5 provenance row.  Called by BeliefState for every status
    change and removal, and by BoxelRegistry for every SHADOW boxel that
    leaves the registry; the channel comes from the innermost provenance
    block, or is None when no call site named one."""
    ctx = dict(_provenance[-1]) if _provenance else {}
    channel = ctx.pop('channel', None)
    ledger_event('belief', region=str(region), op=op, status=status,
                 channel=channel, **ctx)


# ---------------------------------------------------------------------------
# Run outcome reporting (extracted from test_full_pipeline.py 2026-05-05)
# ---------------------------------------------------------------------------


def _suspended_text(belief) -> str:
    """M7: the F9 give-up suspensions still open, for a FAILED line, e.g.
    "shadow_026 (e_cups_ud rediscovered 3 times)"; '' when there are none."""
    get = getattr(belief, 'get_suspended_shadows', None)
    if get is None:
        return ''
    return '; '.join(
        f"{sid} (" + ', '.join(f"{b} rediscovered {n} times"
                               for b, n in belief.suspended[sid]['bodies'].items())
        + ")" for sid in sorted(get()))


def suspension_rows(belief) -> list:
    """M7: every F9 give-up suspension of the episode, its start, planned
    end and end in seconds from the ledger's opening (the clock of the
    ledger's 't'), and how it ended: released, the region's later status,
    or open_at_end."""
    t0 = _ledger_t0 or 0.0

    def rel(t):
        return None if t is None else round(t - t0, 3)

    return [{'region': r['region'], 'bodies': dict(r['bodies']),
             'start_s': rel(r['start']), 'until_s': rel(r['until']),
             'end_s': rel(r['end']), 'ended_by': r['ended_by'] or 'open_at_end'}
            for r in (getattr(belief, 'suspensions', None) or [])]


def report_run_outcome(
    *,
    success: bool,
    exit_reason: Optional[str],
    goal_kind: str,
    goal,
    target_name: Optional[str],
    on_relations: dict,
    belief,
    plan_count: int,
    sense_count: int = 0,  # audit #73 step 3(c) plot 4
    m8_stats: Optional[dict] = None,  # M8: observes and view-fact metrics
    shadows: list,
    blocked_giveup_shadows: set,
    m7_suspend_s: Optional[float] = None,       # M7: the F9 give-up's suspension (None: M7 off)
    pick_giveup_objects: Optional[set] = None,  # #P1 F2 pick 3-strike giveup
    integrity_events: Optional[list] = None,    # #P2 (a) monitor verdicts
    stack_fail_counts: Optional[dict] = None,   # #P2 F28 strikes
    plan_times: list,
    total_plan_time: float,
    physical_failures: list,
    physics_failures: list,
    run_config: Optional[dict],
    run_logger: Optional["RunLogger"],
    registry: Optional["BoxelRegistry"] = None,
    last_init: Optional[list] = None,
    boxel_counts_per_replan: Optional[list] = None,  # audit #73 step 2(d) plot 11
    observer_counts: Optional[dict] = None,     # TB-22: telemetry's run counts
    drops_noticed: Optional[dict] = None,       # TB-22: by the robot's own checks
    collisions_reported: Optional[int] = None,  # TB-22: the executor's reports
):
    """Print success/failure classification, planning timing summary,
    and write timing_summary.json into the run logger's run directory.

    Caller is responsible for computing ``success`` and
    ``physics_failures`` (those depend on goal_kind + domain helpers
    in the orchestrator).  This function only formats and persists
    the result.
    """
    print("\n" + "=" * 60)
    if success:
        print(f"SUCCESS!")
        if goal_kind == 'holding':
            print(f"  Target: {target_name}")
            print(f"  Found in: {belief.target_found_in}")
            print(f"  Plans executed: {plan_count}")
            # #P1 F15(c): parked-unresolved fragments are not searched —
            # count them separately so a success never implies the
            # robot cleared regions it merely gave up on.
            _parked_ok = belief.get_parked_shadows()
            print(f"  Shadows searched: "
                  f"{len(shadows) - len(belief.get_unknown_shadows()) - len(_parked_ok)}"
                  + (f" ({len(_parked_ok)} parked unresolved)"
                     if _parked_ok else ""))
        else:
            print(f"  Stack goal: {goal}")
            print(f"  Final on-relations: {on_relations}")
            print(f"  Plans executed: {plan_count}")
        if integrity_events:
            # #P2 / F18: a success that disturbed, toppled or lost a
            # bystander is not a clean success — say so, and persist it.
            _kinds = Counter(e.get("kind") for e in integrity_events)
            print(f"  NOTE: success with {len(integrity_events)} world-"
                  f"integrity event(s) — {dict(_kinds)}; objects "
                  f"{sorted({e.get('object') for e in integrity_events})} "
                  f"(#P2 monitor; not a clean success)")
    else:
        remaining = belief.get_unknown_shadows()
        # #P1 F15(c): fragments parked UNRESOLVED were never observed
        # empty — the robot saw them occupied by something it could not
        # localize, or never cleared the view at all.  They are excluded
        # from planning but must never read as "searched", or a run that
        # gave up on the region actually holding the target would look
        # like an exhaustive search that came up empty.
        _parked = belief.get_parked_shadows()
        if _parked:
            print(f"  NOTE: {len(_parked)} shadow fragment(s) parked "
                  f"UNRESOLVED, not eliminated — sensing never settled "
                  f"them and the target may be inside: {sorted(_parked)}")
        if exit_reason is None:
            # audit #107: replan cap removed; a failed run with no explicit
            # give-up means the runner's per-cell wall-clock budget was
            # exhausted (it records "timeout").
            exit_reason = "timeout"
        if exit_reason == "all_searched":
            if blocked_giveup_shadows:
                # Audit #21: distinguish observed-empty shadows from
                # blocked-unresolved ones so the run report does not
                # claim a complete search when some shadows were never
                # actually observed.
                observed_empty = len(shadows) - len(blocked_giveup_shadows)
                print(f"FAILED: {observed_empty} shadow(s) observed "
                      f"empty, {len(blocked_giveup_shadows)} "
                      f"blocked-unresolved (target may still be there): "
                      f"{sorted(blocked_giveup_shadows)} — see audit #21 "
                      f"(real fix #47 deferred 2026-05-06)")
            else:
                print(f"FAILED: All {len(shadows)} shadows searched — target not found")
        elif exit_reason == "pick_giveup":
            # #P1 F2: mirror of the audit-#21 blocked-shadow giveup —
            # the run ended because objects were withdrawn from the
            # grasp stream after 3 failed pick attempts each (single
            # fixed grasp cannot adapt to a toppled/shifted pose; the
            # step-(4) sampler is the real remedy).
            print(f"FAILED: Gave up grasping "
                  f"{sorted(pick_giveup_objects or [])} after 3 failed "
                  f"pick attempts each — no plan without them "
                  f"({len(remaining)} unsearched shadows remaining)")
        elif exit_reason == "no_plan_while_holding":
            # 2026-08-21: the audit-#58 blind drop is retired (user
            # directive) — when neither the mission nor a minimal
            # disposal place is plannable with the held object, the
            # episode ends honestly, object still in hand.
            print(f"FAILED: No mission plan and no disposal place for the "
                  f"held object — episode ended while holding (audit-#58 "
                  f"drop retired; {len(remaining)} unsearched shadows "
                  f"remaining)")
        elif exit_reason == "rediscovery_giveup":
            # M7 (Hani, 2026-11-20): the loop stopped because the only
            # regions left were suspended at the F9 give-up.
            print(f"FAILED: the only shadows left to search are suspended "
                  f"at the F9 give-up (M7): {_suspended_text(belief)}; the "
                  f"target may be inside"
                  + (f"; {len(blocked_giveup_shadows)} more given up after "
                     f"repeated still_blocked outcomes (audit #21), not "
                     f"observed empty: {sorted(blocked_giveup_shadows)}"
                     if blocked_giveup_shadows else ""))
        elif exit_reason == "planner_failed":
            _susp = _suspended_text(belief)
            print(f"FAILED: Planner returned no plan "
                  f"({len(remaining)} unsearched shadows remaining"
                  + (f"; suspended at the F9 give-up (M7): {_susp}" if _susp
                     else "") + ")")
        elif exit_reason == "no_plan_binding_death":
            # #P1 F7 (2026-08-22): FastDownward found action skeletons
            # but stream binding never delivered values (sample_time
            # ~0) — the silent re-pick binding death, disclosed as its
            # own class so "skeletons existed" is never silent.  Root
            # cause (skeleton-queue scheduling) is #P2 scope.
            print(f"FAILED: No plan — but action skeleton(s) existed "
                  f"and stream binding failed to deliver values "
                  f"(#P1 F7 binding death; [F7-diag] in the log has "
                  f"the skeleton; {len(remaining)} unsearched shadows "
                  f"remaining)")
        elif exit_reason == "drop_failed":
            print(f"FAILED: Could not release held object after retries — "
                  f"aborted to avoid double-grasp "
                  f"({len(remaining)} unsearched shadows remaining)")
        elif exit_reason == "knocked_off_table":
            # #P2 (a): the monitor saw a goal-critical object below the
            # table surface — the episode ended at once, honestly.
            _gone = sorted({e.get("object") for e in (integrity_events or [])
                            if e.get("kind") == "knocked_off_table"})
            print(f"FAILED: goal-critical object(s) {_gone} knocked off the "
                  f"table (#P2 world-integrity monitor; "
                  f"{len(remaining)} unsearched shadows remaining)")
        elif exit_reason == "target_lost":
            # Review round 2: the target was seen and registered, then its
            # believed region was observed empty (shoved out of view) and
            # it never resurfaced — a manipulation loss, not a search that
            # came up empty.
            _lost = sorted({e.get("object") for e in (integrity_events or [])
                            if e.get("kind") == "lost"})
            _susp = _suspended_text(belief)
            print(f"FAILED: the target was seen, then lost from view "
                  f"({_lost}) and never re-detected (#P2 monitor; "
                  f"{len(remaining)} unsearched shadows remaining"
                  + (f"; suspended at the F9 give-up (M7): {_susp}" if _susp
                     else "") + ")")
        elif exit_reason == "stack_giveup":
            _worst = sorted((stack_fail_counts or {}).items(),
                            key=lambda kv: -kv[1])[:3]
            print(f"FAILED: gave up stacking after repeated physical stack "
                  f"failures — {[(f'{o} on {s}', n) for (o, s), n in _worst]} "
                  f"(#P2 F28, 3-strike counter)")
        elif exit_reason == "physics_mismatch":
            # Audit S-18: belief says target was found, but the
            # end-of-run physics check disagreed (gripper empty
            # or wrong body welded — the lift-above-table sub-
            # check was dropped after it false-failed terminal-
            # pick runs against the post-2026-04-22 no-lift-on-
            # pick design; see _verify_holding docstring and
            # CODEBASE_AUDIT.txt#36).  Details are in
            # physics_failures / the PHYSICAL_FAILURE (goal)
            # line printed earlier.
            print(f"FAILED: Belief said target was found but physics "
                  f"check disagreed (see PHYSICAL_FAILURE above) — "
                  f"audit S-18")
        elif goal_kind == 'stack':
            print(f"FAILED: Stack goal not reached after {plan_count} plans "
                  f"(goal {goal}, achieved {on_relations})")
        else:
            print(f"FAILED: Ran out of wall-clock budget after {plan_count} "
                  f"plans with {len(remaining)} unsearched shadows remaining")
        print(f"  Plans executed: {plan_count}")

    # TB-22 (tracks rule 18): drops, collisions, how each was detected and
    # clean_success, for every episode record (world_counts.py).  Without
    # the observer the counts are None and say "not detected", never 0.
    rule18 = world_counts.episode_fields(
        success, observer_counts, integrity_events,
        drops_noticed=(sum(drops_noticed.values())
                       if drops_noticed is not None else None),
        collisions_reported=collisions_reported)
    rule18["drops_noticed_by"] = dict(drops_noticed or {})
    print(f"  World counts (TB-22): drops {rule18['drops']} "
          f"(noticed by the robot: {rule18['drops_noticed']}), collisions "
          f"{rule18['collisions']} (reported by the executor: "
          f"{rule18['collisions_reported']}), clean success "
          f"{rule18['clean_success']}")

    print(f"\n--- Planning timing summary ---")
    print(f"  Total plan() calls       : {len(plan_times)}")
    print(f"  Cumulative planning time : {total_plan_time:.3f}s")
    if plan_times:
        avg = total_plan_time / len(plan_times)
        print(f"  Average per call         : {avg:.3f}s")
        per_call_str = ', '.join(f'{t:.3f}' for t in plan_times)
        print(f"  Per-call (s)             : [{per_call_str}]")

    # Machine-readable summary alongside the full text log so multi-run
    # comparisons (baseline vs. stack feature, GUI vs. no-GUI, etc.)
    # don't require parsing the prose log.
    if run_logger is not None:
        summary_path = run_logger.run_dir / "timing_summary.json"
        # Audit #73 step 1(a): end-of-run boxel counts by type drive
        # the compactness plots (Tier A, plots 1/3/11).
        boxel_counts: dict = {}
        if registry is not None:
            try:
                obj_boxels = registry.get_object_boxels()
                shadow_boxels = registry.get_shadow_boxels()
                free_boxels = registry.get_free_space_boxels()
                boxel_counts = {
                    "n_object_boxels": len(obj_boxels),
                    "n_shadow_boxels": len(shadow_boxels),
                    "n_free_space_boxels": len(free_boxels),
                    # Audit #73 step 2(c) plot 3: per-boxel volumes by
                    # type for the heterogeneity histogram.  Same end-
                    # of-run snapshot as the counts above; eval_runner's
                    # LIST_VALUED gate keeps these lists out of the
                    # flat CSV.
                    "boxel_volumes_object":     [round(b.volume, 6) for b in obj_boxels],
                    "boxel_volumes_shadow":     [round(b.volume, 6) for b in shadow_boxels],
                    "boxel_volumes_free_space": [round(b.volume, 6) for b in free_boxels],
                }
            except Exception as e:
                print(f"  WARNING: could not snapshot boxel counts: {e}")
        # Audit #73 step 1(b): init-fact totals (last plan() call) +
        # per-predicate breakdown for plot 2's "which atoms blow up"
        # stratification.
        init_facts: dict = {}
        if last_init:
            init_facts["n_init_state_facts"] = len(last_init)
            init_facts["n_facts_by_predicate"] = dict(
                Counter(fact[0] for fact in last_init if fact))
        try:
            summary_path.write_text(json.dumps({
                "run_config": run_config or {},
                "success": bool(success),
                "exit_reason": exit_reason,
                "plan_count": plan_count,
                # Audit #73 step 3(c) plot 4: total sense actions
                # executed across all replans (any outcome).
                "n_sense_actions": sense_count,
                **({"m8": m8_stats} if m8_stats is not None else {}),
                "total_planning_time_s": round(total_plan_time, 3),
                "per_call_planning_time_s": [round(t, 3) for t in plan_times],
                # Audit #40: structured physics-vs-symbolic failure log
                # so eval tooling (#9) can filter false-positive successes.
                "physical_failures_per_action": physical_failures,
                "physical_failures_at_goal": physics_failures,
                # #P2 (d) CB#124 (2026-09-19): the classifications that
                # used to be printed only.  integrity_events are the
                # monitor's perception-only verdicts per action.
                "integrity_events": integrity_events or [],
                "n_integrity_events": len(integrity_events or []),
                "integrity_event_kinds": dict(Counter(
                    e.get("kind") for e in (integrity_events or []))),
                "stack_fail_counts": {f"{o} on {s}": n for (o, s), n
                                      in (stack_fail_counts or {}).items()},
                "blocked_giveup_shadows": sorted(blocked_giveup_shadows or []),
                # M7 (Hani, 2026-11-20): the F9 give-up's suspension length
                # and every suspension's start and end (absent with M7 off).
                **({"m7_suspend_s": m7_suspend_s,
                    "m7_suspensions": suspension_rows(belief)}
                   if m7_suspend_s is not None else {}),
                "pick_giveup_objects": sorted(pick_giveup_objects or []),
                # Audit #73 step 2(d) plot 11: per-replan boxel count
                # snapshots (one dict per planner.plan() iteration) for the
                # adaptive-partition evolution plot.  LIST_VALUED keeps the
                # column in aggregated.jsonl only.
                "boxel_counts_per_replan": boxel_counts_per_replan or [],
                **boxel_counts,
                **init_facts,
                # TB-22 (tracks rule 18): drops, collisions, the two
                # detector texts, clean_success, and what was counted.
                **rule18,
            }, indent=2))
            print(f"  Timing summary written to {summary_path}")
        except Exception as e:
            print(f"  WARNING: could not write timing_summary.json: {e}")
    print("=" * 60)
    # The curated console's closing block (a no-op without a console).
    console_ui.summary(success=success, exit_reason=exit_reason,
                       plan_count=plan_count, plan_times=plan_times,
                       total_plan_time=total_plan_time,
                       log_path=(run_logger.log_path if run_logger is not None
                                 else None))
