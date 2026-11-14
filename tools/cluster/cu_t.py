#!/usr/bin/env python3
"""class_uncertain, arm T (TAMPURA) for the cluster run of Q42: their own run_planner.py, run as it
is, plus one read of their executing world after their rollout.

Run in THEIR venv from a scratch directory that holds env_configs/ and
tampura_environments/class_uncertain/problems (links to their tree), as `run cu -System tampura`
runs their driver (tools/cu_eval.py builds the directory and the command):

  <their venv>/bin/python -u cu_t.py --run-planner <their tree>/tampura_environments/run_planner.py \\
      --world-test-dir <snapshot>/tasks_probe \\
      --config ./env_configs/class_uncertain.yml --global-seed N --save-dir DIR

What is theirs and unchanged: run_planner.py is executed from their file (runpy, as __main__), with
their argument parser, their seeding, their env and their rollout.  What is ours:

  1. one planner name, `tampura_policy_cu_read`: their TampuraPolicy, subclassed.  get_action calls
     theirs inside a clock and writes the span to DIR/get_action_spans.jsonl (as find_dice's arm T,
     tampura_bridge/timed_policy.py).  rollout calls theirs unchanged, then reads once.
  2. the read, after their rollout has returned and their history is saved (so it cannot reach the
     run it reads): the world-state test of path 7's PLAN.md, CU-8 (every true fruit rests in the
     bowl, no break reported; Hani's Q43 makes it the primary success).  The function is path 7's own
     (tasks_probe/cu_rand.world_test, the one its random floor uses), imported, not copied.  The
     handle of their executing world is taken before their rollout starts, because their env sets
     env.state to None after a failed drop (CU-15).  The breaks come from the observations in
     their history.  Written to DIR/cu_final_world.json with the actions and rewards of their
     history; a rollout that raises is recorded there too and raised again (CU-14: a failure).

No step of their run is watched: the rows of this arm carry no world test per step, no drop count
and no collision count (tools/cu_eval.py writes rule 18's words for them).

DIR/cu_t_runtime.json records where their two packages were imported from and what the subclass
overrides, written before their rollout starts.
"""
import argparse
import json
import os
import runpy
import sys
import time
import traceback

PLANNER_NAME = 'tampura_policy_cu_read'
FINAL_NAME = 'cu_final_world.json'
SPANS_NAME = 'get_action_spans.jsonl'
RUNTIME_NAME = 'cu_t_runtime.json'
OVERRIDES = ('__init__', 'get_action', 'rollout')


def history_facts(actions, observations, rewards, max_steps):
    """What the row needs from their RolloutHistory, as plain lists.  Their history holds one entry
    per step (the reward BEFORE the step) and a last entry after the final step (action None), so
    the reward after step i is rewards[i + 1] (tampura/policies/policy.py, rollout)."""
    acts = [str(a) for a in actions if a is not None]
    after = [float(r) for r in rewards[1:]]
    first = next((i + 1 for i, r in enumerate(after) if r > 0), None)
    broken = [str(getattr(o, 'broken')) for o in observations
              if o is not None and getattr(o, 'broken', None) is not None]
    noop = [i + 1 for i, a in enumerate(acts) if a.startswith('no-op')]
    return {'max_steps': max_steps, 'steps': len(acts), 'actions': acts, 'rewards': after,
            'reward_t0': float(rewards[0]) if rewards else None,
            'success_first_goal': first is not None, 'first_goal_step': first,
            'reward_last': after[-1] if after else None,
            'n_noop': len(noop), 'first_noop_step': noop[0] if noop else None,
            'broken': bool(broken), 'broken_reports': broken}


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def record_after_rollout(world, history, save_dir, world_test):
    """The one read: their final world under the world-state test.  Never raises: a read that fails
    is recorded (ok False), and the row then carries no world test."""
    t0 = time.perf_counter()
    rec = {'ok': False}
    try:
        rec.update(history_facts(history.actions, history.observations, history.rewards,
                                 history.config.get('max_steps')))
        bowl = world.regions[1]
        wok, rows = world_test(world, bowl, rec['broken'])
        rec.update(ok=True, world_success_end=bool(wok), world_rows=rows, bowl_body=bowl)
    except Exception as e:  # noqa: BLE001  the read is a recorder
        rec.update(read_error=repr(e), read_trace=traceback.format_exc()[-1500:])
    rec['read_s'] = round(time.perf_counter() - t0, 4)
    write_json(os.path.join(save_dir, FINAL_NAME), rec)
    return rec


def register(world_test):
    """Register `tampura_policy_cu_read` with their planner registry; returns the class."""
    import tampura
    import tampura_environments
    from tampura.config.config import register_planner
    from tampura.policies.tampura_policy import TampuraPolicy

    class TampuraPolicyCuRead(TampuraPolicy):
        def __init__(self, config, problem_spec, **kwargs):
            super().__init__(config, problem_spec, **kwargs)
            os.makedirs(config['save_dir'], exist_ok=True)
            own = sorted(k for k, v in vars(type(self)).items() if callable(v))
            write_json(os.path.join(config['save_dir'], RUNTIME_NAME), {
                'planner': config.get('planner'), 'class': type(self).__name__,
                'base': type(self).__mro__[1].__module__ + '.' + type(self).__mro__[1].__name__,
                'overrides': own, 'overrides_expected': sorted(OVERRIDES),
                'tampura': os.path.dirname(os.path.abspath(tampura.__file__)),
                'tampura_environments': os.path.dirname(os.path.abspath(tampura_environments.__file__)),
                'world_test': getattr(world_test, '__module__', '?') + '.' + getattr(world_test, '__name__', '?'),
                'world_test_file': getattr(sys.modules.get(getattr(world_test, '__module__', '')), '__file__', None),
                'python': sys.executable, 'pythonhashseed': os.environ.get('PYTHONHASHSEED'),
                'config': {k: config[k] for k in sorted(config) if k != 'save_dir'}})
            if own != sorted(OVERRIDES):
                raise SystemExit(f"{type(self).__name__} overrides {own}, expected {sorted(OVERRIDES)}: nothing run")
            self._span_log = os.path.join(config['save_dir'], SPANS_NAME)
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

        def rollout(self, env, b, store):
            world = env.state.world       # the handle only; their env may set env.state to None later
            try:
                out = super().rollout(env, b, store)
            except Exception as e:
                write_json(os.path.join(self.config['save_dir'], FINAL_NAME), {
                    'ok': False, 'crash': {'error': repr(e), 'trace': traceback.format_exc()[-3000:],
                                           'get_action_calls': self._span_step}})
                raise
            record_after_rollout(world, out[0], self.config['save_dir'], world_test)
            return out

    register_planner(PLANNER_NAME, TampuraPolicyCuRead)
    return TampuraPolicyCuRead


def split_args(argv):
    """(our two arguments, their run_planner.py's arguments).  --planner is ours to set."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--run-planner', required=True)
    ap.add_argument('--world-test-dir', required=True)
    own, rest = ap.parse_known_args(argv)
    if any(x == '--planner' or x.startswith('--planner=') for x in rest):
        raise SystemExit('--planner is set by cu_t.py (%s): leave it out' % PLANNER_NAME)
    return own, rest


def main(argv=None):
    own, rest = split_args(sys.argv[1:] if argv is None else argv)
    for p in (own.run_planner, os.path.join(own.world_test_dir, 'cu_rand.py')):
        if not os.path.isfile(p):
            raise SystemExit(f"{p} is missing: nothing run")
    # sys.path[0] as `python run_planner.py` has it: their driver's own directory
    sys.path[0] = os.path.dirname(os.path.abspath(own.run_planner))
    wt = os.path.abspath(own.world_test_dir)
    sys.path.insert(1, wt)
    try:
        import cu_rand            # path 7's random floor: world_test, their packages only
    finally:
        # cu_rand puts its folder on the path too; their driver then runs without it
        sys.path[:] = [p for i, p in enumerate(sys.path) if i == 0 or os.path.abspath(p or '.') != wt]
    register(cu_rand.world_test)
    sys.argv = [own.run_planner] + rest + ['--planner', PLANNER_NAME]
    runpy.run_path(own.run_planner, run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main())
