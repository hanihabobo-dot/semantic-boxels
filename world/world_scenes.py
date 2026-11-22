"""Scene configurations: what a scene holds, and the five preset scenes.

A scene is a ``SceneConfig``: its occluders and targets as ``ObjectSpec``
entries (shape, size, colour, mass, friction, name), their positions on
the table or the seed that draws them, and the switches of the placement.
The presets are ``default_scene``, ``mixed_shapes_scene``, ``stack_scene``,
``scalability_scene`` and ``random_pairs_scene``.

``boxel_env`` imports every name of this module and keeps it importable
from there.  This module imports no pybullet: it describes a scene, the
environment spawns it.
"""

import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Scene configuration types
# ---------------------------------------------------------------------------

class ObjectShape(Enum):
    """Primitive shapes available in PyBullet."""
    BOX = "box"
    CYLINDER = "cylinder"
    SPHERE = "sphere"


# ---------------------------------------------------------------------------
# Named colour palette for scene objects
# ---------------------------------------------------------------------------
# Seven visually distinct RGBA colours used by the scene-preset functions
# to give every manipulable object a unique appearance and a human-readable
# name (e.g. "red_object", "blue_object").  Each entry is [R, G, B, 1.0].

OBJECT_COLORS: Dict[str, List[float]] = {
    "red":    [0.85, 0.20, 0.20, 1.0],
    "green":  [0.15, 0.75, 0.20, 1.0],
    "orange": [0.90, 0.55, 0.10, 1.0],
    "blue":   [0.20, 0.35, 0.90, 1.0],
    "cyan":   [0.15, 0.80, 0.80, 1.0],
    "purple": [0.70, 0.20, 0.80, 1.0],
    "yellow": [0.90, 0.85, 0.10, 1.0],
}


@dataclass
class ObjectSpec:
    """
    Specification for a single scene object.

    Shapes and their ``size`` semantics:
      - BOX:      [half_x, half_y, half_z]  (half-extents)
      - CYLINDER: [radius, half_height]
      - SPHERE:   [radius]

    All dimensions in metres.
    """
    shape: ObjectShape
    size: List[float]
    color: List[float] = field(default_factory=lambda: [0.5, 0.5, 0.5, 1.0])
    mass: float = 0.5
    lateral_friction: float = 1.0
    name: Optional[str] = None  # color-based name; overrides auto-generated occluder_N / target_N

    @property
    def aabb_half_extents(self) -> np.ndarray:
        """Axis-aligned half-extents used for shadow/boxel computation."""
        if self.shape == ObjectShape.BOX:
            return np.array(self.size)
        elif self.shape == ObjectShape.CYLINDER:
            r, hz = self.size
            return np.array([r, r, hz])
        else:
            r = self.size[0]
            return np.array([r, r, r])

    @property
    def full_extents(self) -> np.ndarray:
        """Full dimensions (2 * half-extents)."""
        return self.aabb_half_extents * 2.0

    @property
    def max_horizontal_width(self) -> float:
        """Largest horizontal dimension — must be < 0.08 m for Panda grasping."""
        he = self.aabb_half_extents
        return float(max(he[0], he[1])) * 2.0


@dataclass
class SceneConfig:
    """
    Parameterised scene layout.

    Holds lists of ``ObjectSpec`` for occluders and targets plus their
    world positions.  When ``positions`` is ``None``, objects are placed
    randomly (using ``seed`` for reproducibility).

    Attributes:
        occluders: Specifications for occluder objects.
        targets: Specifications for target objects.
        occluder_positions: XY positions on the table (Z is derived from
            table height + object half-height).  ``None`` → random.
        target_positions: Same, for targets.
        seed: RNG seed for random placement.  ``None`` → non-deterministic.
        constrain_to_reach: When True, random XY sampling is restricted
            to the intersection of (a) a safe on-table window and (b)
            a disk around the robot base.  Used by stack_scene where
            every cube must be both pickable and a viable stack target
            (audit #30).
        n_hidden_targets: When > 0, the first N targets (index-order)
            are placed with XY biased to sit inside occluder footprints
            so they fail the camera's 8-corner visibility check
            (audit #29).  Requires at least one occluder.  The retry
            layer in test_full_pipeline.main() verifies the guarantee
            after spawn via oracle_detect_objects() and nudges the seed
            if it is not met.
    """
    occluders: List[ObjectSpec]
    targets: List[ObjectSpec]
    occluder_positions: Optional[List[List[float]]] = None
    target_positions: Optional[List[List[float]]] = None
    seed: Optional[int] = None
    constrain_to_reach: bool = False
    n_hidden_targets: int = 0
    # audit #49 — when True, spawn a fixed-base tray as a non-pickable
    # support surface (see BoxelTestEnv._create_tray).  Default off so
    # existing scenes/runs are unaffected.  The tray-stack goal mode
    # (audit #49 commit 3) auto-enables it.
    enable_tray: bool = False
    # C-09: the declared upper bound (m) on a target's largest full
    # extent, what the agent may know of a target's size before it sees
    # the target.  main() counts every target at this size when it sets
    # auto_cell.  None: not declared, each target counts its own size
    # (stack and other scenes without occluders: every target in view).
    target_extent: Optional[float] = None


# ---------------------------------------------------------------------------
# Preset scenes
# ---------------------------------------------------------------------------

def default_scene() -> SceneConfig:
    """
    Original hardcoded scene (3 occluders, 4 targets, all boxes).

    Preserved for backward compatibility and regression testing.
    Occluders are 0.06 m wide × 0.075 m tall blocks (#P1 friction
    grasp: the earlier 0.075 m cubes left only 2.5 mm of descent
    clearance per finger at the Panda's 0.08 m max opening — too
    tight without the removed constraint weld; height is kept at
    0.075 m so the cast shadows match the historical scene).  All
    positions within 0.65 m of robot base (fix #17: shifted -0.4 m
    in X, sizes halved from original).
    """
    return SceneConfig(
        occluders=[
            ObjectSpec(ObjectShape.BOX, [0.030, 0.030, 0.0375],
                       color=OBJECT_COLORS["red"],    mass=0.5, name="red_object"),
            ObjectSpec(ObjectShape.BOX, [0.030, 0.030, 0.0375],
                       color=OBJECT_COLORS["green"],  mass=0.5, name="green_object"),
            ObjectSpec(ObjectShape.BOX, [0.030, 0.030, 0.0375],
                       color=OBJECT_COLORS["orange"], mass=0.5, name="orange_object"),
        ],
        targets=[
            ObjectSpec(ObjectShape.BOX, [0.02, 0.02, 0.02],
                       color=OBJECT_COLORS["blue"],   mass=0.1, name="blue_object"),
            ObjectSpec(ObjectShape.BOX, [0.02, 0.02, 0.02],
                       color=OBJECT_COLORS["cyan"],   mass=0.1, name="cyan_object"),
            ObjectSpec(ObjectShape.BOX, [0.02, 0.02, 0.02],
                       color=OBJECT_COLORS["purple"], mass=0.1, name="purple_object"),
            ObjectSpec(ObjectShape.BOX, [0.02, 0.02, 0.02],
                       color=OBJECT_COLORS["yellow"], mass=0.1, name="yellow_object"),
        ],
        occluder_positions=[[0.1, 0.2], [0.2, -0.1], [0.0, -0.2]],
        target_positions=[[0.1, 0.4], [0.2, 0.1], [0.0, -0.1], [0.3, -0.2]],
        target_extent=0.04,  # C-09: the 0.04 m target cubes above
    )


def mixed_shapes_scene(seed: int = 42) -> SceneConfig:
    """
    Scene with diverse shapes — cylinders, boxes, and spheres.

    All objects fit the Panda gripper (max horizontal width < 0.08 m).
    Occluders are tall enough (0.12–0.15 m) to cast shadows from the
    overhead camera that fully hide targets (0.04–0.06 m).
    """
    return SceneConfig(
        occluders=[
            ObjectSpec(ObjectShape.CYLINDER, [0.03, 0.075],
                       color=OBJECT_COLORS["red"],    mass=0.5, name="red_object"),
            ObjectSpec(ObjectShape.BOX, [0.03, 0.03, 0.075],
                       color=OBJECT_COLORS["orange"], mass=0.5, name="orange_object"),
            ObjectSpec(ObjectShape.CYLINDER, [0.035, 0.06],
                       color=OBJECT_COLORS["purple"], mass=0.5, name="purple_object"),
        ],
        targets=[
            ObjectSpec(ObjectShape.BOX, [0.025, 0.025, 0.025],
                       color=OBJECT_COLORS["blue"],   mass=0.1, name="blue_object"),
            ObjectSpec(ObjectShape.CYLINDER, [0.02, 0.03],
                       color=OBJECT_COLORS["cyan"],   mass=0.1, name="cyan_object"),
            ObjectSpec(ObjectShape.SPHERE, [0.025],
                       color=OBJECT_COLORS["green"],  mass=0.1, name="green_object"),
            ObjectSpec(ObjectShape.BOX, [0.02, 0.02, 0.03],
                       color=OBJECT_COLORS["yellow"], mass=0.1, name="yellow_object"),
        ],
        occluder_positions=[[0.5, 0.2], [0.6, -0.1], [0.4, -0.2]],
        target_positions=[[0.5, 0.4], [0.6, 0.1], [0.4, -0.1], [0.7, -0.2]],
        seed=seed,
        target_extent=0.06,  # C-09: the tallest target specs above (0.06 m)
    )


def stack_scene(n_objects: int = 3, seed: int = 0,
                cube_half_extent: float = 0.025) -> SceneConfig:
    """
    Scene for ``--goal stack`` (audit #30): ``n_objects`` identical cubes
    spawned at random reach-constrained positions on the table.

    Identical cubes guarantee flat-on-flat contact during stacking, so
    ``execute_stack`` can compute the release height from a single
    half-extent without per-pair geometry checks.  Every cube is a
    candidate to pick AND a candidate stack support — no occluders.

    Cubes are stored in the ``targets`` list (registered with
    ``is_visible=False``) only because that field has been historically
    used for "things the planner manipulates"; visibility is recomputed
    by ``oracle_detect_objects`` on the first camera pass anyway.

    Args:
        n_objects: Number of cubes to spawn.  Must be >= stack height.
        seed: RNG seed for reproducible XY positions.
        cube_half_extent: Half-side of each cube in metres.  0.025 m
            (5 cm cube) fits the Panda gripper and stacks reliably.
    """
    color_keys = list(OBJECT_COLORS.keys())

    targets = []
    for i in range(n_objects):
        ck = color_keys[i % len(color_keys)]
        suffix = "" if i < len(color_keys) else f"_{i // len(color_keys) + 1}"
        targets.append(ObjectSpec(
            ObjectShape.BOX,
            [cube_half_extent, cube_half_extent, cube_half_extent],
            color=OBJECT_COLORS[ck],
            mass=0.2,
            name=f"{ck}_object{suffix}",
        ))

    return SceneConfig(
        occluders=[],
        targets=targets,
        seed=seed,
        constrain_to_reach=True,
    )


def scalability_scene(n_occluders: int = 3, n_targets: int = 4,
                      n_hidden: int = 0,
                      seed: int = 0) -> SceneConfig:
    """
    Randomly generated scene for scalability evaluation.

    Occluder and target shapes are drawn from a pool; positions are
    randomised within the table bounds.  Use different ``seed`` values
    to produce distinct instances for batch evaluation.

    When ``n_hidden > 0``, the first ``n_hidden`` targets are placed
    with XY biased toward occluder footprints so they fail the
    camera's visibility check (audit #29).  The retry layer in
    ``test_full_pipeline.main()`` verifies the guarantee post-spawn
    and re-seeds if it is not met.  ``n_hidden`` is capped at
    ``n_targets``; callers must ensure ``n_occluders >= 1`` when
    requesting hidden targets.
    """
    n_hidden = max(0, min(int(n_hidden), int(n_targets)))
    if n_hidden > 0 and n_occluders < 1:
        raise ValueError(
            "scalability_scene: n_hidden > 0 requires n_occluders >= 1"
        )
    rng = np.random.RandomState(seed)

    # Boxes only — tall narrow occluders, small cube targets.  No
    # cylinders, no spheres (user pref).  Occluders became tall narrow
    # blocks in the #P1 friction-grasp work (deferred #77): the old
    # occluder cubes drew half-extents up to 0.045 (0.09 m full width),
    # over the Panda's 0.08 m max finger opening — grippable only by
    # the removed constraint weld.  Now XY half-extents stay ≤ 0.030
    # (0.06 m wide, ≥ 1 cm descent clearance per finger) and the lost
    # occlusion volume is recovered in height (0.10–0.15 m tall, which
    # casts LONGER shadows from the fixed overhead camera).  Target
    # halves stay below occluder halves so the lateral jitter window
    # in ``_hidden_xy_positions`` (≈ occ_half − target_half) stays
    # positive and multiple hidden targets can sit behind the same
    # occluder; the raycast verifier backstops the guarantee either
    # way (pre-flight fails loud; seed retry removed 2026-08-23).
    occluders = []
    for _ in range(n_occluders):
        xy_half = rng.uniform(0.025, 0.030)
        z_half = rng.uniform(0.050, 0.075)
        occluders.append(
            ObjectSpec(ObjectShape.BOX, [xy_half, xy_half, z_half],
                       mass=0.5)
        )
    target_half_max = 0.020  # C-09: target_extent declares twice this
    targets = [
        ObjectSpec(ObjectShape.BOX,
                   [rng.uniform(0.015, target_half_max)] * 3,
                   mass=0.1)
        for _ in range(n_targets)
    ]

    # Assign palette colours and names in index order.
    # Sizes/shapes above are unchanged; only color and name are set here.
    # Cycle through the 7-colour palette; append "_2", "_3"... on repeats.
    color_keys = list(OBJECT_COLORS.keys())
    used_names: Dict[str, int] = {}
    for i, spec in enumerate(occluders):
        ck = color_keys[i % len(color_keys)]
        base = f"{ck}_object"
        count = used_names.get(base, 0) + 1
        used_names[base] = count
        spec.color = OBJECT_COLORS[ck]
        spec.name = base if count == 1 else f"{base}_{count}"
    for j, spec in enumerate(targets):
        ck = color_keys[(n_occluders + j) % len(color_keys)]
        base = f"{ck}_object"
        count = used_names.get(base, 0) + 1
        used_names[base] = count
        spec.color = OBJECT_COLORS[ck]
        spec.name = base if count == 1 else f"{base}_{count}"

    # #P3(a) (2026-09-19): every eval scene spawns inside the Panda's
    # reach (TAMPURA's env_generator pattern).  This scene never set the
    # flag, so the eval sweep's scalability cells sampled the wide
    # unconstrained window (x [-0.20, 0.60], y [-0.50, 0.50]) and the
    # thesis sentence "random reachable positions" was not guaranteed
    # for them.  Changes every scalability seed's layout: the canonical
    # re-sweep (CB#113) is planned after this lands.
    return SceneConfig(
        occluders=occluders,
        targets=targets,
        seed=seed,
        n_hidden_targets=n_hidden,
        constrain_to_reach=True,
        # C-09: without occluders every target is in view, none declared.
        target_extent=2 * target_half_max if n_occluders else None,
    )


def random_pairs_scene(n_occluders: int = 3,
                       extra_distractors: int = 0,
                       seed: int = 0) -> SceneConfig:
    """
    Scene with a fixed occluder count and a randomly-drawn hidden-target
    count (audit #68).

    ``n_occluders`` is set by the caller (default 3); the per-run hidden
    count is drawn uniformly from ``[1, n_occluders]`` using ``seed`` so
    the same seed always produces the same scene.  Each hidden target is
    placed behind one of the occluders via the standard scalability_scene
    + _hidden_xy_positions path (audit #29 raycast verification).
    ``extra_distractors`` adds visible (non-hidden) distractor targets on
    top of the K hidden ones; required >= 1 for ``--goal
    find-and-tray-stack`` (auto-bumped in run_logger).

    Vary ``seed`` per run for structurally distinct scenes; run_logger
    draws a fresh seed by default when --scene random-pairs is selected
    without an explicit --seed.
    """
    if n_occluders < 1:
        raise ValueError(
            f"random_pairs_scene: n_occluders must be >= 1 "
            f"(got {n_occluders})"
        )
    if extra_distractors < 0:
        raise ValueError(
            "random_pairs_scene: extra_distractors must be >= 0"
        )
    rng = np.random.RandomState(seed)
    n_hidden = int(rng.randint(1, n_occluders + 1))
    cfg = scalability_scene(
        n_occluders=n_occluders,
        n_targets=n_hidden + int(extra_distractors),
        n_hidden=n_hidden,
        seed=seed,
    )
    # audit #70 (reopened 2026-05-12) — without this, occluders +
    # visible targets sample in the wide _TABLE_PLACE_* window and
    # ~half the placements fall outside the Panda's 0.65 m reach
    # disk; pick IK then succeeds via slack-beyond-comfort-reach
    # and the grasp constraint hangs the cube mid-air on lift.
    # Forcing constrain_to_reach pins occluders and visible-target
    # spawns to _SAFE_TABLE_* ∩ reach disk (same pattern as
    # stack_scene).  Hidden targets are placed behind occluders by
    # _hidden_xy_positions, which is reach-disk-unaware; if a
    # hidden target lands outside reach despite its occluder being
    # inside, the post-spawn assert in _create_objects /
    # _create_targets (audit #70 hardening) will catch it and
    # raise — the pre-flight fails loud (seed retry removed 2026-08-23).
    cfg.constrain_to_reach = True
    return cfg
