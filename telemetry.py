"""Frame-level world telemetry for headless runs (#P1 F17, 2026-08-22).

A GUI run lets the user WATCH the episode: they see the block leave the
gripper mid-transit, the tower lean over, the arm swing through its own
workspace.  A headless run saw none of that — the log recorded DECISIONS
(plans, senses, census verdicts) but almost nothing about PHYSICS, so a
field failure like the F14 transit ejection was only ever caught by a
human staring at the GUI.  This module records the physics at frame
resolution so a headless log misses nothing a GUI run would have shown.

WHAT IS RECORDED

  * FRAMES (default every 0.05 s of SIM time, plus one on every event):
    full world state — every body's pose, linear/angular velocity,
    resting height, tilt, contact partners, displacement since the
    action started, and its position RELATIVE to the end effector; plus
    the arm's joint positions/velocities, per-step joint deltas, EE pose
    and EE speed.  Written to ``telemetry.log`` (human) and
    ``telemetry.jsonl`` (tooling) in the run directory.
  * HEARTBEATS (default every 0.5 s of sim time): a compact one-line-
    per-body pose+speed dump into the MAIN run log, so reading the run
    log alone tells you where everything was at any half second.
  * EVENTS: fired the moment a physical anomaly appears (fling, grip
    loss, topple, off-table, airborne, joint jump, disturbance of a body
    nobody is touching).  Events go to the main run log too — they are
    the "you would have seen this in the GUI" moments.
  * ACTION SUMMARIES: at every phase boundary, the peak EE speed, peak
    joint velocity, worst per-step joint delta, and per-body net
    displacement / peak speed / final state of the action just executed.

SCOPE CONTRACT (important for the p.getAABB grep gate)

  Telemetry is a WRITE-ONLY OBSERVER.  It reads the simulator directly
  (poses, velocities, AABBs, contacts) and its only output is log text —
  it never returns a value to the pipeline, never touches the registry,
  the belief, or the planner's fact set, and disabling it cannot change
  an episode's outcome.  It sits in the same accepted category as the
  eval verifiers and the execution servo, NOT in the perception path:
  nothing here is an observation the robot is allowed to plan on.

CONSOLE CONTRACT

  Every line this module emits goes through ``logger.debug`` or straight
  to the telemetry files, so it lands in the run LOG FILE and never on
  the console — in headless runs or GUI runs alike.  Telemetry is also
  DISABLED BY DEFAULT under the GUI (user direction 2026-08-22: the GUI
  run already shows this, and the sampling should not tax it); pass
  ``--telemetry`` to force it on, ``--no-telemetry`` to force it off.

COUNTS MODE (TB-22, tracks rule 18: drops and collisions in every record)

  ``counts_only=True`` arms the same observer without the recording: no
  frames, heartbeats, summaries, notes or log lines, and no stream files.
  It keeps two run-level counts, which the recorder keeps as well:

  * DROPS.  A body counts as carried once both finger pads hold it and it
    touches nothing but the robot (CARRIED_CHECKS checks in a row).  A
    carried body is dropped when it has no finger contact for DROP_CHECKS
    checks in a row, or when the gripper is opened on it, in both cases
    outside the release of a place (the pipeline tells the observer when
    it commands the gripper: gripper_command).  Unlike GRIP_LOST this
    does not ask how wide the fingers are, so a body that levers the
    fingers past 35 mm on its way out still counts, and so does one
    knocked out of the hand onto another body.
  * COLLISIONS.  The DISTURBED test, counted once per (action, body).
    The fall of a dropped body is its drop: its motion in the action of
    the drop and in the action after it is not counted again.

  Both are ground truth for the episode's record (world_counts.py);
  nothing in the pipeline reads them before the run's summary is written.
  ``world_counts.json`` in the run directory is rewritten at arming, on
  every counted event and at the close, so a run killed at its wall-clock
  cap keeps its counts.  ``--world-counts off`` turns the mode off.
  The mode clocks its own checks: the record's ``counts_cost_s`` is the
  wall time they took in that run.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from time import perf_counter as _perf

import numpy as np
import pybullet as p

logger = logging.getLogger(__name__)

# PyBullet's default fixed timestep; the pipeline never calls
# p.setTimeStep, so every stepSimulation advances sim time by this much.
DEFAULT_TIMESTEP = 1.0 / 240.0

# Full-frame cadence in SIM seconds.  0.05 s = every 12 steps at 240 Hz:
# fine enough that a 0.125 s waypoint interpolation (steps=30) still
# yields several frames, and events force extra frames on top.
DEFAULT_FRAME_PERIOD_S = 0.05

# Compact "where is everything" heartbeat into the main run log.
DEFAULT_HEARTBEAT_PERIOD_S = 0.5

# Event checks run on this stride (2 steps = 120 Hz) — cheap enough to
# run continuously and fast enough to catch a block leaving the hand.
EVENT_STRIDE = 2

# ---------------------------------------------------------------------------
# Event thresholds.  These only decide what gets FLAGGED in the log; no
# threshold here changes execution.
# ---------------------------------------------------------------------------

# A tabletop pick-and-place moves cargo at a few cm/s.  0.60 m/s is far
# above anything the arm should impart to a carried block and well below
# free-fall from table height (~2.5 m/s), so it flags a fling without
# flagging a legitimate drop.
FLING_SPEED = 0.60                  # m/s

EE_SPEED_WARN = 1.00                # m/s at the grasp target

# Per-step joint delta.  The executor interpolates a FIXED step count per
# waypoint pair, so a large delta means a large commanded jump: 0.05 rad
# per step is 12 rad/s at 240 Hz, ~5x the Panda's real joint velocity
# limit — the F14 mechanism, made visible.
JOINT_STEP_WARN = 0.05              # rad per simulation step

# Franka Emika Panda datasheet joint velocity limits (rad/s), joints 1-7.
PANDA_JOINT_VEL_LIMIT = np.array([2.175, 2.175, 2.175, 2.175,
                                  2.610, 2.610, 2.610])

TILT_WARN_DEG = 15.0                # a resting cube should stay near 0
DISTURB_MM = 3.0                    # unheld body moved this much = poked
OFF_TABLE_DROP = 0.05               # m below the support it started on

# The drop count (TB-22).  Checks are EVENT_STRIDE steps apart (1/120 s).
# CARRIED_CHECKS: a pinched body off every support this long is carried
# (25 ms: the squeeze of a grasp on the table does not make a carry).
# DROP_CHECKS: a carried body with no finger contact this long is dropped
# (25 ms of free fall is 3 mm; a hold does not lose both pads that long).
CARRIED_CHECKS = 3
DROP_CHECKS = 3
COUNTS_FILE = 'world_counts.json'


def _yaw_pitch_roll_deg(quat):
    """Body orientation as (roll, pitch, yaw) in degrees."""
    return [math.degrees(a) for a in p.getEulerFromQuaternion(quat)]


def _tilt_deg(quat) -> float:
    """Angle between the body's own +Z axis and world +Z, in degrees."""
    m = p.getMatrixFromQuaternion(quat)
    return math.degrees(math.acos(max(-1.0, min(1.0, m[8]))))


class WorldTelemetry:
    """Samples the simulator every step and writes the frame stream.

    Args:
        client_id: PyBullet client holding the physics.
        robot_id: Robot body id, or None while no robot exists yet
            (Phase-1 settling still gets body frames).
        body_names: ``{body_id: name}`` for everything worth recording.
        run_dir: Run directory; ``telemetry.log`` / ``telemetry.jsonl``
            are written here.
        frame_period_s / heartbeat_period_s / timestep: cadences, in
            SIM seconds.
        ee_link / arm_joints / finger_joints: robot indices, injected so
            this module does not import robot_utils (which imports the
            world back).
        counts_only: the counts mode (module docstring): the drop and
            collision counts without the recording.  ``run_dir`` may then
            be None (no counts file).
    """

    def __init__(self, client_id, robot_id, body_names, run_dir,
                 frame_period_s: float = DEFAULT_FRAME_PERIOD_S,
                 heartbeat_period_s: float = DEFAULT_HEARTBEAT_PERIOD_S,
                 timestep: float = DEFAULT_TIMESTEP,
                 ee_link: int = 11,
                 arm_joints=(0, 1, 2, 3, 4, 5, 6),
                 finger_joints=(9, 10),
                 counts_only: bool = False):
        self.client_id = client_id
        self.robot_id = robot_id
        self.body_names = dict(body_names or {})
        self.timestep = float(timestep)
        self.frame_every = max(1, int(round(frame_period_s / self.timestep)))
        self.heartbeat_every = max(
            1, int(round(heartbeat_period_s / self.timestep)))
        self.ee_link = ee_link
        self.arm_joints = list(arm_joints)
        self.finger_joints = list(finger_joints)
        self.counts_only = bool(counts_only)

        self.run_dir = Path(run_dir) if run_dir is not None else None
        if self.run_dir is not None:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.counts_only:
            self._stream = None
            self._jsonl = None
        else:
            self._stream = open(self.run_dir / 'telemetry.log', 'w',
                                encoding='utf-8')
            self._jsonl = open(self.run_dir / 'telemetry.jsonl', 'w',
                               encoding='utf-8')

        # The run-level counts (TB-22), kept in both modes.
        self._phase_index = 0
        self._release_commanded = True      # no close commanded yet
        self._grip = {}                     # body -> its grip state (_drop_check)
        self._drops = []                    # counted drops, in order
        self._disturbed = {}                # (phase index, body) -> event
        self._dropped_in = {}               # body -> phase index of its last drop
        self._check_s = 0.0                 # wall time spent in the counts mode's checks
        self._closed = False

        self.step_count = 0
        self.sim_time = 0.0
        self._last_frame_step = -10 ** 9
        self._last_heartbeat_step = -10 ** 9

        self._phase = 'startup'
        self._phase_start_step = 0
        self._phase_start_time = 0.0
        self._phase_start_pos = {}          # body -> pos at phase start
        self._phase_peak_speed = {}         # body -> peak |v|
        self._phase_flung = set()           # bodies that fired FLING
        self._phase_events = {}             # event kind -> count
        self._phase_peak_ee_speed = 0.0
        self._phase_peak_joint_vel = 0.0
        self._phase_peak_joint_vel_idx = -1
        self._phase_peak_step_delta = 0.0
        self._phase_peak_step_delta_idx = -1
        self._event_frames_this_phase = 0

        self._prev_joints = None
        self._prev_joints_step = 0
        self._rob_cache = None              # (step, state) — one read per tick
        self._held_prev = set()             # bodies gripped at the last check
        self._held_this_phase = set()       # bodies the arm held this action
        self._grip_pending = set()          # left the pads, awaiting confirm
        self._latched_states = set()        # (body, kind) already reported
        self._prev_fingers = None           # last max finger opening
        self._spawn_pos = {}                # body -> pose at enable()
        self._support_z = {}                # body -> z it started resting at

        if self._stream is not None:
            self._stream.write(
                "# Semantic Boxels world telemetry (#P1 F17)\n"
                f"# frame every {self.frame_every} steps "
                f"({frame_period_s:.3f} s sim), heartbeat every "
                f"{self.heartbeat_every} steps ({heartbeat_period_s:.2f} s sim), "
                f"timestep {self.timestep * 1000:.3f} ms\n"
                "# events checked every "
                f"{EVENT_STRIDE} steps; thresholds: fling {FLING_SPEED} m/s, "
                f"ee {EE_SPEED_WARN} m/s, joint step {JOINT_STEP_WARN} rad, "
                f"tilt {TILT_WARN_DEG} deg, disturb {DISTURB_MM} mm\n\n")
        for bid, name in sorted(self.body_names.items()):
            try:
                pos, quat = p.getBasePositionAndOrientation(
                    bid, physicsClientId=self.client_id)
            except Exception:
                continue
            self._spawn_pos[bid] = np.asarray(pos, dtype=float)
            self._phase_start_pos[bid] = np.asarray(pos, dtype=float)
            self._support_z[bid] = float(pos[2])
        self._save_counts()
        if self.counts_only:
            logger.debug("[tele] counts mode armed: %d bodies, drops and "
                         "collisions only (TB-22)", len(self.body_names))
            return
        logger.debug("[tele] telemetry armed: %d bodies, frame %.3f s, "
                     "heartbeat %.2f s -> %s",
                     len(self.body_names), frame_period_s,
                     heartbeat_period_s, self.run_dir / 'telemetry.log')

    # ----- lifecycle -------------------------------------------------------

    def attach_robot(self, robot_id: int):
        """Register the robot once it exists (scene settling runs first)."""
        self.robot_id = robot_id
        self._prev_joints = None

    def register_bodies(self, body_names):
        """Add bodies discovered after arming (tray, spawned targets)."""
        for bid, name in (body_names or {}).items():
            if bid in self.body_names:
                continue
            self.body_names[bid] = name
            try:
                pos, _ = p.getBasePositionAndOrientation(
                    bid, physicsClientId=self.client_id)
            except Exception:
                continue
            self._spawn_pos[bid] = np.asarray(pos, dtype=float)
            self._phase_start_pos[bid] = np.asarray(pos, dtype=float)
            self._support_z[bid] = float(pos[2])

    def close(self):
        """Flush the final action summary and close the streams."""
        self._closed = True
        self._save_counts()
        if self.counts_only:
            logger.debug("[tele] counts mode closed after %d steps: %d "
                         "drop(s), %d collision(s)", self.step_count,
                         len(self._drops), len(self._disturbed))
            return
        self._emit_phase_summary()
        try:
            self._stream.flush()
            self._stream.close()
            self._jsonl.flush()
            self._jsonl.close()
        except Exception:
            pass
        logger.debug("[tele] telemetry closed after %d steps (%.3f s sim)",
                     self.step_count, self.sim_time)

    # ----- annotation ------------------------------------------------------

    def phase(self, label: str):
        """Close the current action block, summarise it, and start a new one."""
        if not self.counts_only:
            self._emit_phase_summary()
        self._phase_index += 1
        self._phase = label
        self._phase_start_step = self.step_count
        self._phase_start_time = self.sim_time
        self._phase_peak_speed = {}
        self._phase_flung = set()
        self._phase_events = {}
        self._phase_peak_ee_speed = 0.0
        self._phase_peak_joint_vel = 0.0
        self._phase_peak_joint_vel_idx = -1
        self._phase_peak_step_delta = 0.0
        self._phase_peak_step_delta_idx = -1
        self._event_frames_this_phase = 0
        self._held_this_phase = set(self._held_prev)
        for bid in list(self.body_names):
            try:
                pos, _ = p.getBasePositionAndOrientation(
                    bid, physicsClientId=self.client_id)
                self._phase_start_pos[bid] = np.asarray(pos, dtype=float)
            except Exception:
                pass
        if self.counts_only:
            return
        self._write(f"\n===== PHASE: {label}  "
                    f"(t={self.sim_time:7.3f}s step={self.step_count})\n")
        logger.debug("[tele] phase: %s (t=%.3fs step=%d)",
                     label, self.sim_time, self.step_count)

    def note(self, text: str):
        """Inject a pipeline annotation (belief snapshot, decision) inline."""
        self._write(f"  [note t={self.sim_time:7.3f}s] {text}\n")

    # ----- the per-step hook ----------------------------------------------

    def tick(self):
        """Called immediately after every ``p.stepSimulation``."""
        self.step_count += 1
        self.sim_time += self.timestep

        if self.counts_only:
            if self.step_count % EVENT_STRIDE == 0:
                t0 = _perf()                 # the mode's own cost, for the record
                self._check_counts()
                self._check_s += _perf() - t0
            return

        forced = False
        if self.step_count % EVENT_STRIDE == 0:
            forced = self._check_events()

        due_frame = (self.step_count - self._last_frame_step) >= self.frame_every
        if forced and self._event_frames_this_phase < 60:
            due_frame = True
            self._event_frames_this_phase += 1
        if due_frame:
            self._last_frame_step = self.step_count
            self._emit_frame()

        if (self.step_count - self._last_heartbeat_step) >= self.heartbeat_every:
            self._last_heartbeat_step = self.step_count
            self._emit_heartbeat()

    # ----- sampling --------------------------------------------------------

    def _body_state(self, bid, light: bool = False):
        """Pose, velocity, contacts and derived quantities for one body.

        ``light`` (the counts mode): only what the DISTURBED test reads,
        the displacement this action and, for a body that moved past
        DISTURB_MM, its speed; the velocity of a body that did not move
        is not read (the test is false for it whatever its speed)."""
        pos, quat = p.getBasePositionAndOrientation(
            bid, physicsClientId=self.client_id)
        if light:
            start = self._phase_start_pos.get(bid)
            moved_mm = (math.dist(pos, start) * 1000.0
                        if start is not None else 0.0)
            speed = 0.0
            if moved_mm > DISTURB_MM:
                lin, _ = p.getBaseVelocity(bid, physicsClientId=self.client_id)
                speed = math.sqrt(lin[0] ** 2 + lin[1] ** 2 + lin[2] ** 2)
            return {'id': bid, 'name': self.body_names.get(bid, str(bid)),
                    'moved_mm': moved_mm, 'speed': speed}
        lin, ang = p.getBaseVelocity(bid, physicsClientId=self.client_id)
        pos = np.asarray(pos, dtype=float)
        lin = np.asarray(lin, dtype=float)
        ang = np.asarray(ang, dtype=float)
        aabb_min, aabb_max = p.getAABB(bid, physicsClientId=self.client_id)
        contacts = p.getContactPoints(bodyA=bid,
                                      physicsClientId=self.client_id)
        partners = {}
        for c in contacts:
            other = c[2] if c[1] == bid else c[1]
            other_link = c[4] if c[1] == bid else c[3]
            key = (other, other_link)
            partners[key] = partners.get(key, 0.0) + float(c[9])
        start = self._phase_start_pos.get(bid)
        moved_mm = (float(np.linalg.norm(pos - start)) * 1000.0
                    if start is not None else 0.0)
        spawn = self._spawn_pos.get(bid)
        drift_mm = (float(np.linalg.norm(pos - spawn)) * 1000.0
                    if spawn is not None else 0.0)
        return {
            'id': bid,
            'name': self.body_names.get(bid, str(bid)),
            'pos': pos,
            'quat': quat,
            'rpy_deg': _yaw_pitch_roll_deg(quat),
            'tilt_deg': _tilt_deg(quat),
            'v': lin,
            'speed': float(np.linalg.norm(lin)),
            'w_deg_s': float(np.degrees(np.linalg.norm(ang))),
            'aabb_min': np.asarray(aabb_min, dtype=float),
            'aabb_max': np.asarray(aabb_max, dtype=float),
            'contacts': partners,
            'moved_mm': moved_mm,
            'drift_mm': drift_mm,
        }

    def _robot_state(self):
        """Joint positions/velocities, per-step deltas and EE kinematics.

        Cached per simulation step: a tick that both checks events and
        emits a frame must see ONE reading, or the second call would
        difference the joints against themselves and report a per-step
        delta of zero.
        """
        if self.robot_id is None:
            return None
        if self._rob_cache is not None and self._rob_cache[0] == self.step_count:
            return self._rob_cache[1]
        js = p.getJointStates(self.robot_id, self.arm_joints,
                              physicsClientId=self.client_id)
        q = np.array([s[0] for s in js], dtype=float)
        qd = np.array([s[1] for s in js], dtype=float)
        fj = p.getJointStates(self.robot_id, self.finger_joints,
                              physicsClientId=self.client_id)
        fingers = [float(s[0]) for s in fj]
        link = p.getLinkState(self.robot_id, self.ee_link,
                              computeLinkVelocity=1,
                              computeForwardKinematics=1,
                              physicsClientId=self.client_id)
        ee_pos = np.asarray(link[4], dtype=float)
        ee_quat = link[5]
        ee_v = np.asarray(link[6], dtype=float)
        # Normalised to ONE simulation step even though the sampler runs
        # on a stride, so the number is directly comparable to the
        # commanded interpolation increment.
        elapsed = max(1, self.step_count - self._prev_joints_step)
        step_delta = ((q - self._prev_joints) / elapsed
                      if self._prev_joints is not None
                      else np.zeros_like(q))
        self._prev_joints = q
        self._prev_joints_step = self.step_count
        state = {
            'q': q,
            'qd': qd,
            'step_delta': step_delta,
            'fingers': fingers,
            'ee_pos': ee_pos,
            'ee_rpy_deg': _yaw_pitch_roll_deg(ee_quat),
            'ee_speed': float(np.linalg.norm(ee_v)),
            'ee_v': ee_v,
        }
        self._rob_cache = (self.step_count, state)
        return state

    # ----- event detection -------------------------------------------------

    def _check_events(self) -> bool:
        """Flag physical anomalies.  Returns True if anything fired."""
        fired = False
        rob = self._robot_state() if self.robot_id is not None else None
        held_ids = set()
        if rob is not None:
            max_qd_i = int(np.argmax(np.abs(rob['qd']))) if rob['qd'].size else -1
            if max_qd_i >= 0:
                mag = float(abs(rob['qd'][max_qd_i]))
                if mag > self._phase_peak_joint_vel:
                    self._phase_peak_joint_vel = mag
                    self._phase_peak_joint_vel_idx = max_qd_i
                limit = PANDA_JOINT_VEL_LIMIT[max_qd_i] \
                    if max_qd_i < len(PANDA_JOINT_VEL_LIMIT) else 2.61
                if mag > limit:
                    # Recorded, but it does NOT force an extra frame: the
                    # executor exceeds the datasheet limit on ordinary
                    # transits (that is itself the F14 finding), so
                    # treating each occurrence as an anomaly would bury
                    # the events that really are rare.  The per-action
                    # summary carries the peak.
                    self._event('JOINT_OVERSPEED',
                                f"joint {max_qd_i} at {mag:.2f} rad/s "
                                f"(Panda limit {limit:.2f})",
                                force_frame=False)
            max_sd_i = (int(np.argmax(np.abs(rob['step_delta'])))
                        if rob['step_delta'].size else -1)
            if max_sd_i >= 0:
                sd = float(abs(rob['step_delta'][max_sd_i]))
                if sd > self._phase_peak_step_delta:
                    self._phase_peak_step_delta = sd
                    self._phase_peak_step_delta_idx = max_sd_i
                if sd > JOINT_STEP_WARN:
                    fired |= self._event(
                        'JOINT_JUMP',
                        f"joint {max_sd_i} commanded {sd:.4f} rad in one step "
                        f"({sd / self.timestep:.1f} rad/s)")
            if rob['ee_speed'] > self._phase_peak_ee_speed:
                self._phase_peak_ee_speed = rob['ee_speed']
            if rob['ee_speed'] > EE_SPEED_WARN:
                self._event('EE_FAST',
                            f"end effector at {rob['ee_speed']:.2f} m/s",
                            force_frame=False)
            # One read of the robot's contacts gives every body a finger
            # touches (TB-22: the counts mode reads the same, so both
            # modes hand the drop count the same contacts).
            finger_contacts = self._finger_contacts()
            held_ids = set(finger_contacts)
            if self._drop_check(finger_contacts):
                fired = True
            # A body that was between the pads and no longer is, while the
            # fingers are still closed AND the body is touching nothing
            # else, was NOT released — it slipped or was flung.  Both
            # conditions matter: an intended release opens the fingers,
            # and it hands the object to a support, so neither an open
            # gripper nor a landed object raises this.  What is left is
            # the F8/F14 signature, caught at the moment it happens
            # instead of at the next place-entry assert.
            # Confirmed on the NEXT check rather than immediately: a
            # normal release passes through one contact-free sample as
            # the object drops the last millimetre onto its support, and
            # that transient is not a lost grip.  A slip or a fling stays
            # contact-free for many steps, so it still reports.
            # "Still closed" must also mean "not in the act of opening":
            # a release passes through the 0.03-0.035 band on its way to
            # 0.04, and the object separates while it does.  Comparing
            # against the previous reading distinguishes a gripper that
            # is opening from one that is holding on.
            fingers_now = max(rob['fingers'])
            opening = (self._prev_fingers is not None
                       and fingers_now > self._prev_fingers + 1e-5)
            self._prev_fingers = fingers_now
            fingers_closed = fingers_now < 0.035 and not opening
            confirmed = set()
            for bid in self._grip_pending:
                if bid in held_ids or not fingers_closed:
                    continue
                if self._touching_non_robot(bid):
                    continue
                confirmed.add(bid)
                fired |= self._event(
                    'GRIP_LOST',
                    f"{self.body_names.get(bid, bid)} left the pads in "
                    f"mid-air while the gripper was still closed "
                    f"(fingers=[{rob['fingers'][0]:.4f},"
                    f"{rob['fingers'][1]:.4f}])")
            self._grip_pending = {
                bid for bid in (self._held_prev - held_ids)
                if fingers_closed and bid not in confirmed
                and not self._touching_non_robot(bid)}
            self._held_prev = held_ids
            self._held_this_phase |= held_ids

        for bid in list(self.body_names):
            if self.robot_id is not None and bid == self.robot_id:
                continue
            try:
                st = self._body_state(bid)
            except Exception:
                continue
            name = st['name']
            if st['speed'] > self._phase_peak_speed.get(bid, 0.0):
                self._phase_peak_speed[bid] = st['speed']
            # Carried cargo travels at the hand's speed by definition, so
            # raw speed alone cannot separate "being carried briskly" from
            # "being slung off".  For a held body the signal is the cargo
            # OUTRUNNING the hand; for an unheld body, any large speed.
            if bid in held_ids:
                ee_speed = rob['ee_speed'] if rob is not None else 0.0
                # Both conditions: fast in absolute terms AND outrunning
                # the hand.  Setting an object down releases it at
                # 0.1-0.2 m/s while the hand is still — that is a
                # release, not a sling, and only the absolute floor
                # tells the two apart.
                slung = (st['speed'] > FLING_SPEED
                         and st['speed'] > ee_speed * 1.5)
                detail = (f"{name} is outrunning the gripper: "
                          f"{st['speed']:.2f} m/s vs hand "
                          f"{ee_speed:.2f} m/s — the grasp is losing it")
            else:
                slung = st['speed'] > FLING_SPEED
                detail = (f"{name} moving at {st['speed']:.2f} m/s "
                          f"untouched by the arm "
                          f"(v={np.round(st['v'], 3).tolist()})")
            if slung:
                self._phase_flung.add(bid)
                fired |= self._event('FLING', detail)
            # Latched: TOPPLE / OFF_SUPPORT / AIRBORNE describe a STATE,
            # not an instant.  A block lying on the floor satisfies two of
            # them on every sample for the rest of the episode, which
            # would bury every later action's event list under a
            # condition that was already reported.  Each fires on the
            # transition into the state and re-arms when it clears; the
            # standing condition is instead carried by the per-action
            # summary, which reports where every body actually is.
            self._latched(bid, 'TOPPLE', st['tilt_deg'] > TILT_WARN_DEG,
                          f"{name} tilted {st['tilt_deg']:.1f} deg")
            start_z = self._support_z.get(bid)
            off = (start_z is not None
                   and st['pos'][2] < start_z - OFF_TABLE_DROP)
            fired |= self._latched(
                bid, 'OFF_SUPPORT', off,
                f"{name} is {((start_z or 0) - st['pos'][2]) * 1000:.0f} mm "
                f"below its spawn height (z={st['pos'][2]:.3f}) — it left "
                f"the surface it started on")
            fired |= self._latched(
                bid, 'AIRBORNE', (not st['contacts'] and st['speed'] > 0.05),
                f"{name} has no contacts and is moving "
                f"{st['speed']:.2f} m/s at z={st['pos'][2]:.3f}")
            # "Disturbed" means a BYSTANDER moved — something the arm was
            # never holding got knocked.  The object this action picked,
            # carried or placed is excluded (it is supposed to move, and
            # it keeps settling for a moment after release).
            if self._is_disturbed(bid, st, held_ids):
                self._count_disturbed(bid, st)
                fired |= self._event(
                    'DISTURBED',
                    f"{name} moved {st['moved_mm']:.1f} mm this action "
                    f"though the arm never grasped it")
        return fired

    # ----- the run-level counts (TB-22) -------------------------------------

    def _is_disturbed(self, bid, st, held_ids) -> bool:
        """The DISTURBED test, shared by the recorder and the counts mode."""
        return (bid not in held_ids and bid not in self._held_this_phase
                and st['moved_mm'] > DISTURB_MM and st['speed'] > 0.01)

    def _finger_contacts(self) -> dict:
        """``{body: finger links touching it}`` from one read of the
        robot's contact points (either body order of a contact pair)."""
        fingers = self.finger_joints
        touching = {}
        for c in p.getContactPoints(bodyA=self.robot_id,
                                    physicsClientId=self.client_id):
            if c[1] == self.robot_id:
                other, link = c[2], c[3]
            else:
                other, link = c[1], c[4]
            if (link in fingers and other != self.robot_id
                    and other in self.body_names):
                touching.setdefault(other, set()).add(link)
        return touching

    def _check_counts(self):
        """The counts mode's check: the contacts and poses the two counts
        read, and nothing else (no joint, link, AABB or tilt read)."""
        held_ids = set()
        if self.robot_id is not None:
            finger_contacts = self._finger_contacts()
            held_ids = set(finger_contacts)
            self._drop_check(finger_contacts)
            self._held_prev = held_ids
            self._held_this_phase |= held_ids
        for bid in self.body_names:
            if bid == self.robot_id or bid in held_ids \
                    or bid in self._held_this_phase:
                continue
            try:
                st = self._body_state(bid, light=True)
            except Exception:
                continue
            if self._is_disturbed(bid, st, held_ids):
                self._count_disturbed(bid, st)

    def _drop_check(self, finger_contacts) -> bool:
        """Advance the drop count by one check.  Returns True when a drop
        was counted.

        A body both pads hold after a close command is tracked; off every
        support for CARRIED_CHECKS checks in a row it is carried.  A
        carried body without finger contact for DROP_CHECKS checks in a
        row is dropped.  A tracked body that was never carried and loses
        the fingers was a grasp that did not take: it is forgotten."""
        both = set(self.finger_joints)
        if not self._release_commanded:
            for bid, links in finger_contacts.items():
                if links >= both and bid not in self._grip:
                    self._grip[bid] = {'air': 0, 'carried': False, 'free': 0,
                                       'off': False}
        counted = False
        for bid in list(self._grip):
            st = self._grip[bid]
            # 'off': off every support at this check (it touches nothing
            # but the robot); gripper_command reads the last one.
            st['off'] = not self._touching_non_robot(bid)
            if bid in finger_contacts:
                st['free'] = 0
                if not st['carried']:
                    st['air'] = st['air'] + 1 if st['off'] else 0
                    st['carried'] = st['air'] >= CARRIED_CHECKS
                continue
            if not st['carried']:
                del self._grip[bid]
                continue
            st['free'] += 1
            if st['free'] >= DROP_CHECKS:
                del self._grip[bid]
                self._count_drop(bid, 'left the finger pads with no '
                                      'release commanded')
                counted = True
        return counted

    def gripper_command(self, opening: bool, placing: bool = False):
        """The pipeline commands the gripper (robot_utils.open_gripper and
        the two closes call this before their first motor command).

        A close starts a grip.  An open ends every grip: a carried body
        still in the fingers when the gripper opens outside a place is
        dropped by that open (the hand let go of it in mid-air), and so is
        one that had already left the fingers (two checks without them, or
        one check and off every support at the last look); the release of
        a place drops nothing that the fingers still hold.  Reads no
        simulator state."""
        if not opening:
            self._release_commanded = False
            return
        for bid, st in list(self._grip.items()):
            if not st['carried']:
                continue
            if st['free'] == 0 and placing:
                continue
            if st['free'] == 0:
                self._count_drop(bid, 'the gripper opened on it outside the '
                                      'release of a place')
            elif st['free'] >= 2 or st['off']:
                self._count_drop(bid, 'left the finger pads before the '
                                      'gripper was opened')
        self._grip.clear()
        self._release_commanded = True

    def _count_drop(self, bid, how: str):
        name = self.body_names.get(bid, str(bid))
        self._drops.append({'object': name, 'phase': self._phase,
                            't': round(self.sim_time, 3), 'how': how})
        self._dropped_in[bid] = self._phase_index
        self._save_counts()
        if not self.counts_only:
            self._event('DROP', f"{name} {how} (drop {len(self._drops)} of "
                                f"this run)")

    def _count_disturbed(self, bid, st):
        dropped = self._dropped_in.get(bid)
        if dropped is not None and self._phase_index <= dropped + 1:
            return      # still the fall of its drop, not a collision
        key = (self._phase_index, bid)
        seen = self._disturbed.get(key)
        if seen is None:
            self._disturbed[key] = {'object': st['name'], 'phase': self._phase,
                                    't': round(self.sim_time, 3),
                                    'moved_mm': round(st['moved_mm'], 1)}
            self._save_counts()
        elif st['moved_mm'] > seen['moved_mm']:
            seen['moved_mm'] = round(st['moved_mm'], 1)

    def counts(self) -> dict:
        """The run's counts so far: the drops and the collisions (one per
        action and body), each as a list of events."""
        return {'drops': [dict(e) for e in self._drops],
                'collisions': [dict(e) for e in self._disturbed.values()],
                'mode': 'counts' if self.counts_only else 'recorder',
                'steps': self.step_count, 'closed': self._closed,
                # what the counts mode itself cost this run, in wall seconds
                # (None under the recorder, whose cost is its recording)
                'check_s': (round(self._check_s, 4) if self.counts_only
                            else None)}

    def _save_counts(self):
        """Rewrite the counts file (a few hundred bytes): at arming, on
        every counted event and at the close."""
        if self.run_dir is None:
            return
        try:
            with open(self.run_dir / COUNTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.counts(), f)
        except OSError:
            pass

    def _latched(self, bid, kind: str, condition: bool, detail: str) -> bool:
        """Fire ``kind`` on the transition into ``condition``, once."""
        key = (bid, kind)
        if condition:
            if key in self._latched_states:
                return False
            self._latched_states.add(key)
            return self._event(kind, detail)
        self._latched_states.discard(key)
        return False

    def _touching_non_robot(self, bid) -> bool:
        """Is this body resting on / against anything that is not the arm?"""
        for c in p.getContactPoints(bodyA=bid,
                                    physicsClientId=self.client_id):
            other = c[2] if c[1] == bid else c[1]
            if other != self.robot_id:
                return True
        return False

    def _event(self, kind: str, detail: str, force_frame: bool = True) -> bool:
        """Record one event; log the first few of each kind per action.

        ``force_frame`` False marks a routine condition worth counting
        but not worth a dense frame burst (see JOINT_OVERSPEED).
        """
        seen = self._phase_events.get(kind, 0)
        self._phase_events[kind] = seen + 1
        if seen < 200:
            self._write(f"  !! {kind:<14s} t={self.sim_time:7.3f}s "
                        f"step={self.step_count:6d} | {detail}\n")
        if seen < 3:
            logger.debug("[tele] %s t=%.3fs (%s): %s",
                         kind, self.sim_time, self._phase, detail)
        return force_frame

    # ----- emission --------------------------------------------------------

    def _write(self, text: str):
        # Flushed eagerly: a run that dies mid-episode (the interesting
        # case) must still leave a complete frame stream on disk.
        if self._stream is None:        # the counts mode writes no stream
            return
        self._stream.write(text)
        self._stream.flush()

    def _emit_frame(self):
        """Full world state into telemetry.log + telemetry.jsonl."""
        rob = self._robot_state()
        rec = {'t': round(self.sim_time, 4), 'step': self.step_count,
               'phase': self._phase, 'bodies': []}
        head = (f"[t={self.sim_time:7.3f}s step={self.step_count:6d}] "
                f"{self._phase}\n")
        lines = [head]
        ee_pos = None
        if rob is not None:
            ee_pos = rob['ee_pos']
            rec['robot'] = {
                'q': [round(float(v), 5) for v in rob['q']],
                'qd': [round(float(v), 4) for v in rob['qd']],
                'step_delta': [round(float(v), 5) for v in rob['step_delta']],
                'ee_pos': [round(float(v), 5) for v in rob['ee_pos']],
                'ee_rpy_deg': [round(float(v), 2) for v in rob['ee_rpy_deg']],
                'ee_speed': round(rob['ee_speed'], 4),
                'fingers': [round(v, 5) for v in rob['fingers']],
            }
            mi = int(np.argmax(np.abs(rob['qd']))) if rob['qd'].size else 0
            di = (int(np.argmax(np.abs(rob['step_delta'])))
                  if rob['step_delta'].size else 0)
            lines.append(
                f"  robot ee=[{rob['ee_pos'][0]:7.4f},{rob['ee_pos'][1]:8.4f},"
                f"{rob['ee_pos'][2]:7.4f}] rpy=["
                f"{rob['ee_rpy_deg'][0]:7.2f},{rob['ee_rpy_deg'][1]:7.2f},"
                f"{rob['ee_rpy_deg'][2]:7.2f}] |v_ee|={rob['ee_speed']:6.3f} m/s"
                f"  fingers=[{rob['fingers'][0]:.4f},{rob['fingers'][1]:.4f}]\n")
            lines.append(
                "        q =[" + ",".join(f"{v:7.4f}" for v in rob['q']) + "]\n")
            lines.append(
                "        qd=[" + ",".join(f"{v:7.3f}" for v in rob['qd'])
                + f"]  max|qd|={abs(rob['qd'][mi]):6.3f} rad/s (j{mi})"
                f"  max step delta={abs(rob['step_delta'][di]):.5f} rad (j{di})"
                f" = {abs(rob['step_delta'][di]) / self.timestep:6.2f} rad/s\n")

        for bid in sorted(self.body_names):
            if self.robot_id is not None and bid == self.robot_id:
                continue
            try:
                st = self._body_state(bid)
            except Exception:
                continue
            rel = (st['pos'] - ee_pos) if ee_pos is not None else np.zeros(3)
            rel_d = float(np.linalg.norm(rel)) if ee_pos is not None else -1.0
            partners = ",".join(
                f"{self.body_names.get(k[0], k[0])}:{k[1]}"
                f"({v:.1f}N)" for k, v in sorted(st['contacts'].items())
            ) or "none"
            lines.append(
                f"  {st['name']:<15s} pos=[{st['pos'][0]:7.4f},"
                f"{st['pos'][1]:8.4f},{st['pos'][2]:7.4f}] "
                f"rpy=[{st['rpy_deg'][0]:7.2f},{st['rpy_deg'][1]:7.2f},"
                f"{st['rpy_deg'][2]:7.2f}] tilt={st['tilt_deg']:5.1f}d "
                f"|v|={st['speed']:6.3f} |w|={st['w_deg_s']:7.1f}d/s "
                f"z_bot={st['aabb_min'][2]:6.4f} "
                f"d_ee={rel_d:6.3f} rel_ee=[{rel[0]:7.4f},{rel[1]:8.4f},"
                f"{rel[2]:7.4f}] moved={st['moved_mm']:7.1f}mm "
                f"drift={st['drift_mm']:8.1f}mm contacts={partners}\n")
            rec['bodies'].append({
                'name': st['name'], 'id': bid,
                'pos': [round(float(v), 5) for v in st['pos']],
                'rpy_deg': [round(float(v), 2) for v in st['rpy_deg']],
                'tilt_deg': round(st['tilt_deg'], 2),
                'speed': round(st['speed'], 4),
                'v': [round(float(v), 4) for v in st['v']],
                'w_deg_s': round(st['w_deg_s'], 2),
                'z_bottom': round(float(st['aabb_min'][2]), 5),
                'd_ee': round(rel_d, 4),
                'rel_ee': [round(float(v), 5) for v in rel],
                'moved_mm': round(st['moved_mm'], 2),
                'drift_mm': round(st['drift_mm'], 2),
                'contacts': [f"{self.body_names.get(k[0], k[0])}:{k[1]}"
                             for k in sorted(st['contacts'])],
            })
        self._write("".join(lines))
        self._jsonl.write(json.dumps(rec) + "\n")
        self._jsonl.flush()

    def _emit_heartbeat(self):
        """Compact where-is-everything dump into the MAIN run log."""
        parts = []
        for bid in sorted(self.body_names):
            if self.robot_id is not None and bid == self.robot_id:
                continue
            try:
                st = self._body_state(bid)
            except Exception:
                continue
            parts.append(f"{st['name']}@[{st['pos'][0]:.3f},{st['pos'][1]:.3f},"
                         f"{st['pos'][2]:.3f}] v={st['speed']:.3f} "
                         f"tilt={st['tilt_deg']:.0f}d")
        ee_txt = ""
        rob = self._robot_state()
        if rob is not None:
            ee_txt = (f" | ee=[{rob['ee_pos'][0]:.3f},{rob['ee_pos'][1]:.3f},"
                      f"{rob['ee_pos'][2]:.3f}] |v_ee|={rob['ee_speed']:.3f} "
                      f"fingers=[{rob['fingers'][0]:.3f},"
                      f"{rob['fingers'][1]:.3f}]")
        logger.debug("[tele-hb] t=%7.3fs step=%6d %s%s || %s",
                     self.sim_time, self.step_count, self._phase, ee_txt,
                     "  ".join(parts))

    def _emit_phase_summary(self):
        """Per-action rollup: peaks, displacements, events."""
        steps = self.step_count - self._phase_start_step
        if steps <= 0:
            return
        dt = self.sim_time - self._phase_start_time
        body_bits = []
        for bid in sorted(self.body_names):
            if self.robot_id is not None and bid == self.robot_id:
                continue
            try:
                st = self._body_state(bid)
            except Exception:
                continue
            peak = self._phase_peak_speed.get(bid, 0.0)
            # A body can be motionless AND displaced/toppled/on the floor
            # from an earlier action; "still" must never hide that.
            start_z = self._support_z.get(bid)
            displaced = (start_z is not None
                         and st['pos'][2] < start_z - OFF_TABLE_DROP)
            if (st['moved_mm'] < 1.0 and peak < 0.02
                    and not displaced and st['tilt_deg'] <= TILT_WARN_DEG):
                body_bits.append(f"{st['name']}: still")
                continue
            tag = ""
            if displaced:
                tag = (f"  <-- OFF ITS SUPPORT (started z={start_z:.3f}, "
                       f"now z={st['pos'][2]:.3f})")
            elif st['tilt_deg'] > TILT_WARN_DEG:
                tag = "  <-- TOPPLED"
            elif bid in self._phase_flung:
                tag = "  <-- FLUNG (left the gripper's control)"
            body_bits.append(
                f"{st['name']}: displaced {st['moved_mm']:.1f} mm, peak "
                f"{peak:.2f} m/s, ended pos=[{st['pos'][0]:.3f},"
                f"{st['pos'][1]:.3f},{st['pos'][2]:.3f}] "
                f"tilt={st['tilt_deg']:.1f}d{tag}")
        ev = ", ".join(f"{k} x{v}" for k, v in sorted(self._phase_events.items())) \
            or "none"
        summary = (
            f"  ---- action summary: {self._phase} "
            f"({dt:.3f} s sim, {steps} steps)\n"
            f"       peak |v_ee|={self._phase_peak_ee_speed:.3f} m/s, "
            f"peak |qd|={self._phase_peak_joint_vel:.3f} rad/s "
            f"(j{self._phase_peak_joint_vel_idx}), worst per-step joint delta="
            f"{self._phase_peak_step_delta:.5f} rad "
            f"(j{self._phase_peak_step_delta_idx}) = "
            f"{self._phase_peak_step_delta / self.timestep:.2f} rad/s\n"
            f"       events: {ev}\n")
        for b in body_bits:
            summary += f"       {b}\n"
        self._write(summary)
        logger.debug(
            "[tele] action summary %s (%.3fs sim, %d steps): peak |v_ee|=%.3f "
            "m/s, peak |qd|=%.3f rad/s (j%d), worst step delta=%.5f rad "
            "(%.1f rad/s); events: %s; %s",
            self._phase, dt, steps, self._phase_peak_ee_speed,
            self._phase_peak_joint_vel, self._phase_peak_joint_vel_idx,
            self._phase_peak_step_delta,
            self._phase_peak_step_delta / self.timestep, ev,
            "; ".join(body_bits))


# ---------------------------------------------------------------------------
# Module-level singleton.  Every stepSimulation site calls ``tick()``; it is
# a no-op (one attribute test) whenever nothing is armed: GUI runs by
# default, and any run with both --no-telemetry and --world-counts off.  A
# headless run under --no-telemetry alone has the counts mode armed (TB-22).
# ---------------------------------------------------------------------------

_ACTIVE: WorldTelemetry | None = None


def enable(client_id, robot_id, body_names, run_dir, **kwargs) -> WorldTelemetry:
    """Arm the recorder and make it the process-wide sink."""
    global _ACTIVE
    _ACTIVE = WorldTelemetry(client_id, robot_id, body_names, run_dir, **kwargs)
    return _ACTIVE


def disable():
    """Close the recorder and detach it."""
    global _ACTIVE
    if _ACTIVE is not None:
        _ACTIVE.close()
    _ACTIVE = None


def is_active() -> bool:
    """Whether the RECORDER is on (frames, notes, summaries).  False in
    the counts mode, so the pipeline builds no note text for it."""
    return _ACTIVE is not None and not _ACTIVE.counts_only


def is_counting() -> bool:
    """Whether the run's drops and collisions are being counted (the
    recorder or the counts mode)."""
    return _ACTIVE is not None


def run_counts() -> dict | None:
    """The run's drop and collision counts so far (TB-22), or None when
    nothing watches the world.  Reads no simulator state."""
    return _ACTIVE.counts() if _ACTIVE is not None else None


def gripper_command(opening: bool, placing: bool = False):
    """The pipeline is about to command the gripper open or closed
    (``placing``: the open is the release of a place or a stack).  Feeds
    the drop count; a no-op when nothing watches."""
    if _ACTIVE is not None:
        _ACTIVE.gripper_command(opening, placing)


def active() -> WorldTelemetry | None:
    return _ACTIVE


def tick():
    """Per-step hook.  Called right after every ``p.stepSimulation``."""
    if _ACTIVE is not None:
        _ACTIVE.tick()


def phase(label: str):
    if _ACTIVE is not None:
        _ACTIVE.phase(label)


def note(text: str):
    if _ACTIVE is not None:
        _ACTIVE.note(text)


def attach_robot(robot_id: int):
    if _ACTIVE is not None:
        _ACTIVE.attach_robot(robot_id)


def register_bodies(body_names):
    if _ACTIVE is not None:
        _ACTIVE.register_bodies(body_names)
