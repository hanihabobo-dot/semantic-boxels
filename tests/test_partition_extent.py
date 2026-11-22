"""C-09: auto_cell follows the targets' declared class size.

main() sets auto_cell (the uniform cell and, without --min-boxel-size, the
semantic leaf floor) from partition_extent(env.objects,
scene_config.target_extent) + 0.01 m, before the first camera pass.  A
hidden target's own size is not known to the agent, so every target
counts at the bound its scene declares; an occluder, in view, counts at
its own size.  A scene without occluders declares no bound (every
target is in view), and the bridge's env passes no scene_config and
keeps its task_spec class sizes.

Pure tests: the object tables are built from each scene's SceneConfig the
way BoxelTestEnv registers its bodies, with no world and no episode.
"""
import functools
import inspect

import numpy as np
import pytest

import test_full_pipeline as tfp
from boxel_env import (default_scene, mixed_shapes_scene, random_pairs_scene,
                       scalability_scene, stack_scene)
from boxel_types import ObjectInfo


def _info(name, size, occluder, tray=False):
    return ObjectInfo(object_id=0, name=name, position=None,
                      orientation=None, size=np.asarray(size, dtype=float),
                      is_visible=occluder, is_occluder=occluder,
                      is_tray=tray)


def _table(cfg):
    """The object table BoxelTestEnv registers for cfg: plane, table,
    robot, the tray when enabled, then occluders and targets at
    spec.full_extents (boxel_env.py _setup_scene, _create_occluders,
    _create_targets)."""
    objects = {'plane': _info('plane', [10, 10, 0.1], False),
               'table': _info('table', [1.0, 1.0, 0.8], False),
               'robot': _info('robot', [0.5, 0.5, 0.8], False)}
    if cfg.enable_tray:
        objects['tray'] = _info('tray', [0.4, 0.4, 0.05], False, tray=True)
    for i, spec in enumerate(cfg.occluders):
        name = spec.name or f"occluder_{i + 1}"
        objects[name] = _info(name, spec.full_extents, True)
    for i, spec in enumerate(cfg.targets):
        name = spec.name or f"target_{i + 1}"
        objects[name] = _info(name, spec.full_extents, False)
    return objects


def _before(objects):
    """main()'s loop before C-09: every body at its own size."""
    max_extent = 0.0
    for name, info in objects.items():
        if name in ("plane", "table", "robot"):
            continue
        if getattr(info, "is_tray", False):
            continue
        if info.size is None:
            continue
        max_extent = max(max_extent, float(np.max(info.size)))
    return max_extent


def _tallest_occluder(objects):
    return max(float(np.max(info.size)) for info in objects.values()
               if info.is_occluder)


def _scene():
    return scalability_scene(n_occluders=2, n_targets=2, n_hidden=1, seed=0)


def test_hidden_target_larger_than_every_occluder_does_not_move_it():
    cfg = _scene()
    objects = _table(cfg)
    tallest = _tallest_occluder(objects)
    for size in (tallest + 0.01, 0.3, 1.0):
        objects['hidden_big'] = _info('hidden_big', [0.05, 0.05, size],
                                      False)
        assert _before(objects) == size
        assert tfp.partition_extent(objects, cfg.target_extent) == tallest


def test_it_follows_the_declared_target_size():
    objects = _table(_scene())
    tallest = _tallest_occluder(objects)
    for declared in (tallest + 0.01, 0.3):
        assert tfp.partition_extent(objects, declared) == declared
    assert tfp.partition_extent(objects, 0.001) == tallest


def test_without_a_declared_size_each_body_counts_its_own():
    """The bridge's env (main() gets no scene_config; its sizes are
    task_spec's class sizes) and custom SceneConfigs."""
    objects = _table(_scene())
    objects['hidden_big'] = _info('hidden_big', [0.05, 0.05, 0.3], False)
    assert tfp.partition_extent(objects) == _before(objects) == 0.3
    assert tfp.partition_extent(objects, None) == 0.3


def _built_in():
    yield 'default', default_scene
    for seed in (0, 42):
        yield f'mixed-s{seed}', functools.partial(mixed_shapes_scene, seed)
    for n in (1, 3, 5):
        for half in (0.02, 0.025, 0.03):
            yield (f'stack-n{n}-h{half}',
                   functools.partial(stack_scene, n, n, half))
    for occ in range(0, 7):
        for tgt in (1, 4):
            for seed in range(5):
                yield (f'scalability-o{occ}-t{tgt}-s{seed}',
                       functools.partial(scalability_scene, occ, tgt,
                                         min(occ, tgt), seed))
    for occ in (1, 2, 3, 4):
        for extra in (0, 1):
            for seed in range(5):
                yield (f'random-pairs-o{occ}-e{extra}-s{seed}',
                       functools.partial(random_pairs_scene, occ, extra,
                                         seed))


BUILT_IN = list(_built_in())


@pytest.mark.parametrize('tray', [False, True], ids=['no-tray', 'tray'])
@pytest.mark.parametrize('make', [m for _, m in BUILT_IN],
                         ids=[n for n, _ in BUILT_IN])
def test_built_in_scenes_keep_their_value(make, tray):
    cfg = make()
    cfg.enable_tray = tray
    objects = _table(cfg)
    if cfg.target_extent is not None:
        assert cfg.target_extent >= max(float(np.max(spec.full_extents))
                                        for spec in cfg.targets)
    assert tfp.partition_extent(objects, cfg.target_extent) == \
        _before(objects)


@pytest.mark.parametrize('make, extent', [
    (default_scene, 0.075),
    (functools.partial(mixed_shapes_scene, 42), 0.15),
    (stack_scene, 0.05),
], ids=['default', 'mixed', 'stack'])
def test_fixed_scenes_values(make, extent):
    cfg = make()
    assert tfp.partition_extent(_table(cfg), cfg.target_extent) == \
        pytest.approx(extent)


def test_scenes_without_occluders_declare_no_bound():
    """Nothing hides a target there: each counts its own, seen size."""
    assert stack_scene().target_extent is None
    assert scalability_scene(n_occluders=0, n_targets=4).target_extent is None
    assert scalability_scene(n_occluders=1, n_targets=4).target_extent == 0.04


def test_main_reads_the_declared_size():
    # The statement stands in build_world, cut out of main(); scene_config is
    # a field of the episode state st.
    src = inspect.getsource(tfp.build_world)
    assert ("max_extent = partition_extent(\n"
            "        env.objects, getattr(st.opts.scene_config, 'target_extent', "
            "None))") in src
    # main() and every function cut out of it (its first parameter is st) are
    # without a body's own size, as main() was.
    stages = [f for f in vars(tfp).values() if inspect.isfunction(f)
              and next(iter(inspect.signature(f).parameters), None) == 'st']
    assert tfp.build_world in stages
    for fn in [tfp.main] + stages:
        assert 'np.max(info.size)' not in inspect.getsource(fn), fn.__name__
