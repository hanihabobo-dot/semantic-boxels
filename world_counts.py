"""Drops, collisions and clean success in every episode record (TB-22).

Tracks rule 18 (Hani, 2026-11-07: "you should always save in the eval if
there was at least one drop or coalisons"; 2026-11-08: "Record, decide on
counts"): every eval record, of every arm, carries per episode

  drops               how often a held object left the gripper outside a
                      place, or None when nothing could see it;
  collisions          objects knocked (a bystander that the arm or its
                      load touched and moved in an action), or None;
  drop_detector       how each count was detected, or "cannot happen", or
  collision_detector  "not detected".  A 0 is never written where nothing
                      could see the event;
  clean_success       success with no drop and no collision: False for a
                      failure, None for a success whose counts are unknown.

Beside them, for our pipeline: drop_events and collision_events (what was
counted), drops_noticed (the losses the robot itself noticed: the place and
stack entry check, the check after the lift, the carry check) and
collisions_reported (the moves after which the executor's own contact
report named a contact).  The two "noticed" numbers are what the robot saw;
drops and collisions are the simulator's ground truth, read by telemetry's
counts mode (telemetry.py), which nothing in the pipeline decides on.
counts_cost_s is the wall time that counting took in the episode, by the
observer's own clock.

This module builds and reads the fields and keeps the two numbers the robot
itself notices during a run.  It imports no simulator, so the runner, the
bridge driver and the harnesses can use it anywhere.
"""
import json
import os

FIELDS = ('drops', 'collisions', 'drop_detector', 'collision_detector',
          'clean_success')
# Lists and texts kept out of a flat CSV (eval_runner.LIST_VALUED).
DETAIL_FIELDS = ('drop_events', 'collision_events')
# What the robot itself saw, and the wall time the counting took (s).
EXTRA_FIELDS = ('drops_noticed', 'collisions_reported', 'counts_cost_s')
COUNTS_FILE = 'world_counts.json'
SUMMARY_FILE = 'timing_summary.json'

NOT_DETECTED = 'not detected'
CANNOT_HAPPEN = 'cannot happen'
DROP_DETECTOR = ('telemetry counts: a carried body left both finger pads, '
                 'or the gripper opened on it, outside the release of a place')
COLLISION_DETECTOR = ('telemetry counts: distinct (action, body) pairs of a '
                      'body the gripper did not hold in that action that '
                      'moved over 3 mm after the arm, a body in its grip or '
                      'a body so knocked touched it, plus the '
                      "monitor's knocked_off_table bodies not among them")


# ----- what the robot itself notices during a run ------------------------
# The losses of a held body that the pipeline's own checks notice, by the
# check: 'entry' (the place and stack entry assert), 'lift' (the re-verify
# after the post-pick lift), 'carry' (carry_hold_check); and the moves and
# picks after which the executor's own contact report named a contact.
# They are counted where they happen (execution.py, robot_utils.py) and
# stand in the record beside the simulator's counts, so a report can show a
# drop the robot missed.  Counted only: nothing reads them before the run's
# summary is written.
_noticed = {'entry': 0, 'lift': 0, 'carry': 0}
_reported = {'collisions': 0}


def run_reset():
    """A new run in this process: test_full_pipeline.main calls this
    before it arms the counts."""
    for k in _noticed:
        _noticed[k] = 0
    _reported['collisions'] = 0


def notice_drop(check):
    """One of the robot's three checks found the held body gone."""
    _noticed[check] += 1


def report_collision():
    """The executor's contact report named at least one contact."""
    _reported['collisions'] += 1


def noticed_drops():
    """The run's noticed losses by check (a copy)."""
    return dict(_noticed)


def collisions_reported():
    """How many of the run's contact reports named a contact."""
    return _reported['collisions']


# ----- the fields ---------------------------------------------------------

def wanted(mode, gui):
    """Whether a run arms the counts: --world-counts on, off, or auto (the
    default: every headless run, so every eval; not under the GUI)."""
    return mode == 'on' or (mode == 'auto' and not gui)


def clean(success, drops, collisions):
    """Success with no drop and no collision.  A failure is never clean;
    a success with a count nobody could take is unknown (None)."""
    if not success:
        return False
    if drops is None or collisions is None:
        return None
    return drops == 0 and collisions == 0


def not_detected(success, why=None, drops_noticed=None,
                 collisions_reported=None):
    """The fields of an episode nothing watched."""
    text = NOT_DETECTED + (f' ({why})' if why else '')
    return {'drops': None, 'collisions': None, 'drop_detector': text,
            'collision_detector': text,
            'clean_success': clean(success, None, None),
            'drop_events': [], 'collision_events': [],
            'drops_noticed': drops_noticed,
            'collisions_reported': collisions_reported,
            'counts_cost_s': None}


def episode_fields(success, counts, integrity_events=None,
                   drops_noticed=None, collisions_reported=None, note=None):
    """The fields of one episode of our pipeline.

    counts: telemetry's run counts (WorldTelemetry.counts(): 'drops' and
    'collisions' as lists of events), or None when telemetry did not watch.
    integrity_events: the monitor's verdicts; a knocked_off_table body that
    telemetry counted neither as knocked nor as dropped adds one collision.
    note: appended to both detector texts (a run that ended early)."""
    if counts is None:
        return not_detected(success, drops_noticed=drops_noticed,
                            collisions_reported=collisions_reported)
    drop_events = list(counts.get('drops') or [])
    collision_events = list(counts.get('collisions') or [])
    seen = ({e.get('object') for e in collision_events}
            | {e.get('object') for e in drop_events})
    for e in integrity_events or []:
        if e.get('kind') == 'knocked_off_table' and e.get('object') not in seen:
            seen.add(e.get('object'))
            collision_events.append({'object': e.get('object'),
                                     'phase': e.get('label'),
                                     'source': 'knocked_off_table'})
    tail = f' ({note})' if note else ''
    return {'drops': len(drop_events), 'collisions': len(collision_events),
            'drop_detector': DROP_DETECTOR + tail,
            'collision_detector': COLLISION_DETECTOR + tail,
            'clean_success': clean(success, len(drop_events),
                                   len(collision_events)),
            'drop_events': drop_events, 'collision_events': collision_events,
            'drops_noticed': drops_noticed,
            'collisions_reported': collisions_reported,
            # the observer's own clock: what its checks cost this run
            'counts_cost_s': counts.get('check_s')}


def with_success(fields, success):
    """The same fields under another success verdict (a harness whose
    success test is its own, such as the bridge's outcome)."""
    out = dict(fields)
    out['clean_success'] = clean(success, out.get('drops'),
                                 out.get('collisions'))
    return out


def kinematic_arm_fields(success, collisions=None, collision_detector=None):
    """An arm whose carry is kinematic (TAMPURA's): a drop cannot happen.
    Its collisions are what its own execution reports; with no such report
    they are not detected."""
    if collisions is None:
        collision_detector = collision_detector or (
            NOT_DETECTED + ' (their execution reports no collision)')
    return {'drops': 0, 'collisions': collisions,
            'drop_detector': CANNOT_HAPPEN + ' (kinematic carry)',
            'collision_detector': collision_detector or 'their execution',
            'clean_success': clean(success, 0, collisions),
            'drop_events': [], 'collision_events': [],
            'drops_noticed': None, 'collisions_reported': None,
            'counts_cost_s': None}


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def from_run_dir(run_dir, success=None):
    """The fields of the pipeline run in run_dir.

    From its timing_summary.json when the run wrote one; else from the
    counts file telemetry keeps while it runs (a run killed at the cap, or
    one that crashed: the counts up to its end, and a failure); else not
    detected.  success, when given, replaces the summary's own verdict."""
    summary = _read_json(os.path.join(run_dir, SUMMARY_FILE)) if run_dir else None
    if summary is not None and all(k in summary for k in FIELDS):
        fields = {k: summary.get(k)
                  for k in FIELDS + DETAIL_FIELDS + EXTRA_FIELDS}
        return with_success(fields, summary.get('success') if success is None
                            else success)
    counts = _read_json(os.path.join(run_dir, COUNTS_FILE)) if run_dir else None
    if counts is not None:
        return episode_fields(bool(success), counts,
                              note='the run wrote no summary: counts up to '
                                   'its end')
    return not_detected(bool(success),
                        why='no summary and no counts file')


def from_bridge_episode(episode, save_dir, success):
    """The fields of one bridge episode (our arm on their world) under a
    harness's own success test.

    episode: the driver's bridge_episode.json, which carries the fields, or
    None when the driver wrote none (a kill at the cap, a crash): then from
    the pipeline run the driver kept under <save_dir>/ours (its summary,
    else its counts file: the counts up to the kill)."""
    if episode is not None and all(k in episode for k in FIELDS):
        keys = FIELDS + DETAIL_FIELDS + EXTRA_FIELDS
        return with_success({k: episode.get(k) for k in keys}, success)
    try:
        runs = sorted(n for n in os.listdir(os.path.join(save_dir, 'ours'))
                      if n.startswith('run_'))
    except OSError:
        runs = []
    return from_run_dir(os.path.join(save_dir, 'ours', runs[-1]) if runs
                        else None, success=success)


def of_record(rec, success):
    """A record's five fields under another success test (a harness row
    built on an episode record that already carries them)."""
    return with_success({k: rec.get(k) for k in FIELDS}, success)


def newest_counts_dir(logs_dir, before):
    """The newest run directory under logs_dir that is not in ``before``
    (names) and holds a counts file, or None: where a run that ended
    without a summary left its counts."""
    best = None
    try:
        names = sorted(os.listdir(logs_dir))
    except OSError:
        return None
    for name in names:
        path = os.path.join(logs_dir, name, COUNTS_FILE)
        if name in before or not name.startswith('run_') \
                or not os.path.isfile(path):
            continue
        mtime = os.path.getmtime(path)
        if best is None or mtime > best[0]:
            best = (mtime, os.path.join(logs_dir, name))
    return best[1] if best else None
