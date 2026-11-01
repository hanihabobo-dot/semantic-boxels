"""BF#59 grasp_wrist_home: does joint 7 at a top-down grasp follow from the
grasp yaw and the bearing of the target from the robot base?

Kinematics only (no planner, no stepping): their find_dice Panda (PANDA_PATH,
base at the origin, home DEFAULT_ARM_POS) and pybullet_data's Panda (our
scenes, base at (-0.4, 0, 0), home REST_POSES), the planner's own IK
(streams.BoxelStreams._pybullet_ik over _ik_seeds, the FK and orientation
gates), on a grid of targets over each world's pick area and grasp yaws.
For every target and yaw: the predicted joint 7 (pose_belief's formula),
the IK's joint 7 of the first certified seed (what compute_kin yields
first) and of every seed, and whether the choice by prediction equals the
choice by the IK's joint 7.

  python probe_wrist_formula.py <out.json>
"""
import json
import math
import sys
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data

import pose_belief
import robot_utils
import streams

out_path = sys.argv[1]


def fk_orn(rid, cid, q, rm):
    for j, a in zip(rm.arm_joints, q):
        p.resetJointState(rid, j, a, physicsClientId=cid)
    st = p.getLinkState(rid, rm.ee_link, computeForwardKinematics=True,
                        physicsClientId=cid)
    return st[0], st[1]


def run_world(name, urdf, base, home, xs, ys, z):
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    rid = p.loadURDF(urdf, base, [0, 0, 0, 1], useFixedBase=True,
                     physicsClientId=cid)
    rm = robot_utils.resolve_robot_model(rid, cid)
    robot_utils.use_robot_model(rm)
    ns = SimpleNamespace(robot_id=rid, physics_client=cid,
                         ik_max_iterations=100, ik_residual_threshold=1e-4)
    seeds = list(streams.BoxelStreams._ik_seeds(
        SimpleNamespace(_IK_SEED_OFFSETS=streams.BoxelStreams._IK_SEED_OFFSETS,
                        IK_NUM_SEEDS=streams.BoxelStreams.IK_NUM_SEEDS)))
    # The constant: FK at REST_POSES (q1 = 0, q7 = pi/4) against top_down(pi).
    pos_r, orn_r = fk_orn(rid, cid, robot_utils.REST_POSES, rm)
    td_pi = p.getQuaternionFromEuler([0, math.pi, math.pi])
    rest_vs_td_pi = robot_utils.quat_angle_deg(orn_r, td_pi)
    pos_h, orn_h = fk_orn(rid, cid, home, rm)
    rows = []
    yaws = [math.radians(d) for d in range(-45, 45, 15)]   # today's square wrap
    yaws += [math.radians(d) for d in (-90, -67.5, 60, 75)]  # rectangle members
    for x in xs:
        for y in ys:
            t = np.array([x, y, z])
            for gy in yaws:
                rec = {'x': x, 'y': y, 'gy_deg': round(math.degrees(gy), 2)}
                for tag, g in (('today', gy), ('twin', gy + math.pi)):
                    orn = np.array(p.getQuaternionFromEuler([0, math.pi, g]))
                    pred = pose_belief.wrist_joint7_top_down(t[:2], base[:2], g)
                    q7s = []
                    for s in seeds:
                        c = streams.BoxelStreams._pybullet_ik(ns, t, orn, seed=s)
                        if c is not None:
                            q7s.append(round(float(c.joint_positions[6]), 4))
                    rec[tag] = {'pred': round(pred, 4), 'ik_first': q7s[0] if q7s else None,
                                'ik_all': q7s}
                rows.append(rec)
    p.disconnect(cid)
    return {'world': name, 'base': list(base), 'home_q7': home[6],
            'rest_fk_vs_top_down_pi_deg': rest_vs_td_pi,
            'home_fk_orn': list(orn_h), 'rows': rows}


from tampura_environments.panda_utils.robot import PANDA_PATH, DEFAULT_ARM_POS  # noqa: E402

res = [
    run_world('find_dice', PANDA_PATH, [0.0, 0.0, 0.0], list(DEFAULT_ARM_POS),
              [0.35, 0.45, 0.55, 0.65, 0.74], [-0.28, -0.14, 0.0, 0.17, 0.34], 0.135),
    run_world('ours', 'franka_panda/panda.urdf', [-0.4, 0.0, 0.0], list(robot_utils.REST_POSES),
              [-0.1, 0.1, 0.3, 0.5], [-0.4, -0.2, 0.0, 0.2, 0.4], 0.325 + 0.02 + 0.10),
]

# Summaries: the prediction error against the first certified seed, and the
# twin choice by prediction against the choice by the IK's joint 7.
for w in res:
    h = w['home_q7']
    errs, agree, n_both, flips, clipped_today = [], 0, 0, 0, 0
    for r in w['rows']:
        for tag in ('today', 'twin'):
            ik = r[tag]['ik_first']
            if ik is not None:
                e = (ik - r[tag]['pred'] + math.pi) % (2 * math.pi) - math.pi
                errs.append(abs(e))
        a, b = r['today']['ik_first'], r['twin']['ik_first']
        choose_twin_pred = abs(r['twin']['pred'] - h) < abs(r['today']['pred'] - h)
        flips += int(choose_twin_pred)
        if a is not None and abs(a) >= 2.89:
            clipped_today += 1
        if a is not None and b is not None:
            n_both += 1
            agree += int(choose_twin_pred == (abs(b - h) < abs(a - h)))
    w['summary'] = {
        'cells': len(w['rows']),
        'pred_err_deg_median': round(math.degrees(float(np.median(errs))), 2),
        'pred_err_deg_p95': round(math.degrees(float(np.percentile(errs, 95))), 2),
        'pred_err_deg_max': round(math.degrees(float(np.max(errs))), 2),
        'choice_agrees_with_ik': f"{agree}/{n_both}",
        'twin_chosen': flips,
        'today_ik_q7_at_limit': clipped_today,
        'today_no_ik': sum(r['today']['ik_first'] is None for r in w['rows']),
        'twin_no_ik': sum(r['twin']['ik_first'] is None for r in w['rows']),
    }
    print(w['world'], 'rest FK vs top_down(pi) %.2f deg' % w['rest_fk_vs_top_down_pi_deg'],
          json.dumps(w['summary']), flush=True)

with open(out_path, 'w') as f:
    json.dump(res, f, indent=1)
