"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 2: calibrate YAW_NOISE, the Q-C
deadband and PLACE_POSE_TOL on OUR scenes (never a TAMPURA layout), and
run step 2's abort census.  Ground truth is read for calibration only;
the quantile (95th percentile) was fixed before measuring.

Modes (run in wsl_env from the repo root):
  die      a die-class box (17.6 x 17.3 x 17.8 mm) on our table with every
           scene object moved away, at yaws 0..85 deg (5 deg steps) and
           five table positions; detected from the fixed eye and from the
           wrist camera (2 standoffs x 2 wrist yaws, straight down).
           Prints yaw-error quantiles per camera.
  census   random-pairs, n_occluders 2-4, seeds 0-4, after main()'s
           settle: per object, complete or not, yaw_valid, yaw error, the
           A radius against the belief margin (YAW_NOISE given by
           --yaw-noise-deg).  Prints the yaw_valid rate per object class.
  places   placement error from finished runs: every ledger place_target
           paired with the eye.jsonl 'after place' snapshot of that place;
           prints the error quantiles.  Args: run directories.

  bash scripts/_run_in_wsl.sh tools/_calib_pose_noise.py die > out.json
"""
import argparse
import glob
import json
import math
import os
import sys

import numpy as np
import pybullet as p

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import perception        # noqa: E402
import pose_belief       # noqa: E402
import robot_utils       # noqa: E402

DIE_EXT = (0.0176, 0.0173, 0.0178)
YAWS_DEG = list(range(0, 90, 5))
LOOK_STANDOFFS = (0.20, 0.30)
LOOK_WRIST_YAWS = (0.0, math.pi / 2)
QUANTILE = 95


def yaw_err(est, true, square):
    period = math.pi / 2 if square else math.pi
    d = (est - true + period / 2) % period - period / 2
    return abs(d)


def mat_to_quat(r):
    """[x, y, z, w] of a rotation matrix (Shepperd's method)."""
    t = np.trace(r)
    if t > 0:
        s = 2.0 * math.sqrt(t + 1.0)
        return np.array([(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s,
                         (r[1, 0] - r[0, 1]) / s, s / 4.0])
    i = int(np.argmax(np.diag(r)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = 2.0 * math.sqrt(1.0 + r[i, i] - r[j, j] - r[k, k])
    q = np.zeros(4)
    q[i] = s / 4.0
    q[j] = (r[j, i] + r[i, j]) / s
    q[k] = (r[k, i] + r[i, k]) / s
    q[3] = (r[k, j] - r[j, k]) / s
    return q


def build_env(n_occ, seed, goal='holding'):
    import test_full_pipeline as tfp
    np.random.seed(seed)
    cfg = tfp.random_pairs_scene(n_occluders=n_occ, extra_distractors=0, seed=seed)
    if goal == 'find-and-tray-stack':
        cfg.enable_tray = True
    from boxel_env import BoxelTestEnv
    env = BoxelTestEnv(gui=False, scene_config=cfg)
    for _ in range(50):
        env.step_simulation()
    return env


def lattice(lo, hi):
    g = [np.linspace(lo[k], hi[k], 3) for k in range(3)]
    return np.array([[x, y, z] for x in g[0] for y in g[1] for z in g[2]])


def complete(det, depth_m, seg, view, proj, robot, others):
    icp, hid, inv = perception.first_surface_interceptors(
        lattice(det.est_min, det.est_max), depth_m, seg, view, proj)
    return bool(det.pixel_count >= perception.DETECTION_MIN_PIXELS
                and not np.any(~inv)
                and not np.any(icp & (hid == robot))
                and not np.any(icp & np.isin(hid, list(others))))


def render(cid, view, proj, w, h, near, far):
    _, _, _, d, seg = p.getCameraImage(w, h, viewMatrix=view, projectionMatrix=proj,
                                       renderer=p.ER_TINY_RENDERER, physicsClientId=cid)
    buf = np.asarray(d, dtype=float).reshape(h, w)
    return buf, far * near / (far - (far - near) * buf), np.asarray(seg).reshape(h, w)


def mode_die(a):
    env = build_env(2, 0)
    cid = env.client_id
    robot = env.objects['robot'].object_id
    q_home = list(robot_utils.arm_joint_positions(robot, cid))
    for n, info in env.objects.items():
        if n not in ('plane', 'table', 'robot'):
            p.resetBasePositionAndOrientation(info.object_id, (5.0 + info.object_id, 5.0, 0.0),
                                              (0, 0, 0, 1), physicsClientId=cid)
    half = np.array(DIE_EXT) / 2.0
    col = p.createCollisionShape(p.GEOM_BOX, halfExtents=half.tolist(), physicsClientId=cid)
    vis = p.createVisualShape(p.GEOM_BOX, halfExtents=half.tolist(), physicsClientId=cid)
    die = p.createMultiBody(0.0052, col, vis, physicsClientId=cid)
    z0 = env.table_surface_height + half[2]
    xs = np.linspace(env.table_x_range[0] + 0.08, env.table_x_range[1] - 0.08, 3)
    ys = np.linspace(env.table_y_range[0] + 0.08, env.table_y_range[1] - 0.08, 3)
    spots = [(xs[0], ys[0]), (xs[0], ys[2]), (xs[1], ys[1]), (xs[2], ys[0]), (xs[2], ys[2])]
    eview, eproj = env._view_and_projection_matrices()
    rows = []
    ee = robot_utils.robot_model().ee_link

    def set_arm(q):
        for j, v in zip(robot_utils.robot_model().arm_joints, q):
            p.resetJointState(robot, j, v, physicsClientId=cid)

    set_arm(q_home)
    s = p.getLinkState(robot, ee, computeForwardKinematics=True, physicsClientId=cid)
    t_ee = np.eye(4)
    t_ee[:3, :3] = np.array(p.getMatrixFromQuaternion(s[5])).reshape(3, 3)
    t_ee[:3, 3] = s[4]
    t_ee_cam = np.linalg.inv(t_ee) @ robot_utils.wrist_camera_pose(robot, cid)
    for (x, y) in spots:
        for yd in YAWS_DEG:
            yaw = math.radians(yd)
            p.resetBasePositionAndOrientation(die, (x, y, z0), p.getQuaternionFromEuler((0, 0, yaw)),
                                              physicsClientId=cid)
            set_arm(q_home)
            views = [('eye', eview, eproj, env.camera_position[:2],
                      env.image_width, env.image_height, env.near_plane, env.far_plane)]
            for so in LOOK_STANDOFFS:
                for wy in LOOK_WRIST_YAWS:
                    cam = np.eye(4)
                    zc = np.array([0.0, 0.0, -1.0])
                    xc = np.array([math.cos(wy), math.sin(wy), 0.0])
                    cam[:3, :3] = np.column_stack([xc, np.cross(zc, xc), zc])
                    cam[:3, 3] = (x, y, z0 + half[2] + so)
                    tgt = cam @ np.linalg.inv(t_ee_cam)
                    q = robot_utils.solve_ik(robot, tgt[:3, 3],
                                             mat_to_quat(tgt[:3, :3]),
                                             physics_client=cid)
                    if q is None:
                        continue
                    set_arm(q)
                    got = robot_utils.wrist_camera_pose(robot, cid)
                    v, pr = robot_utils.wrist_camera_matrices(got)
                    buf, dm, sg = render(cid, v, pr, robot_utils.WRIST_CAMERA_WIDTH,
                                         robot_utils.WRIST_CAMERA_HEIGHT,
                                         robot_utils.WRIST_CAMERA_NEAR, robot_utils.WRIST_CAMERA_FAR)
                    views.append((f'wrist_{so:.2f}_{round(math.degrees(wy))}', v, pr, got[:3, 3][:2],
                                  None, None, None, None, (buf, dm, sg)))
            for vw in views:
                label, v, pr, cxy = vw[:4]
                if label == 'eye':
                    buf, dm, sg = render(cid, v, pr, *vw[4:8])
                else:
                    buf, dm, sg = vw[8]
                dets = perception.detect_objects_from_render(
                    sg, buf, v, pr, {die: 'die'}, cxy, env.table_surface_height,
                    no_footprint_completion=frozenset({'die'}) if label != 'eye' else frozenset())
                d = dets.get('die')
                row = {'cam': label, 'x': round(x, 3), 'y': round(y, 3), 'yaw_deg': yd}
                if d is None:
                    row['detected'] = False
                else:
                    row.update(detected=True, px=d.pixel_count, yaw_valid=d.yaw_valid,
                               complete=complete(d, dm, sg, v, pr, robot, set()),
                               footprint_mm=round(1e3 * pose_belief.pixel_footprint(
                                   d.pixel_steps, d.yaw if d.yaw_valid else 0.0), 3))
                    if d.yaw_valid:
                        row['yaw_err_deg'] = round(math.degrees(yaw_err(d.yaw, yaw, True)), 3)
                        c = d.rect_center
                        row['centre_err_mm'] = round(1e3 * math.hypot(c[0] - x, c[1] - y), 3)
                rows.append(row)
    summary = {}
    for cam in sorted({r['cam'] for r in rows}):
        errs = [r['yaw_err_deg'] for r in rows if r['cam'] == cam and 'yaw_err_deg' in r]
        n = sum(1 for r in rows if r['cam'] == cam)
        summary[cam] = {'n': n, 'yaw_valid': len(errs),
                        'p50_deg': round(float(np.percentile(errs, 50)), 3) if errs else None,
                        f'p{QUANTILE}_deg': round(float(np.percentile(errs, QUANTILE)), 3) if errs else None,
                        'max_deg': round(max(errs), 3) if errs else None}
    allerr = [r['yaw_err_deg'] for r in rows if 'yaw_err_deg' in r]
    summary['all'] = {'n': len(allerr), f'p{QUANTILE}_deg': round(float(np.percentile(allerr, QUANTILE)), 3)}
    emit(a, ({'summary': summary, 'rows': rows}))


def mode_census(a):
    yaw_noise = math.radians(a.yaw_noise_deg)
    rows = []
    for goal in ('holding', 'find-and-tray-stack'):
        for n_occ in (2, 3, 4):
            for seed in range(5):
                try:
                    env = build_env(n_occ, seed, goal)
                except Exception as e:
                    rows.append({'goal': goal, 'n_occ': n_occ, 'seed': seed, 'error': str(e)[:120]})
                    continue
                cid = env.client_id
                robot = env.objects['robot'].object_id
                ids = {info.object_id for n, info in env.objects.items()
                       if n not in ('plane', 'table', 'robot')}
                hidden = []
                for phase in ('initial', 'after_relocation'):
                    if phase == 'after_relocation':
                        # Every occluder moved off the table (a pose reset),
                        # the hidden targets re-detected: their first view
                        # once the plans have relocated what covered them.
                        for n, info in env.objects.items():
                            if info.is_occluder and n not in ('plane', 'table', 'robot'):
                                p.resetBasePositionAndOrientation(
                                    info.object_id, (5.0 + info.object_id, 5.0, 0.0),
                                    (0, 0, 0, 1), physicsClientId=cid)
                    dets, _, buf, seg = env.detect_objects()
                    view, proj = env._view_and_projection_matrices()
                    dm = env._depth_buffer_to_meters(buf)
                    for n, info in env.objects.items():
                        if n in ('plane', 'table', 'robot') or getattr(info, 'is_tray', False):
                            continue
                        if phase == 'after_relocation' and n not in hidden:
                            continue
                        pos, orn = p.getBasePositionAndOrientation(info.object_id, physicsClientId=cid)
                        tyaw = p.getEulerFromQuaternion(orn)[2]
                        cls = 'x'.join(f'{1e3 * v:.0f}' for v in info.size)
                        row = {'goal': goal, 'n_occ': n_occ, 'seed': seed, 'obj': n, 'class': cls,
                               'occluder': bool(info.is_occluder), 'phase': phase}
                        d = dets.get(n)
                        if d is None:
                            row['detected'] = False
                            hidden.append(n)
                            rows.append(row)
                            continue
                        comp = complete(d, dm, seg, view, proj, robot, ids - {info.object_id})
                        ext = d.est_max - d.est_min
                        m = pose_belief.commit_margin(
                            ext[:2], robot_utils.robot_model().finger_limits[0][1], 0.076, 0.005)
                        r = pose_belief.pose_radius(d, yaw_noise, first_partial=not comp)
                        row.update(detected=True, complete=comp, yaw_valid=d.yaw_valid,
                                   radius_mm=round(1e3 * r, 3),
                                   margin_mm=None if m is None else round(1e3 * m, 3),
                                   pose_known=bool(m is not None and r <= m))
                        if d.yaw_valid:
                            sq = abs(d.body_extents[0] - d.body_extents[1]) <= 0.005
                            row['yaw_err_deg'] = round(math.degrees(yaw_err(d.yaw, tyaw, sq)), 3)
                        rows.append(row)
                p.disconnect(cid)
                for c in ('plan_client_id',):
                    if getattr(env, c, None) is not None:
                        try:
                            p.disconnect(getattr(env, c))
                        except Exception:
                            pass
    by_cls = {}
    for r in rows:
        if r.get('detected'):
            s = by_cls.setdefault(r['class'], {'n': 0, 'yaw_valid': 0, 'complete': 0,
                                               'pose_known': 0, 'margin_none': 0})
            s['n'] += 1
            s['yaw_valid'] += r['yaw_valid']
            s['complete'] += r['complete']
            s['pose_known'] += r['pose_known']
            s['margin_none'] += r['margin_mm'] is None
    errs = [r['yaw_err_deg'] for r in rows if 'yaw_err_deg' in r]
    fails = [r for r in rows if r.get('detected') and r['margin_mm'] is not None and not r['pose_known']]
    emit(a, ({'yaw_noise_deg': a.yaw_noise_deg, 'by_class': by_cls,
                      'yaw_err_p95_deg': round(float(np.percentile(errs, QUANTILE)), 3) if errs else None,
                      'pose_known_false_with_a_grasp': fails, 'rows': rows}))


def mode_places(a):
    errs = []
    for d in a.dirs:
        for run in sorted(glob.glob(os.path.join(d, '**', 'ledger.jsonl'), recursive=True)):
            rd = os.path.dirname(run)
            targets = [json.loads(l) for l in open(run) if '"place_target"' in l]
            eye = os.path.join(rd, 'eye.jsonl')
            if not targets or not os.path.exists(eye):
                continue
            snaps = [json.loads(l) for l in open(eye)]
            after = [s for s in snaps if 'after place(' in s.get('tag', '')]
            for t, s in zip(targets, after):
                obj = s['tag'].split('after place(')[1].split(',')[0]
                o = next((o for o in s['objects'] if o.get('name') == obj), None)
                if o is None or o.get('true_aabb') is None:
                    continue
                lo, hi = (np.array(v) for v in o['true_aabb'])
                txy = np.array(t['target_xy'], dtype=float)
                errs.append({'run': os.path.basename(rd), 'obj': obj, 'boxel': t.get('boxel'),
                             'err_mm': round(1e3 * float(np.linalg.norm((lo[:2] + hi[:2]) / 2 - txy)), 3)})
    e = [r['err_mm'] for r in errs]
    emit(a, ({'n': len(e),
                      'p50_mm': round(float(np.percentile(e, 50)), 3) if e else None,
                      f'p{QUANTILE}_mm': round(float(np.percentile(e, QUANTILE)), 3) if e else None,
                      'max_mm': max(e) if e else None, 'rows': errs}))


def emit(a, obj):
    with open(a.out, 'w') as f:
        json.dump(obj, f, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('die', 'census', 'places'))
    ap.add_argument('--yaw-noise-deg', type=float, default=2.0)
    ap.add_argument('--out', required=True)
    ap.add_argument('dirs', nargs='*')
    a = ap.parse_args()
    {'die': mode_die, 'census': mode_census, 'places': mode_places}[a.mode](a)


if __name__ == '__main__':
    main()
