"""BF#59 carry_hold_check, the loss path's end-to-end check (the orchestrator,
reviews/implrev_carry_hold_check.md).

No laptop episode lost the die in the carry while the switch was on, so the
dispatcher's loss path (the loss line, the gripper opened, the transit
strike, the held state cleared, the lost-region refresh, the replan) never
ran outside the unit tests.  This wrapper runs one find_dice episode of a
checkout's unchanged driver and injects ONE carry loss: the first time
carry_hold_end asks the shared helper about the die while both pads really
hold it, the helper reports no pads.  The gripper then opens for real at
the end of that move and the die drops, so the replan sees the world as it
is.  Nothing else is patched; the pipeline's own code runs the path.

  S=<checkout> python ep_loss_inject.py <driver args...>   (needs --slip-fixes ...,carry_hold_check,...)
"""
import os
import runpy
import sys

S = os.environ['S']
DRIVER = os.path.join(S, 'tampura_bridge', 'run_bridge_on_finddice.py')
sys.argv = [DRIVER] + sys.argv[1:]
sys.path.insert(0, S)

import console_ui                                   # noqa: E402
console_ui.install_early('__main__')
from tampura.config import config as _tconfig       # noqa: E402,F401
import tampura_environments                         # noqa: E402,F401
import execution                                    # noqa: E402

_real = execution.held_pad_contacts
_state = {'injected': False}


def held_pad_contacts(robot_id, body_id):
    pads, nf, npts = _real(robot_id, body_id)
    caller = sys._getframe(1)
    if (not _state['injected'] and caller.f_code.co_name == 'carry_hold_end'
            and caller.f_locals.get('obj_name') == 'dice' and len(pads) == 2):
        _state['injected'] = True
        print(f'[ep_loss_inject] carry_hold_end asked about the dice with both '
              f'pads on it ({nf:.2f} N): reporting NO pads once, so the loss '
              f'path runs', flush=True)
        return frozenset(), 0.0, 0
    return pads, nf, npts


# carry_hold_end looks the helper up in execution's globals at call time, so
# the module attribute is the patch point; execute_pick's post-lift
# re-verify calls the same helper and is left alone by the caller test.
execution.held_pad_contacts = held_pad_contacts
runpy.run_path(DRIVER, run_name='__main__')
