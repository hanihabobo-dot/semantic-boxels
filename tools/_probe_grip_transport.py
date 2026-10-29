"""Grip probe: does the die stay held through the carry home, per grip variant.

The die-class box of _smoke_m9_pick.py (M9 on) at several yaws, picked by
execute_pick with the close call's force and squeeze overridden per
variant, then carried back to the start configuration with
move_robot_smooth.  Records the pad normal force after the close, its
minimum during the carry, and whether both pads still touch the die at
home.  Measurement only: the pipeline is not changed.

  bash scripts/_run_in_wsl.sh tools/_probe_grip_transport.py <out json>
"""
import json
import math
import os
import sys

import numpy as np
import pybullet as p

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'tools'))

import execution                       # noqa: E402
import perception                      # noqa: E402
import pose_belief                     # noqa: E402
import robot_utils                     # noqa: E402
import streams                         # noqa: E402
from boxel_data import BoxelData, BoxelType   # noqa: E402
from boxel_types import ObjectInfo     # noqa: E402
from _calib_pose_noise import build_env, mat_to_quat   # noqa: E402

DIE = (0.0176, 0.0173, 0.0178)
# (name, close force N, squeeze m; None squeeze = hold target fully closed)
VARIANTS = [('60N_3mm', 60.0, 0.003), ('60N_closed', 60.0, None),
            ('70N_3mm', 70.0, 0.003), ('60N_6mm', 60.0, 0.006)]
YAWS = (0, 15, 30, 45)
if os.environ.get('GRIP_PROBE_QUICK'):
    VARIANTS, YAWS = VARIANTS[:1], (0, 30)
# Simulator-side variants at the current grip (60 N, 3 mm): frictionAnchor
# on the pads and the die, more solver iterations, both.
if os.environ.get('GRIP_PROBE_SIM'):
    VARIANTS = [('60N_3mm', 60.0, 0.003), ('anchor', 60.0, 0.003),
                ('iters200', 60.0, 0.003), ('anchor_iters200', 60.0, 0.003)]
if os.environ.get('GRIP_PROBE_SPIN'):
    VARIANTS = [('spin_0.002', 60.0, 0.003), ('spin_0.005', 60.0, 0.003),
                ('spin_0.01', 60.0, 0.003), ('spin_0.02', 60.0, 0.003)]
if os.environ.get('GRIP_PROBE_SLOW'):
    VARIANTS = [('slow2', 60.0, 0.003), ('slow4', 60.0, 0.003)]
if os.environ.get('GRIP_PROBE_LIGHT'):
    VARIANTS = [('60N_0.5mm', 60.0, 0.0005), ('60N_1mm', 60.0, 0.001),
                ('60N_2mm', 60.0, 0.002)]

_orig_close = robot_utils.close_gripper_until_contact


def pad_force(robot, body, cid):
    fingers = robot_utils.robot_model().finger_joints
    cs = p.getContactPoints(bodyA=robot, bodyB=body, physicsClientId=cid)
    links = {c[3] for c in cs if c[3] in fingers}
    return links == set(fingers), sum(c[9] for c in cs if c[3] in fingers)


def run(variant, yaw_deg):
    name, force, squeeze = variant

    def close(robot_id, gui=False, force=60.0, squeeze=0.003, **kw):
        return _orig_close(robot_id, gui, force=variant[1],
                           squeeze=1.0 if variant[2] is None else variant[2], **kw)
    execution.close_gripper_until_contact = close

    pose_belief.SWITCHES['M9'] = True
    env = build_env(2, 0)
    cid = env.client_id
    robot = env.objects['robot'].object_id
    for n, info in list(env.objects.items()):
        if n not in ('plane', 'table', 'robot'):
            p.resetBasePositionAndOrientation(info.object_id, (5.0 + info.object_id, 5, 0),
                                              (0, 0, 0, 1), physicsClientId=cid)
    half = [e / 2 for e in DIE]
    orn = p.getQuaternionFromEuler([0, 0, math.radians(yaw_deg)])
    xy = (float(np.mean(env.table_x_range)) - 0.05, float(np.mean(env.table_y_range)))
    body = p.createMultiBody(
        0.0052, p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
        p.createVisualShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
        basePosition=[xy[0], xy[1], env.table_surface_height + half[2]],
        baseOrientation=orn, physicsClientId=cid)
    p.changeDynamics(body, -1, lateralFriction=1.0, physicsClientId=cid)
    if 'anchor' in name:
        p.changeDynamics(body, -1, frictionAnchor=1, physicsClientId=cid)
        for fj in robot_utils.robot_model().finger_joints:
            p.changeDynamics(robot, fj, frictionAnchor=1, physicsClientId=cid)
    if name.startswith('spin'):
        # Torsional friction about the contact normal (the pinch axis):
        # the pad's contact area, which a point contact lacks.
        for fj in robot_utils.robot_model().finger_joints:
            p.changeDynamics(robot, fj, spinningFriction=float(name.split('_')[1]),
                             physicsClientId=cid)
    if 'iters200' in name:
        p.setPhysicsEngineParameter(numSolverIterations=200, physicsClientId=cid)
    env.objects['die'] = ObjectInfo(object_id=body, name='die', position=None,
                                    orientation=None, size=np.array(DIE),
                                    is_visible=True, is_occluder=False)
    env.pick_contact_floor = 0.0132
    for _ in range(60):
        env.step_simulation()
    det = env.detect_objects()[0]['die']
    bd = BoxelData(id='die', boxel_type=BoxelType.OBJECT,
                   min_corner=det.est_min.copy(), max_corner=det.est_max.copy())
    q_home = list(robot_utils.arm_joint_positions(robot, cid))
    ee = robot_utils.robot_model().ee_link
    s = p.getLinkState(robot, ee, computeForwardKinematics=True, physicsClientId=cid)
    t_ee = np.eye(4)
    t_ee[:3, :3] = np.array(p.getMatrixFromQuaternion(s[5])).reshape(3, 3)
    t_ee[:3, 3] = s[4]
    t_ee_cam = np.linalg.inv(t_ee) @ robot_utils.wrist_camera_pose(robot, cid)
    cam = np.eye(4)
    cam[:3, :3] = np.column_stack([[1, 0, 0], [0, -1, 0], [0, 0, -1]])
    cam[:3, 3] = [*bd.center[:2], bd.max_corner[2] + 0.25]
    tgt = cam @ np.linalg.inv(t_ee_cam)
    q = robot_utils.solve_ik(robot, tgt[:3, 3], mat_to_quat(tgt[:3, :3]), physics_client=cid)
    for j, v in zip(robot_utils.robot_model().arm_joints, q):
        p.resetJointState(robot, j, v, physicsClientId=cid)
    camp = robot_utils.wrist_camera_pose(robot, cid)
    view, proj = robot_utils.wrist_camera_matrices(camp)
    w, h = robot_utils.WRIST_CAMERA_WIDTH, robot_utils.WRIST_CAMERA_HEIGHT
    _, _, _, d, seg = p.getCameraImage(w, h, viewMatrix=view, projectionMatrix=proj,
                                       renderer=p.ER_TINY_RENDERER, physicsClientId=cid)
    wd = perception.detect_objects_from_render(
        np.asarray(seg).reshape(h, w), np.asarray(d, dtype=float).reshape(h, w),
        view, proj, {body: 'die'}, camp[:3, 3], env.table_surface_height,
        no_footprint_completion=frozenset({'die'}))['die']
    yaw = wd.yaw if abs(wd.yaw) >= pose_belief.YAW_DEADBAND['wrist'] else 0.0
    bd.yaw, bd.yaw_valid = yaw, wd.yaw_valid
    bd.body_extents, bd.rect_center = wd.body_extents, wd.rect_center
    for j, v in zip(robot_utils.robot_model().arm_joints, q_home):
        p.resetJointState(robot, j, v, physicsClientId=cid)
    stub = type('S', (), {})()
    stub.ungraspable_objects, stub._grasp_counter = set(), 0
    stub.registry = type('R', (), {'get_boxel': lambda self, i: bd})()
    stub.GRASP_MAX_SPAN = streams.BoxelStreams.GRASP_MAX_SPAN
    stub.GRASP_SQUARE_TOL = streams.BoxelStreams.GRASP_SQUARE_TOL
    stub._GRASP_Z_OFFSETS = list(streams.BoxelStreams._GRASP_Z_OFFSETS)
    (grasp,) = next(streams.BoxelStreams.sample_grasp(stub, 'die'))
    approach = bd.center + grasp.position
    qa = None
    for dq in (0.0, math.radians(yaw_deg), -math.radians(yaw_deg), math.pi / 2, -math.pi / 2):
        seed = list(robot_utils.REST_POSES)
        seed[6] += dq
        qa = robot_utils.solve_ik(robot, approach, grasp.orientation,
                                  physics_client=cid, seed=seed)
        if qa is not None:
            break
    for j, v in zip(robot_utils.robot_model().arm_joints, qa):
        p.resetJointState(robot, j, v, physicsClientId=cid)
    held = execution.execute_pick(
        robot, env, 'die', bd.center.copy(), grasp,
        streams.RobotConfig(joint_positions=np.array(qa)), False,
        obj_aabb=(bd.min_corner.copy(), bd.max_corner.copy()), pose=bd).held_body_id
    row = {'variant': name, 'yaw_deg': yaw_deg, 'picked': held is not None}
    if held is not None:
        both, nf = pad_force(robot, body, cid)
        row['nf_after_pick'] = round(nf, 2)
        # Contact geometry after the close: each pad contact's normal (on
        # the die, world frame) and its height relative to the die centre.
        fingers = robot_utils.robot_model().finger_joints
        cz = p.getBasePositionAndOrientation(body, physicsClientId=cid)[0][2]
        row['contacts'] = [
            {'link': c[3], 'normal': [round(v, 3) for v in c[7]],
             'dz_mm': round(1e3 * (c[6][2] - cz), 1), 'nf': round(c[9], 2)}
            for c in p.getContactPoints(bodyA=robot, bodyB=body, physicsClientId=cid)
            if c[3] in fingers]
        fmin = [nf]
        trace = []

        def on_step(*_a, **_k):
            f = pad_force(robot, body, cid)[1]
            fmin[0] = min(fmin[0], f)
            ee_z = p.getLinkState(robot, robot_utils.robot_model().ee_link,
                                  physicsClientId=cid)[4][2]
            die_z = p.getBasePositionAndOrientation(body, physicsClientId=cid)[0][2]
            if trace and trace[-1][0] > 1.0 and f <= 1.0 and 'loss' not in row:
                ee_s = p.getLinkState(robot, robot_utils.robot_model().ee_link,
                                      computeLinkVelocity=True, physicsClientId=cid)
                lin, ang = p.getBaseVelocity(body, physicsClientId=cid)
                row['loss'] = {
                    'step': len(trace),
                    'die_contacts': sorted({(c[2], c[4]) for c in p.getContactPoints(
                        bodyA=body, physicsClientId=cid)}),
                    'ee_lin_vel': [round(v, 3) for v in ee_s[6]],
                    'ee_ang_vel': [round(v, 2) for v in ee_s[7]],
                    'die_lin_vel': [round(v, 3) for v in lin],
                    'die_ang_vel': [round(v, 1) for v in ang],
                    'fingers_mm': [round(1e3 * p.getJointState(robot, fj, physicsClientId=cid)[0], 2)
                                   for fj in robot_utils.robot_model().finger_joints]}
            trace.append((round(f, 1), round(1e3 * (ee_z - die_z), 1)))
        row['trace_nf_ee_minus_die_mm'] = trace
        limits = robot_utils.JOINT_VELOCITY_LIMITS
        if name.startswith('slow'):
            robot_utils.JOINT_VELOCITY_LIMITS = limits / float(name[4:])
        try:
            robot_utils.move_robot_smooth(robot, q_home, False, settle=True, on_step=on_step)
        finally:
            robot_utils.JOINT_VELOCITY_LIMITS = limits
        both, nf = pad_force(robot, body, cid)
        fingers = [p.getJointState(robot, fj, physicsClientId=cid)[0]
                   for fj in robot_utils.robot_model().finger_joints]
        row.update({'nf_min_carry': round(fmin[0], 2), 'nf_home': round(nf, 2),
                    'held_home': both,
                    'finger_pos_home_mm': [round(1e3 * f, 2) for f in fingers]})
    p.disconnect(cid)
    return row


def main():
    out = []
    for variant in VARIANTS:
        for yaw_deg in YAWS:
            out.append(run(variant, yaw_deg))
            print(out[-1], flush=True)
    with open(sys.argv[1], 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
