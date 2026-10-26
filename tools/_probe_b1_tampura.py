"""#P4 B1 part 1 probe, items (a) (b) (c) (d) (PAPER_AUDIT.txt #P4, P4.4).

Read-only measurements of TAMPURA's robot, meshes and physics.  Runs in
THEIR venv, in this process's own throwaway clients; never writes their
tree.  (a) and (b) read the URDF and the mesh files only.  (c) and (d) build
the three layouts through their own env.initialize(), exactly as
run_planner.py does, and then apply D9's set-up steps (1) to (4) and exactly
50 physics steps, the settle main() performs; those numbers feed disclosures
and feasibility checks, never a decision constant (G9).

  cd /root/tampura-work/tampura_environments
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/tampura-work/tampura:. \\
    /root/tampura-work/.venv/bin/python <repo>/tools/_probe_b1_tampura.py \\
    --out <repo>/archive/tampura_bridge_plan_2026-10-25/bf/BF4_b1/probe_abcd.json
"""
import argparse
import json
import math
import random

import numpy as np
import pybullet as p
import trimesh

from tampura_environments.panda_utils import robot as trobot
from tampura_environments.panda_utils.panda_env_utils import get_ycb_obj_path

CUPS = ('a_cups_ud', 'b_cups_ud', 'c_cups_ud', 'd_cups_ud', 'e_cups_ud')
# D9 step (3): class masses from Calli et al., "The YCB Object and Model
# Set", ICAR 2015, Table I (dice 5.2 g; cups [13, 14, 17, 19, 21, ...] g,
# smallest first).
CLASS_MASS_KG = {'dice': 0.0052, 'a_cups_ud': 0.013, 'b_cups_ud': 0.014,
                 'c_cups_ud': 0.017, 'd_cups_ud': 0.019, 'e_cups_ud': 0.021}
LATERAL_FRICTION = 1.0      # D9 (3), boxel_env.py:91
PAD_FRICTION = 1.2          # D9 (4), boxel_env.py:810-812
FINGER_OPEN = 0.04          # D9 (4), boxel_env.py:824-828
SETTLE_STEPS = 50           # test_full_pipeline.py:562
LAYOUT_SEEDS = {'1747173591': 0, '1747173590': 1, '1747173593': 5}


# ----- (a) the URDF ------------------------------------------------------

def _pose_mat(pos, orn):
    m = np.eye(4)
    m[:3, :3] = np.array(p.getMatrixFromQuaternion(orn)).reshape(3, 3)
    m[:3, 3] = pos
    return m


def _shape_vertices(shape):
    geom, dims, fname = shape[2], shape[3], shape[4]
    if geom == p.GEOM_MESH:
        mesh = trimesh.load(fname.decode(), force='mesh')
        return np.asarray(mesh.vertices) * np.asarray(dims)
    if geom == p.GEOM_BOX:
        h = np.asarray(dims) / 2.0
        return np.array([[sx * h[0], sy * h[1], sz * h[2]]
                         for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    return None


def probe_urdf():
    cid = p.connect(p.DIRECT)
    rob = p.loadURDF(trobot.PANDA_PATH, useFixedBase=True, physicsClientId=cid)
    joints, by_joint, by_link = [], {}, {}
    for j in range(p.getNumJoints(rob, physicsClientId=cid)):
        info = p.getJointInfo(rob, j, physicsClientId=cid)
        row = {'index': j, 'joint': info[1].decode(), 'type': info[2],
               'lower': info[8], 'upper': info[9], 'max_force': info[10],
               'max_velocity': info[11], 'link': info[12].decode()}
        joints.append(row)
        by_joint[row['joint']] = j
        by_link[row['link']] = j
    arm = [by_joint[f'panda_joint{i}'] for i in range(1, 8)]
    for j, q in zip(arm, trobot.DEFAULT_ARM_POS):
        p.resetJointState(rob, j, q, physicsClientId=cid)
    fingers = [by_joint['panda_finger_joint1'], by_joint['panda_finger_joint2']]
    for j in fingers:
        p.resetJointState(rob, j, FINGER_OPEN, physicsClientId=cid)

    def frame(link):
        st = p.getLinkState(rob, link, computeForwardKinematics=True,
                            physicsClientId=cid)
        return _pose_mat(st[4], st[5]), _pose_mat(st[0], st[1])

    refs = {name: by_link[name] for name in ('panda_tool_tip',
                                             'panda_grasptarget', 'panda_hand',
                                             'camera_frame') if name in by_link}
    pads = {}
    for fj in fingers:
        link = fj
        _, com = frame(link)
        pts = []
        for shape in p.getCollisionShapeData(rob, link, physicsClientId=cid):
            v = _shape_vertices(shape)
            if v is None:
                continue
            local = _pose_mat(shape[5], shape[6])
            w = (com @ local @ np.c_[v, np.ones(len(v))].T).T[:, :3]
            pts.append(w)
        pts = np.vstack(pts)
        span = {}
        for name, li in refs.items():
            ref, _ = frame(li)
            inv = np.linalg.inv(ref)
            loc = (inv @ np.c_[pts, np.ones(len(pts))].T).T[:, :3]
            span[name] = {'min': loc.min(0).round(4).tolist(),
                          'max': loc.max(0).round(4).tolist()}
        pads[joints[fj]['link']] = span
    cam, _ = frame(refs['camera_frame'])
    tip, _ = frame(refs['panda_tool_tip'])
    p.disconnect(cid)
    return {'urdf': trobot.PANDA_PATH, 'n_joints': len(joints),
            'joints': joints, 'arm_joint_indices': arm,
            'finger_joint_indices': fingers,
            'finger_limits': [[joints[j]['lower'], joints[j]['upper']]
                              for j in fingers],
            'reference_links': refs,
            'open_gripper_pos_in_code': trobot.OPEN_GRIPPER_POS,
            'finger_collision_extent_in_reference_frames': pads,
            'at_default_arm_pos': {
                'camera_frame_world_pos': cam[:3, 3].round(4).tolist(),
                'camera_frame_world_z_axis': cam[:3, 2].round(4).tolist(),
                'tool_tip_world_pos': tip[:3, 3].round(4).tolist(),
                'tool_tip_world_z_axis': tip[:3, 2].round(4).tolist()},
            'camera_intrinsics_in_code': {'width': trobot.WIDTH,
                                          'height': trobot.HEIGHT,
                                          'fx': trobot.FX, 'fy': trobot.FY}}


# ----- (b) the meshes ----------------------------------------------------

def _cavity(mesh, step=0.001):
    """Upward rays from below on a grid over the footprint.  The first hit
    of a ray under the wall is the rim (at the mesh bottom); inside the
    cavity it is the inner wall or the ceiling above."""
    lo, hi = mesh.bounds
    xs = np.arange(lo[0], hi[0] + 1e-9, step)
    ys = np.arange(lo[1], hi[1] + 1e-9, step)
    gx, gy = np.meshgrid(xs, ys)
    origins = np.c_[gx.ravel(), gy.ravel(), np.full(gx.size, lo[2] - 0.01)]
    dirs = np.tile([0.0, 0.0, 1.0], (len(origins), 1))
    locs, idx, _ = mesh.ray.intersects_location(origins, dirs,
                                                multiple_hits=True)
    first = np.full(len(origins), np.nan)
    for z, i in zip(locs[:, 2], idx):
        if np.isnan(first[i]) or z < first[i]:
            first[i] = z
    clear = first - lo[2]
    inside = clear > 0.003
    out = {'grid_step_m': step}
    if not inside.any():
        out['cavity'] = None
        return out
    pts = origins[inside]
    out['cavity_footprint_extent_xy'] = (pts[:, :2].max(0) - pts[:, :2].min(0)
                                         + step).round(4).tolist()
    out['cavity_max_height'] = round(float(np.nanmax(clear[inside])), 4)
    for h in (0.0162, 0.02, 0.03):
        sel = origins[clear >= h]
        out[f'footprint_extent_xy_with_clearance_{h}'] = (
            (sel[:, :2].max(0) - sel[:, :2].min(0) + step).round(4).tolist()
            if len(sel) else None)
    wall = origins[(~np.isnan(first)) & (~inside)]
    if len(wall):
        out['rim_footprint_extent_xy'] = (wall[:, :2].max(0)
                                          - wall[:, :2].min(0)
                                          + step).round(4).tolist()
    return out


def _mesh_report(path, hollow):
    mesh = trimesh.load(path, force='mesh')
    lo, hi = mesh.bounds
    rep = {'path': path, 'aabb_extent': (hi - lo).round(4).tolist(),
           'n_components': len(mesh.split(only_watertight=False)),
           'visual_com': np.asarray(mesh.center_mass).round(4).tolist()
           if mesh.is_watertight else None}
    top = mesh.vertices[mesh.vertices[:, 2] >= hi[2] - 0.003]
    rep['top_slice_3mm_extent_xy'] = (top[:, :2].max(0)
                                      - top[:, :2].min(0)).round(4).tolist()
    if hollow:
        rep.update(_cavity(mesh))
    return rep


def probe_meshes():
    out = {}
    for name in ('dice',) + CUPS:
        hollow = name != 'dice'
        out[name] = {
            'visual': _mesh_report(get_ycb_obj_path(name), hollow),
            'collision': _mesh_report(get_ycb_obj_path(name, use_concave=True),
                                      hollow),
            'class_mass_kg': CLASS_MASS_KG[name]}
    return out


# ----- (c) and (d) their world, then D9 ----------------------------------

def _inertia_diag(name, mass):
    """Inertia of the collision geometry itself: the VHACD convex parts at
    one uniform density giving the class mass, about the body origin, which
    create_ycb puts at the visual mesh's centre of mass."""
    origin = np.asarray(trimesh.load(get_ycb_obj_path(name),
                                     force='mesh').center_mass)
    col = trimesh.load(get_ycb_obj_path(name, use_concave=True), force='mesh')
    parts = []
    for c in col.split(only_watertight=False):
        # A VHACD piece with fewer than four non-coplanar points has no
        # volume and no inertia; it is skipped.
        if len(np.unique(np.round(c.vertices, 9), axis=0)) < 4:
            continue
        try:
            parts.append(c.convex_hull)
        except Exception:
            continue
    rho = mass / sum(h.volume for h in parts)
    inertia = np.zeros((3, 3))
    for h in parts:
        h.density = rho
        d = np.asarray(h.center_mass) - origin
        inertia += h.moment_inertia + rho * h.volume * (
            np.dot(d, d) * np.eye(3) - np.outer(d, d))
    return np.diag(inertia).tolist()


def probe_layout(scene, seed):
    from tampura.config import config as tconfig
    import tempfile
    cfg = tconfig.load_config(config_file='./env_configs/find_dice.yml',
                              arg_dict={'config': './env_configs/find_dice.yml',
                                        'global_seed': seed, 'vis': 0,
                                        'save_dir': tempfile.mkdtemp()})
    random.seed(cfg['global_seed'])
    np.random.seed(cfg['global_seed'])
    env = tconfig.get_env(cfg['task'])(config=cfg)
    env.initialize()
    w = env.world
    bc = w.client
    c = bc._client
    cats = list(w.categories) if w.categories else []
    res = {'seed': seed, 'scene': scene,
           'executing_world': {'client_map_key': w.client_id,
                               'physics_client_id': c},
           'belief_world': {'client_map_key': env.sim_world.client_id,
                            'physics_client_id': env.sim_world.client._client},
           'categories': cats}
    pe = p.getPhysicsEngineParameters(physicsClientId=c)
    res['engine_before'] = {k: pe[k] for k in pe
                            if k.startswith('gravity') or k in (
                                'fixedTimeStep', 'numSubSteps',
                                'numSolverIterations')}
    bodies = list(w.objects)
    robot = w.robot.body if hasattr(w.robot, 'body') else int(w.robot)
    before = {}
    for b, cat in zip(bodies, cats):
        d = p.getDynamicsInfo(b, -1, physicsClientId=c)
        pos, orn = p.getBasePositionAndOrientation(b, physicsClientId=c)
        before[b] = (np.array(pos), orn)
        res.setdefault('dynamics_before', []).append(
            {'body': b, 'category': cat, 'mass': d[0],
             'lateral_friction': d[1], 'local_inertia_diagonal': d[2],
             'pos': np.round(pos, 4).tolist()})
    n = p.getNumJoints(robot, physicsClientId=c)
    names = {p.getJointInfo(robot, j, physicsClientId=c)[1].decode(): j
             for j in range(n)}
    arm = [names[f'panda_joint{i}'] for i in range(1, 8)]
    fingers = [names['panda_finger_joint1'], names['panda_finger_joint2']]
    arm_before = [p.getJointState(robot, j, physicsClientId=c)[0] for j in arm]

    # D9 (1) to (4), in order, on the executing client.
    p.setGravity(0, 0, -9.81, physicsClientId=c)
    g = p.getPhysicsEngineParameters(physicsClientId=c)
    gz = g.get('gravityAccelerationZ')
    res['gravity_after_step_1'] = gz
    assert gz is None or abs(gz + 9.81) < 1e-9, gz
    p.setTimeStep(1.0 / 240.0, physicsClientId=c)
    for b, cat in zip(bodies, cats):
        m = CLASS_MASS_KG[cat]
        p.changeDynamics(b, -1, mass=m,
                         localInertiaDiagonal=_inertia_diag(cat, m),
                         lateralFriction=LATERAL_FRICTION, physicsClientId=c)
    for j in fingers:
        p.changeDynamics(robot, j, lateralFriction=PAD_FRICTION,
                         physicsClientId=c)
        p.resetJointState(robot, j, FINGER_OPEN, physicsClientId=c)
    res['dynamics_after_set_up'] = [
        {'body': b, 'category': cat,
         'mass': p.getDynamicsInfo(b, -1, physicsClientId=c)[0],
         'lateral_friction': p.getDynamicsInfo(b, -1, physicsClientId=c)[1]}
        for b, cat in zip(bodies, cats)]

    for _ in range(SETTLE_STEPS):
        p.stepSimulation(physicsClientId=c)
    disp = []
    for b, cat in zip(bodies, cats):
        pos, orn = p.getBasePositionAndOrientation(b, physicsClientId=c)
        p0, o0 = before[b]
        e0 = p.getEulerFromQuaternion(o0)
        e1 = p.getEulerFromQuaternion(orn)
        lin, _ = p.getBaseVelocity(b, physicsClientId=c)
        dyaw = (e1[2] - e0[2] + math.pi) % (2 * math.pi) - math.pi
        disp.append({'body': b, 'category': cat,
                     'dxyz': (np.array(pos) - p0).round(4).tolist(),
                     'dxy_norm': round(float(np.linalg.norm(
                         np.array(pos[:2]) - p0[:2])), 4),
                     'dyaw_deg': round(math.degrees(dyaw), 2),
                     'tilt_deg': round(math.degrees(max(abs(e1[0]),
                                                        abs(e1[1]))), 2),
                     'speed_after': round(float(np.linalg.norm(lin)), 4),
                     'nan': bool(np.any(np.isnan(pos)))})
    res['settle_50_steps'] = disp
    arm_after = [p.getJointState(robot, j, physicsClientId=c)[0] for j in arm]
    res['arm_drift_after_settle_rad'] = (np.array(arm_after)
                                         - np.array(arm_before)).round(6).tolist()
    res['arm_at_home_their_test_after_settle'] = bool(
        np.allclose(arm_after, trobot.DEFAULT_ARM_POS, rtol=1e-4, atol=1e-4))
    # Early warning only (B3(c)'s after_settle hook is the real check): is
    # the die in their wrist camera's segmentation after the settle?
    img = w.robot.get_image(client=bc)
    seg = np.asarray(img.segmentationMaskBuffer)
    ids = set(np.unique(seg[..., 0] if seg.ndim == 3 else seg).tolist())
    die = [b for b, cat in zip(bodies, cats) if cat == 'dice']
    res['die_in_wrist_segmentation_after_settle'] = bool(die and die[0] in ids)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', choices=('a', 'b', 'c'), default=None)
    args = ap.parse_args()
    out = {}
    try:
        with open(args.out) as f:
            out = json.load(f)
    except (OSError, ValueError):
        pass
    if args.only in (None, 'a'):
        out['a_urdf'] = probe_urdf()
    if args.only in (None, 'b'):
        out['b_meshes'] = probe_meshes()
    if args.only in (None, 'c'):
        out['c_d_layouts'] = []
        for scene, seed in LAYOUT_SEEDS.items():
            import subprocess
            import sys
            r = subprocess.run([sys.executable, __file__, '--layout',
                                scene, str(seed)], capture_output=True,
                               text=True)
            line = [l for l in r.stdout.splitlines() if l.startswith('{')]
            out['c_d_layouts'].append(json.loads(line[-1]) if line else
                                      {'scene': scene, 'error': r.stderr[-2000:]})
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1)
    print('written', args.out)


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == '--layout':
        print(json.dumps(probe_layout(sys.argv[2], int(sys.argv[3]))))
    else:
        main()
