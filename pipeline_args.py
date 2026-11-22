"""The pipeline's command line: its flags and the rules applied after parsing.

``run_logger`` imports ``parse_pipeline_args`` from this module and keeps
the name importable from there.  The flags keep the order they are added
in: argparse prints ``--help`` in that order and resolves a shortened flag
against all of them.

The flags by group, in the order they are added (their defaults and
meanings are in the help text):

    display and console     --no-gui  --no-boxel-viz  --show-free  --log-level
    scene                   --scene  --n-occluders  --n-targets  --n-hidden
                            --n-extra-distractors  --n-objects  --seed
    goal                    --goal  --stack-height  --allow-unwinnable
    planner model and       --unit-costs  --corridor-test  --path-check-diag
      motion checks         --path-check-step  --search-sample-ratio
                            --sense-gate
    M8 to M10               --m8  --m9  --m10  --pick-aperture-from-pose
                            --sense-over-region
    look, eye, interior     --look  --eye  --eye-start-joints
      regions, M7           --interior-regions  --m7
    optimistic search       --search-effort-weight  --search-initial-complexity
    die-slip fixes,         --slip-fixes  --grip-squeeze-mm  --save-screenshots
      squeeze, screenshots
    FastDownward's search   --planner
    free space              --baseline  --uniform-cell-size  --min-boxel-size
    telemetry and counts    --telemetry  --no-telemetry  --world-counts
                            --telemetry-period  --telemetry-heartbeat
    time limit              --max-plan-time

The rules applied to the parsed arguments, one function each, in call order:

  _promote_default_scene_for_counts  holding with a count flag: scalability
  _check_n_hidden                    what the hidden count needs, and its cap
  _apply_random_pairs_rules          random-pairs errors, auto seed, distractor
  _default_scene_for_stack_goal      stack goal on the default scene: stack
"""

import argparse
import random
import sys


# ---------------------------------------------------------------------------
# Pipeline CLI argument parsing (extracted from test_full_pipeline.py
# 2026-05-05).  Lives here rather than in test_full_pipeline.py so the
# entry-point block stays short; the scene-builder dispatch and main()
# call remain in the orchestrator.
# ---------------------------------------------------------------------------
# Moved from run_logger.py (readable migration P8): "here" now means this file.


def parse_pipeline_args(argv=None):
    """Parse the pipeline CLI args and return the validated Namespace.

    Performs post-parse validation (scene auto-promotion under
    --n-hidden / --goal stack, --n-hidden vs --n-occluders/--n-targets
    sanity checks).  ``parser.error`` exits the process on bad input.
    """
    parser = argparse.ArgumentParser(description='Full PDDLStream Pipeline with Replanning')
    # Flags of the display and the console.
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
    # Flags of the scene.
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
    # Flags of the goal.
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
             'rejection (the find-and-tray-stack role split: at least one '
             'visible and one hidden target) to a loud warning and run the '
             'episode anyway, '
             'e.g. to confirm in the GUI that a rejected seed is truly '
             'unwinnable.  Scene-construction failures still abort — '
             'there is no scene to show.  Never use in eval sweeps.',
    )
    # Flags of the planner model and the motion checks.
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
    # Flags of M8 to M10.
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
    # Flags of the look, the eye, interior regions and M7.
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
    # BF#65 option 1 (2026-11-12; the audit's D6, model tweak M2): a hiding
    # region under an object whose class declares a cavity that holds the
    # target class (interior_regions.py), unknown until the object is moved
    # away and the space looked at.  Off by default: no scene of our own
    # declares a cavity, and on find_dice it is a model addition that Hani
    # switches on.
    parser.add_argument(
        '--interior-regions', choices=['off', 'on'], default='off',
        help="BF#65 option 1 (D6, M2): the space under an object whose "
             "class declares a cavity is a hiding region, searched by "
             "moving the object away (on), or no such region (off, the "
             "default).")
    # M7 (PAPER_AUDIT M7, BF#15, TB-46): on, the default by BF#15.
    parser.add_argument(
        '--m7', choices=['off', 'on'], default='on',
        help="M7: a sense that finds a registered body again keeps its "
             "still-hidden fragments and carves the new ones against every "
             "fragment (on, the default), or drops them unrendered (off).")
    # Flags of the optimistic search.
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
    # Flags of the die-slip fixes, the squeeze and the screenshots.
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
    # Flag of FastDownward's search.
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
    # Flags of free space.
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
    # Flags of telemetry and the world counts.
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
    # Flag of the time limit.
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

    _promote_default_scene_for_counts(args)
    _check_n_hidden(args, parser)
    _apply_random_pairs_rules(args, parser, argv)
    _default_scene_for_stack_goal(args)

    return args


def _promote_default_scene_for_counts(args):
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


def _check_n_hidden(args, parser):
    # The --n-hidden checks announced in _promote_default_scene_for_counts.
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


def _apply_random_pairs_rules(args, parser, argv):
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


def _default_scene_for_stack_goal(args):
    # When --goal stack is requested without an explicit --scene, fall
    # back to stack_scene so the spawned objects are reach-constrained
    # cubes by default.  Explicit --scene overrides this for A/B tests.
    if args.goal == 'stack' and args.scene == 'default':
        args.scene = 'stack'
