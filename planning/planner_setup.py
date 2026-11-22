"""The planner stages of one episode: the belief and the planner with the
run's switches, the export of the initial problem, and the views an
observe or a look may use.

main() of test_full_pipeline.py calls build_planner, export_initial_problem
and arm_observe_views in this order with the episode state `st`
(episode_state.py). test_full_pipeline imports every name of this file,
and callers import them from there.
"""
import os
import tempfile

from world import interior_regions
from sensing import look_views
from planning import m8_domain
from sensing import observe_views
from sensing import pose_belief
from world import world_eye
from sensing.belief import BeliefState
from acting.execution import pick_contact_floor
from planning.pddlstream_planner import PDDLStreamPlanner
from console.run_logger import ledger_event


def build_planner(st, env, slip_fixes, args):
    # Initialise belief (all shadows unknown) and the planner.
    # The planner is stateless between calls — all context it needs
    # (known-empty shadows, moved occluders, current config) is passed
    # in each plan() call so replanning always starts from scratch with
    # the latest world state.
    st.setup.belief = BeliefState(st.setup.shadows, st.setup.target_name)
    tray_name = next((name for name, info in env.objects.items()
                      if info.is_tray), None)
    # Path 9, --eye arm: the planner gets no camera.  Its camera facts
    # (placement_hides, the placement view blocks) keep a camera that stands
    # still in view, and in this mode none does; the sense gate's hide test
    # takes the box test (streams.test_target_can_hide_in_shadow).
    planner_camera_pos = env.camera_position
    if st.setup.eye == 'arm':
        planner_camera_pos = None
    st.setup.planner = PDDLStreamPlanner(st.setup.registry, robot_id=env.plan_robot_id,
                                shadow_occluder_map=st.setup.shadow_occluder_map,
                                physics_client=env.plan_client_id,
                                object_body_ids=st.setup.object_body_ids,
                                support_body_ids=st.setup.planner_support_body_ids,
                                camera_pos=planner_camera_pos,
                                tray_name=tray_name,
                                domain_file=st.setup.domain_file)
    st.setup.planner.search_options = dict(st.setup.search_options)          # BF#53
    # G10: which domain and stream texts the planner loaded, under which
    # switches (the stream file's sha and the fold's switch since BF#52,
    # the search's settings since BF#53).
    ledger_event('domain', file=os.path.basename(st.setup.domain_file or m8_domain.LIVE_FILE),
                 sha=m8_domain.sha(st.setup.planner.domain_pddl),
                 stream_file=os.path.basename(m8_domain.STREAM_LIVE_FILE),
                 stream_sha=m8_domain.sha(st.setup.planner.stream_pddl),
                 switches=dict(pose_belief.SWITCHES,
                               sense_over_region=st.setup.sense_over_region,
                               interior_regions=interior_regions.ENABLED,     # BF#65
                               search_effort_weight=st.setup.search_effort_weight,
                               search_initial_complexity=st.setup.search_initial_complexity,
                               slip_fixes=slip_fixes.spec(),                  # BF#59
                               **({'look': st.setup.look_mode} if st.setup.look_on else {})))   # path 9
    # #P4 B3(d): the scene's reach envelope (None: streams' constants),
    # and D7 (i) to (iii): the home joints, and with a declared goal
    # configuration its init facts and the goal conjunct.
    if env.reach_envelope is not None:
        st.setup.planner.streams.set_reach(*env.reach_envelope)
    # BF#45: the executor's contact rule for the kin stream's contact
    # check (a task's own floor, D8; the table height for boxels without
    # a surface of their own).
    st.setup.planner.streams.contact_floor = pick_contact_floor(env)
    st.setup.planner.streams.surface_z_default = float(env.table_surface_height)
    if st.setup.home_joints is not None:
        st.setup.planner.streams.set_home_joints(st.setup.home_joints)
    if st.opts.goal_at_home:
        st.setup.planner.goal_config = st.setup.planner.home_config
        st.setup.goal = ('and', st.setup.goal, ('at_config', st.setup.planner.home_config))
    # F6: the meaning of the sense hideability fact is a CLI choice
    # until the A/B settles the default (see run_logger --sense-gate).
    st.setup.planner.sense_gate = getattr(args, 'sense_gate', 'off')
    st.setup.planner.corridor_test = getattr(args, 'corridor_test', 'cell+object')
    _ssr = getattr(args, 'search_sample_ratio', None)
    if _ssr is not None:
        st.setup.planner.search_sample_ratio = _ssr
    _pcs = getattr(args, 'path_check_step', None)
    if _pcs is not None:
        st.setup.planner.streams.path_check_step = _pcs
    st.setup.planner.streams.path_check_diag = bool(getattr(args, 'path_check_diag', False))

    # World eye (2026-09-18): textual snapshots of world + belief + camera
    # view at every decision and observation point of the loop, into
    # eye.log / eye.jsonl in the run directory (tools/eye.py queries them
    # by plan / step / time).  Pure observer, GUI and headless alike.
    if st.opts.run_logger is not None:
        world_eye.enable(st.opts.run_logger.run_dir, env, st.setup.robot_id, st.setup.body_id_to_name)
        world_eye.snapshot("initial observation (phase 2-4)",
                           registry=st.setup.registry, belief=st.setup.belief, plan_count=0,
                           with_view=True, save_image=True,
                           on_relations=st.setup.on_relations,
                           shadow_occluder_map=st.setup.shadow_occluder_map,
                           extra={"goal": str(st.setup.goal),
                                  "hidden_targets": sorted(st.setup.hidden_targets_set)})

    # The planner needs to reason about every object that may participate
    # in the goal.  For 'holding' that's just the chosen target; for
    # 'stack' it's every cube in the requested tower.
    st.setup.planner_target_objects = (
        st.setup.stack_target_objects
        if st.opts.goal_kind in ('stack', 'find-and-tray-stack')
        else [st.setup.target_name]
    )


def export_initial_problem(st):
    # BF#54: the debug problem file goes into the run directory (the temp
    # directory without a run logger), never into the code tree: on the
    # cluster the snapshot is read-only and every arm O episode of the
    # 2026-10-30 campaigns crashed here (the smoke returns above this line).
    _export_dir = str(st.opts.run_logger.run_dir) if st.opts.run_logger else tempfile.gettempdir()
    problem_path = st.setup.planner.export_problem_pddl(
        target_objects=st.setup.planner_target_objects,
        goal=st.setup.goal,
        visible_target_locations=st.setup.visible_target_locations,
        filepath=os.path.join(_export_dir, 'problem_debug.pddl'),
    )
    print(f"  Exported initial problem to {problem_path}")
    if st.opts.run_logger:
        st.opts.run_logger.save_artefact(problem_path, "problem_initial.pddl")


def arm_observe_views(st, env):
    # M8 C: the observation configurations, computed in the plan twin at
    # every _build_init from here on (the export above has none).
    if pose_belief.SWITCHES['M8']:
        st.setup.planner.m8_views = observe_views.ObserveViews(
            env, st.setup.planner.streams._robot_base_xy)
        # BF#52: the fold's switch (over_region_facts needs m8_views).
        st.setup.planner.sense_over_region = st.setup.sense_over_region
        # Path 9: the look's viewpoints, from the same plan twin.  The boxel
        # look chooses its own (look_views); the centred look takes the tag's
        # observe rule from m8_views.
        if st.setup.look_on:
            if st.setup.look_mode == 'boxel':
                st.setup.planner.look_views = look_views.LookViews(
                    st.setup.planner.m8_views, reachable=st.setup.planner.streams.ee_reachable)
            st.setup.planner.look_on = True
            st.setup.planner.look_mode = st.setup.look_mode
