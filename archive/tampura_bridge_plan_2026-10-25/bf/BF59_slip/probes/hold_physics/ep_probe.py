"""One find_dice episode of the unchanged driver with the hold-physics fix
candidates patched in (proposal phase, no tracked file edited), and the
loss_dynamics recorder installed for the per-step carry record.

  python ep_probe.py <recorder jsonl> <hold N or 0> <solver iterations or 0> <driver args...>

hold N > 0: after robot_utils' tactile close returns a width, the finger
motors hold a target 4 mm inside the measured width at a motor budget of N
newtons (a force-limited hold) instead of the 0.5 mm position target at
60 N.  iterations > 0: numSolverIterations on the executing client right
after D9's set-up.
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *(['..'] * 6)))
DRIVER = os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')
LD = os.path.join(os.path.dirname(HERE), 'loss_dynamics')

out, hold_n, iters = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
gear = os.environ.get('HP_GEAR', '0') == '1'
sys.argv = [DRIVER] + sys.argv[4:]
sys.path.insert(0, REPO)
sys.path.insert(1, LD)

import console_ui                                   # noqa: E402
console_ui.install_early('__main__')
from tampura.config import config as _tconfig       # noqa: E402,F401
import tampura_environments                         # noqa: E402,F401
import pybullet as p                                # noqa: E402
from tampura_bridge import policy as _bp            # noqa: E402
import execution                                    # noqa: E402
import robot_utils                                  # noqa: E402
import loss_recorder                                # noqa: E402

if iters > 0 or gear:
    _orig_d9 = _bp.d9_setup

    def d9_setup(world, model):
        _orig_d9(world, model)
        c = world.client._client
        if iters > 0:
            p.setPhysicsEngineParameter(numSolverIterations=iters, physicsClientId=c)
            print(f'[hold_physics] numSolverIterations {iters} on client {c}', flush=True)
        if gear:
            rb = world.robot.body
            f1, f2 = model.finger_joints
            gc = p.createConstraint(rb, f1, rb, f2, jointType=p.JOINT_GEAR, jointAxis=[1, 0, 0],
                                    parentFramePosition=[0, 0, 0], childFramePosition=[0, 0, 0],
                                    physicsClientId=c)
            p.changeConstraint(gc, gearRatio=-1, erp=0.1, maxForce=50, physicsClientId=c)
            print(f'[hold_physics] finger gear constraint {gc} on client {c}', flush=True)
    _bp.d9_setup = d9_setup

if hold_n > 0:
    _orig_close = execution.close_gripper_until_contact

    def close_gripper_until_contact(robot_id, gui=False, **kw):
        w = _orig_close(robot_id, gui, **kw)
        if w is not None:
            for fj in robot_utils.robot_model().finger_joints:
                p.setJointMotorControl2(robot_id, fj, p.POSITION_CONTROL,
                                        targetPosition=max(0.0, w - 0.004), force=hold_n)
            print(f'[hold_physics] force-limited hold {hold_n} N, target {1e3 * max(0.0, w - 0.004):.2f} mm',
                  flush=True)
        return w
    execution.close_gripper_until_contact = close_gripper_until_contact

loss_recorder.install(out)
runpy.run_path(DRIVER, run_name='__main__')
