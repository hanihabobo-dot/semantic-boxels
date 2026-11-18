"""make_render_fixture.py: the stored eye renders that pins 13 to 16 read
(group "world" of tools/readable/pin_outputs.py; readable migration Phase 0).

    python tests/readable/make_render_fixture.py [--out DIR]

Default DIR: tests/readable/_scratch/render_fixture (scratch until tag
refactor-checkpoint-2, where the stored copy is made by this script; R's
rule 1).  Run in WSL with /root/armO-venvA/bin/python, PYTHONHASHSEED=0,
under ``flock /root/sb_pipeline.lock``, headless (DIRECT clients only).

Renders (each the env's own eye render, ``env.detect_objects()``:
ER_TINY_RENDERER, 640 x 480, on the executing client 0):
  A   random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0) with the
      tray, after main's first observation (_first_registry of
      pin_outputs.py: the effective cell, 50 settle steps, the registry,
      switches off).  The registry is stored as A_boxel_data.json.
  C   the same scene with the arm posed by solve_ik in front of the first
      shadow fragment (fragment centre + (0, -0.10, 0.04), z at least the
      table + 0.06), resetJointState on client 0, no step; the arm joints are
      restored after the render.
  A2  the same scene with every occluder moved out of view
      (resetBasePositionAndOrientation to [3, 3 + i, 0.5], no step).
  B2  stack_scene(n_objects=3, seed=0), main's 50 settle steps, then cube 2
      put on cube 1 (centre + 2 x 0.025 in z, upright) and 10 steps.
The moves are test-fixture constructions of a scene state, not patches of
pipeline logic.

Files per render: <name>_depth.npy (the raw [0, 1] depth buffer; float32
when that is lossless, see the meta), <name>_seg.npy (the seg mask in the
dtype the env produced), <name>.json (matrices, body map, ids); and
FIXTURE.json (the renders, the scenes, the sha256 of every file).  np.save
output is byte-stable, so two runs can be compared by FIXTURE.json.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools' / 'readable'))

import pin_outputs as po  # noqa: E402

DEFAULT_OUT = REPO / 'tests' / 'readable' / '_scratch' / 'render_fixture'
SCENES = {
    'A': 'random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0), enable_tray=True, after _first_registry',
    'C': 'scene A with the arm posed by solve_ik in front of the first shadow fragment',
    'A2': 'scene A with every occluder moved to [3, 3 + i, 0.5]',
    'B2': 'stack_scene(n_objects=3, seed=0), 50 settle steps, cube 2 put on cube 1, 10 steps',
}


def save_render(out, name, env, extra):
    import numpy as np
    dets, _rgb, buf, seg = env.detect_objects()
    view, proj = env._view_and_projection_matrices()
    f32 = buf.astype(np.float32)
    lossless = bool(np.array_equal(f32.astype(np.float64), buf))
    np.save(out / f'{name}_depth.npy', f32 if lossless else buf)
    np.save(out / f'{name}_seg.npy', seg)
    body_map = [[info.object_id, n] for n, info in env.objects.items() if n not in po.STATIC_NAMES]
    meta = {
        'name': name, 'scene': SCENES[name],
        'view': [float(v) for v in view], 'proj': [float(v) for v in proj],
        'body_id_to_name': body_map,
        'trays': [n for n, i in env.objects.items() if getattr(i, 'is_tray', False)],
        'objects': [[n, i.object_id] for n, i in env.objects.items()],
        'camera_position': [float(v) for v in env.camera_position],
        'camera_xy': [float(v) for v in env.camera_position[:2]],
        'support_z': float(env.table_surface_height),
        'near_plane': env.near_plane, 'far_plane': env.far_plane,
        'image': [env.image_width, env.image_height],
        'robot_id': env.objects['robot'].object_id, 'plane_id': env.objects['plane'].object_id,
        'table_id': env.objects['table'].object_id,
        'tray_ids': [i.object_id for i in env.objects.values() if getattr(i, 'is_tray', False)],
        'depth_dtype_from_env': str(buf.dtype), 'depth_stored_float32': lossless,
        'seg_dtype': str(seg.dtype),
        'detected_names': list(dets),
        **extra,
    }
    (out / f'{name}.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8', newline='\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    import numpy as np
    import pybullet as pb
    import robot_utils
    from boxel_data import BoxelType
    from boxel_env import random_pairs_scene, stack_scene
    po._set_switches(False)

    cfg = random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0)
    cfg.enable_tray = True
    env, _ = po._make_env(cfg)
    try:
        with po.captured():
            obs, registry, cell = po._first_registry(env)
        registry.save_to_json(str(out / 'A_boxel_data.json'))
        targets = po._targets_of(env)
        occluders = [b for b in registry.boxels.values() if b.boxel_type == BoxelType.OBJECT and b.is_occluder]
        ids = {
            'occluder_body_ids': [env.objects[b.object_name].object_id for b in occluders],
            'hidden_target_ids': [env.objects[t].object_id for t in targets if registry.get_boxel(t) is None],
            'visible_target_ids': [env.objects[t].object_id for t in targets if registry.get_boxel(t) is not None],
            'effective_cell': cell,
        }
        save_render(out, 'A', env, ids)
        rid = env.objects['robot'].object_id
        arm = robot_utils.robot_model().arm_joints
        saved = [pb.getJointState(rid, j, physicsClientId=env.client_id)[:2] for j in arm]
        frag = sorted((b for b in registry.boxels.values() if b.boxel_type == BoxelType.SHADOW),
                      key=lambda b: b.id)[0]
        target = np.asarray(frag.center, dtype=float) + np.array([0.0, -0.10, 0.04])
        target[2] = max(float(target[2]), float(env.table_surface_height) + 0.06)
        q = robot_utils.solve_ik(rid, target, None, env.client_id)
        if q is None:
            raise RuntimeError(f'no IK for the arm pose in front of {frag.id}')
        for j, v in zip(arm, q):
            pb.resetJointState(rid, j, float(v), physicsClientId=env.client_id)
        save_render(out, 'C', env, {**ids, 'arm_target': target.tolist(), 'arm_joints': [float(v) for v in q],
                                    'arm_in_front_of': frag.id})
        for j, (ang, vel) in zip(arm, saved):
            pb.resetJointState(rid, j, ang, targetVelocity=vel, physicsClientId=env.client_id)
        for i, b in enumerate(occluders):
            pb.resetBasePositionAndOrientation(env.objects[b.object_name].object_id, [3.0, 3.0 + i, 0.5],
                                               [0, 0, 0, 1], physicsClientId=env.client_id)
        save_render(out, 'A2', env, ids)
    finally:
        env.close()

    env, _ = po._make_env(stack_scene(n_objects=3, seed=0))
    try:
        for _ in range(50):
            env.step_simulation()
        env.update_object_positions()
        cubes = po._targets_of(env)
        lo, up = env.objects[cubes[0]].object_id, env.objects[cubes[1]].object_id
        p_lo = pb.getBasePositionAndOrientation(lo, physicsClientId=env.client_id)[0]
        pb.resetBasePositionAndOrientation(up, [p_lo[0], p_lo[1], p_lo[2] + 2 * 0.025], [0, 0, 0, 1],
                                           physicsClientId=env.client_id)
        for _ in range(10):
            env.step_simulation()
        env.update_object_positions()
        save_render(out, 'B2', env, {'stacked': [cubes[1], cubes[0]],
                                     'occluder_body_ids': [], 'hidden_target_ids': [],
                                     'visible_target_ids': [env.objects[c].object_id for c in cubes]})
    finally:
        env.close()

    names = ['A', 'C', 'A2', 'B2']
    files = {}
    for f in sorted(out.iterdir()):
        if f.is_file() and f.name != 'FIXTURE.json':
            files[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    fixture = {'renders': names, 'scenes': SCENES, 'registry_file': 'A_boxel_data.json', 'files': files,
               'python': sys.version.split()[0], 'pybullet_api': pb.getAPIVersion(),
               'pythonhashseed': os.environ.get('PYTHONHASHSEED')}
    (out / 'FIXTURE.json').write_text(json.dumps(fixture, indent=1) + '\n', encoding='utf-8', newline='\n')
    for name, digest in files.items():
        print(f'{digest}  {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
