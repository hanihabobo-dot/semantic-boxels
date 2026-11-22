"""#P4 B1 part 2 probe, items (e) (f) (h) (i) (PAPER_AUDIT.txt #P4, P4.4).

Measurements on THEIR empty table (their setup_robot + setup_world with no
objects: their Panda at the origin, their table top at z = 0, their posts
and beams) and, for (e)'s disclosures only, on the three layouts their own
initialize() builds.  Runs in their venv (the local arm T venv; the cluster's
armO-venvA holds the same package set), in this process's own clients; our
modules (robot_utils, streams, perception) are imported from the repository
at the B3 commit.  Never writes their tree.  Every number here comes from
the URDF, the YCB meshes, their source constants or a scene-independent
probe on the empty table (G9); the layouts feed disclosures only.

  cd /root/tampura-work/tampura_environments
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/tampura-work/tampura:.:<repo> \\
    /root/tampura-work/.venv/bin/python <repo>/tools/_probe_b1p2_tampura.py \\
    <item> [--prev <json>] > <out json>

Items: f (reach), e (D4 eye, W, cup pinch extents; needs f), e_layout SCENE
SEED (one layout's disclosures), h (D5's M1 rule; needs e), i (at-home
convergence; needs e).  Each prints one JSON object on its last line.
"""
import argparse
import json
import math
import os
import random
import sys

import numpy as np
import pybullet as p

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sensing import perception                                    # noqa: E402
from acting import robot_utils                                   # noqa: E402

CUPS = ('a_cups_ud', 'b_cups_ud', 'c_cups_ud', 'd_cups_ud', 'e_cups_ud')
# BF#4 (b), collision meshes: height, and the cavity footprint a 16.2 mm
# die fits in (the interior region a hollow class would declare) with the
# cavity height.
CLASS_HEIGHT = {'dice': 0.0178, 'a_cups_ud': 0.0625, 'b_cups_ud': 0.065,
                'c_cups_ud': 0.0676, 'd_cups_ud': 0.0696, 'e_cups_ud': 0.0719}
CAVITY = {'a_cups_ud': (0.040, 0.040, 0.0537), 'b_cups_ud': (0.045, 0.044, 0.0558),
          'c_cups_ud': (0.050, 0.048, 0.0591), 'd_cups_ud': (0.054, 0.054, 0.0606),
          'e_cups_ud': (0.056, 0.057, 0.0624)}
DIE_EXTENT = (0.0176, 0.0173, 0.0178)       # BF#4 (b), collision
DIE_MASS = 0.0052                           # Calli et al. 2015, Table I
H_MAX = max(CLASS_HEIGHT.values())          # tallest declared class
LIFT = 0.10                                 # execution.py's post-action lift
TODAY_FLOOR = 0.035                         # execution.py _FINGER_TIP_DEPTH
GRASP_MAX_SPAN = 0.076                      # streams.py
# Their place sampler's shortened table (panda_env_utils.get_shortened_table_dims):
# x 0.1 + 1.5/4 -/+ 0.75/2, y -/+ 1.22/2.
TABLE_X = (0.10, 0.85)
TABLE_Y = (-0.61, 0.61)
W_CELL = 0.01                               # W's grid, 1 cm cells
COARSE = 0.05                               # (h) and (i) cells inside W
HOLD_PROBE_CAP = 2400                       # D7 (vii): 10 s at 240 Hz
LAYOUT_SEEDS = {'1747173591': 0, '1747173590': 1, '1747173593': 5}  # laptop map


def their_empty_world():
    from tampura_environments.find_dice.env import setup_world
    from tampura_environments.panda_utils.panda_env_utils import setup_robot
    robot, client = setup_robot(vis=False)
    world = setup_world(robot, client, [], [])
    cid = client._client
    model = robot_utils.resolve_robot_model(robot.body, cid)
    robot_utils.use_robot_model(model)
    return world, robot, client, cid, model


def top_down(yaw):
    return np.array(p.getQuaternionFromEuler([0.0, math.pi, yaw]))


def d4_eye(robot, client):
    """The view their pbu.get_image_at_pose computes for camera_frame at
    DEFAULT_ARM_POS (their setup_world leaves the arm there)."""
    from tampura_environments.panda_utils import pb_utils as pbu
    pose = robot.camera.get_pose(client=client)
    cm = robot.camera.camera_matrix
    width, height = map(int, pbu.dimensions_from_camera_matrix(cm))
    _, vfov = pbu.get_field_of_view(cm)
    eye = np.asarray(pbu.point_from_pose(pose), dtype=float)
    target = np.asarray(pbu.tform_point(pose, np.array([0.0, 0.0, 5.0])), dtype=float)
    view = client.computeViewMatrix(cameraEyePosition=eye.tolist(),
                                    cameraTargetPosition=target.tolist(),
                                    cameraUpVector=[0, 0, 1])
    proj = pbu.get_projection_matrix(width, height, vfov, 0.02, 5.0, client=client)
    return {'eye': eye.tolist(), 'target': target.tolist(), 'up': [0, 0, 1],
            'fov_deg': math.degrees(float(vfov)), 'width': width,
            'height': height, 'near': 0.02, 'far': 5.0,
            'view': list(view), 'proj': list(proj)}


def render(cid, eye):
    w, h = eye['width'], eye['height']
    _, _, _, depth, seg = p.getCameraImage(
        w, h, viewMatrix=eye['view'], projectionMatrix=eye['proj'],
        renderer=p.ER_TINY_RENDERER, physicsClientId=cid)
    buf = np.asarray(depth, dtype=float).reshape(h, w)
    seg = np.asarray(seg).reshape(h, w)
    depth_m = eye['far'] * eye['near'] / (eye['far'] - (eye['far'] - eye['near']) * buf)
    return buf, depth_m, seg


def column_points(x0, x1, y0, y1, z1, n=(4, 4, 4)):
    xs, ys, zs = (np.linspace(a, b, k) for a, b, k in
                  ((x0, x1, n[0]), (y0, y1, n[1]), (0.002, z1, n[2])))
    return np.array([[x, y, z] for x in xs for y in ys for z in zs])


def ik_any_seed(streams, target, orn):
    for seed in streams._ik_seeds():
        got = streams._pybullet_ik(np.asarray(target, dtype=float), orn, seed=seed)
        if got is not None:
            return got
    return None


# ----- (f) reach ----------------------------------------------------------

def item_f():
    from world.boxel_data import BoxelRegistry
    from planning.streams import BoxelStreams
    world, robot, client, cid, model = their_empty_world()
    streams = BoxelStreams(registry=BoxelRegistry(), robot_id=robot.body,
                           physics_client=cid)
    base = np.asarray(p.getBasePositionAndOrientation(
        robot.body, physicsClientId=cid)[0])
    xs = np.arange(-0.25, 1.001, 0.05)
    ys = np.arange(-0.60, 0.601, 0.05)
    heights = [0.045, 0.10, 0.16, 0.20, 0.245, 0.30]
    rows = []
    for dz in heights:
        for yaw in (0.0, math.pi / 2):
            orn = top_down(yaw)
            ok_r, fail_r = [], []
            for x in xs:
                for y in ys:
                    r = float(np.hypot(x - base[0], y - base[1]))
                    got = ik_any_seed(streams, [x, y, dz], orn)
                    (ok_r if got is not None else fail_r).append(r)
            rows.append({'dz': dz, 'yaw': yaw, 'n_ok': len(ok_r),
                         'n': len(ok_r) + len(fail_r),
                         'max_ok_r': max(ok_r) if ok_r else None,
                         'min_fail_r': min(fail_r) if fail_r else None,
                         'fail_inside_max_ok': sum(1 for r in fail_r
                                                   if ok_r and r < max(ok_r))})
    # Boundary per height (both yaws): the largest radius IK reached; a
    # sphere about a world height fitted to those radii, as #P3(c) did.
    bnd = []
    for dz in heights:
        r = max(row['max_ok_r'] for row in rows if row['dz'] == dz)
        bnd.append((dz, r))
    A = np.array([[2 * z, 1.0] for z, _ in bnd])
    b = np.array([r * r + z * z for z, r in bnd])
    (c, k), *_ = np.linalg.lstsq(A, b, rcond=None)
    R = math.sqrt(k + c * c)
    fit = [{'dz': z, 'r': r, 'fit_r': math.sqrt(max(R * R - (z - c) ** 2, 0.0))}
           for z, r in bnd]
    return {'item': 'f', 'base_xyz': base.round(4).tolist(),
            'table_top_z': 0.0, 'grid': {'x': [xs[0], xs[-1], 0.05],
                                         'y': [ys[0], ys[-1], 0.05]},
            'rows': rows, 'sphere_fit': {'center_z_world': c, 'radius': R,
                                         'per_height': fit},
            'robot_model': {'arm': model.arm_joints, 'fingers': model.finger_joints,
                            'ee': model.ee_link}}


# ----- (e) the D4 eye, W, cup pinch extents --------------------------------

def _max_rectangle(grid):
    """Largest-area axis-aligned all-True rectangle of a 2-D bool grid
    (histogram method).  Returns (area, i0, i1, j0, j1), inclusive."""
    n, m = grid.shape
    heights = np.zeros(m, dtype=int)
    best = (0, 0, -1, 0, -1)
    for i in range(n):
        heights = np.where(grid[i], heights + 1, 0)
        stack = []
        for j in range(m + 1):
            h = heights[j] if j < m else 0
            start = j
            while stack and stack[-1][1] >= h:
                s, sh = stack.pop()
                area = sh * (j - s)
                if area > best[0]:
                    best = (area, i - sh + 1, i, s, j - 1)
                start = s
            stack.append((start, h))
    return best


def item_e(prev):
    from world.boxel_data import BoxelRegistry
    from planning.streams import BoxelStreams
    from tampura_environments.panda_utils.panda_env_utils import create_ycb
    world, robot, client, cid, model = their_empty_world()
    eye = d4_eye(robot, client)
    buf, depth_m, seg = render(cid, eye)
    view, proj = eye['view'], eye['proj']
    ids = sorted(int(v) for v in np.unique(seg))
    robot_px = int(np.sum(seg == robot.body))
    streams = BoxelStreams(registry=BoxelRegistry(), robot_id=robot.body,
                           physics_client=cid)
    # The binding reach height: the post-place lift over the tallest class.
    z_reach = CLASS_HEIGHT['e_cups_ud'] - 0.005 + LIFT
    xs = np.arange(TABLE_X[0], TABLE_X[1] - 1e-9, W_CELL)
    ys = np.arange(TABLE_Y[0], TABLE_Y[1] - 1e-9, W_CELL)
    ok = np.zeros((len(xs), len(ys)), dtype=bool)
    why = {'frame': 0, 'occluded': 0, 'reach': 0}
    blockers = {}
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            pts = column_points(x, x + W_CELL, y, y + W_CELL, H_MAX)
            corners = np.array([[a, b, c] for a in (x, x + W_CELL)
                                for b in (y, y + W_CELL) for c in (0.0, H_MAX)])
            _, _, _, inv = perception.project_points_to_pixels(
                corners, view, proj, eye['width'], eye['height'])
            if not np.all(inv):
                why['frame'] += 1
                continue
            icp, hid, inv2 = perception.first_surface_interceptors(
                pts, depth_m, seg, view, proj)
            if np.any(icp) or not np.all(inv2):
                why['occluded'] += 1
                for b in np.unique(hid[icp]):
                    blockers[int(b)] = blockers.get(int(b), 0) + 1
                continue
            c = [x + W_CELL / 2, y + W_CELL / 2, z_reach]
            if (ik_any_seed(streams, c, top_down(0.0)) is None
                    and ik_any_seed(streams, c, top_down(math.pi / 2)) is None):
                why['reach'] += 1
                continue
            ok[i, j] = True
    area, i0, i1, j0, j1 = _max_rectangle(ok)
    W = {'x': [float(xs[i0]), float(xs[i1] + W_CELL)],
         'y': [float(ys[j0]), float(ys[j1] + W_CELL)],
         'cells': int(area), 'cell_m': W_CELL}
    # D11: our estimated pinch extent per cup class at window cells.
    cells = [(x, y) for x in np.linspace(W['x'][0] + 0.04, W['x'][1] - 0.04, 3)
             for y in np.linspace(W['y'][0] + 0.04, W['y'][1] - 0.04, 3)]
    pinch = {}
    for cat in CUPS:
        body = create_ycb(cat, client=client, use_concave=True)
        widths = []
        for (x, y) in cells:
            lo, hi = p.getAABB(body, physicsClientId=cid)
            pos, orn = p.getBasePositionAndOrientation(body, physicsClientId=cid)
            p.resetBasePositionAndOrientation(
                body, [x, y, pos[2] - lo[2] + 0.0005], orn, physicsClientId=cid)
            b2, dm2, s2 = render(cid, eye)
            det = perception.detect_objects_from_render(
                s2, b2, view, proj, {body: cat}, eye['eye'][:2], 0.0).get(cat)
            if det is None:
                widths.append(None)
                continue
            ext = (np.asarray(det.est_max) - np.asarray(det.est_min))
            widths.append({'cell': [round(x, 3), round(y, 3)], 'px': det.pixel_count,
                           'est_xy': ext[:2].round(4).tolist(),
                           'true_aabb_xy': (np.asarray(p.getAABB(body, physicsClientId=cid)[1])
                                            - np.asarray(p.getAABB(body, physicsClientId=cid)[0]))[:2].round(4).tolist()})
        p.removeBody(body, physicsClientId=cid)
        got = [w for w in widths if w]
        pinch[cat] = {'per_cell': widths,
                      'max_est_width': max(max(w['est_xy']) for w in got) if got else None,
                      'fits_grasp_max_span': (max(max(w['est_xy']) for w in got)
                                              <= GRASP_MAX_SPAN) if got else None}
    return {'item': 'e', 'eye': eye, 'empty_render': {
                'seg_ids': ids, 'robot_body': robot.body, 'robot_pixels': robot_px,
                'frame_pixels': eye['width'] * eye['height']},
            'window_rule': {'table_x': TABLE_X, 'table_y': TABLE_Y,
                            'column_height': H_MAX, 'reach_height': z_reach,
                            'rejected': why, 'occluders': blockers},
            'W': W, 'pinch_extent': pinch,
            'grasp_max_span': GRASP_MAX_SPAN}


def item_e_layout(scene, seed):
    """Disclosures on one layout (no constant, no choice): bodies in frame,
    each cup's in-frame fraction, the die absent (assert), the die's pixel
    count and our AABB error with each cup parked away in turn.  D9's
    set-up and main()'s 50 steps first, as the bridge's first render."""
    import tempfile
    from tampura.config import config as tconfig
    sys.path.insert(0, os.path.join(REPO, 'tools'))
    from _probe_b1_tampura import CLASS_MASS_KG, _inertia_diag
    cfg = tconfig.load_config(config_file='./env_configs/find_dice.yml',
                              arg_dict={'config': './env_configs/find_dice.yml',
                                        'global_seed': seed, 'vis': 0,
                                        'save_dir': tempfile.mkdtemp()})
    random.seed(cfg['global_seed'])
    np.random.seed(cfg['global_seed'])
    env = tconfig.get_env(cfg['task'])(config=cfg)
    env.initialize()
    w = env.world
    c = w.client._client
    rb = w.robot.body
    model = robot_utils.resolve_robot_model(rb, c)
    eye = d4_eye(w.robot, w.client)
    p.setGravity(0, 0, -9.81, physicsClientId=c)
    p.setTimeStep(1.0 / 240.0, physicsClientId=c)
    for b, cat in zip(w.objects, w.categories):
        m = CLASS_MASS_KG[cat]
        p.changeDynamics(b, -1, mass=m, localInertiaDiagonal=_inertia_diag(cat, m),
                         lateralFriction=1.0, physicsClientId=c)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=1.2, physicsClientId=c)
        p.resetJointState(rb, fj, 0.04, physicsClientId=c)
    for _ in range(50):
        p.stepSimulation(physicsClientId=c)
    buf, depth_m, seg = render(c, eye)
    names = {b: f'{cat}#{b}' for b, cat in zip(w.objects, w.categories)}
    die = [b for b, cat in zip(w.objects, w.categories) if cat == 'dice'][0]
    in_frame = {}
    for b, cat in zip(w.objects, w.categories):
        lo, hi = (np.asarray(v) for v in p.getAABB(b, physicsClientId=c))
        pts = column_points(lo[0], hi[0], lo[1], hi[1], hi[2] - lo[2], n=(6, 6, 6))
        pts[:, 2] += lo[2] - 0.002
        _, _, _, inv = perception.project_points_to_pixels(
            pts, eye['view'], eye['proj'], eye['width'], eye['height'])
        in_frame[names[b]] = {'pixels': int(np.sum(seg == b)),
                              'aabb_in_frame_fraction': round(float(np.mean(inv)), 3)}
    assert int(np.sum(seg == die)) == 0, 'the die is visible to the D4 eye'
    parked = {}
    for b, cat in zip(w.objects, w.categories):
        if b == die:
            continue
        pos, orn = p.getBasePositionAndOrientation(b, physicsClientId=c)
        p.resetBasePositionAndOrientation(b, [5, 5, -5], orn, physicsClientId=c)
        b2, _, s2 = render(c, eye)
        det = perception.detect_objects_from_render(
            s2, b2, eye['view'], eye['proj'], {die: 'dice'}, eye['eye'][:2], 0.0).get('dice')
        lo, hi = (np.asarray(v) for v in p.getAABB(die, physicsClientId=c))
        parked[names[b]] = {
            'die_pixels': int(np.sum(s2 == die)),
            'aabb_error_m': (None if det is None else round(float(np.max(np.abs(
                np.r_[det.est_min - lo, det.est_max - hi]))), 4))}
        p.resetBasePositionAndOrientation(b, pos, orn, physicsClientId=c)
    return {'item': 'e_layout', 'scene': scene, 'seed': seed, 'eye': eye['eye'],
            'bodies': in_frame, 'die_absent': True, 'cup_parked_in_turn': parked}


# ----- (h) D5's M1 rule -----------------------------------------------------

def _coarse_cells(W):
    xs = np.arange(W['x'][0] + COARSE / 2, W['x'][1], COARSE)
    ys = np.arange(W['y'][0] + COARSE / 2, W['y'][1], COARSE)
    return [(float(x), float(y)) for x in xs for y in ys]


def item_h(prev):
    from world.boxel_data import BoxelRegistry
    from planning.streams import BoxelStreams
    world, robot, client, cid, model = their_empty_world()
    eye = prev['eye']
    home = [p.getJointState(robot.body, j, physicsClientId=cid)[0]
            for j in model.arm_joints]
    streams = BoxelStreams(registry=BoxelRegistry(), robot_id=robot.body,
                           physics_client=cid)
    out, worst = {}, (0.0, None)
    cells = _coarse_cells(prev['W'])
    for cat in CUPS:
        fx, fy, fz = CAVITY[cat]
        contact = max(CLASS_HEIGHT[cat] - 0.005, TODAY_FLOOR)
        rows = []
        for (x, y) in cells:
            q = ik_any_seed(streams, [x, y, contact + LIFT], top_down(0.0))
            if q is None:
                rows.append({'cell': [x, y], 'ik': False})
                continue
            for j, v in zip(model.arm_joints, q.joint_positions):
                p.resetJointState(robot.body, j, float(v), physicsClientId=cid)
            _, depth_m, seg = render(cid, eye)
            slices, _ = perception.sense_ray_slices(
                [x - fx / 2, y - fy / 2, 0.0], [x + fx / 2, y + fy / 2, fz])
            fr = []
            for sl in slices:
                icp, hid, inv = perception.first_surface_interceptors(
                    sl.points, depth_m, seg, eye['view'], eye['proj'])
                blocked = icp | ~inv
                fr.append(float(np.mean(blocked)))
            rows.append({'cell': [round(x, 3), round(y, 3)], 'ik': True,
                         'slice_blocked_fraction': [round(f, 3) for f in fr],
                         'worst': round(max(fr), 3)})
            if max(fr) > worst[0]:
                worst = (max(fr), (cat, x, y))
        for j, v in zip(model.arm_joints, home):
            p.resetJointState(robot.body, j, v, physicsClientId=cid)
        out[cat] = rows
    thr = perception.SENSE_MARGINAL_BLOCKED_FRACTION
    return {'item': 'h', 'threshold': thr, 'cells': len(cells),
            'worst_blocked_fraction': worst[0], 'worst_at': worst[1],
            'adopt_M1': worst[0] > thr, 'per_class': out}


# ----- (i) at-home convergence ----------------------------------------------

def _pads_on(rb, body, cid, model):
    """Both finger pads touch the body, and the body's pad normal force."""
    cs = p.getContactPoints(bodyA=rb, bodyB=body, physicsClientId=cid)
    pads = {c[3] for c in cs if c[3] in model.finger_joints}
    return {'both': pads == set(model.finger_joints),
            'force': round(sum(c[9] for c in cs if c[3] in model.finger_joints), 2),
            'z': round(float(p.getBasePositionAndOrientation(
                body, physicsClientId=cid)[0][2]), 4)}


def item_i(prev):
    from world.boxel_data import BoxelRegistry
    from planning.streams import BoxelStreams
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world, robot, client, cid, model = their_empty_world()
    assert cid == 0, 'our motion functions drive the default client'
    rb = robot.body
    p.setGravity(0, 0, -9.81, physicsClientId=cid)
    p.setTimeStep(1.0 / 240.0, physicsClientId=cid)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=1.2, physicsClientId=cid)
        p.resetJointState(rb, fj, 0.04, physicsClientId=cid)
    streams = BoxelStreams(registry=BoxelRegistry(), robot_id=rb,
                           physics_client=cid)
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    contact = max(DIE_EXTENT[2] - 0.005, TODAY_FLOOR)
    rows = []
    for (x, y) in _coarse_cells(prev['W']):
        q = ik_any_seed(streams, [x, y, contact + LIFT], top_down(0.0))
        if q is None:
            rows.append({'cell': [x, y], 'ik': False})
            continue
        for payload in ('empty', 'die_class'):
            for j, v in zip(model.arm_joints, q.joint_positions):
                p.resetJointState(rb, j, float(v), physicsClientId=cid)
                p.setJointMotorControl2(rb, j, p.POSITION_CONTROL,
                                        targetPosition=float(v), force=240)
            for fj in model.finger_joints:
                p.resetJointState(rb, fj, 0.04, physicsClientId=cid)
            body = None
            if payload == 'die_class':
                ee = p.getLinkState(rb, model.ee_link, computeForwardKinematics=True,
                                    physicsClientId=cid)[0]
                # A die-class box between the pads, static while they
                # close on it, then given the class mass (probe set-up).
                col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[e / 2 for e in DIE_EXTENT],
                                             physicsClientId=cid)
                body = p.createMultiBody(baseMass=0.0, baseCollisionShapeIndex=col,
                                         basePosition=list(ee), physicsClientId=cid)
                p.changeDynamics(body, -1, lateralFriction=1.0, physicsClientId=cid)
                half = robot_utils.close_gripper_until_contact(rb)
                p.changeDynamics(body, -1, mass=DIE_MASS, physicsClientId=cid)
                held_at = {'closed': _pads_on(rb, body, cid, model)}
                for _ in range(60):
                    p.stepSimulation(physicsClientId=cid)
                held_at['settled'] = _pads_on(rb, body, cid, model)
                if half is None or not held_at['settled']['both']:
                    rows.append({'cell': [x, y], 'payload': payload, 'grip': False,
                                 'held_at': held_at})
                    p.removeBody(body, physicsClientId=cid)
                    continue
            robot_utils.move_robot_smooth(rb, home.tolist(), False, settle=True)
            q1 = robot_utils.arm_joint_positions(rb)
            passed_move = bool(np.allclose(q1, home, rtol=1e-4, atol=1e-4))
            if body is not None:
                held_at['after_move'] = _pads_on(rb, body, cid, model)
            passed, steps = robot_utils.hold_at_config(rb, home.tolist(), HOLD_PROBE_CAP)
            q2 = robot_utils.arm_joint_positions(rb)
            held = None
            if body is not None:
                held_at['after_hold'] = _pads_on(rb, body, cid, model)
                held = held_at['after_hold']['both']
                p.removeBody(body, physicsClientId=cid)
                robot_utils.open_gripper(rb)
            rows.append({'cell': [round(x, 3), round(y, 3)], 'payload': payload,
                         'err_after_move': float(np.max(np.abs(q1 - home))),
                         'passed_after_move': passed_move,
                         'hold_passed': passed, 'hold_steps': steps,
                         'err_after_hold': float(np.max(np.abs(q2 - home))),
                         'still_held': held,
                         'held_at': held_at if body is not None else None})
    ran = [r for r in rows if 'hold_passed' in r]
    all_pass = bool(ran) and all(r['hold_passed'] for r in ran)
    max_steps = max(r['hold_steps'] for r in ran) if ran else None
    return {'item': 'i', 'probe_cap': HOLD_PROBE_CAP, 'post_place_lift_z': contact + LIFT,
            'rows': rows, 'all_pass_within_cap': all_pass,
            'max_steps_to_pass': max_steps if all_pass else None,
            'HOME_HOLD_STEP_CAP_by_D7_vii': 2 * max_steps if all_pass else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('item', choices=('e', 'e_layout', 'f', 'h', 'i'))
    ap.add_argument('args', nargs='*')
    ap.add_argument('--prev', help='JSON with W and the eye (item e output)')
    a = ap.parse_args()
    prev = json.load(open(a.prev)) if a.prev else None
    if a.item == 'f':
        out = item_f()
    elif a.item == 'e':
        out = item_e(prev)
    elif a.item == 'e_layout':
        out = item_e_layout(a.args[0], int(a.args[1]))
    elif a.item == 'h':
        out = item_h(prev)
    else:
        out = item_i(prev)
    print(json.dumps(out, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o)))


if __name__ == '__main__':
    main()
