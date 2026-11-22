"""Where a scene's occluders and targets are put on the table.

``WorldPlacement`` holds the three placement methods of the environment:
``_random_xy_positions`` (rejection sampling inside the placement window),
``_assert_xys_in_reach`` (the reach check after a spawn) and
``_hidden_xy_positions`` (positions behind occluders, out of the camera's
sight).  ``BoxelTestEnv`` in ``boxel_env`` inherits the class.
"""

import numpy as np
import pybullet as p
from typing import List, Tuple, Optional

from world.world_scenes import ObjectSpec


class WorldPlacement:
    """Mixin of ``BoxelTestEnv``: the placement methods, no state of its own.

    The methods read, through ``self``, the class constants
    ``_SAFE_TABLE_X_RANGE``, ``_SAFE_TABLE_Y_RANGE``,
    ``_TABLE_PLACE_X_RANGE``, ``_TABLE_PLACE_Y_RANGE``, ``_ROBOT_BASE_XY``
    and ``_PANDA_REACH_RADIUS`` (the class body of ``BoxelTestEnv`` in
    ``boxel_env.py``) and the instance attributes ``camera_position``,
    ``objects`` and ``table_surface_height``.  The class has no
    ``__init__``.
    """

    def _random_xy_positions(self, n: int, rng: np.random.RandomState,
                             margin: float = 0.15,
                             edge_margin: float = 0.10,
                             constrain_to_reach: bool = False,
                             reach_radius: Optional[float] = None,
                             reserved_xys: Optional[List[List[float]]] = None,
                             ) -> List[List[float]]:
        """
        Sample *n* non-overlapping XY positions inside the on-table
        placement window (``_TABLE_PLACE_*_RANGE``; or
        ``_SAFE_TABLE_*_RANGE`` plus a reach-disk filter when
        ``constrain_to_reach`` is True).

        Uses rejection sampling with a minimum centre-to-centre
        separation of ``margin`` metres between spawned objects.
        Raised 0.10 -> 0.15 (2026-08-21, user request): at 0.10 the
        <= 6 cm occluders regularly spawned inside each other's shadow
        corridors, producing heavy F3 overlap carves (body-in-shadow
        fragment slivers like the 4 mm shadow_of_red_object__02 cap on
        seed 0) and blockers standing in front of half the fragments;
        0.15 leaves >= 9 cm clear gap and makes scenes noticeably more
        spacious without exhausting the placement window.
        ``edge_margin`` (unchanged at 0.10) insets the window bounds so
        objects keep clear of the table edge — kept separate so the
        wider object spacing does not also shrink the usable window.

        When ``constrain_to_reach`` is True, samples must ALSO lie inside
        a disk of radius ``reach_radius`` around the robot base.  Used by
        scenes like ``stack`` where every object must be both pickable
        and a viable stack destination (audit #30).

        When ``reserved_xys`` is provided, samples must also stay at
        least ``margin`` away from those pre-existing positions.  Used
        by ``_create_targets`` to keep visible-target placements clear
        of occluders and pre-placed hidden targets (audit #29).
        """
        if constrain_to_reach:
            x_lo, x_hi = self._SAFE_TABLE_X_RANGE
            y_lo, y_hi = self._SAFE_TABLE_Y_RANGE
        else:
            x_lo, x_hi = self._TABLE_PLACE_X_RANGE
            y_lo, y_hi = self._TABLE_PLACE_Y_RANGE
        x_lo += edge_margin
        x_hi -= edge_margin
        y_lo += edge_margin
        y_hi -= edge_margin
        bx, by = self._ROBOT_BASE_XY
        r_max = (reach_radius if reach_radius is not None
                 else self._PANDA_REACH_RADIUS)
        reserved = list(reserved_xys) if reserved_xys else []
        positions = []
        # 400 rejection-sampling attempts per object — empirical budget
        # that succeeds for typical 2-8 object scenes within the safe
        # placement window.  Exhaustion is hard-raised below (no silent
        # fallback) so over-constrained configurations surface as
        # actionable errors.
        for _ in range(n * 400):
            if len(positions) >= n:
                break
            x = rng.uniform(x_lo, x_hi)
            y = rng.uniform(y_lo, y_hi)
            if constrain_to_reach and np.hypot(x - bx, y - by) > r_max:
                continue
            if any(np.hypot(x - px, y - py) < margin
                   for px, py in reserved):
                continue
            if all(np.hypot(x - px, y - py) >= margin
                   for px, py in positions):
                positions.append([x, y])
        if len(positions) < n:
            bounds_msg = (f"placement window x=({x_lo}, {x_hi}) "
                          f"y=({y_lo}, {y_hi})")
            if constrain_to_reach:
                bounds_msg += f" within reach={r_max}"
            raise RuntimeError(
                f"Could not place {n} objects with margin={margin} m in "
                f"{bounds_msg}"
            )
        return positions

    def _assert_xys_in_reach(self, xys, label: str) -> None:
        """audit #70 (reopened 2026-05-12) hardening.

        Raise RuntimeError if any (x, y) lies outside the Panda's
        _PANDA_REACH_RADIUS disk around _ROBOT_BASE_XY.  Callers gate
        this on cfg.constrain_to_reach so non-reach-bound scenes
        (default scalability matrix) are unaffected.

        Catches _hidden_xy_positions placements that escape the reach
        disk despite the parent occluder being inside it (the helper
        samples behind occluders without filtering), and defends any
        future caller-supplied cfg.{occluder,target}_positions that
        sidesteps _random_xy_positions' filter.  RuntimeError surfaces
        to the pre-flight in test_full_pipeline.main(), which fails loud
        (seed retry removed 2026-08-23; mirrors audit #29's
        hidden-target post-spawn check).
        """
        bx, by = self._ROBOT_BASE_XY
        r_max = self._PANDA_REACH_RADIUS
        for i, xy in enumerate(xys):
            d = float(np.hypot(float(xy[0]) - bx, float(xy[1]) - by))
            if d > r_max:
                raise RuntimeError(
                    f"audit #70: {label}[{i}] spawned at "
                    f"({float(xy[0]):.3f}, {float(xy[1]):.3f}) is "
                    f"{d:.3f} m from robot base — outside reach disk "
                    f"(r_max={r_max} m). Use a different --seed "
                    f"or widen --n-occluders."
                )

    def _hidden_xy_positions(
        self,
        target_specs: List[ObjectSpec],
        occluder_info: List[Tuple[Tuple[float, float], float]],
        rng: np.random.RandomState,
        hidden_margin: float = 0.10,
        reserved_xys: Optional[List[List[float]]] = None,
        constrain_to_reach: bool = False,
        reach_radius: Optional[float] = None,
    ) -> Optional[List[List[float]]]:
        """
        Sample XY positions that are GUARANTEED hidden from the camera
        (audit #29).

        For each target spec:
          1. Pick a random occluder; compute a shadow-axis unit vector
             pointing from the camera XY toward the occluder and
             continuing away.
          2. Sample a candidate XY slightly BEHIND the occluder along
             that axis (distance = target_half + occluder_half + buffer
             + small random radial + lateral jitter bounded by the
             occluder's own width).  This places the target in the
             occluder's shadow cone without physically overlapping it.
          3. Verify with PyBullet raycasts: 8 rays from camera to the 8
             shrunk AABB corners of the prospective target.  Accept
             only if every corner ray is intercepted by a non-background
             body (an occluder).  Same 8-corner criterion as
             ``oracle_detect_objects`` → the scene is self-consistent
             with the downstream visibility check.
          4. Physical-overlap margin against ``reserved_xys`` is
             computed per-occluder (occ_half + target_half + small
             buffer); the ``hidden_margin`` only applies to spacing
             between placed hidden targets, not to occluder clearance.

        Occluders are already spawned in PyBullet when this runs
        (``_create_occluders`` before ``_create_targets`` in
        ``_setup_scene``), so the raycast has live geometry to test
        against.

        Returns ``None`` if the per-slot 400-candidate budget is
        exhausted.  ``_create_targets`` then raises with an actionable
        error — no silent fallback, no retry loop.

        Args:
            target_specs: ObjectSpec for each target slot to hide
                (list length = N-hidden).  Needed to know each
                prospective AABB's half-extents.
            occluder_info: ``((x, y), horizontal_half_extent)`` tuples
                for every already-placed occluder.
            rng: Numpy RandomState for all sampling decisions.
            hidden_margin: Minimum XY separation between two hidden
                target centres, in metres.  Does NOT apply to
                occluders — those use physical-overlap margins only.
            reserved_xys: Pre-existing XY positions that the samples
                must stay clear of.  Must match ``occluder_info`` in
                order; entries beyond ``len(occluder_info)`` are
                treated as additional reserved points kept at the
                ``hidden_margin`` distance.
        """
        if not occluder_info or not target_specs:
            return None
        cam = [float(v) for v in self.camera_position]
        cam_x, cam_y = cam[0], cam[1]
        # Match _random_xy_positions: bound spawns to the actual table
        # mesh, not the wider voxelization workspace.  Otherwise a
        # candidate placed at x < ~-0.25 would tip off the table edge
        # when physics steps and the scene would silently lose objects.
        # audit #70 hardening (iii) — when constrain_to_reach, bound
        # candidates to _SAFE_TABLE_* (matches _random_xy_positions'
        # behaviour for visible-target placement) AND apply the
        # Panda reach-disk filter at sample time inside the candidate
        # loop below.  Without this the post-spawn _assert_xys_in_-
        # reach catches out-of-reach hidden targets and aborts (all
        # seeds are strictly pinned; seed retry removed).  Defended on
        # 2026-05-12 (later) repro: --seed 505998003 placed target[0]
        # at (0.225, 0.190), 3 mm beyond the reach disk, after the
        # original (i)+(ii) fix.
        if constrain_to_reach:
            x_lo, x_hi = self._SAFE_TABLE_X_RANGE
            y_lo, y_hi = self._SAFE_TABLE_Y_RANGE
        else:
            x_lo, x_hi = self._TABLE_PLACE_X_RANGE
            y_lo, y_hi = self._TABLE_PLACE_Y_RANGE
        x_lo += hidden_margin
        x_hi -= hidden_margin
        y_lo += hidden_margin
        y_hi -= hidden_margin
        bx, by = self._ROBOT_BASE_XY
        r_max = (reach_radius if reach_radius is not None
                 else self._PANDA_REACH_RADIUS)

        background_ids = set()
        for k in ("plane", "table", "robot"):
            if k in self.objects:
                background_ids.add(self.objects[k].object_id)

        # Shrink corners inward by EPS so rayTest does not touch the
        # AABB surface exactly (PyBullet returns ambiguous fractions
        # at grazing / coincident surfaces).
        EPS = 1e-3
        # Physical-overlap buffer between target and occluder bodies.
        OVERLAP_BUFFER = 0.005

        # Reserved entries BEYOND the known occluder list (hidden
        # targets generated earlier in the same call, other reserved
        # points the caller passed).  Those use hidden_margin.
        non_occluder_reserved: List[List[float]] = []
        if reserved_xys:
            non_occluder_reserved = [
                list(xy) for xy in reserved_xys[len(occluder_info):]
            ]

        positions: List[List[float]] = []
        for spec in target_specs:
            he = spec.aabb_half_extents
            hx, hy, hz = float(he[0]), float(he[1]), float(he[2])
            target_half = max(hx, hy)
            cz = self.table_surface_height + hz
            placed = False
            # 800 candidate attempts per hidden target — bumped from
            # 400 on 2026-05-12 (later) when audit #70 hardening (iii)
            # added the reach-disk filter inside the candidate loop.
            # The added filter rejects ~10-20% more candidates near the
            # back of the reach disk; the per-attempt success rate goes
            # down accordingly, so the budget doubles to keep the
            # exhaustion-rate-per-seed roughly constant for eval sweeps.
            # Bumped 800 -> 4000 on 2026-05-15 for audit #77: the
            # n_occluders=2 + n_hidden=2 and n_occluders=3 + n_hidden=3
            # corners of random_pairs_scene have the tightest feasibility
            # window (small placer disk behind small occluders intersected
            # with reach disk, table window, and 0.10 m spacing).
            # Empirical pass rate on the audit-77 600-candidate corpus
            # build (commit 1a4ca47): 33.7% — only a marginal gain over
            # 800 (~30%).  The remaining rejections are structural for
            # those seeds (some occluder layouts leave no feasible
            # shadow region behind ANY occluder under the reach +
            # table + spacing constraints), not budget-bound — further
            # bumps offer diminishing returns.  4000 is the cheapest
            # value that empirically helps; geometric tests are
            # ~25 us/iter so worst-case wall-clock per failing seed is
            # ~100 ms.
            # On exhaustion we return None and _create_targets raises
            # 'Could not place ...' — the test_full_pipeline.main()
            # pre-flight fails loud on it (seed retry removed
            # 2026-08-23; audit #68's re-roll is history).
            for _ in range(4000):
                idx = int(rng.randint(len(occluder_info)))
                (ox, oy), occ_half = occluder_info[idx]
                dx = ox - cam_x
                dy = oy - cam_y
                norm = float(np.hypot(dx, dy))
                if norm < 1e-6:
                    continue
                ux = dx / norm
                uy = dy / norm
                # Perpendicular for lateral jitter within the occluder
                # silhouette width.
                px_u = -uy
                py_u = ux
                # Distance BEHIND the occluder center: at least enough
                # to clear physical overlap; add a small random bump so
                # multiple hidden targets don't stack on one line.
                base_d = occ_half + target_half + OVERLAP_BUFFER
                d = base_d + float(rng.uniform(0.0, max(occ_half, 1e-3)))
                lat_range = max(occ_half - target_half - OVERLAP_BUFFER,
                                0.0)
                lat = float(rng.uniform(-lat_range, lat_range))
                tx = ox + ux * d + px_u * lat
                ty = oy + uy * d + py_u * lat
                if not (x_lo <= tx <= x_hi and y_lo <= ty <= y_hi):
                    continue
                # audit #70 hardening (iii) — reach-disk filter at
                # sample time.  The post-spawn _assert_xys_in_reach
                # remains as a safety net for caller-supplied
                # cfg.target_positions that bypass this helper.
                if constrain_to_reach and np.hypot(tx - bx, ty - by) > r_max:
                    continue
                # Physical-overlap check against EVERY occluder (not
                # just the one we biased toward — the candidate may
                # collide with a neighbouring occluder).
                too_close_occ = False
                for (ox2, oy2), occ_half2 in occluder_info:
                    min_d = occ_half2 + target_half + OVERLAP_BUFFER
                    if np.hypot(tx - ox2, ty - oy2) < min_d:
                        too_close_occ = True
                        break
                if too_close_occ:
                    continue
                # Spacing margin against non-occluder reserved points
                # and already-accepted hidden targets.
                if any(np.hypot(tx - rx, ty - ry) < hidden_margin
                       for rx, ry in non_occluder_reserved):
                    continue
                if any(np.hypot(tx - px, ty - py) < hidden_margin
                       for px, py in positions):
                    continue
                corners = []
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        for sz in (-1, 1):
                            corners.append([
                                tx + sx * (hx - EPS),
                                ty + sy * (hy - EPS),
                                cz + sz * (hz - EPS),
                            ])
                # rayTestBatch numThreads=0: let Bullet pick max threads
                # (audit #69). Safe — no concurrent stepSimulation on this
                # client during target placement.
                hits = p.rayTestBatch([cam] * 8, corners, numThreads=0)
                all_occluded = True
                for h in hits:
                    hit_uid = h[0]
                    if hit_uid < 0 or hit_uid in background_ids:
                        all_occluded = False
                        break
                if not all_occluded:
                    continue
                positions.append([float(tx), float(ty)])
                placed = True
                break
            if not placed:
                return None
        return positions
