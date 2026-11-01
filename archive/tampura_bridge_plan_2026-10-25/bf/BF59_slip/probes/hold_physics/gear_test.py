"""Which gearRatio of a JOINT_GEAR constraint between their Panda's two finger
joints realises the URDF's <mimic joint="panda_finger_joint1"/> (both fingers
at the same joint value): drive finger 1 only, the other motor off, read both."""
import os
import sys

import pybullet as p

REPO = os.environ.get('SB_REPO', '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels')
sys.path.insert(0, REPO)
import robot_utils                                   # noqa: E402
from tampura_environments.find_dice.env import setup_world   # noqa: E402
from tampura_environments.panda_utils.panda_env_utils import setup_robot   # noqa: E402

robot, client = setup_robot(vis=False)
setup_world(robot, client, [], [])
rb = robot.body
f1, f2 = robot_utils.resolve_robot_model(rb, 0).finger_joints
p.setGravity(0, 0, -9.81)
for ratio in (-1.0, 1.0):
    for fj in (f1, f2):
        p.resetJointState(rb, fj, 0.02)
    c = p.createConstraint(rb, f1, rb, f2, jointType=p.JOINT_GEAR, jointAxis=[1, 0, 0],
                           parentFramePosition=[0, 0, 0], childFramePosition=[0, 0, 0])
    p.changeConstraint(c, gearRatio=ratio, erp=0.1, maxForce=50)
    p.setJointMotorControl2(rb, f2, p.VELOCITY_CONTROL, targetVelocity=0, force=0)
    for tgt in (0.035, 0.008):
        for _ in range(240):
            p.setJointMotorControl2(rb, f1, p.POSITION_CONTROL, targetPosition=tgt, force=60)
            p.stepSimulation()
        print(f'gearRatio {ratio:+.0f}: finger 1 driven to {1e3 * tgt:.0f} mm -> '
              f'q1 {1e3 * p.getJointState(rb, f1)[0]:.2f} mm, q2 {1e3 * p.getJointState(rb, f2)[0]:.2f} mm')
    p.removeConstraint(c)
