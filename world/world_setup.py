"""The world stages of one episode: the size that sets the partition's cell,
the settled world, the first observation and the boxel registry.

main() of test_full_pipeline.py calls build_world, first_observation and
build_registry in this order, each with the episode state `st`
(episode_state.py) and the environment. test_full_pipeline imports every
name of this file, and callers import them from there.
"""
import sys

import numpy as np

from sensing import arm_eye
from world import interior_regions
from planning import streams
from world.boxel_data import BoxelRegistry, BoxelType
from world.cell_merger import merge_free_space_cells
from acting.execution import record_initial_detections
from console.visualization import BoxelVisualizer


def partition_extent(objects, target_extent=None):
    """Audit #66/#67, C-09: the largest object size that sets auto_cell.

    Plane, table, robot, trays and bodies without a size are left out.
    An occluder counts with its own size: the scene puts it in view.  A
    target (any other body) counts with target_extent, its class's
    declared size bound, when the scene declares one, so a hidden
    target's true size never sets the partition.  Without a declared
    bound a target counts with its own size: scenes without occluders
    (every target in view), the bridge's env (its sizes are task_spec's
    class sizes already) and custom SceneConfigs.
    """
    max_extent = 0.0
    for name, info in objects.items():
        if name in ("plane", "table", "robot"):
            continue
        if getattr(info, "is_tray", False):
            continue
        if info.size is None:
            continue
        if target_extent is not None and not info.is_occluder:
            max_extent = max(max_extent, float(target_extent))
            continue
        max_extent = max(max_extent, float(np.max(info.size)))
    return max_extent


def build_world(st, env):
    # audit #10 — uniform-grid baseline.  Toggle BoxelTestEnv's
    # free-space dispatch and (re)build the lattice at the requested
    # cell size before any boxel/registry work in Phase 2.  Default
    # path (baseline='semantic') leaves env.use_uniform_grid=False, so
    # generate_free_space falls through to the octree pipeline as before.
    # Audit #66 (Plan A) — auto-tune cell size to fit the largest
    # object AABB.  Default uniform cell 0.05 m is smaller than default
    # occluders (6-7 cm wide, 12-16 cm tall), so under uniform mode
    # every (boxel_fits ?occluder ?cell) atom is unsatisfiable on all
    # 3 axes (streams.py:369), the place precondition can't ground,
    # and PDDLStream loops searching for a plan that cannot exist
    # (logs/run_2026-05-09_10-48-13/: 2480 cells, 2472 boxel_fits,
    # iter-1 Cost: inf).  Largest AABB axis is the OCCLUDER HEIGHT,
    # so auto_cell ~ 0.17 m for the default scene.  Headroom +0.01 m
    # for PyBullet contact margin.  Acts as a SAFETY GUARD: if the
    # user passes --uniform-cell-size already >= auto_cell, keep it;
    # otherwise bump up.
    #
    # Audit #67 follow-up — also propagate the same value to the
    # semantic octree's min_resolution so both baselines have the
    # SAME smallest possible boxel size.  Without this match, the
    # octree subdivides down to its 0.035 m default while uniform
    # uses 0.06-0.17 m cells — the comparison ends up dominated by
    # grounding cost (number of cells), not the underlying
    # discretization strategy.  We compute effective_cell
    # unconditionally and apply it to whichever baseline is active.
    # C-09: a target counts with the scene's declared size bound when it
    # has one (SceneConfig.target_extent), not with a hidden body's own size.
    max_extent = partition_extent(
        env.objects, getattr(st.opts.scene_config, 'target_extent', None))
    auto_cell = max_extent + 0.01
    # Audit #66/#67: a uniform cell smaller than the largest object makes
    # (boxel_fits ?occluder ?cell) ungroundable, so uniform is always
    # clamped to auto_cell.  Semantic free space MERGES (CellMerger), so
    # open regions stay large-boxel even at a fine leaf floor — the #67
    # clamp on semantic existed only to keep it comparable to uniform at
    # equal resolution.  Audit #77: an EXPLICIT --min-boxel-size opts out
    # of that clamp (raw, may go below auto_cell); unset keeps the #67
    # default so existing #9/#10 comparisons are unchanged.
    if st.opts.baseline == 'uniform':
        effective_cell = max(st.opts.uniform_cell_size, auto_cell)
    elif st.opts.min_boxel_size is None:
        effective_cell = auto_cell
    else:
        effective_cell = st.opts.min_boxel_size
    print(f"  [audit-66/67] Effective minimum boxel size: "
          f"{effective_cell:.3f} m (largest seen or declared object size "
          f"{max_extent:.3f} m + 0.01 m headroom).")
    if st.opts.baseline != 'uniform' and st.opts.min_boxel_size is not None:
        rel = "below" if st.opts.min_boxel_size < auto_cell else "at/above"
        print(f"  [audit-77] semantic leaf floor set to explicit "
              f"--min-boxel-size {st.opts.min_boxel_size:.3f} m "
              f"({rel} auto_cell {auto_cell:.3f} m).")

    if st.opts.baseline == 'uniform':
        env.use_uniform_grid = True
        if abs(effective_cell - 0.05) > 1e-9:
            env.set_uniform_cell_size(effective_cell)
    else:
        # Semantic octree — clamp the minimum leaf size to
        # effective_cell so leaves can't be smaller than uniform's
        # cells.  Larger leaves are still allowed (CellMerger keeps
        # collapsing same-colour neighbours).
        env.free_space_generator.min_resolution = effective_cell

    # audit #77 — run_config logs the REQUESTED --min-boxel-size (None
    # when unset); also record the resolution ACTUALLY used so
    # timing_summary.json / aggregated.csv carry it.  report_run_outcome
    # serialises this same dict later, so the mutation propagates.
    if st.opts.run_config is not None:
        st.opts.run_config["effective_min_boxel_size"] = round(effective_cell, 4)

    # Path 9, --eye arm: the arm stands at its start configuration before the
    # settle (scene construction; an adopted world is not moved), and after it
    # the overview camera is the arm camera: there for the first image, and
    # where the arm stands for every later image and cast (follow_arm).
    if st.setup.eye == 'arm':
        arm_eye.place_arm(env, st.setup.eye_start)
    # Let settle: 50 steps at 240 Hz ≈ 0.2 s.  Enough for the loaded
    # Panda + cubes to reach static equilibrium after spawning.
    for _ in range(50):
        env.step_simulation()
    env.update_object_positions()
    if st.setup.eye == 'arm':
        _cam = arm_eye.use_start_view(env)
        st.setup.eye_camera_pose = _cam['camera_pose']
        print(f"  [eye] the overview camera is the arm camera at the start "
              f"configuration: {np.round(_cam['camera_position'], 3).tolist()}")
        arm_eye.follow_arm(env)

    # Audit #29: single-shot sanity log.  Placement in
    # ``_hidden_xy_positions`` already uses 8-corner raycasts against
    # the spawned occluders, so if the scene loaded at all the hidden
    # targets were raycast-verified occluded at spawn time.  We still
    # run one ``oracle_detect_objects`` pass AFTER physics settle to
    # catch any drift, but we do NOT retry — a mismatch here is either
    # a placement-vs-oracle logic bug worth investigating, or sub-mm
    # settling drift that does not affect downstream behaviour.
    required_hidden = int(getattr(st.opts.scene_config, 'n_hidden_targets', 0) or 0)
    if required_hidden > 0 and st.opts.oracle_phases:
        visible, _ = env.oracle_detect_objects()
        target_names = [
            name for name, info in env.objects.items()
            if not info.is_occluder
            and name not in ("plane", "table", "robot")
        ]
        hidden_now = sum(1 for t in target_names if t not in visible)
        if hidden_now >= required_hidden:
            print(f"  Hidden-target guarantee OK: {hidden_now}/"
                  f"{len(target_names)} hidden "
                  f"(requested >= {required_hidden}, "
                  f"seed={st.opts.scene_config.seed}).")
        else:
            print(f"  [warn] Hidden-target post-spawn check: "
                  f"{hidden_now}/{required_hidden} hidden "
                  f"(placement was raycast-verified; mismatch likely "
                  f"from physics settling drift). Continuing without "
                  f"retry.", file=sys.stderr)

    st.setup.robot_id = env.objects["robot"].object_id
    print(f"Robot ID: {st.setup.robot_id}")

    # #P4 B3(c): the caller's read-only check between the settle and the
    # first render (the bridge's D9 hook; it steps and moves nothing).
    if st.opts.after_settle is not None:
        st.opts.after_settle(env)


def first_observation(st, env):
    # =========================================================
    # PHASE 2: Boxel Calculation (fast, no visualization)
    # =========================================================
    # Perception pipeline:
    #   1. Camera observation → occupied boxels (objects + shadows they cast)
    #   2. Free-space generation → fills unoccupied table surface with boxels
    #   3. Cell merging → collapses adjacent free-space cells into fewer,
    #      larger boxels so the planner's search space stays tractable
    # The combined set gives the planner a complete spatial model of the
    # table surface: where objects are, where shadows are, and where
    # the robot can safely place things.
    print("\n--- Phase 2: Calculating Boxels ---")
    obs = env.get_camera_observation()
    all_known = obs.boxels
    if st.setup.eye == 'arm':
        # Path 9, --eye arm (PLAN 11.16): the part of the safe window the
        # first image does not show joins the known boxels as hidden regions,
        # as tall as the planner's prior for a hidden target, so free space at
        # the table top is made only where the image showed the table.
        _unseen = arm_eye.unseen_boxels(
            st.setup.eye_camera_pose, env._SAFE_TABLE_X_RANGE, env._SAFE_TABLE_Y_RANGE,
            env.table_surface_height, float(streams.NOMINAL_HIDDEN_EXTENTS[2]),
            known=all_known)
        all_known = all_known + _unseen
        print(f"  [eye] {len(_unseen)} unseen regions: the part of the table "
              f"the first image does not show")
    free_boxels = env.generate_free_space(all_known, visualize=False)
    # audit #10 — uniform baseline produces a strict static lattice;
    # CellMerger would collapse adjacent uniform cubes back into
    # variable-sized rectangles, defeating the uniform property.  Skip
    # merging under that mode; semantic mode keeps the merge as before
    # (octree leaves benefit from collapse).
    merged_free = (free_boxels if env.use_uniform_grid
                   else merge_free_space_cells(free_boxels))
    # Free-space geometry is stateless until here; tag table-contact info
    # so the planner can emit (on_surface ?b) for place actions (audit #35).
    env.annotate_free_space_surface(merged_free)
    st.setup.all_boxels = all_known + merged_free
    print(f"  Calculated {len(st.setup.all_boxels)} boxels")


def build_registry(st, env, overlay_bodies):
    # =========================================================
    # PHASE 3: Create Registry
    # =========================================================
    # The registry is the single source of truth for spatial reasoning.
    # It assigns stable IDs, classifies boxels by type, and records
    # parent relationships (which occluder created which shadow).
    # Both the PDDL planner and the execution layer reference the same
    # registry, ensuring symbolic names map to consistent geometry.
    print("\n--- Phase 3: Creating BoxelRegistry ---")
    # Post-#35: producers emit BoxelData with semantic IDs (object name for
    # OBJECT, "shadow_of_<name>" for SHADOW) and parent linkage already set.
    # Free-space cells arrive with empty IDs; add_boxel assigns "free_NNN".
    st.setup.registry = BoxelRegistry()
    for bd in st.setup.all_boxels:
        st.setup.registry.add_boxel(bd)
    # M8 A: the initial registrations' pose radius (no-op, no render,
    # while every switch is OFF).
    record_initial_detections(env, st.setup.registry)
    # BF#65 option 1 (D6, M2; no-op with the switch off): every registered
    # object whose class declares a cavity that holds a target class gets
    # its interior region, unknown, before the shadow list below is taken,
    # so it is wired like any fragment (belief, census, facts).  BF#65 (d):
    # a target the first render shows INSIDE a standing cover's box leaves
    # the registry again and is recorded as seen under that cover.
    if interior_regions.ENABLED:
        interior_regions.cast_first_observation(env, st.setup.registry, [st.setup.target_name])
    st.setup.registry.save_to_json("boxel_data.json")
    if st.opts.run_logger:
        st.opts.run_logger.save_artefact("boxel_data.json")

    # Extract the two categories the planner cares about:
    # - shadows: regions that might hide the target (must be sensed)
    # - occluders: objects blocking those shadows (must be relocated first)
    st.setup.shadows = [b.id for b in st.setup.registry.boxels.values() if b.boxel_type == BoxelType.SHADOW]
    st.setup.occluders = [b.id for b in st.setup.registry.boxels.values() if b.boxel_type == BoxelType.OBJECT]
    print(f"  {len(st.setup.registry.boxels)} boxels, {len(st.setup.shadows)} shadows, {len(st.setup.occluders)} occluders")

    st.setup.viz = None
    if st.opts.gui and st.opts.draw_boxel_overlays:
        st.setup.viz = BoxelVisualizer(phantoms=overlay_bodies)
        st.setup.viz.draw_registry(st.setup.registry, duration=0, label_size=1.0,
                          skip_free=not st.opts.show_free)
