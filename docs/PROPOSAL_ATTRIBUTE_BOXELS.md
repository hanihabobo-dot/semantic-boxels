# PROPOSAL: attribute boxelization (merge by what the planner reads, not only by a shared face)

Status: DESIGN, 2026-11-06, written on branch `tampura-bridge` at HEAD 177cc87
(dirty tree). No code changed. Line numbers are today's working tree; re-check
before editing. Logged in PAPER_AUDIT.txt as BF#66 (far future work, with
Hani's question and the answer verbatim; #P9 points to it), on Hani's word
the same day; the options of section 8 stay open. The belief part extends
BF#60, which Hani parked for after the ICAPS paper on 2026-10-31; that
decision stands until he says otherwise.

## 0. The idea (Hani, 2026-11-06, restated)

A boxel today is a box that carries one label (OBJECT, SHADOW, FREE_SPACE),
and free cells merge when they share an exactly aligned face. The proposal:
the merge criterion is "same value of the attribute the planner cares about",
with the shared face as an option, not a requirement. Wherever the pipeline
holds a probability distribution over the plane (the hidden target's
position), the distribution is not enumerated cell by cell, as TAMPURA's
15 mm visibility grid does; it is boxelized into a few regions of equal
density level, each carrying its mass. The same move applies to other
attributes and to the values of fluents: cells, or values, that no predicate
of the domain tells apart become one symbol.

Short form: a boxel is a maximal region over which the planner's predicates
are constant. Probability density is one more such predicate.

## 1. What the code does today

Merge ingredients (cell_merger.py:125-166, `_try_merge`):

| ingredient | today | where |
|---|---|---|
| label | FREE_SPACE only; OBJECT and SHADOW never merge | cell_merger.py:33-74 |
| adjacency | the two boxes share an exactly aligned face (same extents on the other two axes, touching on one, 0.1 mm tolerance) | cell_merger.py:145-166 |
| tie break | the more cubic result wins | cell_merger.py:181-192 |
| when | after every octree pass, to a fixed point; off under the uniform baseline | reboxelize.py:46-51 |

Belief ingredients:

| belief | representation | where |
|---|---|---|
| hidden target | one status per shadow fragment: unknown, not_here, found, unresolved; no mass | belief.py:17-52 |
| hiding capacity | a yes/no test, "can a die-class body rest fully hidden in this fragment", sampled on a 1 cm grid, up to 12 per axis, returning at the first hit | streams.py:647-682 |
| cup cavities | per class, the footprint and height a die fits in | tampura_bridge/task_spec.py:31-37 |
| object pose | a disc of radius `pose_radius` around the believed centre, compared with a commit margin | pose_belief.py:303-331 |
| partial look | the fraction of a fragment's sense rays a body blocks (per slice); `marginally_blocked` is emitted but no action consumes it since F12's sense_partial was withdrawn | pddlstream_planner.py:482, 816-828; perception.py:37, 88 |

What the planner reads per boxel (the attribute vector a merge may key on):

| fact | arity | meaning | emitted at |
|---|---|---|---|
| is_shadow / is_free_space / is_object | per boxel | the label | pddlstream_planner.py `_build_init` |
| on_surface | per boxel | rests on the table | boxel_env.annotate_free_space_surface |
| boxel_fits(o, b) | per object and boxel | the box is large enough for o | streams.py |
| blocks_view_at(o, b, region) | per object, free cell and shadow | placing o at b blinds region | pddlstream_planner.py:837-868 |
| placement_hides(o, b) | per object and free cell | placing o at b hides a known body | pddlstream_planner.py:484, 883-887 |
| marginally_blocked(region) | per shadow | worst slice still mostly observable | pddlstream_planner.py:816-828 |
| config_for_boxel(q, b), kin_solution(o, b, g, q) | per boxel, from streams | reachable | streams.py |

Two free cells with the same row in every one of these facts are
interchangeable to FastDownward: it cannot tell them apart, it only pays for
grounding both. That is the lever.

## 2. The general rule: merge what no predicate tells apart

Definition. For a cell b let kappa(b) be the vector of answers of every
predicate and stream test the domain reads at b (the table above; for the
belief, the density level, section 3). Two cells merge when kappa is equal.
Adjacency is a separate choice:

| adjacency | result | keeps "boxel = box" | use |
|---|---|---|---|
| exactly aligned shared face (today) | a box | yes | free space, belief boxels |
| any contact | a connected union of boxes under one ID: a two-level structure, region over member boxels | the region does not; its members do | free space keyed by view signature (section 4) |
| none | an equivalence class of values, no geometry | n/a | fluent values: class belief, yaw families (section 5) |

Why it is sound. If kappa carries every fact the domain reads, the planner's
state space over merged IDs is the quotient of the unmerged one under "same
facts": every plan over merged IDs maps to plans over the originals and back.
This is model minimisation by bisimulation (Givan, Dean and Greig, "Equivalence
notions and model minimization in Markov decision processes", AIJ 2003; Li,
Walsh and Littman, "Towards a unified theory of state abstraction for MDPs",
ISAIM 2006). The continuous counterpart in mapping is OctoMap's pruning
(Hornung et al., Autonomous Robots 2013): children whose occupancy
probabilities are equal after clamping collapse into their parent, so a
probabilistic grid stays small where it is flat. Hani's "high versus low
density" is that clamping, applied to a belief the planner reads.

This is the "full semantic merge" the thesis names as future work
(thesis/chapters/conclusion.tex:47-51, "view-blocking, observability, and
back-to-front ordering") and the convex-only caveat in methods.tex:28.

Implementation of the rule itself is small: `CellMerger` takes a `key`
callable (default: the boxel type, so behaviour is unchanged); `_try_merge`
refuses a pair whose keys differ; the merged boxel copies the key's fields
and sums any additive ones (mass, hide count). About 15 lines plus a unit
test. Everything below is a choice of key.

## 3. Application A: the hidden-target belief as iso-mass boxels

This is Hani's 2D density case. The target rests on the table or on a cup's
cavity floor, so the belief lives on the plane; the shadow model is already
2.5-D (shadow_calculator.py:95-117).

### 3.1 The density

The declared prior (as BF#60 sketches it): uniform over the hiding spots,
the positions where a target-class body rests fully occluded. The sampler
exists: `test_target_can_hide_in_shadow` walks a 1 cm grid of candidate
placements per fragment and casts the eight corner rays (streams.py:650-740).
Today it returns at the first hidden placement; counting them instead gives
each fragment's hiding mass (cups: the cavity, HOLLOW_CAVITY). Mass is
geometry the registry already knows, read from our own render, never from
TAMPURA's grid (gates G2 and G13: their grid is their belief, arm O never
reads it, BF#41).

### 3.2 Construction

1. Quantise the density into levels. Two levels, zero and positive, are
   exact for a uniform prior; with a non-uniform density use log-spaced
   levels with a declared ratio r (r = 2: the density inside one boxel is
   known to within a factor 2).
2. Quadtree over the table window: subdivide a cell while it holds more
   than one level, stop at the hide grid's 1 cm (the resolution the
   sampler already uses). This is free_space.py's octree in 2D with "level
   mixed" in place of "overlaps an obstacle".
3. Merge leaves of equal level across aligned faces with the keyed
   `CellMerger`; each boxel carries `mass` (its share of the hiding spots)
   and `level`.
4. Level-zero regions are not boxels: they are free space or known-empty.

### 3.3 The key fact: with our sensor this is lossless

A sense that finds nothing removes the seen spots and renormalises. With a
perfect sensor and a uniform prior the posterior is uniform over the
surviving set, always. So two levels {0, c} represent the belief exactly
after any sequence of looks; no approximation enters until the sensor is
noisy (then the levels and their ratio are the declared error, as in 3.2).
The 1 cm hide grid is the only discretisation, and it is today's.

### 3.4 The update after a look

A look from configuration q sees part of a fragment: the per-endpoint test
exists (perception.py:231 `first_surface_interceptors` over
`sense_ray_slices`). Cut the seen part out with the slab cut that already
splits boxes around AABBs (shadow_calculator.py:375 `_subtract_aabb`;
free_space.py:179 `split_free_boxel`): the seen remainders get level 0, the
unseen remainders keep the mass of their surviving spots, masses are
renormalised, the keyed merge runs again. A fragment therefore SHRINKS under
a partial look. This is exactly what F12's sense_partial lacked ("a grazed
fragment cannot be shrunk by sensing", pddlstream_planner.py:820-823) and
what made seed 13 loop until three strikes parked every fragment (BF#60).
TAMPURA's grid does this per voxel; the boxel version does it with a few
cuts and keeps the symbol set small.

IDs change under split and merge. The belief ledger (G5 rows), the KIF facts
and the strike counter are keyed by fragment ID, so the update must map old
IDs to new ones the way `reboxelize_free_space` diffs free cells
(reboxelize.py:37-77): unchanged boxes keep their ID, cut boxes hand their
status and strikes to their remainders.

### 3.5 What the planner sees

- The sense action's cost becomes a function of mass, inside the model
  (BF#60 (2)): `(increase (total-cost) (SenseCost ?region))` with a
  :function stream (pddlstream multi_cost pattern). Rank by mass over reach
  cost, not by entropy (BF#60's argument: for a find-and-hold goal the
  optimal order of boxes with fixed costs is highest p/c first). The exchange
  rate between one action and one unit of probability is the single new
  constant, declared before measuring, pipeline-wide (never tuned on
  find_dice: the no-bridge-only-tuning rule).
- The episode ends when the residual mass is below a declared epsilon
  (BF#60 (3)), replacing the three-strike park, which #P9 records as an
  unsound bounded give-up. An unresolved fragment keeps its mass; a look at
  it from the same q has zero gain and is never re-selected.
- Nothing edits a plan. The belief changes the model's facts and costs,
  the planner chooses.

### 3.6 Size, as an estimate (not measured)

| representation | cells or boxels in TAMPURA's window W (0.39 m by 0.62 m, task_spec.py:81-82) |
|---|---|
| 15 mm grid, 2D | about 1 070 |
| 15 mm grid, 3D (their grid) | several thousand, height unknown here |
| iso-mass boxels, one cup | 1 cavity boxel plus 1 to 3 shadow remainders |
| iso-mass boxels, four cups | about 4 to 16 |

### 3.7 Relation to TAMPURA

Their belief is the enumerated version of ours: candidate voxels, cleared
per look, 7.5 mm from any concave mesh (PAPER_AUDIT.txt:3567-3569). Ours is
the same set, pruned to its maximal boxes, with mass. Same information, a
symbol count independent of the grid resolution. In the paper this is the
cleanest sentence the comparison can offer about the representation.

## 4. Application B: free space merged by its view and placement signature

Key for a free cell: (on_surface, the set of shadows a placement there
blinds, from blocks_view_at; the set of bodies a placement there hides, from
placement_hides; reachable, from the kin stream's answer). Cells with equal
keys merge; adjacency may be the shared face (convex, a box) or any contact
(a region of boxes). The plan set is unchanged by construction (section 2),
the init state is smaller, and that is the sentence the thesis conclusion
already promises.

Acceptance is cheap and strong: BF#13's distributional plan-count test
between merged and unmerged init on the same scenes should show equality,
and the init-fact and grounding counts the reduction. No success metric is
needed to accept B; it is a compression with a proof, not a model change.

Caveat. `boxel_fits`, `config_for_boxel` and `kin_solution` are per box.
A region of boxes answers them through its members: the place stream
returns a pose inside one member box, and the fact is certified for the
region. With the "any contact" adjacency, keep the two-level structure
(region over boxels) rather than a non-convex boxel: the name promises a
box, and every sampler assumes one.

## 5. Application C: values of fluents

The "none" adjacency of section 2: merge values no predicate tells apart.

- Class belief (class_uncertain, the pending plan's Q2 in
  archive/tampura_bridge_plan_2026-10-25/class_uncertain/BRIEF.md): six
  classes, but the goal reads two things, "may still be a fruit" and "may
  break when picked". Boxelize the class value into those two fluents per
  object; `inspect` refines by collapsing the set. The planner's symbol set
  is 2 values, not 6, and stays uncertain for our arm exactly as for theirs
  until inspect runs. This is the cheapest and most defensible instance of
  the idea, and it answers a question the class_uncertain plan must answer
  anyway.
- Pose radius against the commit margin (pose_belief.py:327-331) is already a
  two-level value boxelization; nothing to add.
- Grasp yaw families under quarter-turn symmetry
  (pose_belief.py:199-219) are already value classes; nothing to add.
- The recipe for any continuous value: cut the range exactly where some
  precondition or stream answer flips (the commit margin, GRASP_MAX_SPAN,
  SENSE_MARGINAL_BLOCKED_FRACTION); never at round numbers.

## 6. Costs and failure modes

- ID churn (3.4): the one real engineering cost; the diff pattern exists.
- Non-convex regions: keep the two-level structure (section 4 caveat).
- Noisy sensors: levels approximate; declare r and the resulting ranking
  error (within a level, p/c can be off by r).
- Resolution: the hide grid (1 cm) and the sense slices (12 mm) bound what a
  cut can resolve; a boxel narrower than 12 mm cannot be shrunk by a look
  and is treated whole (today's rule).
- Pipeline-wide only: no constant may be set from a find_dice failure.
- Evidence: find_dice cannot show A (BF#60 WHY LATER: three saved scenes,
  the order changes in two). Random-pairs can (the hidden target moves with
  the seed; empty senses and replans per episode). B shows on our own
  scenes by fact counts and plan-set equality. C shows on class_uncertain.
- Timing: the paper deadline is 2026-12-04; the B8 re-runs and CB#113 are
  pending; BF#60 parked the probabilistic belief for after the paper. A and
  C change the system under test; B does not change plans but does change
  the partition the campaigns ran on.

## 7. Smallest implementation that tests the idea

Each step small, each behind a default-off switch in the M8-M10 style, on its
own branch (BF#60's decision), committed one by one:

1. `CellMerger(key=...)`, default key = boxel type; unit test that the
   default reproduces today's merge byte for byte on a saved registry.
2. `BoxelData.mass` and `hide_count`; a counting variant of
   `test_target_can_hide_in_shadow` (the bool API keeps its early return).
3. `BeliefState` masses, `residual_mass()`, epsilon; the park rule under the
   switch.
4. The look update: seen-AABB subtraction, renormalisation, re-merge, ID
   mapping; a unit test with one fragment and one partial look.
5. `SenseCost` function stream and the domain delta, generated like M8's.
6. Acceptance: random-pairs A/B (senses, replans, planning time, success,
   init size), arms "today", "mass-ranked fragments", "iso-mass boxels";
   for B the plan-set equality test; for C the class_uncertain plan.

Steps 1 and the B key alone (two small commits) give the thesis-paragraph
result with no belief change at all.

## 8. Decision for Hani

Options:
(a) Paper: one paragraph in the discussion naming the rule of section 2 and
    the lossless fact of 3.3, as the representation's relation to
    TAMPURA's grid; no code before the deadline. Keeps BF#60's decision.
(b) B now: the keyed merge and the view-signature key, accepted by plan-set
    equality; small, but it changes the partition under the pending
    campaigns, so it would wait for the B8 re-runs or run as its own arm.
(c) A and C after the paper, on a branch, as section 7.

Recommendation: (a) now, (c) after the deadline, (b) only if the B8 re-runs
leave room for one more arm. The logging is done (BF#66, this file as its
evidence); the option chosen goes into BF#66's DECISION line when Hani
picks one.
