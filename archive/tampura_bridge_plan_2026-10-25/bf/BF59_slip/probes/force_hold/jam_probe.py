"""BF#59 force_hold jam probe (reviews/impl_force_hold.md, "Jam probe").

The seed-0 cup (d_cups_ud at the scene's pose, their create_ycb concave
mesh, D9's mass, inertia and friction through the branch's d9_setup) on
their empty table, picked by the branch's own primitives at the episode's
grasp (top down, yaw 0, contact z 0.0641 m), lifted 10 cm, carried home
on the straight joint line (9 pairs, settle on the last, the home hold),
carried to 10 cm over a free cell on the same line, lowered to the same
contact height (execute_place's rule: the estimate the cup was picked with)
and released as _release_and_verify_drop does (open_gripper, 30 settle
steps, verify: fingers >= 0.038 and no robot contact; up to 3 attempts,
+30 steps each).  Every simulation step is recorded.

  S=<worktree> python jam_probe.py --lever fh --place 000 --reps 6 --out x.json [--trace 0,1]

Levers (the hold law is the branch's code; the reach and the force are
the branch's module constants, patched for the variants):
  base       switch off: the 60 N, 0.5 mm position hold
  fh         force_hold: 10 N, 4 mm reach, the gear
  fh_reach1  10 N, 1 mm reach, the gear
  fh_f20     20 N, 4 mm reach, the gear
  fh_nogear  10 N, 4 mm reach, the gear removed after d9_setup
plus --iters (200 default, as ep_iters.py; 50 = PyBullet's default).
"""
import argparse
import json
import math
import os
import sys
import types

import numpy as np
import pybullet as p

S = os.environ['S']
for _d in (S, os.path.join(S, 'tools')):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import robot_utils                                   # noqa: E402
import slip_fixes                                    # noqa: E402
from tampura_bridge import policy, task_spec         # noqa: E402
from _probe_b1p2_tampura import top_down, ik_any_seed   # noqa: E402

slip_fixes.register('solver_iters', 'stand-in of probes/force_hold/jam_probe.py: '
                                    'the iterations set by the probe')
CUP = 'd_cups_ud'
SCENE_POSE = ([0.6726919346967372, 0.21612314786045383, 0.04931395796324741],
              [0.0, 0.0, -0.824892882161695, 0.565289070263146])   # 1747173591.670785.json
CONTACT_Z = 0.0641          # the episode's pick and place contact z
PLACES = {'000': (0.5463, -0.1280), '003': (0.6435, 0.0665), 'ep000': (0.5463, -0.1280)}
# The s0_i200 episode's own configurations (its eye.jsonl records 18 and 19):
# arrived over free_000 (the hand at z 0.351 m) and at the place contact
# (z 0.0655 m) after a joint-space descent of 0.76 rad on joint 1 and 0.86 rad
# on joint 3 (the log's 'stretching 60 -> 95 steps').
EP000_ABOVE = [1.349, -0.1948, -1.508, -2.0059, -0.2118, 1.9862, -2.847]
EP000_CONTACT = [2.1129, -0.6671, -2.365, -2.1269, -0.7849, 2.4808, -2.481]
LIFT = 0.10
LEVERS = {
    'base': dict(fh=False),
    'fh': dict(fh=True),
    'fh_reach1': dict(fh=True, reach=0.001),
    'fh_f20': dict(fh=True, force=20.0),
    'fh_nogear': dict(fh=True, gear=False),
}


def their_world():
    from tampura_environments.find_dice.env import setup_world
    from tampura_environments.panda_utils.panda_env_utils import setup_robot
    robot, client = setup_robot(vis=False)
    world = setup_world(robot, client, [], [])
    cid = client._client
    model = robot_utils.resolve_robot_model(robot.body, cid)
    robot_utils.use_robot_model(model)
    return world, robot, client, cid, model


def cup_profile(cup):
    """The collision mesh's radius from the cup's axis per height band (world
    frame, the cup standing at its pose)."""
    pos, orn = p.getBasePositionAndOrientation(cup)
    R = np.asarray(p.getMatrixFromQuaternion(orn)).reshape(3, 3)
    shapes = p.getCollisionShapeData(cup, -1)
    out = {'shapes': [{'type': s[2], 'file': os.path.basename(s[4].decode() if isinstance(s[4], bytes) else str(s[4])),
                       'local_pos': [round(x, 4) for x in s[5]]} for s in shapes]}
    try:
        n, verts = p.getMeshData(cup, -1)
        V = np.asarray(verts) @ R.T + np.asarray(pos)
    except Exception as e:                           # noqa: BLE001
        out['mesh_error'] = repr(e)
        return out
    lo, hi = p.getAABB(cup)
    ctr = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2])
    r = np.hypot(V[:, 0] - ctr[0], V[:, 1] - ctr[1])
    bands = []
    for z0 in np.arange(0.0, V[:, 2].max() + 0.005, 0.005):
        m = (V[:, 2] >= z0) & (V[:, 2] < z0 + 0.005)
        if m.any():
            bands.append({'z_mm': round(1e3 * z0, 1), 'r_max_mm': round(1e3 * r[m].max(), 1),
                          'r_min_mm': round(1e3 * r[m].min(), 1), 'n': int(m.sum())})
    out.update(n_vertices=int(n), aabb=[[round(x, 4) for x in lo], [round(x, 4) for x in hi]],
               bands=bands)
    return out


class Recorder:
    def __init__(self, rb, cup, table_ids, model):
        self.rb, self.cup, self.table, self.model = rb, cup, table_ids, model
        self.phase = 'setup'
        self.cmd_z = None
        self.rel0 = None
        self.rows = []
        self.on = False

    def hand(self):
        ls = p.getLinkState(self.rb, self.model.ee_link, computeForwardKinematics=True)
        return np.asarray(ls[0]), np.asarray(p.getMatrixFromQuaternion(ls[1])).reshape(3, 3)

    def cup_in_hand(self):
        pe, Re = self.hand()
        cp, co = p.getBasePositionAndOrientation(self.cup)
        Rc = np.asarray(p.getMatrixFromQuaternion(co)).reshape(3, 3)
        return Re.T @ (np.asarray(cp) - pe), Re.T @ Rc, Rc

    def mark(self):
        rp, rR, _ = self.cup_in_hand()
        self.rel0 = (rp, rR)

    def step(self):
        if not self.on:
            return
        pads = list(self.model.finger_joints)
        pe, Re = self.hand()
        nf, dmin, npt = [0.0, 0.0], [1.0, 1.0], [0, 0]
        other_f, other_d = 0.0, 1.0
        for c in p.getContactPoints(bodyA=self.rb, bodyB=self.cup):
            if c[3] in pads:
                i = pads.index(c[3])
                nf[i] += c[9]
                dmin[i] = min(dmin[i], c[8])
                npt[i] += 1
            else:
                other_f += c[9]
                other_d = min(other_d, c[8])
        table_f = sum(c[9] for t in self.table for c in p.getContactPoints(bodyA=self.cup, bodyB=t))
        rp, rR, Rc = self.cup_in_hand()
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(Rc[2, 2])))))
        row = {'ph': self.phase, 'z': round(1e3 * float(pe[2]), 2),
               'cmd_z': None if self.cmd_z is None else round(1e3 * self.cmd_z, 2),
               'q': [round(1e3 * p.getJointState(self.rb, j)[0], 3) for j in pads],
               'nf': [round(x, 2) for x in nf], 'd': [round(1e3 * x, 2) if x < 1 else None for x in dmin],
               'np': npt, 'other_f': round(other_f, 2),
               'other_d': round(1e3 * other_d, 2) if other_d < 1 else None,
               'table_f': round(table_f, 2), 'tilt': round(tilt, 2),
               'cup_hand_mm': [round(1e3 * x, 2) for x in rp]}
        if self.rel0 is not None:
            d = rp - self.rel0[0]
            rel = rR @ self.rel0[1].T
            row['slip_mm'] = [round(1e3 * x, 2) for x in d]
            row['turn_deg'] = round(math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(rel) - 1) / 2)))), 2)
        self.rows.append(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lever', default='fh', choices=sorted(LEVERS))
    ap.add_argument('--iters', type=int, default=200)
    ap.add_argument('--place', default='000', choices=sorted(PLACES))
    ap.add_argument('--reps', type=int, default=6)
    ap.add_argument('--trace', default='')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    lev = LEVERS[a.lever]
    slip_fixes.configure('solver_iters,force_hold' if lev['fh'] else '')
    if 'reach' in lev:
        robot_utils.FORCE_HOLD_REACH = lev['reach']
    if 'force' in lev:
        robot_utils.FORCE_HOLD_BUDGET_N = lev['force']
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    from tampura_environments.panda_utils.panda_env_utils import create_ycb
    from boxel_data import BoxelRegistry
    from streams import BoxelStreams
    world, robot, client, cid, model = their_world()
    assert cid == 0
    rb = robot.body
    static = [b for b in range(p.getNumBodies()) if b != rb]
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    st = BoxelStreams(registry=BoxelRegistry(), robot_id=rb, physics_client=cid)
    orn = top_down(0.0)
    trace_ids = {int(x) for x in a.trace.split(',') if x}
    orig_step = p.stepSimulation
    rec_box = {}

    def stepping(*args, **kw):
        r = orig_step(*args, **kw)
        if 'rec' in rec_box:
            rec_box['rec'].step()
        return r
    p.stepSimulation = stepping
    rows, profile = [], None
    for k in range(a.reps):
        rng = np.random.default_rng(500 + k)
        cup = create_ycb(CUP, client=client, use_concave=True)
        fake = types.SimpleNamespace(client=types.SimpleNamespace(_client=cid),
                                     robot=types.SimpleNamespace(body=rb),
                                     objects=[cup], categories=[CUP])
        for cnum in range(p.getNumConstraints()):
            p.removeConstraint(p.getConstraintUniqueId(cnum))
        policy.d9_setup(fake, model)                  # D9 values, the gear when fh
        p.setPhysicsEngineParameter(numSolverIterations=a.iters)
        if lev['fh'] and not lev.get('gear', True):
            for cnum in range(p.getNumConstraints()):
                p.removeConstraint(p.getConstraintUniqueId(cnum))
        n_gear = p.getNumConstraints()
        dxy = rng.uniform(-0.002, 0.002, 2)
        pos = [SCENE_POSE[0][0] + dxy[0], SCENE_POSE[0][1] + dxy[1], SCENE_POSE[0][2]]
        p.resetBasePositionAndOrientation(cup, pos, SCENE_POSE[1])
        q_above = ik_any_seed(st, [SCENE_POSE[0][0], SCENE_POSE[0][1], CONTACT_Z + LIFT], orn)
        for j, v in zip(model.arm_joints, q_above.joint_positions):
            p.resetJointState(rb, j, float(v))
            p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=float(v), force=240)
        for fj in model.finger_joints:
            p.resetJointState(rb, fj, task_spec.FINGER_OPEN)
            p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=task_spec.FINGER_OPEN,
                                    force=60)
        for _ in range(120):
            p.stepSimulation()
        if profile is None:
            profile = cup_profile(cup)
        rec = Recorder(rb, cup, static, model)
        rec.on = True
        rec_box['rec'] = rec
        pinch_half = task_spec.CLASS_EXTENTS[CUP][0] / 2
        rec.phase = 'aperture'
        robot_utils.close_gripper(rb, False, target_finger_pos=min(task_spec.FINGER_OPEN, pinch_half + 0.008))
        rec.phase, rec.cmd_z = 'descent_pick', CONTACT_Z
        q_c = robot_utils.solve_ik(rb, np.array([SCENE_POSE[0][0], SCENE_POSE[0][1], CONTACT_Z]), orn, cid,
                                   seed=q_above.joint_positions)
        robot_utils.move_robot_smooth(rb, q_c, False, settle=True)
        rec.phase = 'close'
        half = robot_utils.close_gripper_until_contact(rb, False, force=60.0, ignore_body_ids=frozenset(static))
        row = {'trial': k, 'half_mm': None if half is None else round(1e3 * half, 2), 'gear': n_gear,
               'dxy_mm': [round(1e3 * x, 2) for x in dxy]}
        if half is None:
            rows.append(row)
            p.removeBody(cup)
            continue
        rec.mark()
        rec.phase, rec.cmd_z = 'lift', CONTACT_Z + LIFT
        lift = robot_utils.solve_ik(rb, np.array([SCENE_POSE[0][0], SCENE_POSE[0][1], CONTACT_Z + LIFT]),
                                    orn, cid, seed=q_c)
        robot_utils.move_robot_smooth(rb, lift, False)
        rec.phase, rec.cmd_z = 'carry_home', None
        q0 = np.array([p.getJointState(rb, j)[0] for j in model.arm_joints])
        for i in range(1, 10):
            robot_utils.move_robot_smooth(rb, list(q0 + (home - q0) * i / 9), False, steps=30, settle=(i == 9))
        rec.phase = 'home_hold'
        robot_utils.hold_at_config(rb, home, task_spec.HOME_HOLD_STEP_CAP)
        px, py = PLACES[a.place]
        if a.place == 'ep000':
            q1 = np.asarray(EP000_ABOVE)
        else:
            q1 = np.asarray(ik_any_seed(st, [px, py, CONTACT_Z + LIFT], orn).joint_positions)
        rec.phase = 'carry_place'
        q0 = np.array([p.getJointState(rb, j)[0] for j in model.arm_joints])
        for i in range(1, 10):
            robot_utils.move_robot_smooth(rb, list(q0 + (q1 - q0) * i / 9), False, steps=30, settle=(i == 9))
        q_pc = (np.asarray(EP000_CONTACT) if a.place == 'ep000' else
                robot_utils.solve_ik(rb, np.array([px, py, CONTACT_Z]), orn, cid, seed=q1))
        row['place_ik'] = 'episode' if a.place == 'ep000' else 'seeded'
        if q_pc is None:
            q_pc = robot_utils.solve_ik(rb, np.array([px, py, CONTACT_Z]), orn, cid)
            row['place_ik'] = 'rest_poses'
        row['q_place_above'] = [round(float(x), 4) for x in q1]
        row['q_place_contact'] = [round(float(x), 4) for x in q_pc]
        row['place_descent_max_dq'] = round(float(np.max(np.abs(np.asarray(q_pc) - q1))), 4)
        rec.phase, rec.cmd_z = 'descent_place', CONTACT_Z
        n_before = len(rec.rows)
        robot_utils.move_robot_smooth(rb, q_pc, False, settle=True)
        end = rec.rows[-1]
        desc = rec.rows[n_before:]
        row.update(before_open={k2: end.get(k2) for k2 in ('z', 'q', 'nf', 'd', 'other_f', 'table_f',
                                                          'tilt', 'slip_mm', 'turn_deg')},
                   carry_slip_mm=rec.rows[n_before - 1].get('slip_mm'),
                   carry_turn_deg=rec.rows[n_before - 1].get('turn_deg'),
                   descent_min_d=[min((r['d'][i] for r in desc if r['d'][i] is not None), default=None)
                                  for i in range(2)],
                   descent_max_table_f=max(r['table_f'] for r in desc))
        attempts = []
        released = False
        for att in range(1, 4):
            rec.phase = f'open{att}'
            robot_utils.open_gripper(rb, False)
            for _ in range(30 + 30 * (att - 1)):
                p.stepSimulation()
            fpos = [p.getJointState(rb, fj)[0] for fj in model.finger_joints]
            cs = p.getContactPoints(bodyA=cup, bodyB=rb)
            links = {}
            for c in cs:
                f0, d0 = links.get(c[4], (0.0, 1.0))
                links[c[4]] = (f0 + c[9], min(d0, c[8]))
            ok = min(fpos) >= 0.038 and not cs
            attempts.append({'fingers_mm': [round(1e3 * x, 2) for x in fpos], 'ok': ok,
                             'links': {str(l): [round(f, 2), round(1e3 * d, 2)] for l, (f, d) in links.items()}})
            if ok:
                released = True
                break
        row.update(released=released, attempts=attempts)
        if k in trace_ids:
            row['trace'] = rec.rows
        rec.on = False
        rec_box.pop('rec', None)
        rows.append(row)
        p.removeBody(cup)
        print(json.dumps({x: row[x] for x in row if x not in ('trace',)}), flush=True)
    summ = {'lever': a.lever, 'iters': a.iters, 'place': a.place, 'reps': a.reps,
            'released': sum(bool(r.get('released')) for r in rows),
            'jammed': sum(r.get('released') is False for r in rows)}
    with open(a.out, 'w') as f:
        json.dump({'summary': summ, 'profile': profile, 'rows': rows}, f)
    print('SUMMARY ' + json.dumps(summ), flush=True)


if __name__ == '__main__':
    main()
