"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 1: the seed-0 abort probe.

Diagnostic only: ground truth is read freely, nothing here feeds the
planner, and NO constant is calibrated from it (seed 0 is a released
evaluation layout).  It answers step 1's questions:

  * the die's true yaw at seed 0;
  * the wrist camera: their camera_frame link pose against the declared
    hand-to-camera transform (C2), which must agree;
  * per object, the BELIEF-derived commit margin (from the fixed eye's
    detection, as the registry would hold it) and, at every look
    configuration (LOOK_STANDOFFS x wrist yaws, camera straight down over
    the believed centre), the wrist detection: complete or not, centre
    and yaw error against ground truth, and the A formula's pixel term;
    the same from the fixed eye at q_home for comparison;
  * the plan-twin render verdict against the executing client's render at
    every look and sense candidate (disagreement rate);
  * the fraction of the die's lattice the arm hides from the eye at the
    die's grasp configurations (pre-grasp and contact).

The formula's YAW_NOISE is step 2's calibration and does not exist yet, so
the probe reports, per look, the largest YAW_NOISE that would still keep
the radius within the margin (break-even); DETECTION_PIXEL_NOISE_PX is
taken as 1 px (declared a priori, not fitted).  The cup d_cups_ud covers
the die at seed 0; it is moved with a pose reset to where plan#1 places it
(free_000, about (0.538, -0.125)) before the die is imaged.

  cd /root/tampura-work/tampura_environments
  PYTHONHASHSEED=0 PYTHONPATH=<repo>:<repo>/pddlstream_lib:/root/tampura-work/tampura:. \\
    /root/armO-venvA/bin/python <repo>/tools/_probe_seed0_die.py <out json>
"""
import json
import logging
import math
import os
import random
import sys

import numpy as np
import pybullet as p

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import perception                                    # noqa: E402
import robot_utils                                   # noqa: E402
from tampura_bridge import task_spec                 # noqa: E402
from tampura_bridge.env_adapter import symbol_names  # noqa: E402

LOOK_STANDOFFS = (0.20, 0.30)          # C2, declared before measuring
LOOK_WRIST_YAWS = (0.0, math.pi / 2)
PIXEL_NOISE_PX = 1.0                   # declared a priori (not fitted)
PROVISIONAL_YAW_NOISE = math.radians(2.0)   # display only; step 2 calibrates
CUP_PLACE_XY = (0.538, -0.125)         # plan#1's place at seed 0 (log)
TOP_FACE_BAND = 0.003                  # M9: top-face points within 3 mm
# C2: TAMPURA's camera_frame joint (panda.urdf:282-287), parent panda_hand.
WRIST_XYZ = (0.036499, -0.034889, 0.0574)
WRIST_RPY = (-0.0056067, 0.0145899, 1.5605169)


def pose_mat(pos, orn):
    m = np.eye(4)
    m[:3, :3] = np.array(p.getMatrixFromQuaternion(orn)).reshape(3, 3)
    m[:3, 3] = pos
    return m


def link_mat(body, link, cid):
    s = p.getLinkState(body, link, computeForwardKinematics=True,
                       physicsClientId=cid)
    return pose_mat(s[4], s[5])


def link_index(body, name, cid):
    for j in range(p.getNumJoints(body, physicsClientId=cid)):
        if p.getJointInfo(body, j, physicsClientId=cid)[12].decode() == name:
            return j
    raise KeyError(name)


def wrist_view(cam):
    """View matrix of a camera pose (optical frame: +z forward, -y up)."""
    eye = cam[:3, 3]
    return p.computeViewMatrix(eye.tolist(), (eye + 5.0 * cam[:3, 2]).tolist(),
                               (-cam[:3, 1]).tolist())


PROJ = p.computeProjectionMatrixFOV(
    fov=task_spec.EYE_FOV_DEG, aspect=task_spec.EYE_WIDTH / task_spec.EYE_HEIGHT,
    nearVal=task_spec.EYE_NEAR, farVal=task_spec.EYE_FAR)
EYE_VIEW = p.computeViewMatrix(list(task_spec.EYE_POSITION),
                               list(task_spec.EYE_TARGET), list(task_spec.EYE_UP))


def render(cid, view):
    w, h = task_spec.EYE_WIDTH, task_spec.EYE_HEIGHT
    _, _, _, d, seg = p.getCameraImage(w, h, viewMatrix=view, projectionMatrix=PROJ,
                                       renderer=p.ER_TINY_RENDERER,
                                       physicsClientId=cid)
    buf = np.asarray(d, dtype=float).reshape(h, w)
    far, near = task_spec.EYE_FAR, task_spec.EYE_NEAR
    return buf, far * near / (far - (far - near) * buf), np.asarray(seg).reshape(h, w)


def lattice(lo, hi, n=3):
    g = [np.linspace(lo[k], hi[k], n) for k in range(3)]
    return np.array([[x, y, z] for x in g[0] for y in g[1] for z in g[2]])


def min_area_rect(xy):
    """Rotating calipers on the convex hull: (centre, (ext_a, ext_b), yaw)."""
    from scipy.spatial import ConvexHull
    if len(xy) < 3:
        return None
    try:
        hull = xy[ConvexHull(xy).vertices]
    except Exception:
        return None
    best = None
    for i in range(len(hull)):
        e = hull[(i + 1) % len(hull)] - hull[i]
        ang = math.atan2(e[1], e[0])
        c, s = math.cos(ang), math.sin(ang)
        r = hull @ np.array([[c, -s], [s, c]])
        lo, hi = r.min(axis=0), r.max(axis=0)
        area = float(np.prod(hi - lo))
        if best is None or area < best[0]:
            mid = (lo + hi) / 2.0
            centre = np.array([[c, s], [-s, c]]).T @ mid
            best = (area, centre, hi - lo, ang)
    _, centre, ext, ang = best
    return centre, ext, ang


def yaw_mod(a, period):
    return (a + period / 2) % period - period / 2


def footprint(rows, cols, buf, view, axes):
    """Per-axis pixel footprint at the cloud centroid's depth: the larger
    world displacement along each axis for one column or one row step."""
    r, c = int(np.median(rows)), int(np.median(cols))
    w, h = task_spec.EYE_WIDTH, task_spec.EYE_HEIGHT
    pts = perception.unproject_depth_pixels(
        [r, r, r + 1], [c, c + 1, c], [buf[r, c]] * 3, view, PROJ, w, h)
    dc, dr = pts[1] - pts[0], pts[2] - pts[0]
    return [max(abs(float(dc[:2] @ a)), abs(float(dr[:2] @ a))) for a in axes]


def margin(half_xy):
    """Belief-derived commit margin over both grasp families."""
    hmax = robot_utils.robot_model().finger_limits[0][1]
    out = []
    for pinch, perp in ((half_xy[0], half_xy[1]), (half_xy[1], half_xy[0])):
        if 2 * pinch > 0.076:           # GRASP_MAX_SPAN: family not offered
            continue
        out.append(min(hmax - pinch - 0.002, 0.5 * perp))
    return min(out) if out else None


def analyse(name, body, cid, view, cam_xy, bodies, truth, belief, robot):
    buf, depth_m, seg = render(cid, view)
    dets = perception.detect_objects_from_render(
        seg, buf, view, PROJ, bodies, cam_xy, task_spec.TABLE_TOP_Z,
        no_footprint_completion=frozenset(bodies.values()))
    rows, cols = np.nonzero(seg == body)
    rec = {'pixels': int(rows.size)}
    icp, hid, inv = perception.first_surface_interceptors(
        lattice(belief[0], belief[1]), depth_m, seg, view, PROJ)
    rec['lattice_robot'] = int(np.sum(icp & (hid == robot)))
    rec['lattice_other'] = int(np.sum(icp & (hid != robot) & (hid != body)
                                      & np.isin(hid, list(bodies))))
    rec['lattice_out_of_view'] = int(np.sum(~inv))
    rec['complete'] = bool(rows.size >= perception.DETECTION_MIN_PIXELS
                           and rec['lattice_robot'] == 0
                           and rec['lattice_other'] == 0
                           and rec['lattice_out_of_view'] == 0)
    if name not in dets:
        return rec
    w, h = task_spec.EYE_WIDTH, task_spec.EYE_HEIGHT
    pts = perception.unproject_depth_pixels(rows, cols, buf[rows, cols],
                                            view, PROJ, w, h)
    top = pts[pts[:, 2] >= pts[:, 2].max() - TOP_FACE_BAND][:, :2]
    rec['top_pixels'] = int(len(top))
    fit = min_area_rect(top)
    t_lo, t_hi, t_yaw = truth
    t_c = (t_lo[:2] + t_hi[:2]) / 2.0
    d = dets[name]
    rec['aabb_centre_err_mm'] = round(1e3 * float(np.linalg.norm(d.est_center[:2] - t_c)), 2)
    if fit is not None:
        centre, ext, ang = fit
        square = abs(ext[0] - ext[1]) <= 0.005
        period = math.pi / 2 if square else math.pi
        rec['rect_centre_err_mm'] = round(1e3 * float(np.linalg.norm(centre - t_c)), 2)
        rec['rect_ext_mm'] = [round(1e3 * float(v), 2) for v in ext]
        rec['rect_yaw_deg'] = round(math.degrees(yaw_mod(ang, period)), 2)
        rec['yaw_err_deg'] = round(math.degrees(abs(yaw_mod(ang - t_yaw, period))), 2)
    gy = 0.0
    axes = [np.array([math.cos(gy), math.sin(gy)]), np.array([-math.sin(gy), math.cos(gy)])]
    fp = footprint(rows, cols, buf, view, axes)
    rec['footprint_mm'] = [round(1e3 * v, 3) for v in fp]
    rec['px_term_mm'] = round(1e3 * PIXEL_NOISE_PX * max(fp), 3)
    return rec


def main():
    from tampura.config import config as tconfig
    import tampura_environments  # noqa: F401
    config = tconfig.load_config(config_file='./env_configs/find_dice.yml',
                                 arg_dict={'config': './env_configs/find_dice.yml',
                                           'global_seed': 0, 'vis': False,
                                           'save_dir': '/root/probe_seed0_die'})
    random.seed(0)
    np.random.seed(0)
    logging.disable(logging.CRITICAL)
    env = tconfig.get_env(config['task'])(config=config)
    env.initialize()
    world = env.world
    cid = world.client._client
    robot = world.robot.body
    model = robot_utils.resolve_robot_model(robot, cid)
    robot_utils.use_robot_model(model)
    out = {}
    names = symbol_names(list(world.categories))
    bodies = dict(zip(world.objects, names))
    by_name = {n: b for b, n in bodies.items()}
    die, cup = by_name['dice'], [n for n in names if n != 'dice']
    q_home = [p.getJointState(robot, j, physicsClientId=cid)[0] for j in model.arm_joints]
    from tampura_bridge.policy import d9_setup
    d9_setup(world, model)

    def settle(n):
        """main()'s settle: n steps at 240 Hz, the arm held at q_home."""
        for j, v in zip(model.arm_joints, q_home):
            p.setJointMotorControl2(robot, j, p.POSITION_CONTROL, targetPosition=v,
                                    force=500, physicsClientId=cid)
        for _ in range(n):
            p.stepSimulation(physicsClientId=cid)

    def die_pose():
        pos, orn = p.getBasePositionAndOrientation(by_name['dice'], physicsClientId=cid)
        e = p.getEulerFromQuaternion(orn)
        return {'pos': np.round(pos, 4).tolist(), 'yaw_deg': round(math.degrees(e[2]), 2),
                'tilt_deg': round(math.degrees(max(abs(e[0]), abs(e[1]))), 2)}
    out['die_scene_file'] = die_pose()
    settle(50)
    out['die_after_settle'] = die_pose()

    # The wrist camera: their link against the declared transform.
    hand = link_index(robot, 'panda_hand', cid)
    camf = link_index(robot, 'camera_frame', cid)
    declared = pose_mat(WRIST_XYZ, p.getQuaternionFromEuler(WRIST_RPY))
    t_hand, t_cam = link_mat(robot, hand, cid), link_mat(robot, camf, cid)
    via_decl = t_hand @ declared
    rel = via_decl[:3, :3].T @ t_cam[:3, :3]
    out['wrist_mount'] = {
        'pos_diff_mm': round(1e3 * float(np.linalg.norm(via_decl[:3, 3] - t_cam[:3, 3])), 4),
        'ang_diff_deg': round(math.degrees(math.acos(min(1.0, (np.trace(rel) - 1) / 2))), 4)}
    t_ee_cam = np.linalg.inv(link_mat(robot, model.ee_link, cid)) @ t_hand @ declared

    # Ground truth (diagnostics only).
    def truth(b):
        lo, hi = (np.array(v) for v in p.getAABB(b, physicsClientId=cid))
        yaw = p.getEulerFromQuaternion(p.getBasePositionAndOrientation(
            b, physicsClientId=cid)[1])[2]
        return lo, hi, yaw
    out['truth'] = {n: {'aabb': [np.round(v, 4).tolist() for v in truth(b)[:2]],
                        'yaw_deg': round(math.degrees(truth(b)[2]), 2)}
                    for n, b in by_name.items()}

    def set_arm(q):
        for j, v in zip(model.arm_joints, q):
            p.resetJointState(robot, j, v, physicsClientId=cid)

    # The plan twin, built with their construction functions in its own client.
    from pybullet_utils import bullet_client
    from tampura_environments.panda_utils.panda_env_utils import (
        create_default_env, create_ycb)
    from tampura_environments.panda_utils.robot import PANDA_PATH
    tw = bullet_client.BulletClient(connection_mode=p.DIRECT)
    tcid = tw._client
    create_default_env(client=tw)
    t_robot = tw.loadURDF(PANDA_PATH, useFixedBase=True)
    twin = {b: create_ycb(c, use_concave=True, client=tw)
            for b, c in zip(world.objects, world.categories)}

    def sync_twin(q):
        for b, tb in twin.items():
            pos, orn = p.getBasePositionAndOrientation(b, physicsClientId=cid)
            p.resetBasePositionAndOrientation(tb, pos, orn, physicsClientId=tcid)
        for j, v in zip(model.arm_joints, q):
            p.resetJointState(t_robot, j, v, physicsClientId=tcid)
        for fj in model.finger_joints:
            v = p.getJointState(robot, fj, physicsClientId=cid)[0]
            p.resetJointState(t_robot, fj, v, physicsClientId=tcid)

    def verdicts(view, lo, hi):
        """The executor's test in both clients: the lattice points the robot
        hides and the points another body hides."""
        res = []
        for c_, rb, ids in ((cid, robot, set(world.objects)),
                            (tcid, t_robot, set(twin.values()))):
            _, dm, sg = render(c_, view)
            icp, hid, _ = perception.first_surface_interceptors(
                lattice(lo, hi), dm, sg, view, PROJ)
            res.append((int(np.sum(icp & (hid == rb))),
                        int(np.sum(icp & np.isin(hid, list(ids))))))
        return res

    agree = []
    # Sense candidates at seed 0: the region under the cup (its footprint).
    cup_body = by_name[cup[0]]
    clo, chi, _ = truth(cup_body)
    sense_cands = {'current_q_home': q_home}
    for k, xyz in enumerate(((0.25, -0.30, 0.35), (0.25, 0.30, 0.35), (0.20, 0.0, 0.45))):
        q = robot_utils.solve_ik(robot, np.array(xyz), physics_client=cid)
        if q is not None:
            sense_cands[f'retracted_{k}'] = list(q)
    out['sense_candidates'] = {}
    for nm, q in sense_cands.items():
        set_arm(q)
        sync_twin(q)
        (ra, oa), (rt, ot) = verdicts(EYE_VIEW, clo, chi)
        out['sense_candidates'][nm] = {'robot_hidden_actual': ra, 'robot_hidden_twin': rt}
        agree.append((ra == 0) == (rt == 0))

    # Move the cup to plan#1's place so the die is in view (diagnostic).
    pos, orn = p.getBasePositionAndOrientation(cup_body, physicsClientId=cid)
    p.resetBasePositionAndOrientation(cup_body, (CUP_PLACE_XY[0], CUP_PLACE_XY[1], pos[2]),
                                      orn, physicsClientId=cid)
    set_arm(q_home)
    settle(240)
    out['die_after_cup_moved'] = die_pose()
    out['objects'] = {}
    for n, b in by_name.items():
        rec = {}
        lo, hi, yaw = truth(b)
        buf, dm, sg = render(cid, EYE_VIEW)
        det = perception.detect_objects_from_render(
            sg, buf, EYE_VIEW, PROJ, bodies, task_spec.EYE_POSITION,
            task_spec.TABLE_TOP_Z).get(n)
        if det is None:
            rec['eye'] = 'not detected'
            out['objects'][n] = rec
            continue
        belief = (det.est_min.copy(), det.est_max.copy())
        half = (belief[1] - belief[0]) / 2.0
        rec['belief_half_mm'] = [round(1e3 * float(v), 2) for v in half]
        m = margin(half[:2])
        rec['belief_margin_mm'] = None if m is None else round(1e3 * m, 2)
        pinch_half = float(min(half[0], half[1]))
        rec['eye_q_home'] = analyse(n, b, cid, EYE_VIEW, task_spec.EYE_POSITION,
                                    bodies, (lo, hi, yaw), belief, robot)
        looks = []
        cx, cy = (belief[0][:2] + belief[1][:2]) / 2.0
        for so in LOOK_STANDOFFS:
            for wy in LOOK_WRIST_YAWS:
                cam = np.eye(4)
                z = np.array([0.0, 0.0, -1.0])
                x = np.array([math.cos(wy), math.sin(wy), 0.0])
                cam[:3, :3] = np.column_stack([x, np.cross(z, x), z])
                cam[:3, 3] = (cx, cy, float(belief[1][2]) + so)
                ee = cam @ np.linalg.inv(t_ee_cam)
                orn = robot_utils_quat(ee[:3, :3])
                q = robot_utils.solve_ik(robot, ee[:3, 3], orn, physics_client=cid)
                lk = {'standoff': so, 'wrist_yaw_deg': round(math.degrees(wy))}
                if q is None:
                    lk['ik'] = False
                    looks.append(lk)
                    continue
                set_arm(q)
                got = link_mat(robot, camf, cid)
                lk['cam_pos_err_mm'] = round(1e3 * float(np.linalg.norm(got[:3, 3] - cam[:3, 3])), 2)
                lk['cam_axis_err_deg'] = round(math.degrees(math.acos(
                    min(1.0, float(got[:3, 2] @ cam[:3, 2])))), 2)
                lk['collision_free'] = bool(robot_utils.is_config_collision_free(
                    robot, q, physics_client=cid))
                view = wrist_view(got)
                lk.update(analyse(n, b, cid, view, got[:3, 3], bodies,
                                  (lo, hi, yaw), belief, robot))
                if m is not None and 'px_term_mm' in lk:
                    lk['break_even_yaw_noise_deg'] = round(math.degrees(
                        (m - lk['px_term_mm'] / 1e3) / pinch_half), 3)
                    lk['radius_at_2deg_mm'] = round(
                        lk['px_term_mm'] + 1e3 * PROVISIONAL_YAW_NOISE * pinch_half, 3)
                sync_twin(q)
                (ra, oa), (rt, ot) = verdicts(view, *belief)
                lk['twin'] = {'actual': [ra, oa], 'twin': [rt, ot]}
                agree.append(((ra + oa) == 0) == ((rt + ot) == 0))
                looks.append(lk)
        set_arm(q_home)
        rec['looks'] = looks
        out['objects'][n] = rec

    # The die's lattice hidden from the eye at its grasp configurations.
    lo, hi, _ = truth(die)
    cxy = (lo[:2] + hi[:2]) / 2.0
    hidden = {}
    for label, z in (('pregrasp_0.10', hi[2] - 0.005 + 0.10),
                     ('contact', max(hi[2] - 0.005, task_spec.PICK_CONTACT_FLOOR))):
        q = robot_utils.solve_ik(robot, np.array([cxy[0], cxy[1], z]), physics_client=cid)
        if q is None:
            hidden[label] = 'ik failed'
            continue
        set_arm(q)
        _, dm, sg = render(cid, EYE_VIEW)
        icp, hid, _ = perception.first_surface_interceptors(lattice(lo, hi), dm, sg,
                                                             EYE_VIEW, PROJ)
        hidden[label] = round(float(np.mean(icp & (hid == robot))), 3)
    set_arm(q_home)
    out['die_lattice_robot_hidden_fraction'] = hidden
    out['twin_agreement'] = {'n': len(agree), 'disagree': int(sum(not a for a in agree))}
    with open(sys.argv[1], 'w') as f:
        json.dump(out, f, indent=1)


def robot_utils_quat(r):
    from scipy.spatial.transform import Rotation
    return np.array(Rotation.from_matrix(r).as_quat())


if __name__ == '__main__':
    main()
