"""Drops and collisions in every Wumpus episode record (tracks rule 18).

Hani, 2026-11-07, to Go: "you should always save in the eval if there was at
least one drop or coalisons".  Every record carries, per episode, `drops`,
`collisions`, `drop_detector`, `collision_detector` and `clean_success`
(success with no drop and no collision).  A detector names how it saw the
event, or says "not detected": never a 0 where nothing could see it.

WumpusEnv (wumpus/env.py) detects both and only records them: no detector
changes an action, a pose or a simulation step (tests/test_wumpus_incidents.py
plays the same episodes with and without them).  What counts:

- a drop: the gold bar was held by the grab's own test (both finger pads on
  the bar, the bar more than 5 cm above its pedestal) and later fails that
  test: after the stow inside grab, or at the end of a later move or grab.  A
  grasp whose lift fails never held the bar: a failed grab, not a drop.
- a collision: a body the robot touched or moved without meaning to, counted
  once per action and body:
  - the arm touching a body (PyBullet's contact points within 0.5 mm, the
    grab's own pad threshold, read after every simulation step); touching the
    bar is meant during a grab and while the bar is held;
  - the chassis, which has no collision shape, entering a fixed body's box or
    the bar's (box against box after every base step; a held bar rides along);
  - the bar, never held, moved more than 3 mm since the last check, or lying
    more than 5 cm below its rest height (telemetry.py's DISTURB_MM and
    OFF_TABLE_DROP), checked at the end of every move and grab; its small
    shifts in a grasp that touched it are part of that grasp.
- deaths stay deaths (the outcome), counted apart: no drop or collision.

No PyBullet import here: fields(), record() and line() are pure.
"""
DISTURB_M = 0.003          # telemetry.py DISTURB_MM: an unheld body moved this much
OFF_PEDESTAL_M = 0.05      # telemetry.py OFF_TABLE_DROP: this far below its rest height
CONTACT_M = 0.0005         # a contact point this close is a touch (grab's own pad test)

NOT_DETECTED = 'not detected'
DROP_DETECTOR = ("wumpus/env.py: the grab's held test (both finger pads on the bar, the bar 5 cm "
                 "over its pedestal) after the stow and at the end of every later move or grab")
COLLISION_DETECTOR = ("wumpus/env.py: the arm's PyBullet contacts with any body (the bar is meant in "
                      "a grab and while held) after every sim step; the chassis box against the fixed "
                      "boxes and the bar after every base step; the bar, never held, moved 3 mm or "
                      "fell 5 cm")


def fields(success, drops, collisions):
    """The five rule 18 fields of one episode.  drops or collisions None: no
    detector ran ('not detected'), and a success's clean_success is then None
    (not known); a failure is never a clean success."""
    if not success:
        clean = False
    elif drops is None or collisions is None:
        clean = None
    else:
        clean = drops == 0 and collisions == 0
    return {'drops': drops, 'collisions': collisions,
            'drop_detector': NOT_DETECTED if drops is None else DROP_DETECTOR,
            'collision_detector': NOT_DETECTED if collisions is None else COLLISION_DETECTOR,
            'clean_success': clean}


def record(env, success):
    """fields() of an episode on `env` from its counters, plus `incidents`
    (one entry per counted event).  An env without detectors (a test's
    stand-in, or WumpusEnv(detect=False)) gives 'not detected'."""
    out = fields(success, getattr(env, 'drops', None), getattr(env, 'collisions', None))
    out['incidents'] = list(getattr(env, 'incidents', None) or [])
    return out


def line(rec):
    """Success as before, with clean success beside it: the counts for a
    console or report line."""
    def n(v):
        return NOT_DETECTED if v is None else str(v)
    clean = {True: 'yes', False: 'no', None: 'not known'}[rec['clean_success']]
    return f"drops {n(rec['drops'])}, collisions {n(rec['collisions'])}, clean success {clean}"
