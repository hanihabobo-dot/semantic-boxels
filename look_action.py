"""
look_action.py: the Python of the `look` action (path 9 of the dev tracks,
BF#68; PLAN.md 3.6 of tracks/look).

The PDDL says (look_domain.LOOK_SECTION):

  (:action look :parameters (?o ?h ?v ?q)
    :precondition (and (look_for ?o ?h) (Config ?q) (Boxel ?v) (handempty)
                       (at_config ?q) (config_for_boxel ?q ?v) (look_clear ?q ?h))
    :effect (and (obj_at_boxel ?o ?h) (obj_pose_known ?o)
                 (forall (?r) (when (look_clear ?q ?r) (obj_at_boxel_KIF ?o ?r)))
                 (forall (?p) (when (and (Obj ?p) (look_clear ?q ?p))
                                (obj_pose_known ?p)))))

handle_look_action does exactly that and nothing else: it checks what the
precondition names, renders once with the wrist camera, and writes what the
effects name.  LOOK_SPEC is the contract; tests/test_look_correspondence.py
compares its keys with the PDDL's precondition and effect atoms and runs the
handler on a synthetic scene, comparing the whole before and after state with
the writes the spec names.

The object-centred look (--look centred, look_domain.LOOK_SECTION_CENTRED) is
the same handler with params (?o ?h ?q): no viewpoint boxel to check, and the
plan names the one hypothesis ?h and nothing else, so only ?h (a region or the
object's own boxel) and ?o are written.  CENTRED_SPEC is its contract.

What the action does NOT write (the sense and observe of the tag did): the
other fragments a render clears beyond the named ones, the re-pose of bodies
the plan did not name, the partial shrink of a blocked fragment, the free
space partition, the strike counters, the lost verdict.  Strikes are loop
rules (the dispatcher), the lost verdict belongs to the integrity monitor, and
a body the render shows that has no boxel goes through register_new_detections,
the function that runs after every action that renders (monitor rule M-1, a
log row of its own).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

import interior_regions
import observe_views
import pose_belief
import robot_utils
from boxel_data import BoxelData, BoxelType
from execution import (detection_complete, register_new_detections,
                       sense_shadow_from_render)
from look_views import _overlaps, points_in_box
from perception import (SENSE_MARGINAL_BLOCKED_FRACTION,
                        first_surface_interceptors, sense_ray_slices)
from run_logger import provenance, provenance_channel

AT_CONFIG_TOL_RAD = 0.05        # the arm readback against ?q, per joint
LOOK_BOXEL_TOL_M = 0.01         # the camera against ?v, inflated by this
STRIKE_PARK = 3                 # blocked looks at one region before it is parked

# The contract between the PDDL action and this handler.  Keys are the
# predicates the action's precondition and effect name (effects as
# (predicate, polarity, conditional)); each value says what the Python does
# for it.  A PDDL edit with no entry here, or an entry with no PDDL line,
# fails tests/test_look_correspondence.py.
LOOK_SPEC = {
    'parameters': ['?o', '?h', '?v', '?q'],
    'pre': {
        'look_for': ('static', "the plan's own init; nothing to check"),
        'Config': ('static', "type"),
        'Boxel': ('static', "type"),
        'handempty': ('check', "held_body_id is None, else stale_precondition"),
        'at_config': ('check', f"the arm readback is within {AT_CONFIG_TOL_RAD} rad "
                               "of ?q on every joint, else stale_precondition"),
        'config_for_boxel': ('check', f"the camera from the readback lies inside ?v "
                                      f"inflated by {LOOK_BOXEL_TOL_M} m, else "
                                      "stale_precondition"),
        'look_clear': ('render', "judged by the one render: a region that renders "
                                 "still_blocked, or an object not seen completely, "
                                 "takes no effect"),
    },
    'eff': {
        ('obj_at_boxel', True, False): (
            'write', "?o found in ?h: register ?o's OBJECT boxel at its wrist "
                     "detection (the audit #76 hook), belief.mark_sensed(?h, found)"),
        ('obj_pose_known', True, False): (
            'write', "?o's wrist detection is complete: pose_belief.record_detection "
                     "(wrist), the A rule; known when the commit margin holds"),
        ('obj_at_boxel_KIF', True, True): (
            'write', "a named region the render clears of ?o: belief.mark_sensed(r, "
                     "not found) and the fragment leaves the registry"),
        ('obj_pose_known', True, True): (
            'write', "a named object the render shows completely: "
                     "pose_belief.record_detection (wrist), the box re-posed"),
    },
    'eff_cond': {'look_clear', 'Obj'},
    # Not part of the action: the shared rule run after every render.
    'monitor': {'M-1': "register_new_detections for a body the render shows "
                       "that has no boxel"},
}


CENTRED_SPEC = {
    'parameters': ['?o', '?h', '?q'],
    'pre': {
        'look_for': ('static', "the plan's own init; nothing to check"),
        'Config': ('static', "type"),
        'handempty': ('check', "held_body_id is None, else stale_precondition"),
        'at_config': ('check', f"the arm readback is within {AT_CONFIG_TOL_RAD} rad "
                               "of ?q on every joint, else stale_precondition"),
        'look_config': ('static', "planner side: at ?q the plan twin's wrist camera "
                                  "is aimed at the centre of ?h (straight over it, "
                                  "or from a horizontal offset for a region) and "
                                  "shows all of ?h in view and unblocked "
                                  "(ObserveViews.look_configs, the tag's observe "
                                  "rule); the executor does not check it, and a "
                                  "render that still hides part of ?h is a strike"),
    },
    'eff': {
        ('obj_at_boxel', True, False): (
            'write', "?o found in ?h: register ?o's OBJECT boxel at its wrist "
                     "detection (the audit #76 hook), belief.mark_sensed(?h, found)"),
        ('obj_at_boxel_KIF', True, False): (
            'write', "?h seen without ?o: belief.mark_sensed(?h, not found) and the "
                     "fragment leaves the registry; a view that does not show all of "
                     "?h writes nothing (a strike)"),
        ('obj_pose_known', True, False): (
            'write', "?o's wrist detection is complete: pose_belief.record_detection "
                     "(wrist), the A rule; known when the commit margin holds"),
    },
    'eff_cond': set(),
    'monitor': {'M-1': "register_new_detections for a body the render shows "
                       "that has no boxel"},
}

SPECS = {'boxel': LOOK_SPEC, 'centred': CENTRED_SPEC}


@dataclass
class LookResult:
    """What the handler did; ``continue_`` and ``reason`` as ActionResult."""
    continue_: bool
    reason: str
    outcomes: Dict[str, str] = field(default_factory=dict)   # named region -> outcome
    hidden: Dict[str, float] = field(default_factory=dict)   # named region -> blocked fraction
    reposed: List[str] = field(default_factory=list)         # named objects re-posed
    found_in: Optional[str] = None
    registered: List[str] = field(default_factory=list)      # M-1
    stale: Optional[str] = None
    parked: List[str] = field(default_factory=list)          # regions parked by strikes
    blocked: List[str] = field(default_factory=list)         # named regions still blocked
    pose_known: Optional[bool] = None

    @property
    def reached(self) -> bool:
        """The precondition held and the look was made (nothing stale); how it
        went is in ``continue_`` and ``reason``.  Path 8's inspect reads this
        and nothing of the render (tracks/look/PLAN.md section 13)."""
        return self.stale is None


def _stale(why: str) -> LookResult:
    print(f"    look: stale precondition: {why}")
    return LookResult(False, 'look_stale_precondition', stale=why)


def check_preconditions(*, env, registry, robot_id, held_body_id, params,
                        mode='boxel'):
    """The checks the precondition names that Python can make; None when they
    all hold, else why not.  Writes nothing."""
    if mode == 'centred':
        obj, h, q, v = str(params[0]), str(params[1]), params[2], None
    else:
        obj, h, v, q = str(params[0]), str(params[1]), str(params[2]), params[3]
    if held_body_id is not None:
        return "the hand is not empty (handempty)"
    if registry.get_boxel(h) is None:
        return f"{h} is not in the registry (look_for)"
    if obj not in env.objects:
        return f"{obj} is not a task body"
    arm = robot_utils.arm_joint_positions(robot_id, env.client_id)
    dq = float(np.max(np.abs(np.asarray(arm, dtype=float)
                             - np.asarray(q.joint_positions, dtype=float))))
    if dq > AT_CONFIG_TOL_RAD:
        return f"the arm is {dq:.3f} rad from {q.name} (at_config)"
    if v is None:                       # the centred look has no viewpoint boxel
        return None
    vb = registry.get_boxel(v)
    if vb is None:
        return f"viewpoint boxel {v} is not in the registry (config_for_boxel)"
    cam = robot_utils.wrist_camera_pose(robot_id, env.client_id)[:3, 3]
    lo = np.asarray(vb.min_corner, dtype=float) - LOOK_BOXEL_TOL_M
    hi = np.asarray(vb.max_corner, dtype=float) + LOOK_BOXEL_TOL_M
    if not (np.all(cam >= lo) and np.all(cam <= hi)):
        return f"the camera {np.round(cam, 3).tolist()} is outside {v} (config_for_boxel)"
    return None


def _stands_at(bd, region) -> bool:
    """A registered body stands in or at ``region``: its believed box
    overlaps or touches it: look_views._overlaps, the plan twin's test in
    look_views._content."""
    return _overlaps(bd.min_corner, bd.max_corner,
                     region.min_corner, region.max_corner)


def _judged_body(env, obj, target_name):
    """(name, body id) the named regions are judged for: the mission target,
    whatever the look's ?o (a pose look's ?o is another body); ?o itself only
    when the env has no body of the target's name."""
    tname = str(target_name)
    if tname in env.objects:
        return tname, env.objects[tname].object_id
    return str(obj), env.objects[obj].object_id


def _struck(blocked, h, registry):
    """The still-blocked named regions that take a strike.  An interior region
    whose cover still stands over it is hidden by that cover, not by a bad
    view: it takes no strike unless it is the planned region ?h, as the sense
    strikes only the shadow it was planned for (BF#65 x path 9)."""
    out = []
    for sid in blocked:
        if sid != h and interior_regions.standing_cover_of(
                registry, registry.get_boxel(sid)) is not None:
            print(f"    look: {sid} blocked by its standing cover (no strike)")
            continue
        out.append(sid)
    return out


def _occluder_ids(registry, region, env):
    """The executing client's ids of the registered bodies that do not stand
    in or at ``region``: what may hide it.  A body in or at it is content
    (_content_boxes)."""
    ids = set()
    cover = interior_regions.standing_cover_of(registry, region)   # BF#65: hides, never content
    for bd in registry.get_boxels_by_type(BoxelType.OBJECT):
        if _stands_at(bd, region) and not (cover is not None and bd.id == cover.id):
            continue
        info = env.objects.get(bd.object_name or bd.id)
        if info is not None:
            ids.add(info.object_id)
    return ids


def _content_boxes(registry, region, env):
    """{executing client id: believed (lo, hi)} of the registered bodies that
    stand in or at ``region``, the ones _occluder_ids leaves out.  Such a body
    is seen where it stands and hides what lies behind it (PLAN.md 11.14)."""
    out = {}
    cover = interior_regions.standing_cover_of(registry, region)   # BF#65: hides, never content
    for bd in registry.get_boxels_by_type(BoxelType.OBJECT):
        if not _stands_at(bd, region) or (cover is not None and bd.id == cover.id):
            continue
        info = env.objects.get(bd.object_name or bd.id)
        if info is not None:
            out[info.object_id] = (np.asarray(bd.min_corner, dtype=float),
                                   np.asarray(bd.max_corner, dtype=float))
    return out


def _hidden_fraction(region, render, occluder_ids, content, robot_id) -> float:
    """The worst sense slice's fraction of the region's endpoints that the
    render does not show, by the look's rule: outside the frame (always, as
    the plan twin counts them; the sense counts them only when an occluder or
    the robot hides an endpoint of the region), or behind an occluder or the
    robot, or behind a body standing in or at the region (a support such as a
    tray too) and outside its believed box grown by
    look_views.LOOK_CONTENT_TOL_M (points_in_box); an endpoint inside that box
    is the body itself, seen.  The plan twin applies the same test to such a
    body (look_views.LookViews._evaluate); the twin also counts a surface the
    sense ignores and no boxel names (the table)."""
    depth_m, seg, view, proj = render
    slices, _ = sense_ray_slices(region.min_corner, region.max_corner)
    hiders = set(occluder_ids) | ({robot_id} if robot_id is not None else set())
    worst = 0.0
    for sl in slices:
        icp, hids, in_view = first_surface_interceptors(sl.points, depth_m, seg,
                                                        view, proj)
        in_view = np.asarray(in_view, dtype=bool)
        hit = in_view & np.asarray(icp, dtype=bool)
        hids = np.asarray(hids)
        hidden = ~in_view | (hit & np.isin(hids, list(hiders)))
        for pid, (lo, hi) in content.items():
            hidden |= hit & (hids == pid) & ~points_in_box(sl.points, lo, hi)
        worst = max(worst, float(np.count_nonzero(hidden)) / len(sl.points))
    return worst


def _judge(region, target_pid, render, registry, env, robot_id, supports):
    """One named region against the look's one render: the outcome of
    sense_shadow_from_render, and one rule more (PLAN.md 11.14).  The sense
    takes every surface of a body standing in or at the region for the body
    in it, and ignores the surface of a support (a tray, in ``supports``)
    altogether; the look counts the endpoints behind such a body, outside its
    box, as hidden, so a region the render does not show beyond the sense
    tolerance is still_blocked (a strike), not contains_nontarget or
    clear_but_empty (removed).  Only a region with such a body is counted
    again, on the same render.  Returns the sense's five values."""
    depth_m, seg, view, proj = render
    occ = _occluder_ids(registry, region, env)
    outcome, frac, bodies, bbox, counts = sense_shadow_from_render(
        region, target_pid, depth_m, seg, view, proj, occ,
        robot_id=robot_id, support_body_ids=supports)
    if outcome in ('contains_nontarget', 'clear_but_empty'):
        content = _content_boxes(registry, region, env)
        if content:
            hidden = _hidden_fraction(region, render, occ, content, robot_id)
            if hidden > SENSE_MARGINAL_BLOCKED_FRACTION:
                return 'still_blocked', hidden, set(), None, counts
    return outcome, frac, bodies, bbox, counts


def _remove_fragment(sid, registry, belief, viz, shadows, shadow_occluder_map,
                     boxel_centers):
    """The fragment leaves the world model: it was seen without the target."""
    belief.mark_sensed(sid, found=False)
    bd = registry.get_boxel(sid)
    registry.remove_boxel(sid)
    if viz is not None:
        viz.remove_boxel_viz(sid)
    if sid in shadows:
        shadows.remove(sid)
    shadow_occluder_map.pop(sid, None)
    boxel_centers.pop(sid, None)
    caster_id = (bd.created_by_boxel_id or bd.created_by_object) if bd is not None else None
    caster = registry.get_boxel(caster_id) if caster_id else None
    if caster is not None and sid in getattr(caster, 'shadow_boxel_ids', []):
        caster.shadow_boxel_ids.remove(sid)


def _register_target(obj, det, env, registry, viz, render, boxel_centers,
                     boxel_to_pybullet, object_body_ids):
    """The audit #76 hook on the wrist render: ?o found in a region becomes an
    OBJECT boxel at its detection.  False when the detection is below the
    minimum (nothing registered; the next observation localizes it)."""
    info = env.objects.get(obj)
    if info is None or det is None:
        return False
    bd = BoxelData(
        id=obj, boxel_type=BoxelType.OBJECT,
        min_corner=np.array(det.est_min), max_corner=np.array(det.est_max),
        object_name=obj, is_occluder=False,
        on_surface=("table" if det.est_min[2] <= env.table_surface_height + 0.01
                    else None),
        surface_z=env.table_surface_height)
    registry.add_boxel(bd)
    pose_belief.record_detection(
        bd, det, 'wrist',
        detection_complete(env, det.est_min, det.est_max, det, render),
        first=True)
    boxel_centers[obj] = bd.center
    object_body_ids[obj] = env.plan_body_id(info.object_id)
    boxel_to_pybullet[obj] = {'name': obj, 'pybullet_id': info.object_id,
                              'position': np.array(det.est_center)}
    if viz is not None:
        viz.draw_boxel_data(bd)
    return True


def _repose(bd, det, env, registry, viz, render) -> bool:
    """The A rule on one registered body the render shows: the box keeps its
    size and is re-posed on the detection (observe_views' C2 write).  Only a
    complete detection counts."""
    cur_ext = np.asarray(bd.max_corner, dtype=float) - np.asarray(bd.min_corner, dtype=float)
    canon = np.maximum(cur_ext, det.est_max - det.est_min)
    centre = (det.est_min[:2] + det.est_max[:2]) / 2.0
    new_max = np.array([centre[0] + canon[0] / 2.0, centre[1] + canon[1] / 2.0,
                        det.est_max[2]])
    new_min = new_max - canon
    if not detection_complete(env, new_min, new_max, det, render):
        return False
    pose_belief.record_detection(bd, det, 'wrist', True, rigid_ext=cur_ext)
    if not (np.allclose(new_min, bd.min_corner, atol=1e-4)
            and np.allclose(new_max, bd.max_corner, atol=1e-4)):
        bd.min_corner = new_min
        bd.max_corner = new_max
        setattr(registry, "_dirty", True)
        if viz is not None and viz.tracks_boxel(bd.id):
            viz.remove_boxel_viz(bd.id)
            viz.draw_boxel_data(bd)
    return True


@provenance_channel('planned_look_render')
def handle_look_action(*, action_params, named, env, registry, belief, viz,
                       robot_id, held_body_id, support_body_ids, shadows,
                       occluders, shadow_occluder_map, blocked_counts,
                       blocked_giveup_shadows, boxel_centers, boxel_to_pybullet,
                       object_body_ids, pose_known, target_name,
                       mode='boxel') -> LookResult:
    """Execute one PDDL ``look`` (module docstring).

    ``named``: the region and object ids of the plan's own ``(reveals ?q r)``
    facts for this ?q, the single source of what the render may write (the
    centred look: just ?h).  ``pose_known(boxel)``: the planner's commit rule.
    ``mode``: 'boxel' (params ?o ?h ?v ?q) or 'centred' (params ?o ?h ?q).
    """
    obj, h = str(action_params[0]), str(action_params[1])
    q = action_params[2] if mode == 'centred' else action_params[3]
    why = check_preconditions(env=env, registry=registry, robot_id=robot_id,
                              held_body_id=held_body_id, params=action_params,
                              mode=mode)
    if why is not None:
        return _stale(why)

    # One wrist render in the executing client; detections of every task body.
    dets, render = observe_views.wrist_observation(env, robot_id)
    supports = frozenset(support_body_ids or ()) | {
        info.object_id for info in env.objects.values()
        if getattr(info, 'is_tray', False)}
    # Every named region is judged for the MISSION target, as the sense judges
    # its shadow (track/evalfinal, 2026-11-19): a pose look's ?o is another
    # body (a cup), and judging the regions for that body "found" it in its
    # own interior and shadow, marking them found with the die never seen
    # (find_dice seeds 142, 146, 149, --look boxel --eye arm --interior-regions on).
    tname, target_pid = _judged_body(env, obj, target_name)

    regions = [n for n in sorted(named)
               if registry.get_boxel(n) is not None
               and registry.get_boxel(n).boxel_type == BoxelType.SHADOW]
    objects = [n for n in sorted(named)
               if registry.get_boxel(n) is not None
               and registry.get_boxel(n).boxel_type == BoxelType.OBJECT]
    # The planned region first: its outcome is the unconditional effect.
    if h in regions:
        regions.remove(h)
        regions.insert(0, h)

    res = LookResult(True, 'look_ok')
    found_here = False
    pose_look_registered = []     # the target registered by a pose look (another ?o): a replan
    for sid in regions:
        region = registry.get_boxel(sid)
        outcome, frac, bodies, _bbox, _counts = _judge(
            region, target_pid, render, registry, env, robot_id, supports)
        res.outcomes[sid] = outcome
        res.hidden[sid] = round(float(frac), 4)
        print(f"    look {sid}: {outcome}"
              f"{f' ({frac:.0%} hidden)' if outcome == 'still_blocked' else ''}")
        if outcome == 'still_blocked':
            res.blocked.append(sid)
            continue
        if outcome == 'contains_nontarget':
            # Observed without the target, but only if what stands in it can
            # be registered; else the volume behind it is not accounted for.
            names = {env_name for env_name, info in env.objects.items()
                     if info.object_id in bodies}
            if any(n not in dets and registry.get_boxel(n) is None for n in names):
                res.outcomes[sid] = 'unlocalizable'
                res.blocked.append(sid)
                continue
        if outcome == 'found_target':
            belief.mark_sensed(sid, found=True)
            res.found_in = sid
            found_here = sid == h and obj == tname
            if registry.get_boxel(tname) is None:
                if (_register_target(tname, dets.get(tname), env, registry, viz, render,
                                     boxel_centers, boxel_to_pybullet, object_body_ids)
                        and obj != tname):
                    pose_look_registered.append(tname)
            continue
        _remove_fragment(sid, registry, belief, viz, shadows,
                         shadow_occluder_map, boxel_centers)

    for pid in objects:
        bd = registry.get_boxel(pid)
        det = dets.get(pid)
        if det is not None and _repose(bd, det, env, registry, viz, render):
            res.reposed.append(pid)

    # Monitor rule M-1: a body the render shows that has no boxel.
    res.registered = register_new_detections(
        env=env, registry=registry, belief=belief, viz=viz, detections=dets,
        target_name=str(target_name), shadows=shadows, occluders=occluders,
        shadow_occluder_map=shadow_occluder_map, boxel_centers=boxel_centers,
        boxel_to_pybullet=boxel_to_pybullet, object_body_ids=object_body_ids,
        render=render, held_body_id=held_body_id, camera='wrist')
    # A pose look that found and registered the target: reported as a
    # registration, so the dispatcher replans as it does after M-1 (review of a3fa79c).
    res.registered = list(res.registered or []) + [n for n in pose_look_registered
                                                   if n not in (res.registered or [])]

    # Strikes are a loop rule: a named region still blocked is one more strike.
    for sid in _struck(res.blocked, h, registry):
        blocked_counts[sid] = blocked_counts.get(sid, 0) + 1
        print(f"    look: {sid} blocked [strike {blocked_counts[sid]}/{STRIKE_PARK}]")
        if blocked_counts[sid] >= STRIKE_PARK:
            blocked_giveup_shadows.add(sid)
            with provenance('strike_park'):
                belief.mark_unresolved(sid)
            res.parked.append(sid)

    # Continue or replan: the unconditional effects hold in the belief now.
    bd_o = registry.get_boxel(obj)
    if h == obj:
        at_ok = bd_o is not None
    else:
        at_ok = found_here and bd_o is not None
    pose_ok = bd_o is not None and bool(pose_known(bd_o))
    res.pose_known = pose_ok
    if not (at_ok and pose_ok):
        res.continue_ = False
        res.reason = ('look_not_found' if not at_ok else 'look_pose_incomplete')
        if h in res.blocked:
            res.reason = 'look_blocked'
    print(f"    look {obj} from {q.name}: {res.reason}; named regions "
          f"{regions}, objects {objects}, re-posed {res.reposed}, "
          f"registered {res.registered}")
    return res
