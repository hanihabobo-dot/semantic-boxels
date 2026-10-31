"""BF#59 force_hold, the implementation's episode check (reviews/impl_force_hold.md).

One find_dice episode of a worktree's unchanged driver with 200 solver
iterations set on the executing client right after D9's set-up, as
probes/hold_physics/ep_probe.py set them for the proposal's episodes.  This
stands in for the solver_iters switch, which lives on its own branch: the
name 'solver_iters' is registered here (a stand-in line) so that
--slip-fixes solver_iters,force_hold passes force_hold's refusal without the
check-only escape.  Nothing else is patched: the hold and the gear are the
branch's own code.

  S=<worktree> python ep_iters.py <driver args...>
"""
import os
import runpy
import sys

S = os.environ['S']
DRIVER = os.path.join(S, 'tampura_bridge', 'run_bridge_on_finddice.py')
ITERS = 200
sys.argv = [DRIVER] + sys.argv[1:]
sys.path.insert(0, S)

import console_ui                                   # noqa: E402
console_ui.install_early('__main__')
from tampura.config import config as _tconfig       # noqa: E402,F401
import tampura_environments                         # noqa: E402,F401
import pybullet as p                                # noqa: E402
import slip_fixes                                   # noqa: E402
from tampura_bridge import policy as _bp            # noqa: E402

slip_fixes.register('solver_iters', 'stand-in of reviews/impl_force_hold/ep_iters.py: '
                                    '200 solver iterations after d9_setup')
_orig_d9 = _bp.d9_setup


def d9_setup(world, model):
    _orig_d9(world, model)
    c = world.client._client
    p.setPhysicsEngineParameter(numSolverIterations=ITERS, physicsClientId=c)
    print(f'[impl_force_hold ep_iters] numSolverIterations {ITERS} on client {c} '
          f'(stand-in for solver_iters)', flush=True)


_bp.d9_setup = d9_setup
runpy.run_path(DRIVER, run_name='__main__')
