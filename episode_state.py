"""The state of one episode: what main() of test_full_pipeline.py and its
stage functions share.

main() makes one EpisodeState object, `st`, and hands it to every stage
function. A stage returns nothing; it binds its results as fields of `st`.
The fields sit in groups: `st.opts` holds the parameters of main() that are
never rebound, `st.setup` what the set-up stages build, and `st.counts`,
`st.hand`, `st.arm`, `st.strikes`, `st.round` and `st.ending` what the
plan-act-sense loop carries from one round to the next.

No field has a start value. A stage binds a field where main() bound the
local of the same name, and a read before that raises AttributeError.
Above each field stand the functions that bind it and the functions that
read it ("main" is the text of main() itself; a change in place, as an
append or a dict store, counts as a read). This file imports nothing of
the pipeline.
"""

# choose_target_and_goal returns it; main() then returns False at once.
EARLY_FALSE = object()


class EpisodeOptions:
    """Parameters of main() that are never rebound and that a stage reads.

    Each holds the object the caller passed, never a copy (run_config is
    written through it). Above each: the stages that read it.
    """
    __slots__ = ('gui', 'run_logger', 'scene_config', 'draw_boxel_overlays',
                 'show_free', 'goal_kind', 'stack_height', 'unit_costs',
                 'baseline', 'uniform_cell_size', 'min_boxel_size',
                 'run_config', 'telemetry_enabled', 'telemetry_period',
                 'telemetry_heartbeat', 'oracle_phases', 'after_settle',
                 'gui_hold_s', 'goal_at_home', 'held_cargo_resolve',
                 'home_hold_step_cap')

    def __init__(self, *, gui, run_logger, scene_config, draw_boxel_overlays,
                 show_free, goal_kind, stack_height, unit_costs, baseline,
                 uniform_cell_size, min_boxel_size, run_config,
                 telemetry_enabled, telemetry_period, telemetry_heartbeat,
                 oracle_phases, after_settle, gui_hold_s, goal_at_home,
                 held_cargo_resolve, home_hold_step_cap):
        # read by: build_registry, arm_observers, plan_or_stop, dispatch_step,
        #   do_move, do_pick, do_place, do_stack, close_episode
        self.gui = gui
        # read by: build_registry, arm_observers, build_planner,
        #   export_initial_problem, report_episode
        self.run_logger = run_logger
        # read by: build_world
        self.scene_config = scene_config
        # read by: build_registry
        self.draw_boxel_overlays = draw_boxel_overlays
        # read by: build_registry, plan_or_stop, do_sense
        self.show_free = show_free
        # read by: choose_target_and_goal, build_planner, _loop_done,
        #   plan_or_stop, judge_success, report_episode
        self.goal_kind = goal_kind
        # read by: choose_target_and_goal
        self.stack_height = stack_height
        # read by: plan_or_stop
        self.unit_costs = unit_costs
        # read by: build_world
        self.baseline = baseline
        # read by: build_world
        self.uniform_cell_size = uniform_cell_size
        # read by: build_world
        self.min_boxel_size = min_boxel_size
        # read by: announce_run, build_world, report_episode
        self.run_config = run_config
        # read by: arm_observers
        self.telemetry_enabled = telemetry_enabled
        # read by: arm_observers
        self.telemetry_period = telemetry_period
        # read by: arm_observers
        self.telemetry_heartbeat = telemetry_heartbeat
        # read by: build_world, choose_target_and_goal
        self.oracle_phases = oracle_phases
        # read by: build_world
        self.after_settle = after_settle
        # read by: close_episode
        self.gui_hold_s = gui_hold_s
        # read by: build_planner, initial_home_readback, _loop_done, do_move,
        #   judge_success
        self.goal_at_home = goal_at_home
        # read by: _readback_config, do_move
        self.held_cargo_resolve = held_cargo_resolve
        # read by: do_move
        self.home_hold_step_cap = home_hold_step_cap


class SetupState:
    """What the set-up stages build; the loop reads and changes it in place."""
    __slots__ = ('domain_file', 'home_joints', 'target_name', 'look_mode',
                 'look_on', 'eye', 'eye_start', 'sense_over_region',
                 'search_effort_weight', 'search_initial_complexity',
                 'search_options', 'eye_camera_pose', 'robot_id', 'all_boxels',
                 'registry', 'shadows', 'occluders', 'viz',
                 'hidden_targets_set', 'visible_target_locations',
                 'on_relations', 'physical_failures', 'stack_target_objects',
                 'goal', 'shadow_occluder_map', 'boxel_to_pybullet',
                 'object_body_ids', 'planner_support_body_ids',
                 'support_body_ids', 'body_id_to_name', 'belief', 'planner',
                 'planner_target_objects', 'boxel_centers', '_target_body_id')

    # bound by: EpisodeState (the parameter of main), modes_from_args
    # read by: modes_from_args, check_domain_matches_switches, build_planner
    domain_file: object
    # bound by: EpisodeState (the parameter of main), modes_from_args
    # read by: modes_from_args, build_planner
    home_joints: object
    # bound by: EpisodeState (the parameter of main), choose_target_and_goal
    # read by: main, build_registry, choose_target_and_goal, build_planner,
    #   _integrity_after, plan_or_stop, do_sense, do_look, do_pick,
    #   judge_success, report_episode
    target_name: object
    # bound by: modes_from_args
    # read by: modes_from_args, check_domain_matches_switches, build_planner,
    #   arm_observe_views, do_look
    look_mode: object
    # bound by: modes_from_args
    # read by: modes_from_args, build_planner, arm_observe_views,
    #   report_episode
    look_on: object
    # bound by: modes_from_args
    # read by: modes_from_args, build_world, first_observation,
    #   map_blockers_and_bodies, build_planner, do_place, do_stack
    eye: object
    # bound by: modes_from_args
    # read by: build_world
    eye_start: object
    # bound by: modes_from_args
    # read by: build_planner, arm_observe_views
    sense_over_region: object
    # bound by: modes_from_args
    # read by: modes_from_args, build_planner
    search_effort_weight: object
    # bound by: modes_from_args
    # read by: modes_from_args, build_planner
    search_initial_complexity: object
    # bound by: modes_from_args
    # read by: build_planner
    search_options: object
    # bound by: build_world
    # read by: first_observation
    eye_camera_pose: object
    # bound by: build_world
    # read by: build_world, arm_observers, build_planner,
    #   initial_home_readback, do_move, do_sense, do_observe, do_look, do_pick,
    #   do_place, do_stack
    robot_id: object
    # bound by: first_observation
    # read by: first_observation, build_registry
    all_boxels: object
    # bound by: build_registry
    # read by: main, build_registry, choose_target_and_goal,
    #   map_blockers_and_bodies, build_planner, start_loop, _readback_config,
    #   _integrity_after, plan_or_stop, dispatch_step, do_move, do_sense,
    #   do_observe, do_look, do_pick, do_place, do_stack, report_episode
    registry: object
    # bound by: build_registry
    # read by: build_registry, choose_target_and_goal, map_blockers_and_bodies,
    #   build_planner, _integrity_after, plan_or_stop, do_move, do_sense,
    #   do_observe, do_look, do_pick, do_place, do_stack, report_episode
    shadows: object
    # bound by: build_registry
    # read by: build_registry, map_blockers_and_bodies, _integrity_after,
    #   do_move, do_sense, do_observe, do_look, do_pick, do_place, do_stack
    occluders: object
    # bound by: build_registry
    # read by: build_registry, _integrity_after, plan_or_stop, do_move,
    #   do_sense, do_observe, do_look, do_pick, do_place, do_stack
    viz: object
    # bound by: choose_target_and_goal
    # read by: choose_target_and_goal, build_planner
    hidden_targets_set: object
    # bound by: choose_target_and_goal
    # read by: choose_target_and_goal, export_initial_problem, plan_or_stop,
    #   do_pick
    visible_target_locations: object
    # bound by: choose_target_and_goal
    # read by: build_planner, _integrity_after, _loop_done, plan_or_stop,
    #   dispatch_step, do_pick, do_place, do_stack, judge_success,
    #   report_episode
    on_relations: object
    # bound by: choose_target_and_goal
    # read by: do_stack, report_episode
    physical_failures: object
    # bound by: choose_target_and_goal
    # read by: choose_target_and_goal, build_planner, plan_or_stop
    stack_target_objects: object
    # bound by: choose_target_and_goal, build_planner
    # read by: choose_target_and_goal, build_planner, export_initial_problem,
    #   _loop_done, plan_or_stop, judge_success, report_episode
    goal: object
    # bound by: map_blockers_and_bodies, do_place
    # read by: map_blockers_and_bodies, build_planner, _integrity_after,
    #   plan_or_stop, dispatch_step, do_move, do_sense, do_observe, do_look,
    #   do_pick, do_place, do_stack, report_episode
    shadow_occluder_map: object
    # bound by: map_blockers_and_bodies
    # read by: map_blockers_and_bodies, _integrity_after, do_sense, do_look,
    #   do_pick, do_place
    boxel_to_pybullet: object
    # bound by: map_blockers_and_bodies
    # read by: map_blockers_and_bodies, build_planner, _integrity_after,
    #   do_sense, do_look
    object_body_ids: object
    # bound by: map_blockers_and_bodies
    # read by: build_planner
    planner_support_body_ids: object
    # bound by: map_blockers_and_bodies
    # read by: do_move, do_sense, do_look, do_pick
    support_body_ids: object
    # bound by: map_blockers_and_bodies
    # read by: arm_observers, build_planner, _readback_config,
    #   _integrity_after, plan_or_stop, dispatch_step, do_move, do_sense,
    #   do_pick, report_episode
    body_id_to_name: object
    # bound by: build_planner
    # read by: build_planner, _integrity_after, plan_or_stop, dispatch_step,
    #   do_move, do_sense, do_observe, do_look, do_pick, do_place, do_stack,
    #   judge_success, report_episode
    belief: object
    # bound by: build_planner
    # read by: build_planner, export_initial_problem, arm_observe_views,
    #   start_loop, _at_home, initial_home_readback, plan_or_stop,
    #   no_plan_ends_episode, do_move, do_observe, do_look, do_pick, do_place,
    #   do_stack, report_episode
    planner: object
    # bound by: build_planner
    # read by: main, export_initial_problem, _integrity_after, plan_or_stop,
    #   no_plan_ends_episode, do_observe
    planner_target_objects: object
    # bound by: start_loop
    # read by: _integrity_after, plan_or_stop, do_move, do_sense, do_observe,
    #   do_look, do_pick, do_place, do_stack
    boxel_centers: object
    # bound by: main
    # read by: _loop_done
    _target_body_id: object


class Counts:
    """The loop's counters and per-plan records, reported at the end."""
    __slots__ = ('plan_count', 'sense_count', 'observe_count',
                 'observe_strikes', 'm8_per_plan', 'look_count',
                 'look_per_plan', 'plan_times', 'total_plan_time',
                 'boxel_counts_per_replan', 'integrity_events')

    # bound by: start_loop, plan_or_stop
    # read by: _integrity_after, plan_or_stop, dispatch_step, do_move, do_pick,
    #   do_place, do_stack, report_episode
    plan_count: object
    # bound by: start_loop, do_sense
    # read by: do_sense, report_episode
    sense_count: object
    # bound by: start_loop, do_observe
    # read by: do_observe, report_episode
    observe_count: object
    # bound by: start_loop
    # read by: plan_or_stop, do_observe, do_look
    observe_strikes: object
    # bound by: start_loop
    # read by: plan_or_stop, report_episode
    m8_per_plan: object
    # bound by: start_loop, do_look
    # read by: do_look, report_episode
    look_count: object
    # bound by: start_loop
    # read by: plan_or_stop, report_episode
    look_per_plan: object
    # bound by: start_loop
    # read by: plan_or_stop, report_episode
    plan_times: object
    # bound by: start_loop, plan_or_stop
    # read by: plan_or_stop, report_episode
    total_plan_time: object
    # bound by: start_loop
    # read by: plan_or_stop, report_episode
    boxel_counts_per_replan: object
    # bound by: start_loop
    # read by: _integrity_after, report_episode
    integrity_events: object


class Hand:
    """What the gripper holds, as the dispatcher verified it."""
    __slots__ = ('held_body_id', 'held_object_boxel_id', 'held_grasp_xy')

    # bound by: start_loop, do_move, do_pick, do_place, do_stack
    # read by: _readback_config, _integrity_after, _loop_done, plan_or_stop,
    #   dispatch_step, do_move, do_look, do_pick, do_place, do_stack,
    #   judge_success, report_episode
    held_body_id: object
    # bound by: start_loop, do_move, do_pick, do_place, do_stack
    # read by: nobody
    held_object_boxel_id: object
    # bound by: start_loop, do_pick
    # read by: _readback_config
    held_grasp_xy: object


class Arm:
    """The arm's last known configuration and the at-home record."""
    __slots__ = ('current_config', 'at_home_ok', 'home_misses',
                 'readback_count')

    # bound by: start_loop, initial_home_readback, do_move, do_pick, do_place,
    #   do_stack
    # read by: plan_or_stop, do_move, do_pick
    current_config: object
    # bound by: start_loop, dispatch_step, do_move
    # read by: _loop_done, do_move, judge_success
    at_home_ok: object
    # bound by: start_loop, do_move
    # read by: do_move
    home_misses: object
    # bound by: start_loop, do_move
    # read by: do_move
    readback_count: object


class Strikes:
    """The give-up rules' strike counts, and what was given up."""
    __slots__ = ('blocked_counts', 'blocked_giveup_shadows',
                 'pick_fail_counts', 'pick_giveup_objects',
                 'pick_giveup_marked_at', 'pick_parole_counts',
                 'transit_loss_counts', 'nontarget_rediscovery_counts',
                 'stack_fail_counts', 'disturbed_counts')

    # bound by: start_loop
    # read by: do_sense, do_look
    blocked_counts: object
    # bound by: start_loop
    # read by: plan_or_stop, do_sense, do_look, report_episode
    blocked_giveup_shadows: object
    # bound by: start_loop
    # read by: plan_or_stop, do_pick
    pick_fail_counts: object
    # bound by: start_loop
    # read by: plan_or_stop, no_plan_ends_episode, do_move, do_pick, do_place,
    #   do_stack, report_episode
    pick_giveup_objects: object
    # bound by: start_loop
    # read by: plan_or_stop, do_move, do_pick, do_place, do_stack
    pick_giveup_marked_at: object
    # bound by: start_loop
    # read by: plan_or_stop
    pick_parole_counts: object
    # bound by: start_loop
    # read by: plan_or_stop, do_move, do_place, do_stack
    transit_loss_counts: object
    # bound by: start_loop
    # read by: do_sense
    nontarget_rediscovery_counts: object
    # bound by: start_loop
    # read by: do_stack, report_episode
    stack_fail_counts: object
    # bound by: start_loop
    # read by: _integrity_after, plan_or_stop
    disturbed_counts: object


class Round:
    """What one round of the loop hands from its planning to its execution."""
    __slots__ = ('plan', 'held_obj_name')

    # bound by: plan_or_stop
    # read by: plan_or_stop, no_plan_ends_episode, execute_plan,
    #   dispatch_step, do_move
    plan: object
    # bound by: plan_or_stop
    # read by: plan_or_stop
    held_obj_name: object


class Ending:
    """Why and how the episode ended."""
    __slots__ = ('exit_reason', 'episode_over', 'target_lost_seen', 'success',
                 'physics_failures')

    # bound by: start_loop, _integrity_after, plan_or_stop,
    #   no_plan_ends_episode, do_move, do_stack, judge_success, report_episode
    # read by: judge_success, report_episode
    exit_reason: object
    # bound by: start_loop, _integrity_after, do_move, do_stack
    # read by: execute_plan
    episode_over: object
    # bound by: start_loop, _integrity_after, do_observe
    # read by: report_episode
    target_lost_seen: object
    # bound by: judge_success
    # read by: main, report_episode
    success: object
    # bound by: judge_success
    # read by: judge_success, report_episode
    physics_failures: object


class EpisodeState:
    """One episode's options and state groups; `st` in every stage function."""
    __slots__ = ('opts', 'setup', 'counts', 'hand', 'arm', 'strikes', 'round',
                 'ending')

    def __init__(self, opts, *, target_name, domain_file, home_joints):
        self.opts = opts
        self.setup = SetupState()
        self.counts = Counts()
        self.hand = Hand()
        self.arm = Arm()
        self.strikes = Strikes()
        self.round = Round()
        self.ending = Ending()
        # the three parameters of main() that its stages rebind
        self.setup.target_name = target_name
        self.setup.domain_file = domain_file
        self.setup.home_joints = home_joints
