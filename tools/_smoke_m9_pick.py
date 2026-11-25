"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 3 smoke: execute_pick at any yaw.

A die-class box (17.6 x 17.3 x 17.8 mm, 5.2 g) on our table with the scene
objects moved away, at yaws 0, 30 and 45 deg; its belief comes from one
fixed-eye render (the registry's AABB) plus a wrist look straight down
(M9's yaw, extents and centre).  The first grasp sample_grasp would offer
is picked with M9 OFF and ON; the result is whether the die is held 10 cm
up.  Contact floor 13.2 mm (the bridge's D8 value; our 35 mm default
closes above a 17.8 mm die, BF#26).

  bash tools/_run_in_wsl.sh tools/_smoke_m9_pick.py <out json>
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

from sensing import perception                      # noqa: E402
from sensing import pose_belief                     # noqa: E402
from acting import robot_utils                     # noqa: E402
from planning import streams                         # noqa: E402
from world.boxel_data import BoxelData, BoxelType   # noqa: E402
from world.boxel_types import ObjectInfo     # noqa: E402
from _calib_pose_noise import build_env, mat_to_quat   # noqa: E402

DIE = (0.0176, 0.0173, 0.0178)


def main():
    out = []
    for m9 in (False, True):
        for yaw_deg in (0, 30, 45):
            pose_belief.SWITCHES['M9'] = m9
            env = build_env(2, 0)
            cid = env.client_id
            robot = env.objects['robot'].object_id
            for n, info in list(env.objects.items()):
                if n not in ('plane', 'table', 'robot'):
                    p.resetBasePositionAndOrientation(info.object_id, (5.0 + info.object_id, 5, 0),
                                                      (0, 0, 0, 1), physicsClientId=cid)
            half = [e / 2 for e in DIE]
            body = p.createMultiBody(
                0.0052, p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
                p.createVisualShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
                basePosition=[0.0, 0.0, env.table_surface_height + half[2]],
                baseOrientation=p.getQuaternionFromEuler([0, 0, math.radians(yaw_deg)]),
                physicsClientId=cid)
            xy = (float(np.mean(env.table_x_range)) - 0.05, float(np.mean(env.table_y_range)))
            p.resetBasePositionAndOrientation(
                body, (xy[0], xy[1], env.table_surface_height + half[2]),
                p.getQuaternionFromEuler([0, 0, math.radians(yaw_deg)]), physicsClientId=cid)
            p.changeDynamics(body, -1, lateralFriction=1.0, physicsClientId=cid)
            env.objects['die'] = ObjectInfo(object_id=body, name='die', position=None,
                                            orientation=None, size=np.array(DIE),
                                            is_visible=True, is_occluder=False)
            env.pick_contact_floor = 0.0132
            for _ in range(60):
                env.step_simulation()
            det = env.detect_objects()[0]['die']
            bd = BoxelData(id='die', boxel_type=BoxelType.OBJECT,
                           min_corner=det.est_min.copy(), max_corner=det.est_max.copy())
            # The wrist look: straight down 0.25 m over the believed centre.
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
            # The first grasp the sampler offers, and its approach config.
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
            from acting.execution import execute_pick
            held, _cfg = execute_pick(robot, env, 'die', bd.center.copy(), grasp,
                                      streams.RobotConfig(joint_positions=np.array(qa)),
                                      False, obj_aabb=(bd.min_corner.copy(), bd.max_corner.copy()),
                                      pose=bd)
            z = p.getBasePositionAndOrientation(body, physicsClientId=cid)[0][2]
            d_ = robot_utils.pinch_direction(grasp.orientation)
            out.append({'M9': m9, 'yaw_deg': yaw_deg,
                        'fitted_yaw_deg': round(math.degrees(wd.yaw), 2),
                        'grasp_yaw_deg': round(math.degrees(math.atan2(-d_[0], d_[1])), 2),
                        'held': held is not None,
                        'die_z_above_table_mm': round(1e3 * (z - env.table_surface_height - half[2]), 1)})
            print(out[-1], flush=True)
            p.disconnect(cid)
    with open(sys.argv[1], 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
