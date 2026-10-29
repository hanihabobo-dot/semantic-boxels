"""PLAN_P4_POSE_GRASP_SAMPLERS.md steps 3-4 smoke: one of our cells with
M9, M10 and the aperture rule ON (M8's domain does not exist before step
5), so the pose writers, the fitted grasp and the pad poll run for real.
A crash check, not an evaluation.  Arguments after the script go to
test_full_pipeline.py unchanged.

  bash scripts/_run_in_wsl.sh tools/_smoke_switches_on.py --no-gui \\
    --scene random-pairs --seed 0 --goal holding --n-occluders 2
"""
import os
import runpy
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import pose_belief  # noqa: E402

pose_belief.SWITCHES.update({'M9': True, 'M10': True, 'pick_aperture_from_pose': True})
if pose_belief.PLACE_POSE_TOL is None:
    pose_belief.PLACE_POSE_TOL = float(os.environ.get('PLACE_POSE_TOL', '0.004'))
sys.argv = [os.path.join(REPO, 'test_full_pipeline.py')] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
