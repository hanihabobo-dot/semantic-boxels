"""The hook for path 4's LW1 driver.

Fill in ``run_lw1``: it takes the (logging) env, which has the WumpusEnv
interface without truth(), and returns {'outcome': 'success'|'stuck'|
'error'|'step_limit', 'reason': str}.  Until then the runner refuses
--controller lw1 cleanly.
"""


def run_lw1(env, max_steps=500, log=print):
    raise NotImplementedError('the LW1 controller is path 4\'s and not plugged in yet')


AVAILABLE = False
