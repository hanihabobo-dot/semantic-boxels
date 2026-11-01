"""Run tampura_bridge/run_bridge_on_finddice.py unchanged, with
loss_recorder installed.  Usage (cwd = their tampura_environments):

  python run_probe.py <recorder jsonl> <the driver's arguments...>
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, *(['..'] * 6)))
DRIVER = os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')

out = sys.argv[1]
sys.argv = [DRIVER] + sys.argv[2:]
sys.path.insert(0, REPO)
sys.path.insert(1, HERE)

import console_ui                                   # noqa: E402
console_ui.install_early('__main__')
# the driver's own import order, then the patches
from tampura.config import config as _tconfig       # noqa: E402,F401
import tampura_environments                         # noqa: E402,F401
from tampura_bridge import policy as _bp            # noqa: E402,F401
import loss_recorder                                # noqa: E402
loss_recorder.install(out)
runpy.run_path(DRIVER, run_name='__main__')
