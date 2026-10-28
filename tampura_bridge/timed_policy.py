"""#P4 arm T's timed policy (PAPER_AUDIT.txt P4.6 ARMS, gate G13).

TAMPURA's own TampuraPolicy, timed: a subclass that overrides get_action
only, calling super().get_action inside perf_counter and writing the span
to a side log in the run's save_dir (get_action_spans.jsonl); rollout is
inherited unchanged.  Importing this module makes the one arm-T runtime
registration, "tampura_policy_timed"; tools/run_tampura_timed.py imports it
and runs with --planner tampura_policy_timed.  Nothing of ours enters their
RolloutHistory: the spans live in the side log only.  G13's runtime half
(GF1) runs in __init__, the last code of ours before their rollout, since
the driver copy cannot change: recorded in g13_runtime.json, and a failure
stops the run.
"""
import json
import os
import time

from tampura.config.config import register_planner
from tampura.policies.tampura_policy import TampuraPolicy

from tampura_bridge import g13_runtime

PLANNER_NAME = 'tampura_policy_timed'


class TampuraPolicyTimed(TampuraPolicy):
    def __init__(self, config, problem_spec, **kwargs):
        super().__init__(config, problem_spec, **kwargs)
        g13_runtime.write_and_enforce(
            g13_runtime.check_arm_t(self, problem_spec, PLANNER_NAME, TampuraPolicyTimed),
            config['save_dir'])
        os.makedirs(config['save_dir'], exist_ok=True)
        self._span_log = os.path.join(config['save_dir'],
                                      'get_action_spans.jsonl')
        self._span_step = 0

    def get_action(self, belief, store):
        t0 = time.perf_counter()
        out = super().get_action(belief, store)
        span = time.perf_counter() - t0
        with open(self._span_log, 'a') as f:
            f.write(json.dumps({'step': self._span_step, 'get_action_s': span,
                                'action': str(out[0])}) + '\n')
        self._span_step += 1
        return out


register_planner(PLANNER_NAME, TampuraPolicyTimed)
