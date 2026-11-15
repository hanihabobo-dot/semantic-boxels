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

# The ways a dispatched step may end.  'ok' is the only one that lets the
# dispatcher go on to the next step of the same plan; every other value is
# a logged early end (gate G3).  'unlabelled' is written only when the
# dispatcher left a step without saying why, and fails G3.
# 'home_not_reached' is D7 (vi)'s bound (#P4 B3(d)): the second
# consecutive planned move to q_home that fails the at-home test.
STEP_END_STATUSES = (
    'ok', 'sense_outcome', 'integrity_replan', 'motion_resolve_failed',
    'pick_failure', 'place_failure', 'stack_failure', 'empty_hand',
    'stale_precondition', 'home_not_reached', 'observe_ok',
    'observe_incomplete', 'look_outcome', 'unlabelled',
)


def ledger_open(run_dir) -> None:
    """Start <run_dir>/ledger.jsonl.  Called by RunLogger."""
    global _ledger_file, _ledger_write_errors, _dispatch
    ledger_close()
    _ledger_write_errors = 0
    _dispatch = None
    _provenance.clear()
    _ledger_file = open(Path(run_dir) / 'ledger.jsonl', 'w', encoding='utf-8')
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
        elif exit_reason == "planner_failed":
            print(f"FAILED: Planner returned no plan "
                  f"({len(remaining)} unsearched shadows remaining)")
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
            print(f"FAILED: the target was seen, then lost from view "
                  f"({_lost}) and never re-detected (#P2 monitor; "
                  f"{len(remaining)} unsearched shadows remaining)")
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


# ---------------------------------------------------------------------------
# Pipeline CLI argument parsing (extracted from test_full_pipeline.py
# 2026-05-05).  Lives here rather than in test_full_pipeline.py so the
# entry-point block stays short; the scene-builder dispatch and main()
# call remain in the orchestrator.
# ---------------------------------------------------------------------------


def parse_pipeline_args(argv=None):
    """Parse the pipeline CLI args and return the validated Namespace.

    Performs post-parse validation (scene auto-promotion under
    --n-hidden / --goal stack, --n-hidden vs --n-occluders/--n-targets
    sanity checks).  ``parser.error`` exits the process on bad input.
    """
    parser = argparse.ArgumentParser(description='Full PDDLStream Pipeline with Replanning')
    parser.add_argument('--no-gui', action='store_true', help='Run without GUI')
    parser.add_argument(
        '--no-boxel-viz',
        action='store_true',
        help='Keep PyBullet GUI but skip drawing boxel AABBs/labels (debug clutter)',
    )
    parser.add_argument(
        '--show-free',
        action='store_true',
        help='Include free-space boxels in the visualisation overlay',
    )
    parser.add_argument('--log-level',
                        choices=['smart', 'normal', 'quiet', 'verbose'],
                        default='smart',
                        help='Console verbosity. "smart" (default) shows the '
                             'curated console (header, planner calls, actions '
                             'with outcomes, sense results, warnings, summary) '
                             'and sends the raw stdout and stderr of the whole '
                             'process to <run_dir>/console_debug.log. "normal", '
                             '"quiet", and "verbose" leave stdout untouched. '
                             'The log file always captures everything.')
    parser.add_argument('--scene', choices=['default', 'mixed',
                                            'scalability', 'stack',
                                            'random-pairs'],
                        default='default',
                        help='Scene preset: default (original cubes), mixed (diverse '
                             'shapes), scalability (random for evaluation), '
                             'stack (N identical cubes, no occluders), '
                             'random-pairs (audit #68 — fixed --n-occluders, '
                             'hidden count drawn uniformly from [1, --n-occluders] '
                             'per seed).')
    parser.add_argument('--n-occluders', type=int, default=3,
                        help='Number of occluders (scalability + random-pairs '
                             'scenes). Default 3.')
    parser.add_argument('--n-targets', type=int, default=4,
                        help='Number of targets (scalability scene only)')
    parser.add_argument('--n-hidden', type=int, default=0,
                        help='Number of targets that must be hidden from '
                             'the camera at spawn time (scalability + '
                             'holding only, audit #29). 0 = no guarantee '
                             '(emergent from RNG). Capped at --n-targets. '
                             'Requires --n-occluders >= 1.')
    parser.add_argument('--n-extra-distractors', type=int, default=0,
                        help='Visible (non-hidden) distractor targets added '
                             'on top of the K hidden targets in --scene '
                             'random-pairs (audit #68). Default 0.')
    parser.add_argument('--n-objects', type=int, default=3,
                        help='Number of cubes for the stack scene '
                             '(must be >= --stack-height)')
    parser.add_argument('--seed', type=int, default=0,
                        help='Random seed (scalability/mixed/stack scenes). '
                             'Note: --n-hidden > 0 may nudge the seed on '
                             'retry if placement fails; the effective seed '
                             'is logged in run_config.')
    parser.add_argument(
        '--goal',
        choices=['holding', 'stack', 'find-and-tray-stack'],
        default='holding',
        help="Goal kind. 'holding' picks the (hidden or visible) target; "
             "'stack' builds a randomised tower of cubes (audit #30); "
             "'find-and-tray-stack' senses every target then stacks them "
             "on a tray (audit #49 — auto-enables the tray entity; "
             "--stack-height ignored, every spawned target is included).",
    )
    parser.add_argument(
        '--stack-height',
        type=int,
        default=2,
        help='Stack tower height in cubes (>= 2). Only used with '
             '--goal stack. Defaults to 2 (one stacking action).',
    )
    parser.add_argument(
        '--allow-unwinnable',
        action='store_true',
        help='Inspection mode: downgrade the pre-flight CLASSIFICATION '
             'rejections (F5 sensable guarantee, find-and-tray-stack '
             'role split) to loud warnings and run the episode anyway, '
             'e.g. to confirm in the GUI that a rejected seed is truly '
             'unwinnable.  Scene-construction failures still abort — '
             'there is no scene to show.  Never use in eval sweeps.',
    )
    parser.add_argument(
        '--unit-costs',
        action='store_true',
        help='Pass unit_costs=True to PDDLStream solve(): override the '
             'domain numeric (increase (total-cost) ...) effects so every '
             'action is cost 1. Default off keeps the domain costs '
             '(place_hiding=2, stack=3, others=1; see THESIS_NOTES section '
             '17); unit costs therefore also disable the F31 hiding-'
             'placement penalty and the place-before-stack preference. Useful '
             'for evaluation sweeps that compare planner behaviour with '
             'and without the stack-cost bias.',
    )
    parser.add_argument(
        '--corridor-test', choices=['cell+object', 'object'],
        default='cell+object',
        help='F32 (2026-09-19): how placement-blocking corridor facts are '
             'tested. cell+object (default, F11): the free cell\'s own AABB '
             'at the census margin plus per-object virtual boxes at the '
             'looser margin. object: virtual boxes only, the volume the '
             'census will actually see after the place (a coarse merged '
             'cell no longer blocks a corridor its centre placement would '
             'not). A/B decides.')
    parser.add_argument(
        '--path-check-diag', action='store_true',
        help='F18 (2026-09-20): report, for every trajectory the motion '
             'stream yields, how many INTERIOR segments of it pass only '
             'with the gripper relaxed — the residual left by growing '
             'the RRT with the relaxed rule applied per edge. Off by '
             'default because it costs a strict check per segment of '
             'every sampled trajectory, most of which are never '
             'executed.')
    parser.add_argument(
        '--path-check-step', type=float, default=None,
        help='F18 (2026-09-20): the resolution of every motion-plan '
             'collision check, in radians of the largest-moving joint '
             'between consecutive samples along an edge. DEFAULT 0 = a '
             'fixed 8 samples per edge, whatever its length. Pass 0.0286 '
             '(0.2/7, what an RRT edge already gets) for the finer check: '
             'it is the sounder test, since 8 samples cannot certify a '
             '63 cm end-effector sweep, but the A/B measured more and '
             'larger bystander disturbances with it on, at equal success '
             'and planning time, so it is not the default.')
    parser.add_argument(
        '--search-sample-ratio', type=float, default=None,
        help='F7 remedy 3 (2026-09-19): the sampling-to-search budget '
             'ratio pddlstream\'s adaptive loop uses per iteration. The '
             'pipeline default is 0.25 (planner.SEARCH_SAMPLE_RATIO); the '
             'library default is 1.0, which busy-waits the full budget on '
             'bindings that are standing by, so one unbindable skeleton '
             'doubles the wall clock every iteration. Pass 1.0 to A/B the '
             'library behaviour on the same code.')
    parser.add_argument(
        '--sense-gate', choices=['off', 'strict'], default='off',
        help='F6 (2026-09-19): what (boxel_fits ?o ?shadow) means for the '
             'sense action. off (default): every view-clear fragment is '
             'sensable (a0e536b behaviour). strict: only fragments in which '
             'a target-class box can rest fully occluded (dense hideability '
             'test, streams.test_target_can_hide_in_shadow). A/B decides '
             'the default for CB#113.')
    # M8-M10 (PLAN_P4_POSE_GRASP_SAMPLERS.md, P4.5 model tweaks): each
    # behind its own switch, default ON by the Q-F decision (BF#34); off
    # gives the pipeline without them (the BEFORE arm).
    parser.add_argument(
        '--m8', choices=['off', 'on'], default='on',
        help='M8: pose-gated pick, view-clear sense configurations and the '
             'wrist-camera observe action (loads the generated domain '
             'pddl/domain_pddlstream_m8.pddl).')
    parser.add_argument(
        '--m9', choices=['off', 'on'], default='on',
        help='M9: object-fitted grasps (yaw and extents of the top-face '
             'rectangle) instead of the AABB grasp candidates.')
    parser.add_argument(
        '--m10', choices=['off', 'on'], default='on',
        help='M10: a failed pick that touched the target makes its pose '
             'unknown (no in-action retry).')
    parser.add_argument(
        '--pick-aperture-from-pose', choices=['off', 'on'], default='on',
        help="M8's aperture rule: open the pads to the pinch half-width "
             "plus pose_radius plus 8 mm (capped at the finger limit).")
    # BF#52 (2026-10-30): with M8 on, the fixed eye senses a region from the
    # target's pick configuration over it when the arm there keeps out of
    # the view (static facts, pddlstream_planner.over_region_facts), and the
    # pick follows without a move; off: every sense returns the arm to a C1
    # spot as before (the A/B against Hani's 18:09 baseline).  Back on the
    # branch after BF#57 for Hani's own test.
    parser.add_argument(
        '--sense-over-region', choices=['off', 'on'], default='on',
        help="BF#52: sense from the target's pick configuration over the "
             "region when the arm there does not block the eye's view, then "
             'pick from there (on), or return to a static view spot before '
             'every sense as before (off).')
    # Path 9 (BF#68, tracks/look): one look action replaces sense and
    # observe (look_domain.py, look_action.py); off keeps both, as before.
    # boxel: the look from a free-space boxel (look_views.py); centred: the
    # reference look that uses no boxel model (the camera straight over the
    # object the look is about, the tag's observe rule).  `on` means boxel.
    parser.add_argument(
        '--look', choices=['off', 'on', 'boxel', 'centred'], default='off',
        help="Path 9: replace the sense and observe actions by one look "
             "action: boxel (a free-space boxel, the generated domain "
             "pddl/domain_pddlstream_look.pddl; `on` is the same) or centred "
             "(the object-centred look, pddl/domain_pddlstream_look_centred."
             "pddl); needs --m8 on.")
    # Path 9, the arm camera only (tracks/look/ARM_ONLY_DESIGN.md): every
    # image comes from the arm camera, the first one at the start
    # configuration, which is q_home.  fixed keeps the overview camera.
    parser.add_argument(
        '--eye', choices=['fixed', 'arm'], default='fixed',
        help="Path 9: arm: the overview camera is the arm camera at the start "
             "configuration (needs --look boxel or --look centred); fixed: "
             "the fixed overview camera, as before.")
    parser.add_argument(
        '--eye-start-joints', default='',
        help="Path 9, --eye arm: the start configuration, one angle per arm "
             "joint in radians, comma separated; it becomes q_home.  Empty: "
             "the caller's home joints (find_dice: TAMPURA's DEFAULT_ARM_POS), "
             "else TAMPURA's home joints (arm_eye.TAMPURA_HOME_JOINTS).")
    # BF#53 (2026-10-30), the optimistic search's settings.  pddlstream
    # weighs a stream result's effort into the search's costs only with
    # effort_weight set; without it every attempt of the adaptive loop may
    # pick a fresh unrefined alternative (seed 10's first call: 13
    # attempts, 11 s of search; with the weight 2.4 s).  The starting
    # complexity: every pick needs a grasp, a kin solution and a motion,
    # three stream levels, so the loop's levels 0 to 2 find no plan.
    # Defaults 1 and 3 since BF#53; 'off' and 0 are pddlstream's own.
    parser.add_argument(
        '--search-effort-weight', default='1',
        help="pddlstream solve(effort_weight=...): a number weighs stream "
             "effort against action cost in the optimistic search, so the "
             "search prefers results already refined (BF#53, default 1); "
             "'off' is pddlstream's default, no weighting.")
    parser.add_argument(
        '--search-initial-complexity', type=int, default=3,
        help="pddlstream solve(initial_complexity=...): the stream "
             "complexity level the adaptive loop starts at (BF#53, default "
             "3); 0 is pddlstream's default.")
    # BF#59 (the die-slip campaign): the candidate fixes' switches
    # (slip_fixes.py holds the names the fixes register; an unknown name is
    # refused before anything runs).  BF#62 (Hani, 2026-11-02): the four
    # switches of the chosen set are on unless the run says otherwise.
    parser.add_argument(
        '--slip-fixes', default='',
        help="BF#59: comma-separated names of the die-slip campaign's fixes "
             "to switch on (slip_fixes.py).  Empty: the four defaults "
             "(solver_iters, force_hold, pose_radius_keep, grasp_wrist_home; "
             "BF#62).  'none': every fix off, the base arm.  'default,x': "
             "the four and x.")
    # GF10 (PAPER_AUDIT.txt BF#38): the pick close's squeeze; 0.5 mm is the
    # default since BF#44 (Hani's GUI verdict, 2026-10-30), 3 mm was before.
    parser.add_argument(
        '--grip-squeeze-mm', type=float, default=0.5,
        help="How far inside the measured width the pick's close holds the "
             "pads, in mm: 0.5 (the default since BF#44, GF10's remedy by "
             "Q14's rule), 3 (the pipeline before it); "
             "other values are for watching only, not measured.")
    # BF#50 (user rule, 2026-10-30): sim screenshots are for debugging only,
    # so world_eye's eye_<k>_camera.png and eye_<k>_gui.png are off unless a
    # run asks for them; eye.log and eye.jsonl are written either way.
    parser.add_argument(
        '--save-screenshots', choices=['off', 'on'], default='off',
        help="Save world_eye's eye_<k>_camera.png (the robot's camera) and, "
             "under the GUI, eye_<k>_gui.png at every snapshot, in the run "
             "directory.  Debugging only; off by default (BF#50).")
    parser.add_argument(
        '--planner',
        choices=['ff-astar1', 'ff-astar2', 'ff-astar', 'ff-wastar1',
                 'ff-wastar2', 'dijkstra'],
        default='ff-astar2',
        help='FastDownward search PDDLStream runs for every action-plan '
             'search (2026-09-18, audit F30). Default ff-astar2 is '
             'PDDLStream\'s own: eager weighted A* with the FF heuristic '
             'doubled (f = g + 2h), which can return a 10-action plan when '
             'a 7-action one exists (a place-then-pick detour of the same '
             'object; the plan is executed as returned, nothing edits it). '
             'ff-astar1 is the same search with w=1 (f = g + h): no '
             'detours, but seed 13 planned 12 -> 103 s and seed 999 hit a '
             '900 s cap, so it is opt-in. ff-astar is plain A*(ff) without '
             'preferred operators; dijkstra is blind, cost-optimal, slow.',
    )
    parser.add_argument(
        '--baseline',
        choices=['semantic', 'uniform'],
        default='semantic',
        help='Free-space discretization strategy (audit #10). "semantic" '
             '(default) is the octree + cell-merger pipeline. "uniform" '
             'replaces it with a strict static uniform 3D grid (see '
             'uniform_grid.py); only the per-cell label mutates over '
             'time, the lattice positions stay fixed across replans.',
    )
    parser.add_argument(
        '--uniform-cell-size',
        type=float,
        default=0.05,
        help='Edge length of each uniform-grid cell, in metres. Only '
             'meaningful with --baseline uniform. Default 0.05 m (5 cm) '
             'matches roughly one cube footprint per cell. Range '
             '[0.02, 0.20] is sane; smaller cells inflate the cell '
             'count quadratically, larger cells overconstrain '
             '(boxel_fits) for cube placement.',
    )
    parser.add_argument(
        '--min-boxel-size',
        type=float,
        default=None,
        help='Minimum FREE-SPACE octree leaf size for the SEMANTIC '
             'baseline, in metres (audit #77). Unset (default) keeps '
             'the audit-#67 floor — semantic is clamped to the '
             'audit-#66 auto_cell (largest object AABB + 1 cm), so '
             'existing #9/#10 comparisons are unchanged. An explicit '
             'value is used RAW and may go below auto_cell, for the '
             'audit-#77 anytime sweep — lets semantic exploit adaptive '
             'partitioning at higher resolution within a fixed time '
             'budget. OBJECT / SHADOW boxels are unaffected — they '
             'remain per-object regardless of this knob.',
    )
    parser.add_argument(
        '--telemetry',
        dest='telemetry',
        action='store_true',
        default=None,
        help='Force the #P1 F17 world telemetry recorder ON. Default: ON '
             'for headless runs, OFF under the GUI (a GUI run already '
             'shows the physics, and sampling should not tax it). The '
             'recorder writes telemetry.log / telemetry.jsonl into the run '
             'directory (every body pose, velocity, tilt, contacts, '
             'relative-to-EE offset and every arm joint at frame '
             'resolution) plus half-second heartbeats, physical events '
             '(fling, grip loss, topple, off-support, joint jump) and '
             'per-action summaries into the run log. Nothing telemetry '
             'writes ever reaches the console.',
    )
    parser.add_argument(
        '--no-telemetry',
        dest='telemetry',
        action='store_false',
        help='Force the world telemetry recorder OFF, including headless. '
             'The drop and collision counts stay (--world-counts).',
    )
    parser.add_argument(
        '--world-counts',
        dest='world_counts',
        choices=['auto', 'on', 'off'],
        default='auto',
        help='TB-22 (tracks rule 18): count drops and collisions for the '
             "run's record (drops, collisions, clean_success in "
             'timing_summary.json). auto (default): on in every headless '
             'run, also under --no-telemetry, as the recorder\'s counts '
             'mode (no frames, no heartbeats, no stream files); off under '
             'the GUI. on: also under the GUI. off: no counts unless the '
             'recorder itself runs; the record then says "not detected". '
             'Nothing in the pipeline reads the counts.',
    )
    parser.add_argument(
        '--telemetry-period',
        type=float,
        default=0.05,
        help='Telemetry FRAME cadence in simulated seconds (default 0.05 = '
             'every 12 steps at 240 Hz). Events force extra frames on top, '
             'so anomalies are always captured densely.',
    )
    parser.add_argument(
        '--telemetry-heartbeat',
        type=float,
        default=0.5,
        help='Cadence in simulated seconds of the compact where-is-'
             'everything dump written into the MAIN run log (default 0.5).',
    )
    parser.add_argument(
        '--max-plan-time',
        type=float,
        default=1800.0,
        help='Per-call PDDLStream max_time in seconds (audit #76 — '
             'plumbed end-to-end to planner.plan() at both the primary '
             'and safety-net call sites). Default 1800.0 keeps pre-#76 '
             'behaviour; lower values fail fast for diagnostic runs.',
    )
    args = parser.parse_args(argv)

    # Audit #29: --n-hidden only makes sense on the scalability scene
    # with --goal holding.  Auto-promote --scene default to scalability
    # when the user passes any of the count knobs under --goal holding
    # (mirrors the --goal stack auto-override below).  Reject clearly
    # wrong combinations early so the user sees a CLI error instead of
    # silently running a scene that cannot satisfy the request.
    _holding_counts_explicit = (
        args.n_hidden > 0
        or '--n-occluders' in sys.argv
        or '--n-targets' in sys.argv
    )
    if (args.goal == 'holding'
            and args.scene == 'default'
            and _holding_counts_explicit):
        args.scene = 'scalability'

    if args.n_hidden > 0:
        if args.scene not in ('scalability',):
            parser.error(
                f"--n-hidden > 0 requires --scene scalability "
                f"(got --scene {args.scene}). Hidden-target guarantee "
                f"only applies to the scalability scene."
            )
        if args.goal not in ('holding', 'find-and-tray-stack'):
            parser.error(
                f"--n-hidden > 0 is only meaningful with --goal holding "
                f"or --goal find-and-tray-stack (got --goal {args.goal}). "
                f"--goal stack uses an occluder-free scene by default."
            )
        if args.n_occluders < 1:
            parser.error(
                "--n-hidden > 0 requires --n-occluders >= 1."
            )
        if args.n_hidden > args.n_targets:
            print(f"[warn] --n-hidden={args.n_hidden} > "
                  f"--n-targets={args.n_targets}; capping to "
                  f"{args.n_targets}.", file=sys.stderr)
            args.n_hidden = args.n_targets

    # Audit #68: random-pairs derives n_hidden from --n-occluders
    # (hidden count is drawn uniformly from [1, --n-occluders] per
    # seed).  --n-hidden / --n-targets remain mutually exclusive — they
    # would contradict the random hidden count, and n_targets is fixed
    # by the design (= n_hidden + --n-extra-distractors).  Also draw a
    # fresh seed by default so consecutive runs differ structurally;
    # explicit --seed N keeps reproducibility.
    if args.scene == 'random-pairs':
        if args.goal not in ('holding', 'find-and-tray-stack'):
            parser.error(
                f"--scene random-pairs requires --goal holding or "
                f"--goal find-and-tray-stack (got --goal {args.goal})."
            )
        _argv_for_check = argv if argv is not None else sys.argv
        for flag in ('--n-hidden', '--n-targets'):
            if flag in _argv_for_check:
                parser.error(
                    f"{flag} is mutually exclusive with --scene "
                    f"random-pairs (hidden count is randomized in "
                    f"[1, --n-occluders] per seed; tune --n-occluders "
                    f"or --n-extra-distractors instead)."
                )
        if args.n_occluders < 1:
            parser.error(
                f"--scene random-pairs requires --n-occluders >= 1 "
                f"(got {args.n_occluders})."
            )
        if '--seed' not in _argv_for_check:
            args.seed = random.randint(0, 2**31 - 1)
            args.seed_auto = True  # consumed by the placement-retry layer
            print(f"[random-pairs] no --seed given; using fresh "
                  f"seed={args.seed}", file=sys.stderr)
        else:
            args.seed_auto = False

        # find-and-tray-stack needs at least 1 VISIBLE target (to place
        # on the tray first) AND at least 1 HIDDEN target (to sense and
        # stack on top).  random-pairs hides every non-distractor target
        # by construction, so a default --n-extra-distractors=0 yields
        # 0 visible / N hidden and the goal-check in test_full_pipeline
        # main() bombs out AFTER the GUI window already opened.  Auto-
        # bump to 1 here so the pre-flight sees a goal-compatible scene
        # and the user only ever sees one GUI window pop up.
        if args.goal == 'find-and-tray-stack' and args.n_extra_distractors < 1:
            print(f"[random-pairs+find-and-tray-stack] auto-bumping "
                  f"--n-extra-distractors from {args.n_extra_distractors} "
                  f"to 1: the goal needs at least one visible target on "
                  f"top of the K hidden ones.", file=sys.stderr)
            args.n_extra_distractors = 1

    # When --goal stack is requested without an explicit --scene, fall
    # back to stack_scene so the spawned objects are reach-constrained
    # cubes by default.  Explicit --scene overrides this for A/B tests.
    if args.goal == 'stack' and args.scene == 'default':
        args.scene = 'stack'

    return args
