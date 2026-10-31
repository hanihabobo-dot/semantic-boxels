# BF#59 proposal: loss dynamics (when and how the die leaves, what the model does)

Agent angle: instrument real find_dice episodes step by step through the
carry home, measure the first variance of one episode under identical
settings, and read how the model handles a loss. Commit 92d1e06, branch
tampura-bridge, laptop (WSL, arm O's venv), every episode under
`/root/sb_pipeline.lock` (with a 600 s cap from episode 4 on). No tracked
file was edited. The step-by-step work log is kept at
`probes/loss_dynamics/work_log.md`.

## 1. Diagnosis

### 1.1 The instrument

`probes/loss_dynamics/run_probe.py` runs the unchanged driver
`tampura_bridge/run_bridge_on_finddice.py` in-process after
`loss_recorder.install()`, which wraps `telemetry.tick` (called after every
`p.stepSimulation` of the executing world), `telemetry.phase` (the
dispatcher's action label), the dispatcher's `move_robot_smooth` and
`hold_at_config` names in `test_full_pipeline` (the waypoint index),
`execute_pick` (the die pick's start and end) and `_verify_holding` (the
goal check). From the die pick's entry it writes one JSON line per
simulation step: per pad link the contact count, the normal force, the two
friction sums and the contact points in the die frame; the die's pose in
the grasp-target frame; the arm joint velocities; the hand's linear and
angular velocity; the finger joint positions. The truth reads are
print-only and live in an untracked probe. Command, per episode:

    bash archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/loss_dynamics/run_episode.sh <seed> <tag> [driver flags]
    # = cd $TW/tampura_environments && flock /root/sb_pipeline.lock -c "timeout 600 $PY run_probe.py <out>/carry.jsonl --global-seed <seed> --vis 0 --allow-g19-mismatch 1 --save-dir <out>/save [flags]"

`analyse.py` (per waypoint table, first motion, first pad break, loss),
`trace.py` (step trace), `compare.py` (run against run) and `predictor.py`
(the loss predictor, 2.5) read the recordings.

### 1.2 The episodes (measured)

| run | seed | scene file loaded | settings | outcome | plans | die carry |
|---|---|---|---|---|---|---|
| s0_r1 | 0 | 1747173591.670785 (pinned) | defaults | success | 3 | held, rot 26.8 deg at home |
| s1_r1 | 1 | 1747173590.312597 (cluster pins 1747173593) | defaults | held (reward 1.0) | 7 | held, rot 4.1 deg |
| s14_base_r1 | 14 | 1747173590.312597 (cluster pins 1747173593) | base arm (`--sense-over-region off --search-effort-weight off --search-initial-complexity 0`) | no die pick, cup loop, stopped at 92 plans (14 min) | 92 | none |
| s1_r2 | 1 | 1747173590.312597 | defaults, as s1_r1 | LOST, physics_mismatch | 7 | lost at wp 9 |
| s1_r3 | 1 | 1747173590.312597 | defaults, as s1_r1 | LOST, physics_mismatch | 90 | lost at wp 7 |
| s6_r1 | 6 | 1747173593.826745 (cluster pins 1747173590) | defaults | LOST, physics_mismatch | 5 | lost at wp 9 |

The laptop's problems/ listing swaps 1747173590 and 1747173593 against the
cluster's (tools/bridge_gates.py `SCENE_MAP_LAPTOP_2026_05_26`, BF#39), so
seeds 1 and 14 on the laptop are not the cluster's seed 1 and 14 episodes;
no laptop seed reproduces a cluster base loss exactly. "defaults" means the
driver's defaults at 92d1e06 (sense_over_region on, search effort weight 1,
initial complexity 3, squeeze 0.5 mm, M8 to M10 on).

Every carry home is a re-solved RRT path of 9 waypoints whose pairs are all
0.42 to 0.45 rad apart, so `move_robot_smooth` stretches every pair to 39
to 42 steps and the arm runs at 2.50 to 2.54 rad/s, the datasheet limit,
for the whole swing (about 1.4 s), then the 76 to 79 step settle of the
last waypoint and a 23 step home hold.

### 1.3 When and how the die leaves (measured, s1_r2 and s1_r3)

Recorder steps; pick_done (after the 10 cm lift and the re-verify) is step
359 in s1_r2 and 357 in s1_r3.

| phase | s1_r2 (lost) | s1_r3 (lost) | s1_r1 (held, same seed) |
|---|---|---|---|
| pad force at the lift, per pad | 1.15 N, 4 points each | 1.70 N, 3 points each | 0.92 N, 1 point each |
| first motion (drift > 0.5 mm or rot > 1 deg) | step 381, wp 1 (22 steps into the swing) | step 382, wp 1 (25) | step 381, wp 1 (22) |
| rotation in the hand at the end of wp 3 / 4 / 5 / 6 / 7 / 8 | 4.9 / 9.8 / 21.9 / 48.8 / 74.0 / 100.1 deg | 10.8 / 26.3 / 52.4 / 59.6 / lost | 3.1 / 3.1 / 2.6 / 2.8 / 2.5 / 4.2 deg |
| finger width growth (proprioception) | +0.225 mm max (wp 6) | +0.157 mm max (wp 5) | +0.013 mm max |
| peak pad force while turning (wedging) | 6.9 N | 6.8 N | 1.3 N |
| contact points on the worse pad while turning | 1 (a corner) | 1 | 1 to 4 |
| release event | wp 8 to 9 junction, step 687: hand deceleration 74 m/s^2, both pads 0.0 N at 687 to 688 | wp 6 to 7 junction, step 595: 86 m/s^2, pads 0.0 and 0.38 N | wp 3 to 4 junction, steps 477 to 479: 79 and 65 m/s^2, both pads 0.0 N for 2 steps, recovered |
| last pad contact | step 692 (5 steps after the junction) | step 601 (6 steps) | |
| first motion to loss | 311 steps, 1.30 s | 219 steps, 0.91 s | |
| where the die went | onto the table (z 0.014 m at the end) | onto the table (touching body 1 from step 682, z 0.012 m) | |

How it leaves: it ROTATES OUT. The die turns in the hand during the swing
(about an axis between the hand's approach and pinch axes: (0.3, 0.2, 0.9)
in s1_r2, (0.36, 0.7, 0.6) in s1_r3, hand frame), the pinch goes from face
to edge (one contact point on a pad, the pads pushed apart by 0.15 to
0.23 mm, the force rising to 7 N), the die reseats on another face at 60 to
100 deg with a low force on one point, and the next waypoint junction (a
one to two step hand deceleration of 74 to 86 m/s^2) unloads both pads; the
contacts are gone 3 to 6 steps later and the die drops onto the table. It
is neither thrown nor slid along the pads. The loss happens in the move (wp
7 or wp 9), not at the pick or the lift and not in the home hold, which
matches the eval's "gone at home" (the goal check is the first thing that
looks).

The held carries show the same ingredients at a smaller scale: in s0_r1 the
die turns 26.8 deg, from wp 4 on about the pinch axis (a hinge between the
pads), and one pad reads 0.00 N in wp 6 and 8; in s1_r1 both pads read
0.0 N for two steps right after the wp 3 to 4 junction and the die
recovers. Every waypoint junction of every carry shows a 60 to 97 m/s^2
hand acceleration spike for one or two steps (inside a pair it is 1 to
3 m/s^2): the pairs are streamed as separate linear interpolations, each
starting at full speed from the arm's current state, so the velocity
changes stepwise at every junction (`robot_utils.move_robot_smooth` 877 to
967: the F14 velocity bound, no acceleration bound).

The junctions release the die, but they do not turn it. `turning.py` sums
the per-step change of the die's orientation in the hand up to the first
pad break: in the losses the 3 steps after each junction (7 to 9 % of the
steps) carry only 10, 14 and 6 % of the turning (s1_r2, s1_r3, s6_r1); 86
to 94 % happens
inside the pairs, where the hand's acceleration is 1 to 3 m/s^2, and the
rotation rate correlates weakly with the hand's angular acceleration
(+0.22 and +0.13; +0.46 and +0.40 in the held carries). The turning goes
with a rising pad force (1.2 N to 7 N while the width grows), so it is the
squeeze itself that turns the die once the pinch sits off a face (a wedge),
not inertia. That points at where the pads land on the die (the grasp) and
at the squeeze, which are other angles of this campaign; this angle's
fixes catch and recover the loss (2.1, 2.2), remove the release trigger
(2.3) and remove the slow tail (2.4).

Inferred, not measured: the die's collision shape is the YCB scan's convex
hull (their `models/srl/ycb/062_dice`, google_16k with a vhacd log), so its
edges are rounded and the pads touch it at one to four points; contact
points sit at |y| 9.3 to 10.0 mm in the die frame against the 8.9 mm half
side, and the measured half-width (10.0 to 10.8 mm in the eval) is
consistent with a pinch that is not face-centred. With few contact points
the grasp resists rotation weakly, and the rotation, once past an edge,
ends in a single-point hold that the junction kick breaks (or, past about
100 deg, that fails on its own, 1.7).

### 1.4 Determinism (measured)

Seed 1 (laptop scene 1747173590.312597), three runs under identical
settings: held, lost, lost (the third after 82 extra plans in the cup loop
of 1.6). The first motion was at 22, 22 and 25 steps into the swing in all
three; the outcome and the episode length were not reproducible.
`compare.py` finds the step rows of s1_r1 and s1_r2 different from the
first recorded step of the die pick (the die's pose differs by 5 um and
0.06 deg before the pick). The divergence starts in the planner: the same
action skeletons, but plan times that depend on the machine's load (plan 1:
10.7 s against 7.0 s; the laptop was shared with other agents' probes) and
a different free spot for the last cup (free_016 against free_017); the
pick's pad force then differs (1.63 against 2.28 N in the pick's own line),
and the carry, on the same path to 1e-4 rad, amplifies that into held or
lost. So the same seed under the same settings is not the same episode, and
on this seed the die carry is close to a coin flip (one held, two lost). A
per-seed outcome of the eval is one draw; the campaign's replication is
needed to read any per-seed difference.

### 1.5 What the model does about a loss (code reading, 92d1e06)

Nothing, for a holding goal. After the pick, nothing reads the pads during
or after a move: the move branch of the dispatch loop
(`test_full_pipeline.py`, the `action_name == 'move'` block, 1795 to 1960
as read) streams the waypoints, holds at home, runs TAMPURA's at-home test
and `detect_execution_collisions`, and `_integrity_after` re-reads the scene
but excludes the held body (F26). The only tactile checks of a held body
are the pick's post-lift re-verify (`execution.py` 1325 to 1344) and the
place's empty-hand check at place entry (EmptyHandError, handled with the
transit-loss strike counter, `test_full_pipeline.py` 2261 to 2304 as read).
find_dice's mission has no place after the die pick, so a die lost on the
move home leaves `held_body_id` set, `_loop_done` (1437 to 1447) ends the
loop on that stale held state and the at-home test, and the scorer
`_verify_holding` (242, called at 2768) is the first thing that notices:
physics_mismatch. The die lies on the table in plain view (1.3), but the
model never learns it fell and never re-picks it.

### 1.6 The slow tail is not the die (measured)

The brief's "picked the die 10 to 41 times" in seeds 5, 10, 17 and 19 does
not hold. In every one of the 31 loss episodes of
`evidence/tc_4912db9_loss_context.txt` the die is picked once ("I have a
firm grip on dice" appears once). The long episodes alternate "look closer
at d_cups_ud, pick it up" and "pick up d_cups_ud" 10 to 41 times with no
grip in between; the metrics' `picks` count every pick action, cups
included. The laptop runs s14_base_r1 and s1_r3 reproduce the loop, and
the run's console_debug.log names it (plans 46 to 53 of s14_base_r1):

1. `observe(d_cups_ud)`: "[M8] observe d_cups_ud: wrist re-posed;
   d_cups_ud complete, pose_radius 0.39 mm";
2. the next plan's move to the cup's pick approach; `_integrity_after`
   re-reads the overhead render and `refresh_object_aabbs`
   (`execution.py` 2033, the `record_detection` call at 2139) re-poses the
   cup from the overhead camera, whose complete detection sets the radius
   by its own formula: 5.49 mm;
3. the pick's commit check refuses ("d_cups_ud pose_radius 5.49 mm is
   outside its commit margin", stale_precondition), and the next plan
   observes again.

`pose_belief.record_detection` (282 to 299) overwrites the radius with the
latest complete detection's radius, so a coarser camera undoes a finer one
although the body did not move. Nothing counts the cycles; the 600 s cap
ends them (s14_base_r1: 92 plans and no die pick in 14 minutes; s1_r3: 82
refusals in 90 plans). This is a separate failure that costs the eval its
slow tail and several caps; it is cheap to fix and it sits in the model.

### 1.7 A third loss, another scene (measured, s6_r1)

Seed 6 on the laptop loads 1747173593.826745, the scene the cluster pins for
seeds 1, 2, 3, 4, 8, 14, 15 and 18 (most of the eval's losses), with another
seed. Defaults, 5 plans, 45 s, lost: physics_mismatch, "links none". The
carry (pick_done 355; 9 waypoints of 0.48 rad, 45 steps each): pad force
1.92 N at the lift on 2 and 1 contact points; rotation 8.4, 12.8, 10.8,
19.6, 56.9, 94.3 deg at the end of wp 3 to 8; width +0.198 mm max (wp 8),
pad force up to 5.5 N; first motion step 378 (23 steps into the swing). The
release is different from 1.3: it is not at a junction. Inside the last
pair, at a hand acceleration of 1.3 m/s^2, the die turns on past 105 deg,
pad 13's single contact point walks across the die (its centroid moves
5 mm in 6 steps), the force decays from 5 N to 2.5 N (step 714) and to
0.1 N (step 724), and the contacts are gone at step 731, 25 steps after the
wp 8 to 9 junction. First motion to loss 353 steps (1.47 s). The die lands
on the table (touching body 1, z 0.013 m). The junction steps carry 6 % of
its turning. So all three measured losses are the same rotation out; the
junction kick is the trigger in two of them, and a die turned past about
100 deg leaves without one.

## 2. Proposed fixes

All four are model side (the belief, the dispatcher's use of the robot's
own senses, an executor primitive), pipeline-wide, behind
`slip_fixes.on('<name>')`, default off. The tactile reads are
`getContactPoints` on the pad links and the finger joint readback, the
robot's own senses (brief section 5, rule 3).

### 2.1 `carry_hold_check`: verify the hold after every move made while holding, and replan on a loss

Mechanism: 1.5. A carry loss is never seen by the model.

Change (`test_full_pipeline.py`, the move branch, right after the
waypoints, the home hold and the at-home test, before the integrity check):
with the switch on and `held_body_id` set, apply the post-lift re-verify's
rule (both pad links in contact with the held body, summed normal force
>= 0.5 N, the threshold `_verify_holding` uses) through one shared helper
in `execution.py` (the post-lift code at 1331 to 1336 becomes its first
caller, unchanged in behaviour). On a failed check: print the loss with the
pad contacts and the force, and take the EmptyHandError path's handling as
it is (`transit_loss_counts` strike with the giveup at 3, `held_body_id =
None`, `audit_robot_held_state`, `env.update_object_positions()`,
`pose_belief.mark_pose_unknown`, `refresh_object_aabbs(check_lost=True)`
and `retire_lost_objects`), `dispatch_end('empty_hand')` and break.
`_loop_done` then sees an empty hand and the loop replans the pick from the
overhead re-detection of the die on the table; a die that fell off the
table ends the episode as knocked_off_table, as now.

Section 5: the robot's tactile sense only; no plan is edited (the dispatch
breaks and the planner replans); every scene and goal (a cube lost on the
way to a place is caught at the end of the move instead of at place entry,
with the same handling).

Expected effect: the loss rate per carry does not change; the episode
outcome does. With 21 % of carries lost and the outcome of a carry close to
an independent draw (1.4), a second carry turns about 80 % of the 36 lost
episodes into successes, if the die rests reachable on the table (it did in
both measured losses). Time: one more plan, pick and carry per loss, about
8 to 15 s by the laptop numbers. It has to move the eval's success count by
at least 15 of the 36 losses to be real against the within-seed
disagreement measured in 1.4.

Falsify: with the switch on, (a) any physics_mismatch with "links none"
remains (a loss after the check), or (b) fewer than half the fired checks
end in success (the re-pick finds the die unreachable or loops), or (c) the
transit-loss giveup fires on our own scenes where base delivered.

Risk to our own scenes: a false loss on a body held at < 0.5 N summed at
rest; BF#48 measured 1.6 to 7.6 N at rest at 0.5 mm, so a false alarm at
rest is unlikely; check on random-pairs holding and stack seeds.

Effort: 2 hours with a unit test (a fake contact list).

### 2.2 `carry_grip_watch`: watch the grip during the swing and set the die down when it starts to turn

Mechanism: 1.3. The die turns for 0.4 to 0.6 s before it leaves, and the
pads' wedging is visible to proprioception (finger width growth 0.157 and
0.225 mm in the losses, 0.002 and 0.013 mm in the holds).

Change: `move_robot_smooth` already takes an `on_step` callable run after
every step (M10's read-only poll). With the switch on, the dispatcher's
move passes a watcher for a move made while holding: it records the finger
width at the start of the move (the post-pick readback) and sets a flag
when the width exceeds it by `GRIP_WATCH_WIDEN` (0.05 mm, a quarter of the
smaller measured loss signal and four times the larger measured held
value) or a pad loses contact. The dispatcher checks the flag between
waypoint pairs; when set it streams no further pair, settles at the current
readback (`move_robot_smooth(..., settle=True)`), runs the 2.1 check, and
on a hold still present plans the disposal the loop already has for "no
plan while holding" (`planner.plan(goal=('handempty',))`, a (move, place)
of the held body to a free spot, `test_full_pipeline.py` 1640 to 1684 as
read), executes it, and the mission replans from an empty hand with the die
re-observed, so the next pick is a fresh grasp at the die's new fitted yaw
(M9). A die that left before the settle goes the 2.1 way.

Section 5: proprioception and touch only; the disposal is a plan of the
planner, not an edit of one; every body carried (the threshold is relative
to the body's own width at the lift).

Expected effect: a turning die becomes a controlled place and a re-pick
before it can fall where a re-pick fails (off the table, under a cup).
Measured lead time 98 and 139 steps (2.4 and 3.4 waypoint pairs) from the
flag to the first pad break. Time: a place and a pick per trigger, about
10 to 20 s. Loss rate per carry: lower by the triggered fraction, if the
settle itself does not release the die (it decelerates the hand, the event
that released it at the junctions; this is the first thing to measure,
section 3).

Falsify: on the eval, (a) the flag fires on carries that would have held
(false alarms on more than 10 % of the carries), or (b) the die leaves
during the settle in more than a third of the triggers, or (c) the loss
rate per carry with 2.1 and 2.2 on is not below 2.1 alone.

Risk to our own scenes: a 40 mm cube whose width reading changes under the
pads' compliance; the threshold is relative and is checked on random-pairs
before the eval.

Effort: 4 hours.

### 2.3 `carry_accel_limit`: an acceleration bound in the executor's waypoint streaming

Mechanism: 1.3. Every waypoint junction gives a one to two step hand
acceleration spike of 60 to 97 m/s^2 (1 to 3 m/s^2 inside a pair); two of
the three measured releases (s1_r2, s1_r3) and both measured zero-force
events of the held carries are 0 to 6 steps after a junction; the third
release (s6_r1, 1.7) is not. This is the weakest of the four: it removes a
trigger, not the turning.

Change (`robot_utils.move_robot_smooth`, the dispatcher's move): with the
switch on, the dispatcher passes the whole waypoint list to one streaming
call that time-parameterises the polyline with a trapezoidal profile per
joint under the Franka Panda's datasheet joint acceleration limits (15,
7.5, 10, 12.5, 15, 20, 20 rad/s^2, the source of F14's
`JOINT_VELOCITY_LIMITS`) and the existing velocity limits, with the
junction speed limited by the direction change between the pairs (a pair
whose direction differs by more than 30 deg in joint space slows to rest at
the junction; nearly collinear ones keep their speed), so the executed path
stays the certified polyline. The settle of the last waypoint and the home
hold stay.

Section 5: an executor primitive, datasheet-matched like F14, every move of
every scene; the plan's waypoints are executed as planned.

Expected effect: the junction spikes fall to the datasheet bound (a few
m/s^2 at the hand), and the releases measured here lose their trigger. It
does not stop the in-pair turning (the rotation grew inside pairs too), so
alone it may leave the die turning and dropping at the settle. Time: a
carry of 1.4 s grows by about 0.3 to 0.6 s.

Falsify: the recorder on the same seeds shows the spikes gone and the loss
rate per carry not below base, or the losses move into the settle.

Risk to our own scenes: slower moves (wall); nothing for grasp quality.

Effort: 4 hours (the profile and a unit test on a two-pair polyline).

### 2.4 `pose_radius_keep`: a consistent detection does not loosen the pose radius

Mechanism: 1.6. The cup loop that makes the slow tail.

Change (`pose_belief.record_detection`): with the switch on, a complete
detection whose rectangle centre lies within the current radius plus the
new radius of the believed centre (the two uncertainty discs overlap: the
detection is consistent with the belief) sets `pose_radius = min(old,
new)`; an inconsistent detection (the body moved) sets the new radius as
now. `mark_pose_unknown`, the disturbance path and the touched-by-the-pads
path (M10) keep setting infinity, so a body that was moved never keeps an
old tight radius.

Section 5: the belief only, every body and camera (the intersection rule
for two consistent bounded estimates).

Expected effect: the observe's 0.39 mm survives the overhead refresh after
the approach move, the pick runs and the loop ends at its first cycle. On
the eval: the 600 s caps of seeds 5, 10, 17 and 19 (over their arms) become
finished episodes, the wall of those seeds falls from 90 to 550 s to about
40 to 90 s and their plan counts from 20 to 190 to under 15. Loss rate per
carry: no direct effect, but more episodes reach the die carry.

Falsify: the alternation "observe / pick refused" recurs in any episode
with the switch on, or the picks that now run on the kept radius fail the
grip check more often than base's picks of the same bodies.

Risk to our own scenes: a body nudged without a detected disturbance keeps
a too-tight radius; the pick's grip check and M10 (touched bodies go
unknown) bound the damage.

Effort: 1.5 hours with a unit test in tests/test_pose_writers.py (wrist
0.39 mm then a consistent eye detection keeps 0.39 mm; an inconsistent one
takes the eye's radius).

### 2.5 The loss predictor (a metric, not a switch)

One line per die carry, from the robot's own senses (the finger joint
readback and the pad contacts), logged by the dispatcher at the end of
every move made while holding:

    carry_grip: width0 <mm>, widen_max <+mm> at wp <k>, nf_min <N>, single-point steps <n>, pads at the end <n12,n13>

Measured on the recorded carries: widen_max +0.002 and +0.013 mm in the
held carries, +0.225 and +0.157 mm in the lost ones, crossing 0.05 mm 139
and 98 steps before the first pad break; zero-force steps do not separate
(2 and 5 held, 3 and 5 lost). s6_r1 (lost) widens +0.198 mm and crosses
0.05 mm at step 627 (wp 7), 103 steps before its first pad break; it has 6
zero-force steps. So 3 of 3 losses and 0 of 3 holds (s0_r1 +0.002 mm is
the third hold) are separated by the 0.05 mm line, with 98 to 139 steps of
lead. The eval can test it on every
carry of every arm: "widen_max > 0.05 mm predicts a loss" is falsified by a
held carry over 0.05 mm or a lost carry under it. `predictor.py` computes it
from a recording.

## 3. What I would measure first with one more hour

1. The settle after a trigger (2.2): replay s1_r2's carry with the recorder
   and stop the stream at the flag's step 550 to see whether the die,
   turned 17 deg, survives the deceleration of the settle. This decides
   between 2.2's "stop and set down" and "continue under 2.3's profile".
2. Five more repeats of seed 1 (laptop) and of seed 0, to put a number on
   the per-carry loss probability of one scene (here 2 of 3) and on how
   often the plan itself differs between repeats, and one run with the
   machine otherwise idle, to see whether the plan divergence of 1.4 is the
   load or the planner's own randomness.
3. What starts the turning: the correlation of the die's rotation rate with
   the hand's angular acceleration and with the pad force inside a pair
   (the data is in the recordings: hand_w, qd, pads).

## 4. Data generated and deleted

Under `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/loss_dynamics/`
(none of it tracked):

- `loss_recorder.py`, `run_probe.py`, `run_episode.sh`, `analyse.py`,
  `trace.py`, `compare.py`, `predictor.py`, `turning.py` (the probe, about
  22 KB) and
  `work_log.md` (10 KB, the log written as the work went).
- `runs/s0_r1` (0.8 MB), `runs/s1_r1` (1.4 MB), `runs/s1_r2` (1.4 MB),
  `runs/s1_r3` (1.9 MB), `runs/s6_r1` (1.3 MB): carry.jsonl (the per-step
  recording), stdout.txt (the curated console) and save/ (their run
  directory with our run's console_debug.log, ledger and eye logs). Kept
  for this proposal's numbers until the review phase; then the carry.jsonl
  and stdout.txt of each run stay and save/ becomes garbage.
- `runs/s14_base_r1` (4.1 MB): the episode stopped in the cup loop at 92
  plans; kept for 1.6's quoted log lines (its console_debug.log, 0.6 MB);
  the rest of its save/ is garbage once the review has read 1.6.

Deleted: nothing yet (the stopped run is the evidence of 1.6).
