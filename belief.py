"""
Belief state for the partial-observability search.

Extracted from test_full_pipeline.py during the audit #26 refactor.
Pure bookkeeping — no PyBullet, no planner.  This makes the
class trivially unit-testable and lets the orchestration loop in
test_full_pipeline.py read top-down without scrolling past dataclasses.
The one output is the #P4 B0 ledger row per fragment change (gate G5),
a no-op when no run ledger is open.
"""

from typing import Dict, List, Optional

from run_logger import ledger_belief, ledger_event


class BeliefState:
    """
    Epistemic model of the robot's partial observability.

    The robot cannot see through occluders, so it doesn't know which shadow
    hides the target.  This class tracks what has been learned through
    sensing actions, enabling the replanning loop to avoid re-exploring
    already-checked shadows.

    Lifecycle per shadow:
      unknown  ─── sense ───► not_here    (target absent → eliminate)
                         ├──► found       (target present → goal reached)
                         └──► unresolved  (#P1 F15: repeatedly observed to
                              contain SOMETHING the render could not
                              localize.  The planner stops offering it —
                              otherwise the episode loops on it forever —
                              but this is NOT a claim that the target is
                              absent, and the run outcome discloses it.
                              Marking such a fragment 'not_here' was the
                              F15 belief lie: it retired the fragment the
                              target was physically sitting in.)
      unresolved ─── time up ───► unknown   (M7's F9 give-up only: that
                              park is a suspension, suspend() and
                              release_suspended(); the others stay.)

    ``occluders_moved`` records physical relocations so the planner can
    emit correct ``obj_at_boxel`` facts for objects that are no longer at
    their original positions.
    """

    def __init__(self, shadows: List[str], target: str):
        self.target = target
        self.shadow_status: Dict[str, str] = {s: 'unknown' for s in shadows}
        self.target_found_in: Optional[str] = None
        self.occluders_moved: Dict[str, str] = {}
        # #P1 F20 follow-up: bodies registered from a whole-workspace sense
        # observation (register_new_detections).  Their FIRST discovery
        # inside a fragment is a discovery, not an F9 "rediscovery".
        self.redetected: set = set()
        # M7's F9 give-up as Hani set it on 2026-11-20 (a timer, 1 to 3
        # minutes): a region parked there is suspended for a while, not for
        # good.  suspended: region -> its open suspension; suspensions: every
        # suspension of the episode in order.  Times are time.perf_counter()
        # values, the clock of the ledger's 't'.
        self.suspended: Dict[str, dict] = {}
        self.suspensions: List[dict] = []

    def add_shadow(self, shadow_id: str) -> None:
        """Register a shadow fragment created AFTER construction as unknown.

        #P1 F20 follow-up (2026-09-18): fragments cast for an object that
        enters the registry mid-episode (contains_nontarget discovery, or
        a whole-workspace re-detection) used to be added to the registry
        and the planner's shadow list but never to this belief, so
        ``get_unknown_shadows`` omitted them and the replan loop could
        declare "all searched" with unsensed fragments still standing.
        A fragment that already has a status keeps it.
        """
        if shadow_id not in self.shadow_status:
            ledger_belief(shadow_id, 'add', 'unknown')
        self.shadow_status.setdefault(shadow_id, 'unknown')

    def remove_shadow(self, shadow_id: str) -> None:
        """Forget a fragment that left the registry WITHOUT an observation
        (the discovery branch's rediscovery cleanup supersedes an object's
        old fragments when it re-registers the object).  An entry left
        behind as 'unknown' would keep get_unknown_shadows() non-empty for
        a fragment nobody can sense, so the loop could never reach its
        all-searched exit and the run summary would name phantom
        unsearched shadows (review finding 2026-09-18).  Observation-backed
        removals keep using mark_sensed(found=False)."""
        if shadow_id in self.shadow_status:
            ledger_belief(shadow_id, 'forget', None)
        self.shadow_status.pop(shadow_id, None)

    def mark_sensed(self, shadow_id: str, found: bool) -> None:
        """Update belief after sensing a shadow."""
        ledger_belief(shadow_id, 'status', 'found' if found else 'not_here')
        if found:
            self.shadow_status[shadow_id] = 'found'
            self.target_found_in = shadow_id
        else:
            self.shadow_status[shadow_id] = 'not_here'

    def mark_unresolved(self, shadow_id: str) -> None:
        """Park a shadow the robot could observe but never resolve (#P1 F15).

        Distinct from ``mark_sensed(found=False)``: that asserts the
        target is NOT in the region, which a "contains something I could
        not localize" observation does not support.  This records only
        that sensing it repeatedly failed to settle the question, so the
        planner should stop spending actions on it.
        """
        if self.shadow_status.get(shadow_id) == 'found':
            return
        ledger_belief(shadow_id, 'status', 'unresolved')
        self.shadow_status[shadow_id] = 'unresolved'

    def get_parked_shadows(self) -> List[str]:
        """Shadows parked unresolved — not eliminated, just not plannable."""
        return [s for s, status in self.shadow_status.items()
                if status == 'unresolved']

    def suspend(self, shadow_id: str, *, bodies: Dict[str, int], now: float,
                seconds: float) -> None:
        """M7's F9 give-up: park the shadow unresolved (the caller names the
        channel) until ``now + seconds``.  ``bodies`` maps each body that
        reached the give-up to its rediscovery count.  A shadow already
        found is left alone, as mark_unresolved leaves it.  A shadow still
        suspended (no path is known to reach this) has its open suspension
        ended as 'resuspended' and a new one started, so no row stays open."""
        self.mark_unresolved(shadow_id)
        if self.shadow_status.get(shadow_id) != 'unresolved':
            return
        old = self.suspended.pop(shadow_id, None)
        if old is not None:
            old['end'], old['ended_by'] = now, 'resuspended'
            ledger_event('m7_suspension', op='end', region=shadow_id,
                         ended_by='resuspended')
        row = {'region': shadow_id, 'bodies': dict(bodies), 'start': now,
               'until': now + seconds, 'end': None, 'ended_by': None}
        self.suspended[shadow_id] = row
        self.suspensions.append(row)
        ledger_event('m7_suspension', op='start', region=shadow_id,
                     bodies=dict(bodies), seconds=seconds)

    def release_suspended(self, now: float) -> List[str]:
        """End the suspensions whose time is up: each region goes back to
        unknown (it was never observed empty) and is offered to the planner
        again; the caller names the channel.  A suspension whose region
        changed meanwhile (a sweep saw it empty, it left the belief) ends
        without a release.  Returns the released regions."""
        released = []
        for sid, row in list(self.suspended.items()):
            status = self.shadow_status.get(sid)
            if status != 'unresolved':
                row['end'], row['ended_by'] = now, status or 'forgotten'
            elif now >= row['until']:
                ledger_belief(sid, 'status', 'unknown')
                self.shadow_status[sid] = 'unknown'
                row['end'], row['ended_by'] = now, 'released'
                released.append(sid)
            else:
                continue
            del self.suspended[sid]
            ledger_event('m7_suspension', op='end', region=sid,
                         ended_by=row['ended_by'])
        return released

    def get_suspended_shadows(self) -> List[str]:
        """Shadows suspended at M7's F9 give-up and not yet released."""
        return [s for s in self.suspended
                if self.shadow_status.get(s) == 'unresolved']

    def mark_occluder_moved(self, occluder_id: str, destination: str) -> None:
        """
        Mark that an occluder has been moved to a new location.

        Args:
            occluder_id: Boxel ID of the occluder that was moved.
            destination: Symbolic boxel ID for the destination (used by
                the planner to emit obj_at_boxel for the new location).
        """
        self.occluders_moved[occluder_id] = destination

    def get_unknown_shadows(self) -> List[str]:
        """Get list of shadows we haven't checked yet."""
        return [s for s, status in self.shadow_status.items() if status == 'unknown']

    def get_known_empty_shadows(self) -> List[str]:
        """Get list of shadows we've checked and found empty."""
        return [s for s, status in self.shadow_status.items() if status == 'not_here']

    def is_target_found(self) -> bool:
        """Check if we've found the target."""
        return self.target_found_in is not None
