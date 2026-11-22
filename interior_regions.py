"""
interior_regions.py: the hiding region under a cover (BF#65 option 1; the
audit's D6, model tweak M2).

BEFORE: a hiding region is the space BEHIND an object as the camera sees it
(shadow_calculator.py); an OBJECT boxel is solid (audit #67), so the space
its box takes is no hiding place.  A target under an upside-down cup starts
in no region (BF#65: every find_dice scene).

AFTER, with the switch on: an object whose class is DECLARED to have a
cavity that holds a target class (ObjectInfo.cavity: the inner footprint and
height; None for a solid body) owns one more hiding region, of kind
'interior': the cavity's footprint at table height under the object's
estimated box.  It is a SHADOW boxel and is wired exactly like a lateral
fragment: registry, belief (unknown), the blocker census (every point of it
lies inside the cover, so the cover is what blocks the view; with --eye arm
no blocker census is run at all, a look reads none of it), the planner's
facts, the sense and its grid, the kin stream.  It is searched by moving the
cover away and looking.  It is a fixed region of space: when its cover is
moved it stays where it was.  No domain, planner or sense change.

Classes that declare no cavity cast nothing (every scene of our own: solid
blocks).  The switch is off by default: main() sets ENABLED from
--interior-regions each run.

STATUS RULE (D6): at the first observation every such region is unknown.
At a later registration of a hollow body (discovery, re-detection) it is
unknown unless its whole footprint lies in free-space boxels, which were
observed empty before the body came to stand there; then none is cast.  A
placement by the robot casts none.

SEEN UNDER A COVER (BF#65 (d)): a detection of the target INSIDE the box of
a cover that still stands over its interior region is no pose the robot can
use: no wrist look sees it (observe_views.look_configs: the cover hides
every point) and no grasp reaches it.  It is not registered as an object;
the module records "target seen under <cover>", and while that record
holds the main loop offers the planner that one region (the others are
withheld through known_empty_shadows; the belief itself is not changed), so
the plan is: move the cover, look, pick.  If no plan binds through that one
region, the record ends (release) and is not made again for that region, so
the planner is offered every unknown region; the target stays unregistered
while the cover stands over it.

The interior ids live in the cover's ``interior_boxel_ids``, not in
``shadow_boxel_ids``: the rediscovery cleanup and the lost-object
retirement walk the latter, and an interior region leaves the belief only
through a render of its own grid (the sense or the sweep).
"""
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from boxel_data import BoxelData, BoxelType
from run_logger import ledger_event

# Set by main() each run (configure); False: this module does nothing.
ENABLED = False

KIND = 'interior'
ID_PREFIX = 'interior_of_'

# The status rule's lattice over the footprint, per axis.
_STATUS_GRID = 5
# A detection counts as inside a cover's box up to this margin (the box is
# a perception estimate; the render's depth noise is millimetres).
_INSIDE_TOL = 0.005
# A carved part of a region narrower than this is not kept (cast_for).
_MIN_PART_SIDE = 0.01

# target name -> the interior region id it was seen in while the cover
# stood (BF#65 (d)).  Per run: configure() clears it.
_seen_under: Dict[str, str] = {}
# Regions for which a record ended because no plan bound through them
# (release): no record is made for them again.  Per run.
_no_plan_regions: set = set()


def configure(flag) -> bool:
    """Set the switch for this run ('on'/'off' or a bool) and clear the
    run's records."""
    global ENABLED
    ENABLED = (flag is True) or (str(flag).lower() == 'on')
    _seen_under.clear()
    _no_plan_regions.clear()
    return ENABLED


def is_interior(bd) -> bool:
    return (bd is not None and bd.boxel_type == BoxelType.SHADOW
            and getattr(bd, 'region_kind', 'lateral') == KIND)


def standing_cover_of(registry, region) -> Optional[BoxelData]:
    """The cover of an interior region while it still stands over it (the
    region's centre inside the cover's footprint), else None.  For the look
    (track/evalfinal, 2026-11-19): such a cover hides its region and is never
    its content, so a look must wait until a plan has moved it away, as the
    sense does."""
    if not ENABLED or not is_interior(region):
        return None
    cover = registry.get_boxel(region.created_by_boxel_id or '')
    if cover is None:
        return None
    rc = region.center
    cmin = np.asarray(cover.min_corner, dtype=float)
    cmax = np.asarray(cover.max_corner, dtype=float)
    if cmin[0] <= rc[0] <= cmax[0] and cmin[1] <= rc[1] <= cmax[1]:
        return cover
    return None


def cavity_of(env, name: str) -> Optional[np.ndarray]:
    """The declared cavity (x, y, z in metres) of the object's class, or
    None for a solid body."""
    info = env.objects.get(name)
    cav = getattr(info, 'cavity', None) if info is not None else None
    if cav is None:
        return None
    cav = np.asarray(cav, dtype=float)
    return cav if cav.shape == (3,) and np.all(cav > 0) else None


def holds(cavity, extents) -> bool:
    """Does a body of full ``extents`` fit in ``cavity``, resting flat, at
    either quarter turn?"""
    c = np.asarray(cavity, dtype=float)
    e = np.asarray(extents, dtype=float)
    if e.shape != (3,) or not np.all(np.isfinite(e)) or np.any(e <= 0):
        return False
    return bool(e[2] <= c[2]
                and min(e[0], e[1]) <= min(c[0], c[1])
                and max(e[0], e[1]) <= max(c[0], c[1]))


def target_classes(env, target_names: Iterable[str]) -> List[np.ndarray]:
    """The class sizes of the bodies the task may look for: the named
    targets, or (none named yet) every object that is neither an occluder
    nor the tray."""
    names = [t for t in (target_names or []) if t]
    if not names:
        names = [n for n, i in env.objects.items()
                 if n not in ('plane', 'table', 'robot')
                 and not i.is_occluder and not getattr(i, 'is_tray', False)]
    out = []
    for n in names:
        info = env.objects.get(n)
        if info is not None and info.size is not None:
            out.append(np.asarray(info.size, dtype=float))
    return out


def region_bounds(obj_bd: BoxelData, cavity, table_z: float
                  ) -> Tuple[np.ndarray, np.ndarray]:
    """The interior region of an object: the cavity's footprint centred on
    the object's estimated box, from the table up to the cavity's height
    (never above the box's top)."""
    c = np.asarray(obj_bd.center, dtype=float)
    cav = np.asarray(cavity, dtype=float)
    top = min(float(table_z) + float(cav[2]), float(obj_bd.max_corner[2]))
    lo = np.array([c[0] - cav[0] / 2.0, c[1] - cav[1] / 2.0, float(table_z)])
    hi = np.array([c[0] + cav[0] / 2.0, c[1] + cav[1] / 2.0, top])
    return lo, hi


def observed_before(registry, lo, hi) -> bool:
    """D6's status rule: does the whole footprint lie in free-space boxels
    (space observed empty before the body came to stand there)?"""
    free = [(np.asarray(b.min_corner, dtype=float), np.asarray(b.max_corner, dtype=float))
            for b in registry.get_free_space_boxels()]
    if not free:
        return False
    z = float(lo[2]) + 0.005
    for x in np.linspace(lo[0], hi[0], _STATUS_GRID):
        for y in np.linspace(lo[1], hi[1], _STATUS_GRID):
            if not any(fmin[0] - 1e-9 <= x <= fmax[0] + 1e-9
                       and fmin[1] - 1e-9 <= y <= fmax[1] + 1e-9
                       and fmin[2] - 1e-9 <= z <= fmax[2] + 1e-9
                       for fmin, fmax in free):
                return False
    return True


def _carve(env, region: BoxelData, registry, caster_id: str) -> List[BoxelData]:
    """B5's one carve set: the region minus every OBJECT box but its
    cover's and minus every existing SHADOW fragment, so a point belongs to
    at most one hiding region (audit #68)."""
    calc = env.shadow_calculator
    obstacles = [b for b in registry.boxels.values()
                 if (b.boxel_type == BoxelType.OBJECT and b.id != caster_id)
                 or b.boxel_type == BoxelType.SHADOW]
    active = [region]
    for ob in obstacles:
        nxt = []
        for frag in active:
            if calc._check_aabb_intersection(frag, ob):
                nxt.extend(calc._subtract_aabb(frag, ob, np.zeros(3)))
            else:
                nxt.append(frag)
        active = nxt
    return active


def cast_for(env, registry, obj_bd: BoxelData, target_names: Iterable[str],
             first_observation: bool) -> List[BoxelData]:
    """Cast the interior region of one registered object and add it to the
    registry.  Returns the new SHADOW boxels (none when the switch is off,
    the class declares no cavity, the cavity holds no target class, or the
    status rule says the footprint was observed empty before)."""
    if not ENABLED or obj_bd is None or obj_bd.boxel_type != BoxelType.OBJECT:
        return []
    name = obj_bd.id
    cavity = cavity_of(env, name)
    if cavity is None:
        return []
    if not any(holds(cavity, e) for e in target_classes(env, target_names)):
        return []
    table_z = float(env.table_surface_height)
    if float(obj_bd.min_corner[2]) > table_z + 0.01:
        return []                      # not resting on the table (held, stacked)
    lo, hi = region_bounds(obj_bd, cavity, table_z)
    if np.any(hi - lo <= 1e-3):
        return []
    if not first_observation and observed_before(registry, lo, hi):
        print(f"    [interior] {name}: the space it now covers lay in free "
              f"space, observed empty before it came to stand there; no "
              f"region under it (D6 status rule)")
        ledger_event('interior_region', obj=name, cast=False,
                     reason='observed_before_placement')
        return []
    region = BoxelData(boxel_type=BoxelType.SHADOW, min_corner=lo, max_corner=hi,
                       created_by_object=name)
    parts = _carve(env, region, registry, name)
    # A carve's remainder under 1 cm wide is the noise of two estimates of
    # one place (a body registered again where its first region still
    # lies), not a hiding place of its own.
    slivers = [q for q in parts
               if float(min(q.max_corner[0] - q.min_corner[0],
                            q.max_corner[1] - q.min_corner[1])) < _MIN_PART_SIDE]
    if slivers:
        parts = [q for q in parts if not any(q is s for s in slivers)]
        print(f"    [interior] {name}: {len(slivers)} carve remainder(s) under "
              f"{_MIN_PART_SIDE * 100:.0f} cm wide not kept as regions")
    new = []
    for idx, part in enumerate(parts):
        base = ID_PREFIX + name + (f"__{idx:02d}" if len(parts) > 1 else "")
        pid, k = base, 0
        while registry.get_boxel(pid) is not None:
            k += 1
            pid = f"{base}__r{k}"
        part.id = pid
        part.region_kind = KIND
        part.created_by_boxel_id = name
        part.created_by_object = name
        part.on_surface = "table"
        part.surface_z = table_z
        registry.add_boxel(part)
        obj_bd.interior_boxel_ids.append(pid)
        new.append(part)
        ext = part.max_corner - part.min_corner
        print(f"    [interior] {pid}: the space under {name} "
              f"({ext[0] * 100:.1f} x {ext[1] * 100:.1f} x {ext[2] * 100:.1f} cm) "
              f"is a hiding region, unknown; searched by moving {name} away")
        ledger_event('interior_region', obj=name, cast=True, region=pid,
                     min_corner=part.min_corner, max_corner=part.max_corner,
                     first_observation=bool(first_observation))
    return new


def bookkeep(new: List[BoxelData], *, shadows, shadow_occluder_map,
             boxel_centers, belief, viz=None) -> List[str]:
    """Enter freshly cast regions into the loop's lists, as the lateral
    fragments of a newly registered object are."""
    ids = []
    for part in new:
        owner = part.created_by_boxel_id
        shadows.append(part.id)
        shadow_occluder_map[part.id] = [owner]
        boxel_centers[part.id] = part.center
        if belief is not None:
            belief.add_shadow(part.id)
        if viz is not None:
            viz.draw_boxel_data(part)
        ids.append(part.id)
    return ids


def _inside_box(point, box: BoxelData) -> bool:
    """Inside the box's footprint and not above its top, up to _INSIDE_TOL."""
    pt = np.asarray(point, dtype=float)
    lo = np.asarray(box.min_corner, dtype=float)
    hi = np.asarray(box.max_corner, dtype=float)
    return bool(np.all(pt[:2] >= lo[:2] - _INSIDE_TOL)
                and np.all(pt[:2] <= hi[:2] + _INSIDE_TOL)
                and pt[2] <= hi[2] + _INSIDE_TOL)


def _take_out_covered_targets(env, registry, target_names: Iterable[str]
                              ) -> List[Tuple[str, str, np.ndarray]]:
    """BF#65 (d) at the first observation: a named target whose box centre
    lies inside the box of an object that will own an interior region (its
    class's cavity holds the target's class) leaves the registry again, with
    the fragments it cast.  Before the regions are cast: a target's box is
    no solid that carves the region it lies in.  Returns (target, cover id,
    the target's believed centre) per target taken out."""
    table_z = float(env.table_surface_height)
    out = []
    for t in [t for t in (target_names or []) if t]:
        tbd = registry.get_boxel(t)
        info = env.objects.get(t)
        if tbd is None or tbd.boxel_type != BoxelType.OBJECT or info is None:
            continue
        centre = np.asarray(tbd.center, dtype=float)
        for cover in sorted(registry.get_object_boxels(), key=lambda b: b.id):
            cavity = cavity_of(env, cover.id)
            if (cover.id == t or cavity is None
                    or float(cover.min_corner[2]) > table_z + 0.01
                    or not holds(cavity, info.size)
                    or not _inside_box(centre, cover)):
                continue
            for sid in list(tbd.shadow_boxel_ids):
                registry.boxels.pop(sid, None)   # cast a moment ago, never in the belief
            registry.boxels.pop(t, None)
            setattr(registry, "_dirty", True)    # free space was carved around it
            out.append((t, cover.id, centre))
            break
    return out


def cast_first_observation(env, registry, target_names: Iterable[str]) -> List[str]:
    """The interior regions of every object the first observation
    registered (main(), Phase 3, before the shadow list is taken), after
    BF#65 (d)'s step: a target that observation shows inside a cover's box
    is taken out of the registry and recorded as seen under that cover."""
    if not ENABLED:
        return []
    covered = _take_out_covered_targets(env, registry, target_names)
    ids = []
    for obj_bd in sorted(registry.get_object_boxels(), key=lambda b: b.id):
        ids.extend(p.id for p in cast_for(env, registry, obj_bd, target_names,
                                          first_observation=True))
    for t, cover_id, centre in covered:
        cover = registry.get_boxel(cover_id)
        regions = [registry.get_boxel(i) for i in cover.interior_boxel_ids]
        regions = [r for r in regions if r is not None]
        if not regions:
            print(f"    [interior] {t} was in view inside {cover_id}'s box, but "
                  f"{cover_id} got no interior region: {t} is left unregistered "
                  f"for a later observation")
            continue
        region = min(regions, key=lambda r: float(np.linalg.norm(
            np.asarray(r.center, dtype=float)[:2] - centre[:2])))
        note_seen_under(t, cover, region)
    return ids


# ----- seen under a cover (BF#65 (d)) --------------------------------------

def standing_cover(registry, point, exclude: Iterable[str] = ()
                   ) -> Optional[Tuple[BoxelData, BoxelData]]:
    """(cover, region) when ``point`` lies inside the box of an object that
    still stands over an interior region of its own, else None.  A cover in
    ``exclude`` (the held object) is not standing."""
    if not ENABLED:
        return None
    pt = np.asarray(point, dtype=float)
    skip = set(exclude or ())
    for region in registry.get_shadow_boxels():
        if not is_interior(region):
            continue
        cover = registry.get_boxel(region.created_by_boxel_id or '')
        if cover is None or cover.id in skip:
            continue
        rc = region.center
        cmin = np.asarray(cover.min_corner, dtype=float)
        cmax = np.asarray(cover.max_corner, dtype=float)
        if not (cmin[0] <= rc[0] <= cmax[0] and cmin[1] <= rc[1] <= cmax[1]):
            continue                   # the cover was moved off this region
        if _inside_box(pt, cover):
            return cover, region
    return None


def note_seen_under(target: str, cover: BoxelData, region: BoxelData,
                    pixel_count=None) -> None:
    if region.id in _no_plan_regions:
        return                         # released: every region is on offer
    first = _seen_under.get(target) != region.id
    _seen_under[target] = region.id
    if first:
        print(f"    [interior] {target} is in view"
              f"{'' if pixel_count is None else f' ({pixel_count} px)'} inside "
              f"{cover.id}'s box: it lies under that cover, where no look and "
              f"no grasp reaches it.  Not registered as an object; "
              f"{region.id} is where to look once {cover.id} is moved "
              f"(BF#65 (d))")
        ledger_event('seen_under', target=target, cover=cover.id,
                     region=region.id, pixels=pixel_count)


def seen_under(target: str) -> Optional[str]:
    return _seen_under.get(target)


def release(target_names: Iterable[str]) -> List[str]:
    """No plan was found while the planner was offered only the region a
    target was seen in (its look or its pick did not bind): the record
    ends, and none is made for that region again, so the next plan is
    offered every unknown region.  Returns the released region ids."""
    out = []
    for t in [t for t in (target_names or []) if t]:
        rid = _seen_under.pop(t, None)
        if rid is None:
            continue
        _no_plan_regions.add(rid)
        out.append(rid)
        print(f"  [interior] no plan through {rid} alone: the record '{t} seen "
              f"under a cover' ends; every unknown region is on offer again "
              f"(BF#65 (d))")
        ledger_event('seen_under_released', target=t, region=rid,
                     reason='no_plan')
    return out


def withheld(registry, belief, target_names: Iterable[str]) -> List[str]:
    """The unknown regions the planner is NOT offered this plan: while a
    target is recorded as seen under a cover, every unknown region but that
    one.  A record ends when the target has its own boxel or the region left
    the belief (looked at; the target was not there after all)."""
    if not ENABLED or not _seen_under:
        return []
    keep = set()
    for t in [t for t in (target_names or []) if t]:
        rid = _seen_under.get(t)
        if rid is None:
            continue
        if (registry.get_boxel(t) is not None
                or registry.get_boxel(rid) is None
                or belief.shadow_status.get(rid) != 'unknown'):
            print(f"  [interior] the record '{t} seen under a cover' ends "
                  f"({rid} "
                  f"{'looked at' if registry.get_boxel(rid) is None else 'settled'})")
            _seen_under.pop(t, None)
            continue
        keep.add(rid)
    if not keep:
        return []
    return [s for s in belief.get_unknown_shadows() if s not in keep]


# ----- the truthful record of a look into an interior region -----------------

def holds_detection(region: BoxelData, det) -> bool:
    """Does the detection's box centre lie inside the interior region (the
    cover away, the render showing the target where the cover stood)?  The
    sense grid's lowest slice sits 2 cm above the table, above a target
    shorter than that, so the grid alone would call the region empty."""
    if det is None or not is_interior(region):
        return False
    c = np.asarray(det.est_center, dtype=float)
    lo = np.asarray(region.min_corner, dtype=float) - _INSIDE_TOL
    hi = np.asarray(region.max_corner, dtype=float) + _INSIDE_TOL
    return bool(np.all(c >= lo) and np.all(c <= hi))
